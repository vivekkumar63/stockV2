from datetime import date
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session


class DataService:
    def __init__(self, db: Session):
        self.db = db

    def list_stocks(self) -> list[dict]:
        rows = self.db.execute(
            text("SELECT symbol, name, sector, industry, exchange, is_active FROM stocks ORDER BY symbol")
        ).fetchall()
        return [dict(r._mapping) for r in rows]

    def get_stock(self, symbol: str) -> Optional[dict]:
        row = self.db.execute(
            text("SELECT symbol, name, sector, industry, market_cap, exchange, is_active FROM stocks WHERE symbol = :s"),
            {"s": symbol.upper()},
        ).fetchone()
        return dict(row._mapping) if row else None

    def get_prices(
        self,
        symbol: str,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
        limit: int = 500,
    ) -> list[dict]:
        query = "SELECT symbol, date, open, high, low, close, volume FROM stock_prices_daily WHERE symbol = :s"
        params: dict = {"s": symbol.upper()}
        if from_date:
            query += " AND date >= :fd"
            params["fd"] = str(from_date)
        if to_date:
            query += " AND date <= :td"
            params["td"] = str(to_date)
        query += " ORDER BY date DESC LIMIT :lim"
        params["lim"] = limit
        rows = self.db.execute(text(query), params).fetchall()
        return [dict(r._mapping) for r in rows]

    def get_latest_price(self, symbol: str) -> Optional[float]:
        row = self.db.execute(
            text("SELECT close FROM stock_prices_daily WHERE symbol = :s ORDER BY date DESC LIMIT 1"),
            {"s": symbol.upper()},
        ).fetchone()
        return float(row[0]) if row else None
