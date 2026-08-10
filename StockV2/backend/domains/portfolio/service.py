import json
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from settings import settings


class PortfolioService:
    def __init__(self, db: Session):
        self.db = db

    def get_holdings(self) -> list[dict]:
        rows = self.db.execute(
            text("""
                SELECT ph.id, ph.symbol, ph.quantity, ph.avg_buy_price,
                       ph.first_buy_date, ph.last_buy_date,
                       ROUND(ph.quantity * ph.avg_buy_price, 2) AS invested_value,
                       er.stop_loss_price, er.target_1_price, er.max_exit_date
                FROM portfolio_holdings ph
                LEFT JOIN exit_rules er ON er.symbol = ph.symbol
                WHERE ph.is_active = 1
                ORDER BY ph.symbol
            """)
        ).fetchall()
        return [dict(r._mapping) for r in rows]

    def get_portfolio_summary(self) -> dict:
        holdings = self.get_holdings()
        total_invested = sum(h["invested_value"] or 0 for h in holdings)
        return {
            "paper_capital": settings.paper_capital,
            "total_invested": round(total_invested, 2),
            "cash_available": round(settings.paper_capital - total_invested, 2),
            "open_positions": len(holdings),
            "max_positions": settings.max_open_positions,
        }

    def get_trade_history(self, symbol: Optional[str] = None, limit: int = 50) -> list[dict]:
        q = "SELECT * FROM trades WHERE mode='paper'"
        params: dict = {}
        if symbol:
            q += " AND symbol=:sym"
            params["sym"] = symbol.upper()
        q += " ORDER BY trade_date DESC LIMIT :lim"
        params["lim"] = limit
        rows = self.db.execute(text(q), params).fetchall()
        return [dict(r._mapping) for r in rows]

    def get_closed_pnl(self) -> dict:
        rows = self.db.execute(
            text("SELECT * FROM trades WHERE trade_type='SELL' AND mode='paper' "
                 "ORDER BY trade_date DESC")
        ).fetchall()
        total_pnl = 0.0
        closed_trades = []
        for r in rows:
            row = dict(r._mapping)
            if row.get("notes"):
                try:
                    meta = json.loads(row["notes"])
                    row["pnl"] = meta.get("pnl", 0.0)
                    row["pnl_pct"] = meta.get("pnl_pct", 0.0)
                    row["buy_avg"] = meta.get("buy_avg")
                    total_pnl += meta.get("pnl", 0.0)
                except (json.JSONDecodeError, TypeError):
                    pass
            closed_trades.append(row)
        return {"total_pnl": round(total_pnl, 2), "closed_trades": closed_trades}
