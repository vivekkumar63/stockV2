"""
False signal detector — tracks whether recent strategy signals were profitable.

A BUY signal is deemed:
  - Profitable (true signal)  : close HOLDING_DAYS later > price_at_signal
  - False signal              : close HOLDING_DAYS later <= price_at_signal

Rolling false signal rate = false_signals / (true + false) over last LOOKBACK_SIGNALS.

This rate is used in OpportunityScorer as a penalty on the full score.
Only signals at least HOLDING_DAYS old are evaluated (outcome known).

Runs nightly via the scheduler to keep signal_outcomes current.
"""

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

HOLDING_DAYS    = 15   # default holding period used to judge outcome
LOOKBACK_SIGNALS = 30  # evaluate last N signals per strategy for the rolling rate
MIN_SIGNALS     = 5    # need at least this many evaluated signals to report a rate


@dataclass
class SignalOutcomeRecord:
    signal_id: int
    symbol: str
    strategy_id: int
    signal_date: date
    price_at_signal: float
    outcome_price: Optional[float]
    outcome_date: Optional[date]
    pnl_pct: Optional[float]
    is_profitable: Optional[bool]
    holding_days_actual: Optional[int]


class FalseSignalDetector:
    """
    Evaluates recent BUY signal outcomes and computes rolling false-signal rates.

    Usage:
        detector = FalseSignalDetector()
        n = detector.compute_outcomes(db)        # run nightly, returns #new records
        rates = detector.get_false_signal_rates(db)  # {strategy_id: false_rate}
    """

    def compute_outcomes(self, db: Session) -> int:
        """
        For every BUY signal that:
        - has no entry in signal_outcomes yet
        - was generated at least HOLDING_DAYS ago (outcome is observable)

        look up the close price HOLDING_DAYS after the signal date and record the outcome.
        Returns number of new outcome records written.
        """
        cutoff = date.today() - timedelta(days=HOLDING_DAYS)

        rows = db.execute(
            text("""
                SELECT ss.id, ss.symbol, ss.strategy_id, ss.signal_date,
                       ss.price_at_signal, ss.holding_period_days
                FROM strategy_signals ss
                WHERE ss.signal_type = 'BUY'
                  AND ss.signal_date <= :cutoff
                  AND ss.price_at_signal IS NOT NULL
                  AND ss.id NOT IN (SELECT signal_id FROM signal_outcomes)
                ORDER BY ss.signal_date DESC
                LIMIT 500
            """),
            {"cutoff": str(cutoff)},
        ).fetchall()

        if not rows:
            return 0

        written = 0
        for sig_id, symbol, strategy_id, sig_date, price_at_signal, holding_days in rows:
            hp = int(holding_days) if holding_days else HOLDING_DAYS
            target_date = (
                date.fromisoformat(str(sig_date)[:10]) + timedelta(days=hp)
            )

            # Find the closest trading day on or after target_date (up to 7 extra days)
            price_row = db.execute(
                text("""
                    SELECT date, close
                    FROM stock_prices_daily
                    WHERE symbol = :sym
                      AND date >= :target
                      AND date <= :max_date
                    ORDER BY date ASC
                    LIMIT 1
                """),
                {
                    "sym": symbol,
                    "target": str(target_date),
                    "max_date": str(target_date + timedelta(days=7)),
                },
            ).fetchone()

            if not price_row:
                continue

            outcome_date  = date.fromisoformat(str(price_row[0])[:10])
            outcome_price = float(price_row[1])
            pnl_pct       = (outcome_price - float(price_at_signal)) / float(price_at_signal) * 100
            is_profitable = pnl_pct > 0
            actual_days   = (outcome_date - date.fromisoformat(str(sig_date)[:10])).days

            db.execute(
                text("""
                    INSERT INTO signal_outcomes
                    (signal_id, symbol, strategy_id, signal_date, signal_type,
                     price_at_signal, outcome_price, outcome_date, pnl_pct,
                     is_profitable, holding_days_actual, computed_at)
                    VALUES (:sid, :sym, :strat, :sdate, 'BUY',
                            :price, :oprice, :odate, :pnl,
                            :prof, :hdays, CURRENT_TIMESTAMP)
                    ON CONFLICT (signal_id) DO NOTHING
                """),
                {
                    "sid": sig_id, "sym": symbol, "strat": strategy_id,
                    "sdate": str(date.fromisoformat(str(sig_date)[:10])),
                    "price": float(price_at_signal), "oprice": outcome_price,
                    "odate": str(outcome_date), "pnl": round(pnl_pct, 4),
                    "prof": 1 if is_profitable else 0, "hdays": actual_days,
                },
            )
            written += 1

        if written:
            db.commit()
        logger.info("[FalseSignalDetector] %d new outcomes recorded", written)
        return written

    def get_false_signal_rates(self, db: Session) -> dict[int, float]:
        """
        Returns {strategy_id: false_signal_rate} for the last LOOKBACK_SIGNALS
        evaluated signals per strategy. Only strategies with MIN_SIGNALS+ outcomes
        are included.
        """
        rows = db.execute(
            text("""
                WITH ranked AS (
                    SELECT strategy_id, is_profitable,
                           ROW_NUMBER() OVER (
                               PARTITION BY strategy_id
                               ORDER BY signal_date DESC
                           ) AS rn
                    FROM signal_outcomes
                    WHERE signal_type = 'BUY' AND is_profitable IS NOT NULL
                )
                SELECT strategy_id,
                       COUNT(*) AS total,
                       SUM(CASE WHEN is_profitable = 0 THEN 1 ELSE 0 END) AS false_count
                FROM ranked
                WHERE rn <= :lookback
                GROUP BY strategy_id
                HAVING COUNT(*) >= :min_sigs
            """),
            {"lookback": LOOKBACK_SIGNALS, "min_sigs": MIN_SIGNALS},
        ).fetchall()

        return {
            int(r[0]): round(float(r[2]) / float(r[1]), 4)
            for r in rows
        }

    def get_rate_for_strategy(self, db: Session, strategy_id: int) -> Optional[float]:
        """Return false signal rate for a single strategy, or None if insufficient data."""
        rates = self.get_false_signal_rates(db)
        return rates.get(strategy_id)

    def get_stats(self, db: Session) -> list[dict]:
        """
        Returns summary stats per strategy: total evaluated, win rate, false rate,
        average pnl. Used by the /intelligence/false-signal-stats endpoint.
        """
        rows = db.execute(
            text("""
                SELECT so.strategy_id, s.name,
                       COUNT(*)  AS total_evaluated,
                       SUM(CASE WHEN so.is_profitable = 1 THEN 1 ELSE 0 END) AS profitable,
                       AVG(so.pnl_pct) AS avg_pnl_pct,
                       MAX(so.signal_date) AS latest_signal_date
                FROM signal_outcomes so
                JOIN strategies s ON s.id = so.strategy_id
                WHERE so.signal_type = 'BUY' AND so.is_profitable IS NOT NULL
                GROUP BY so.strategy_id, s.name
                ORDER BY so.strategy_id
            """)
        ).fetchall()

        false_rates = self.get_false_signal_rates(db)

        return [
            {
                "strategy_id":         int(r[0]),
                "strategy_name":       str(r[1]),
                "total_evaluated":     int(r[2]),
                "profitable":          int(r[3]),
                "win_rate":            round(int(r[3]) / int(r[2]), 4) if int(r[2]) > 0 else None,
                "false_signal_rate":   false_rates.get(int(r[0])),
                "avg_pnl_pct":         round(float(r[4]), 4) if r[4] is not None else None,
                "latest_signal_date":  str(r[5])[:10] if r[5] else None,
            }
            for r in rows
        ]
