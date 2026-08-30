"""
Strategy selection by market regime.

Ranks active strategies by their historical win rate in the current market regime.
Falls back to overall average win rate when regime-specific data is absent.
"""

import logging
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


@dataclass
class StrategyRank:
    strategy_id: int
    strategy_name: str
    regime_win_rate: Optional[float]    # win rate specifically in the given regime
    overall_win_rate: Optional[float]   # average win rate across all regimes
    regime_total_trades: int
    rank: int


class StrategySelectionEngine:
    """
    Ranks strategies for the current (or specified) market regime.

    Uses regime-specific win rates when available; falls back to the
    overall average across all regimes.
    """

    def rank_for_current_regime(self, db: Session) -> list[StrategyRank]:
        from domains.market.regime import MarketRegimeEngine
        result = MarketRegimeEngine().get_or_compute(db)
        return self.rank_for_regime(db, result.regime)

    def rank_for_regime(self, db: Session, regime: str) -> list[StrategyRank]:
        rows = db.execute(
            text("""
                SELECT s.id, s.name,
                       srp.win_rate       AS regime_win_rate,
                       srp.total_trades   AS regime_trades,
                       overall.avg_win_rate AS overall_win_rate
                FROM strategies s
                LEFT JOIN strategy_regime_performance srp
                    ON srp.strategy_id = s.id AND srp.regime = :regime
                LEFT JOIN (
                    SELECT strategy_id, AVG(win_rate) AS avg_win_rate
                    FROM strategy_regime_performance
                    GROUP BY strategy_id
                ) overall ON overall.strategy_id = s.id
                WHERE s.is_active = true
                ORDER BY
                    COALESCE(srp.win_rate, overall.avg_win_rate, 0.5) DESC
            """),
            {"regime": regime},
        ).fetchall()

        return [
            StrategyRank(
                strategy_id=int(r[0]),
                strategy_name=str(r[1]),
                regime_win_rate=float(r[2]) if r[2] is not None else None,
                regime_total_trades=int(r[3]) if r[3] is not None else 0,
                overall_win_rate=float(r[4]) if r[4] is not None else None,
                rank=i + 1,
            )
            for i, r in enumerate(rows)
        ]
