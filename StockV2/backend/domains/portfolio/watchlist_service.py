from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session


class WatchlistService:
    def __init__(self, db: Session):
        self.db = db

    def get_all(self) -> list[dict]:
        rows = self.db.execute(
            text("SELECT * FROM watchlist ORDER BY added_at DESC")
        ).fetchall()
        return [dict(r._mapping) for r in rows]

    def add(self, symbol: str, reason: Optional[str] = None) -> dict:
        self.db.execute(
            text("INSERT INTO watchlist (symbol, reason, added_at) "
                 "VALUES (:sym, :reason, CURRENT_TIMESTAMP) "
                 "ON CONFLICT (symbol) DO NOTHING"),
            {"sym": symbol.upper(), "reason": reason},
        )
        self.db.commit()
        row = self.db.execute(
            text("SELECT * FROM watchlist WHERE symbol=:s"),
            {"s": symbol.upper()},
        ).fetchone()
        return dict(row._mapping)

    def remove(self, symbol: str) -> bool:
        result = self.db.execute(
            text("DELETE FROM watchlist WHERE symbol=:s"),
            {"s": symbol.upper()},
        )
        self.db.commit()
        return result.rowcount > 0
