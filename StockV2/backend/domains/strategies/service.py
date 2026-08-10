from datetime import datetime
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session


class StrategyService:
    def __init__(self, db: Session):
        self.db = db

    def get_all_strategies(self) -> list[dict]:
        rows = self.db.execute(
            text("SELECT id, name, type, description, is_active, created_at FROM strategies ORDER BY id")
        ).fetchall()
        return [dict(r._mapping) for r in rows]

    def get_today_signals(self, signal_date: Optional[str] = None) -> list[dict]:
        date_str = signal_date or datetime.utcnow().strftime("%Y-%m-%d")
        rows = self.db.execute(
            text("""
                SELECT ss.id, ss.symbol, ss.strategy_id, s.name AS strategy_name,
                       ss.signal_date, ss.signal_type, ss.price_at_signal,
                       ss.confidence_score, ss.risk_score, ss.expected_upside_pct,
                       ss.suggested_stop_loss, ss.suggested_target,
                       ss.holding_period_days, ss.reasoning_json
                FROM strategy_signals ss
                JOIN strategies s ON ss.strategy_id = s.id
                WHERE ss.signal_date = :d
                ORDER BY ss.confidence_score DESC
            """),
            {"d": date_str},
        ).fetchall()
        return [dict(r._mapping) for r in rows]

    def get_signals(
        self,
        symbol: Optional[str] = None,
        signal_type: Optional[str] = None,
        from_date: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict]:
        q = """
            SELECT ss.id, ss.symbol, ss.strategy_id, s.name AS strategy_name,
                   ss.signal_date, ss.signal_type, ss.price_at_signal, ss.confidence_score, ss.risk_score
            FROM strategy_signals ss
            JOIN strategies s ON ss.strategy_id = s.id
            WHERE 1=1
        """
        params: dict = {}
        if symbol:
            q += " AND ss.symbol = :sym"
            params["sym"] = symbol.upper()
        if signal_type:
            q += " AND ss.signal_type = :st"
            params["st"] = signal_type.upper()
        if from_date:
            q += " AND ss.signal_date >= :fd"
            params["fd"] = from_date
        q += " ORDER BY ss.signal_date DESC, ss.confidence_score DESC LIMIT :lim"
        params["lim"] = limit
        rows = self.db.execute(text(q), params).fetchall()
        return [dict(r._mapping) for r in rows]

    def get_signal_by_id(self, signal_id: int) -> Optional[dict]:
        row = self.db.execute(
            text("""
                SELECT ss.*, s.name AS strategy_name,
                       st.name AS stock_name, st.sector
                FROM strategy_signals ss
                JOIN strategies s ON ss.strategy_id = s.id
                LEFT JOIN stocks st ON ss.symbol = st.symbol
                WHERE ss.id = :id
            """),
            {"id": signal_id},
        ).fetchone()
        return dict(row._mapping) if row else None
