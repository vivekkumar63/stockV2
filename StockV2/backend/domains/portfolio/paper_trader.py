import json
import logging
from datetime import timedelta
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from domains.portfolio.position_sizer import PositionSizer
from ist import ist_today

logger = logging.getLogger(__name__)


class PaperTrader:
    def __init__(self, db: Session):
        self.db = db
        self.sizer = PositionSizer()

    def enter(self, signal_id: int, price: float) -> Optional[dict]:
        signal = self._load_signal(signal_id)
        if not signal or signal["signal_type"] != "BUY":
            return None

        stop_loss_price = signal.get("suggested_stop_loss") or round(price * 0.93, 2)
        target_price = signal.get("suggested_target") or round(price * 1.15, 2)

        open_positions, invested_capital = self._portfolio_state()
        pos = self.sizer.compute(
            entry_price=price,
            stop_loss_price=stop_loss_price,
            target_price=target_price,
            open_positions=open_positions,
            invested_capital=invested_capital,
        )
        if not pos.is_valid:
            logger.warning("[PaperTrader] enter rejected for %s: %s",
                           signal["symbol"], pos.reject_reason)
            return None

        symbol = signal["symbol"]
        total_value = round(pos.quantity * price, 2)
        trade_id = self._insert_trade(
            symbol=symbol, trade_type="BUY", quantity=pos.quantity,
            price=price, total_value=total_value,
            strategy_id=signal.get("strategy_id"), signal_id=signal_id,
        )
        self._upsert_holding(symbol, pos.quantity, price)
        self._insert_exit_rule(
            trade_id=trade_id, symbol=symbol, entry_price=price,
            stop_loss_price=pos.stop_loss_price, target_price=pos.target_price,
            holding_days=signal.get("holding_period_days") or 15,
        )
        self.db.commit()
        logger.info("[PaperTrader] entered %s: qty=%d @ %.2f sl=%.2f tgt=%.2f",
                    symbol, pos.quantity, price, pos.stop_loss_price, pos.target_price)
        return self._load_trade(trade_id)

    def exit(self, symbol: str, current_price: float, reason: str = "manual") -> Optional[dict]:
        holding = self._load_holding(symbol)
        if not holding or holding["quantity"] <= 0:
            logger.warning("[PaperTrader] exit skipped — no active holding for %s", symbol)
            return None

        quantity = holding["quantity"]
        avg_buy = holding["avg_buy_price"]
        pnl = round((current_price - avg_buy) * quantity, 2)
        pnl_pct = round((current_price - avg_buy) / avg_buy * 100, 2)
        notes = json.dumps({"reason": reason, "buy_avg": avg_buy, "pnl": pnl, "pnl_pct": pnl_pct})
        trade_id = self._insert_trade(
            symbol=symbol, trade_type="SELL", quantity=quantity,
            price=current_price, total_value=round(quantity * current_price, 2),
            notes=notes,
        )
        self.db.execute(
            text("UPDATE portfolio_holdings SET is_active=0, quantity=0 "
                 "WHERE symbol=:s AND is_active=true"),
            {"s": symbol},
        )
        self.db.commit()
        logger.info("[PaperTrader] exited %s: qty=%d @ %.2f pnl=%.2f (%.1f%%) — %s",
                    symbol, quantity, current_price, pnl, pnl_pct, reason)
        return self._load_trade(trade_id)

    # ── internal helpers ────────────────────────────────────────────────────────

    def _load_signal(self, signal_id: int) -> Optional[dict]:
        row = self.db.execute(
            text("""
                SELECT id, symbol, signal_type, strategy_id,
                       suggested_stop_loss, suggested_target, holding_period_days
                FROM strategy_signals WHERE id = :id
            """),
            {"id": signal_id},
        ).fetchone()
        return dict(row._mapping) if row else None

    def _portfolio_state(self) -> tuple[int, float]:
        row = self.db.execute(
            text("SELECT COUNT(*), COALESCE(SUM(quantity * avg_buy_price), 0.0) "
                 "FROM portfolio_holdings WHERE is_active=true")
        ).fetchone()
        return row[0], float(row[1])

    def _insert_trade(self, symbol: str, trade_type: str, quantity: int,
                      price: float, total_value: float,
                      strategy_id: Optional[int] = None,
                      signal_id: Optional[int] = None,
                      notes: Optional[str] = None) -> int:
        result = self.db.execute(
            text("""
                INSERT INTO trades
                    (symbol, trade_type, quantity, price, total_value, brokerage,
                     mode, strategy_id, signal_id, notes, trade_date)
                VALUES (:sym, :tt, :qty, :price, :tv, 0, 'paper',
                        :sid, :sigid, :notes, CURRENT_TIMESTAMP)
            """),
            {"sym": symbol, "tt": trade_type, "qty": quantity, "price": price,
             "tv": total_value, "sid": strategy_id, "sigid": signal_id, "notes": notes},
        )
        return result.lastrowid

    def _upsert_holding(self, symbol: str, quantity: int, price: float):
        existing = self.db.execute(
            text("SELECT id, quantity, avg_buy_price FROM portfolio_holdings "
                 "WHERE symbol=:s AND is_active=true"),
            {"s": symbol},
        ).fetchone()
        if existing:
            old_qty, old_avg = existing[1], existing[2]
            new_qty = old_qty + quantity
            new_avg = round((old_qty * old_avg + quantity * price) / new_qty, 4)
            self.db.execute(
                text("UPDATE portfolio_holdings SET quantity=:q, avg_buy_price=:a, "
                     "last_buy_date=CURRENT_DATE WHERE id=:id"),
                {"q": new_qty, "a": new_avg, "id": existing[0]},
            )
        else:
            self.db.execute(
                text("""
                    INSERT INTO portfolio_holdings
                        (symbol, quantity, avg_buy_price, first_buy_date, last_buy_date, is_active)
                    VALUES (:sym, :qty, :avg, CURRENT_DATE, CURRENT_DATE, true)
                """),
                {"sym": symbol, "qty": quantity, "avg": round(price, 4)},
            )

    def _insert_exit_rule(self, trade_id: int, symbol: str, entry_price: float,
                          stop_loss_price: float, target_price: float, holding_days: int):
        max_exit = ist_today() + timedelta(days=holding_days)
        self.db.execute(
            text("""
                INSERT INTO exit_rules
                    (order_id, symbol, entry_price, stop_loss_price,
                     target_1_price, target_2_price, max_exit_date, partial_exit_at_t1)
                VALUES (:oid, :sym, :ep, :sl, :t1, :t2, :med, false)
            """),
            {"oid": trade_id, "sym": symbol, "ep": entry_price,
             "sl": stop_loss_price, "t1": target_price,
             "t2": round(target_price * 1.05, 2), "med": str(max_exit)},
        )

    def _load_holding(self, symbol: str) -> Optional[dict]:
        row = self.db.execute(
            text("SELECT * FROM portfolio_holdings WHERE symbol=:s AND is_active=true"),
            {"s": symbol},
        ).fetchone()
        return dict(row._mapping) if row else None

    def _load_trade(self, trade_id: int) -> dict:
        row = self.db.execute(
            text("SELECT * FROM trades WHERE id=:id"), {"id": trade_id}
        ).fetchone()
        return dict(row._mapping) if row else {}
