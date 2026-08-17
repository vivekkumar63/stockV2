"""
Strategy win-rate breakdown by market regime.

Algorithm:
  1. JOIN backtest_trades x backtest_results x market_regime on entry_date = date
  2. GROUP BY strategy_id, regime
  3. win_rate = count(pnl > 0) / total_trades  (min 5 trades to qualify)

Requires market_regime to be populated — run /intelligence/regime-backfill first
if the table is empty. Falls back gracefully if either table has no data.
"""

import logging
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


@dataclass
class RegimePerf:
    strategy_id: int
    regime: str
    total_trades: int
    win_rate: float       # 0.0–1.0
    avg_pnl_pct: float    # average % return per trade


class RegimePerformanceEngine:
    """
    Computes and caches per-strategy win rates for each market regime.

    Reads backtest_trades (individual trades) and market_regime (daily labels),
    writes to strategy_regime_performance.
    """

    def compute_all(self, db: Session) -> list[RegimePerf]:
        """Compute win rates for every (strategy_id, regime) pair."""
        rows = db.execute(
            text("""
                SELECT br.strategy_id,
                       mr.regime,
                       COUNT(*)  AS total_trades,
                       SUM(CASE WHEN bt.pnl > 0 THEN 1 ELSE 0 END) * 1.0 / COUNT(*) AS win_rate,
                       AVG(bt.pnl_pct) AS avg_pnl_pct
                FROM backtest_trades bt
                JOIN backtest_results br ON bt.backtest_result_id = br.id
                JOIN market_regime mr ON bt.entry_date = mr.date
                WHERE bt.pnl IS NOT NULL AND br.strategy_id IS NOT NULL
                GROUP BY br.strategy_id, mr.regime
                HAVING COUNT(*) >= 5
            """)
        ).fetchall()

        results = [
            RegimePerf(
                strategy_id=int(r[0]),
                regime=str(r[1]),
                total_trades=int(r[2]),
                win_rate=round(float(r[3]), 4),
                avg_pnl_pct=round(float(r[4]), 4) if r[4] is not None else 0.0,
            )
            for r in rows
        ]
        logger.info("[RegimePerf] computed %d strategy-regime pairs", len(results))
        return results

    def save(self, db: Session, results: list[RegimePerf]) -> None:
        for r in results:
            db.execute(
                text("""
                    INSERT OR REPLACE INTO strategy_regime_performance
                    (strategy_id, regime, total_trades, win_rate, avg_pnl_pct, computed_at)
                    VALUES (:sid, :regime, :n, :wr, :pnl, CURRENT_TIMESTAMP)
                """),
                {
                    "sid": r.strategy_id, "regime": r.regime, "n": r.total_trades,
                    "wr": r.win_rate, "pnl": r.avg_pnl_pct,
                },
            )
        db.commit()

    def get_for_regime(self, db: Session, regime: str) -> dict[int, RegimePerf]:
        """Return {strategy_id: RegimePerf} for the given regime."""
        rows = db.execute(
            text("""
                SELECT strategy_id, regime, total_trades, win_rate, avg_pnl_pct
                FROM strategy_regime_performance
                WHERE regime = :r
            """),
            {"r": regime},
        ).fetchall()
        return {
            int(r[0]): RegimePerf(
                strategy_id=int(r[0]),
                regime=str(r[1]),
                total_trades=int(r[2]),
                win_rate=float(r[3]) if r[3] is not None else 0.5,
                avg_pnl_pct=float(r[4]) if r[4] is not None else 0.0,
            )
            for r in rows
        }

    def get_all(self, db: Session) -> dict[tuple[int, str], RegimePerf]:
        """Return {(strategy_id, regime): RegimePerf} for all rows."""
        rows = db.execute(
            text("""
                SELECT strategy_id, regime, total_trades, win_rate, avg_pnl_pct
                FROM strategy_regime_performance
            """)
        ).fetchall()
        return {
            (int(r[0]), str(r[1])): RegimePerf(
                strategy_id=int(r[0]),
                regime=str(r[1]),
                total_trades=int(r[2]),
                win_rate=float(r[3]) if r[3] is not None else 0.5,
                avg_pnl_pct=float(r[4]) if r[4] is not None else 0.0,
            )
            for r in rows
        }
