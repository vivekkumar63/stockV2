from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session


class BacktestService:
    def __init__(self, db: Session):
        self.db = db

    def get_results(self, symbol: Optional[str] = None, limit: int = 20) -> list[dict]:
        q = "SELECT * FROM backtest_results"
        params: dict = {}
        if symbol:
            q += " WHERE symbol = :sym"
            params["sym"] = symbol.upper()
        q += " ORDER BY ran_at DESC LIMIT :lim"
        params["lim"] = limit
        rows = self.db.execute(text(q), params).fetchall()
        return [dict(r._mapping) for r in rows]

    def get_result(self, result_id: int) -> Optional[dict]:
        row = self.db.execute(
            text("SELECT * FROM backtest_results WHERE id = :id"), {"id": result_id}
        ).fetchone()
        return dict(row._mapping) if row else None

    def get_trades(self, result_id: int, limit: int = 100) -> list[dict]:
        rows = self.db.execute(
            text("SELECT * FROM backtest_trades WHERE backtest_result_id = :id "
                 "ORDER BY entry_date LIMIT :lim"),
            {"id": result_id, "lim": limit},
        ).fetchall()
        return [dict(r._mapping) for r in rows]
