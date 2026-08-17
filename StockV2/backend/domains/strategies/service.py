import logging
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from ist import ist_today

logger = logging.getLogger(__name__)


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
        date_str = signal_date or ist_today().strftime("%Y-%m-%d")

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
                       lp.close AS latest_price, lp.date AS latest_price_date,
                       src.win_rate AS historical_win_rate
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
                LEFT JOIN (
                    SELECT symbol, strategy_id, win_rate
                    FROM scan_result_cache
                    WHERE stop_loss_pct = 5.0 AND target_pct = 10.0
                      AND from_date = '2015-01-01'
                ) src ON src.symbol = ss.symbol AND src.strategy_id = ss.strategy_id
                WHERE ss.signal_date = :d
                ORDER BY ss.confidence_score DESC
            """),
            {"d": effective_date},
        ).fetchall()
        signals = [dict(r._mapping) for r in rows]
        self._attach_opportunity_scores(signals)
        return signals

    def _attach_opportunity_scores(self, signals: list[dict]) -> None:
        """Attach opportunity_score and opportunity_grade to each signal in-place."""
        if not signals:
            return
        try:
            from domains.intelligence.opportunity_scorer import OpportunityScorer
            from domains.intelligence.regime_performance import RegimePerformanceEngine
            from domains.market.regime import MarketRegimeEngine

            regime_result = MarketRegimeEngine().get_or_compute(self.db)
            regime = regime_result.regime
            regime_perf = RegimePerformanceEngine().get_for_regime(self.db, regime)
            scorer = OpportunityScorer()

            for sig in signals:
                sid = sig.get("strategy_id")
                regime_wr = regime_perf.get(sid)
                opp = scorer.quick_score(
                    symbol=sig["symbol"],
                    strategy_id=sid,
                    confidence=float(sig.get("confidence_score") or 0.5),
                    historical_win_rate=sig.get("historical_win_rate"),
                    regime=regime,
                    regime_strategy_win_rate=regime_wr.win_rate if regime_wr else None,
                )
                sig["opportunity_score"] = opp.score
                sig["opportunity_grade"] = opp.grade
        except Exception:
            logger.warning("[StrategyService] opportunity scoring failed", exc_info=True)
            for sig in signals:
                sig["opportunity_score"] = None
                sig["opportunity_grade"] = None

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
