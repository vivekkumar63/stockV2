"""
Strategy correlation — measures signal overlap between strategy pairs.

Correlation = shared_signals / min(signals_a, signals_b)

A value near 1.0 means the two strategies almost always fire on the same stocks
on the same day — they're measuring the same thing. When both agree, it provides
less independent confirmation than two uncorrelated strategies agreeing.

Used by the risk check to warn when only correlated strategies are backing a signal.
"""

import logging
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Minimum signal history to compute a meaningful correlation
MIN_SIGNALS_FOR_CORRELATION = 20


@dataclass
class CorrelationPair:
    strategy_id_a: int
    strategy_id_b: int
    strategy_name_a: str
    strategy_name_b: str
    correlation: float     # 0.0–1.0
    shared_signals: int


class StrategyCorrelationEngine:
    """
    Computes pairwise signal-overlap correlation from strategy_signals history.

    Runs as a weekly batch job; results cached in strategy_correlations table.
    """

    def compute(self, db: Session) -> list[CorrelationPair]:
        """
        Count (symbol, signal_date) pairs that appear in multiple strategies.
        Returns all pairs with at least MIN_SIGNALS_FOR_CORRELATION signals each.
        """
        # Get signal counts per strategy
        count_rows = db.execute(
            text("""
                SELECT strategy_id, COUNT(DISTINCT symbol || '|' || signal_date) AS cnt
                FROM strategy_signals
                WHERE signal_type = 'BUY'
                GROUP BY strategy_id
                HAVING cnt >= :min_sigs
            """),
            {"min_sigs": MIN_SIGNALS_FOR_CORRELATION},
        ).fetchall()

        if len(count_rows) < 2:
            return []

        counts = {int(r[0]): int(r[1]) for r in count_rows}
        strategy_ids = list(counts.keys())

        # Count shared (symbol, signal_date) pairs for all pairs in one query
        id_list = ",".join(str(s) for s in strategy_ids)
        overlap_rows = db.execute(
            text(f"""
                SELECT a.strategy_id, b.strategy_id, COUNT(*) AS shared
                FROM strategy_signals a
                JOIN strategy_signals b
                    ON a.symbol = b.symbol
                   AND a.signal_date = b.signal_date
                   AND a.strategy_id < b.strategy_id
                WHERE a.signal_type = 'BUY' AND b.signal_type = 'BUY'
                  AND a.strategy_id IN ({id_list})
                  AND b.strategy_id IN ({id_list})
                GROUP BY a.strategy_id, b.strategy_id
            """)
        ).fetchall()

        # Fetch strategy names
        name_rows = db.execute(
            text(f"SELECT id, name FROM strategies WHERE id IN ({id_list})")
        ).fetchall()
        names = {int(r[0]): str(r[1]) for r in name_rows}

        results: list[CorrelationPair] = []
        for sid_a, sid_b, shared in overlap_rows:
            sid_a, sid_b, shared = int(sid_a), int(sid_b), int(shared)
            min_count = min(counts.get(sid_a, 1), counts.get(sid_b, 1))
            corr = round(shared / min_count, 4) if min_count > 0 else 0.0
            results.append(CorrelationPair(
                strategy_id_a=sid_a,
                strategy_id_b=sid_b,
                strategy_name_a=names.get(sid_a, str(sid_a)),
                strategy_name_b=names.get(sid_b, str(sid_b)),
                correlation=corr,
                shared_signals=shared,
            ))

        logger.info("[StrategyCorr] computed %d pairs", len(results))
        return results

    def save(self, db: Session, pairs: list[CorrelationPair]) -> None:
        for p in pairs:
            db.execute(
                text("""
                    INSERT INTO strategy_correlations
                    (strategy_id_a, strategy_id_b, correlation, shared_signals, computed_at)
                    VALUES (:a, :b, :corr, :shared, CURRENT_TIMESTAMP)
                    ON CONFLICT (strategy_id_a, strategy_id_b) DO UPDATE SET
                        correlation=EXCLUDED.correlation, shared_signals=EXCLUDED.shared_signals,
                        computed_at=CURRENT_TIMESTAMP
                """),
                {"a": p.strategy_id_a, "b": p.strategy_id_b,
                 "corr": p.correlation, "shared": p.shared_signals},
            )
        db.commit()

    def get_correlation(self, db: Session, sid_a: int, sid_b: int) -> float:
        """Return stored correlation between two strategies (0.0 if not computed)."""
        a, b = (sid_a, sid_b) if sid_a < sid_b else (sid_b, sid_a)
        row = db.execute(
            text("""
                SELECT correlation FROM strategy_correlations
                WHERE strategy_id_a = :a AND strategy_id_b = :b
            """),
            {"a": a, "b": b},
        ).fetchone()
        return float(row[0]) if row else 0.0

    def get_matrix(self, db: Session) -> list[dict]:
        """Return all stored correlations for the matrix endpoint."""
        rows = db.execute(
            text("""
                SELECT sc.strategy_id_a, sa.name, sc.strategy_id_b, sb.name,
                       sc.correlation, sc.shared_signals, sc.computed_at
                FROM strategy_correlations sc
                JOIN strategies sa ON sa.id = sc.strategy_id_a
                JOIN strategies sb ON sb.id = sc.strategy_id_b
                ORDER BY sc.correlation DESC
            """)
        ).fetchall()
        return [
            {
                "strategy_id_a":   int(r[0]),
                "strategy_name_a": str(r[1]),
                "strategy_id_b":   int(r[2]),
                "strategy_name_b": str(r[3]),
                "correlation":     float(r[4]),
                "shared_signals":  int(r[5]),
                "computed_at":     str(r[6])[:19] if r[6] else None,
            }
            for r in rows
        ]
