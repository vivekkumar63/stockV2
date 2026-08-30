import logging
from datetime import date
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from ist import ist_today

logger = logging.getLogger(__name__)


class ExitMonitor:
    def __init__(self, db: Session):
        self.db = db

    def scan_exits(self, current_prices: dict[str, float]) -> list[dict]:
        """Check open exit rules against current_prices. Returns list of executed exits."""
        from domains.portfolio.paper_trader import PaperTrader
        trader = PaperTrader(self.db)
        exits = []
        for rule in self._load_open_rules():
            symbol = rule["symbol"]
            price = current_prices.get(symbol)
            if price is None:
                continue
            reason = self._check_exit(rule, price)
            if reason:
                trade = trader.exit(symbol, price, reason)
                if trade:
                    exits.append({"symbol": symbol, "reason": reason, "price": price})
                    logger.info("[ExitMonitor] %s exited at ₹%.2f — %s", symbol, price, reason)
        return exits

    def _check_exit(self, rule: dict, price: float) -> Optional[str]:
        if price <= rule["stop_loss_price"]:
            return "stop_loss"
        if price >= rule["target_1_price"]:
            return "target_hit"
        if rule["max_exit_date"]:
            max_date = date.fromisoformat(str(rule["max_exit_date"]))
            if ist_today() >= max_date:
                return "max_holding_days"
        return None

    def _load_open_rules(self) -> list[dict]:
        rows = self.db.execute(
            text("""
                SELECT er.id, er.symbol, er.stop_loss_price,
                       er.target_1_price, er.max_exit_date
                FROM exit_rules er
                JOIN portfolio_holdings ph
                    ON er.symbol = ph.symbol AND ph.is_active = true
            """)
        ).fetchall()
        return [dict(r._mapping) for r in rows]
