# backend/domains/combinations/filter.py
import logging
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from domains.strategies.engine import ALL_STRATEGIES

logger = logging.getLogger(__name__)


@dataclass
class FilterConfig:
    min_trades: int = 30
    max_drawdown: float = 0.40       # absolute fraction, e.g. 0.40 = max 40% drawdown
    min_win_rate: float = 0.35
    top_n_overall: int = 30
    top_n_per_regime: int = 15
    sharpe_weight: float = 0.30
    wf_consistency_weight: float = 0.30
    win_rate_weight: float = 0.20
    profit_factor_weight: float = 0.20


class StrategyFilter:
    def __init__(self, db: Session, config: FilterConfig = FilterConfig()):
        self.db = db
        self.config = config
        self._strategy_id_map: dict[str, int] = self._load_strategy_ids()

    def _load_strategy_ids(self) -> dict[str, int]:
        rows = self.db.execute(text("SELECT id, name FROM strategies")).fetchall()
        return {r[1]: r[0] for r in rows}

    def select_candidates(self) -> dict:
        """
        Returns:
        {
            "overall": list[BaseStrategy],         # top_n_overall strategies
            "by_regime": {
                "BULL": list[BaseStrategy],
                "SIDEWAYS": list[BaseStrategy],
                "BEAR": list[BaseStrategy],
            },
            "scores": dict[str, float],            # strategy_name -> multi_factor_score
            "disqualified": list[str],             # strategy names that failed config floor
        }
        """
        scores: dict[str, float] = {}
        disqualified: list[str] = []

        for strategy in ALL_STRATEGIES:
            if strategy.name not in self._strategy_id_map:
                disqualified.append(f"{strategy.name} (not in DB)")
                continue

            strategy_id = self._strategy_id_map[strategy.name]

            # Aggregate performance across all symbols
            perf_row = self.db.execute(text("""
                SELECT
                    SUM(total_trades) AS total_trades,
                    AVG(win_rate)      AS avg_win_rate,
                    AVG(sharpe_ratio)  AS avg_sharpe,
                    AVG(max_drawdown)  AS avg_drawdown,
                    AVG(profit_factor) AS avg_profit_factor
                FROM strategy_performance
                WHERE strategy_id = :sid
            """), {"sid": strategy_id}).fetchone()

            if not perf_row or perf_row[0] is None:
                disqualified.append(f"{strategy.name} (no performance data)")
                continue

            total_trades = perf_row[0] or 0
            avg_win_rate = perf_row[1]
            avg_sharpe = perf_row[2]
            avg_drawdown = perf_row[3]   # stored as negative percentage, e.g. -15.4
            avg_profit_factor = perf_row[4]

            # Config floor checks
            if total_trades < self.config.min_trades:
                disqualified.append(f"{strategy.name} (total_trades={total_trades})")
                continue
            if avg_drawdown is not None and abs(avg_drawdown) > self.config.max_drawdown * 100:
                disqualified.append(f"{strategy.name} (avg_drawdown={avg_drawdown:.1f}%)")
                continue
            if avg_win_rate is not None and avg_win_rate < self.config.min_win_rate:
                disqualified.append(f"{strategy.name} (avg_win_rate={avg_win_rate:.2f})")
                continue

            # Walk-forward consistency
            wf_row = self.db.execute(text("""
                SELECT AVG(consistency_score) AS avg_consistency
                FROM walk_forward_results
                WHERE strategy_id = :sid
            """), {"sid": strategy_id}).fetchone()
            avg_consistency = wf_row[0] if wf_row and wf_row[0] is not None else 0.0

            # Multi-factor score (normalise each component to 0–1)
            sharpe_norm = min(1.0, max(0.0, (avg_sharpe or 0.0) / 2.0))
            wr_norm = min(1.0, max(0.0, avg_win_rate or 0.0))
            pf_norm = min(1.0, max(0.0, ((avg_profit_factor or 0.0) - 1.0) / 2.0))
            wf_norm = min(1.0, max(0.0, avg_consistency))

            score = (
                self.config.sharpe_weight * sharpe_norm
                + self.config.wf_consistency_weight * wf_norm
                + self.config.win_rate_weight * wr_norm
                + self.config.profit_factor_weight * pf_norm
            )
            scores[strategy.name] = round(score, 4)

        # Top N overall by score
        sorted_names = sorted(scores, key=lambda n: scores[n], reverse=True)
        top_names_overall = set(sorted_names[:self.config.top_n_overall])
        overall = [s for s in ALL_STRATEGIES if s.name in top_names_overall]

        # Regime-specific pools — use overall ordering filtered to top_n_per_regime
        top_names_regime = set(sorted_names[:self.config.top_n_per_regime])
        regime_pool = [s for s in ALL_STRATEGIES if s.name in top_names_regime]
        by_regime = {
            "BULL": regime_pool,
            "SIDEWAYS": regime_pool,
            "BEAR": regime_pool,
        }

        logger.info(
            "[filter] selected %d overall, disqualified %d",
            len(overall), len(disqualified)
        )
        return {
            "overall": overall,
            "by_regime": by_regime,
            "scores": scores,
            "disqualified": disqualified,
        }
