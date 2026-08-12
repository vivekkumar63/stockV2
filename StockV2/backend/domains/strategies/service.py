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
        """Return signals for the requested date. If none exist, fall back to the most recent scan date."""
        date_str = signal_date or datetime.utcnow().strftime("%Y-%m-%d")

        # Check if there are any signals for today; if not, use the most recent date available
        latest_date = self.db.execute(
            text("SELECT MAX(signal_date) FROM strategy_signals")
        ).scalar()
        if latest_date:
            effective_date = max(str(latest_date), date_str) if str(latest_date) >= date_str else str(latest_date)
        else:
            effective_date = date_str

        rows = self.db.execute(
            text("""
                SELECT ss.id, ss.symbol, ss.strategy_id, s.name AS strategy_name,
                       ss.signal_date, ss.signal_type, ss.price_at_signal,
                       ss.confidence_score, ss.risk_score, ss.expected_upside_pct,
                       ss.suggested_stop_loss, ss.suggested_target,
                       ss.holding_period_days, ss.reasoning_json,
                       lp.close AS latest_price, lp.date AS latest_price_date
                FROM strategy_signals ss
                JOIN strategies s ON ss.strategy_id = s.id
                LEFT JOIN (
                    SELECT sp.symbol, sp.close, sp.date
                    FROM stock_prices_daily sp
                    WHERE sp.date = (
                        SELECT MAX(sp2.date) FROM stock_prices_daily sp2
                        WHERE sp2.symbol = sp.symbol
                    )
                ) lp ON lp.symbol = ss.symbol
                WHERE ss.signal_date = :d
                ORDER BY ss.confidence_score DESC
            """),
            {"d": effective_date},
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
