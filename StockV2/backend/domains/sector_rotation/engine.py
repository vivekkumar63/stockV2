"""Sector rotation pre-computation engine.

Computes two sets of daily metrics:
  sector_breadth_daily   — breadth/momentum per sector per trading day
  sector_signal_flow     — signal counts per sector per ISO week
"""
import logging
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from domains.data.index_universe import INDEX_DEFINITIONS, STOCK_INDEX_MAP

logger = logging.getLogger(__name__)

# Short friendly names used in the DB (no "NIFTY " prefix)
_INDEX_TO_SECTOR: dict[str, str] = {
    "NIFTY BANK":   "BANK",
    "NIFTY IT":     "IT",
    "NIFTY FMCG":   "FMCG",
    "NIFTY AUTO":   "AUTO",
    "NIFTY PHARMA": "PHARMA",
    "NIFTY METAL":  "METAL",
    "NIFTY ENERGY": "ENERGY",
}

# Reverse lookup: stock symbol → short sector name
SYMBOL_TO_SECTOR: dict[str, str] = {
    sym: _INDEX_TO_SECTOR[idx]
    for sym, idx in STOCK_INDEX_MAP.items()
    if idx in _INDEX_TO_SECTOR
}

# Sector → list of stocks
_SECTOR_STOCKS: dict[str, list[str]] = {}
for sym, sector in SYMBOL_TO_SECTOR.items():
    _SECTOR_STOCKS.setdefault(sector, []).append(sym)


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _compute_health_score(
    pct_above_sma50: float,
    index_vs_sma20: float,
    return_1m: float,
) -> float:
    breadth  = pct_above_sma50 * 0.50
    momentum = _clamp(index_vs_sma20 * 10.0, -50.0, 50.0) * 0.30
    trend    = _clamp(return_1m * 5.0, -50.0, 50.0) * 0.20
    return _clamp(50.0 + breadth + momentum + trend, 0.0, 100.0)


def _rotation_direction(score: float) -> str:
    if score >= 60:
        return "ROTATING_IN"
    if score >= 40:
        return "NEUTRAL"
    return "ROTATING_OUT"


class SectorRotationEngine:

    def compute_breadth(self, db: Session, trade_date: date) -> int:
        """Compute sector_breadth_daily rows for trade_date. Returns rows written."""
        written = 0
        for index_name, sector in _INDEX_TO_SECTOR.items():
            stocks = _SECTOR_STOCKS.get(sector, [])
            if not stocks:
                continue

            placeholders = ",".join(f"'{s}'" for s in stocks)

            # % of stocks above their 50-day SMA — computed directly from price history
            # so this works even before the indicator cache is populated for today.
            above_sma50_row = db.execute(text(f"""
                WITH ranked AS (
                    SELECT symbol, close,
                           ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) AS rn
                    FROM stock_prices_daily
                    WHERE symbol IN ({placeholders})
                      AND date <= :d
                ),
                latest AS (
                    SELECT symbol, close FROM ranked WHERE rn = 1
                ),
                sma50 AS (
                    SELECT symbol, AVG(close) AS sma
                    FROM ranked WHERE rn <= 50
                    GROUP BY symbol
                    HAVING COUNT(*) >= 10
                )
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN l.close > s.sma THEN 1 ELSE 0 END) AS above
                FROM latest l
                JOIN sma50 s ON s.symbol = l.symbol
            """), {"d": str(trade_date)}).fetchone()

            if above_sma50_row is None or above_sma50_row[0] == 0:
                logger.debug("[sector_breadth] no price data for %s on %s — skipping", sector, trade_date)
                continue

            total_stocks = above_sma50_row[0]
            above_sma50_count = above_sma50_row[1] or 0
            pct_above_sma50 = (above_sma50_count / total_stocks) * 100.0

            # Index prices for the sector
            idx_rows = db.execute(text("""
                SELECT date, close FROM index_prices_daily
                WHERE index_name = :name ORDER BY date DESC LIMIT 60
            """), {"name": index_name}).fetchall()

            if len(idx_rows) < 2:
                logger.debug("[sector_breadth] no index price data for %s — skipping", index_name)
                continue

            closes = [r[1] for r in reversed(idx_rows)]
            current_close = closes[-1]

            # SMA20 for index_vs_sma20
            sma20_window = closes[-20:] if len(closes) >= 20 else closes
            sma20 = sum(sma20_window) / len(sma20_window)
            index_vs_sma20 = ((current_close / sma20) - 1.0) * 100.0

            # 1M and 3M returns
            close_22 = closes[-22] if len(closes) >= 22 else closes[0]
            close_63 = closes[-63] if len(closes) >= 63 else closes[0]
            return_1m = ((current_close / close_22) - 1.0) * 100.0
            return_3m = ((current_close / close_63) - 1.0) * 100.0

            score = _compute_health_score(pct_above_sma50, index_vs_sma20, return_1m)
            direction = _rotation_direction(score)

            db.execute(text("""
                INSERT INTO sector_breadth_daily
                    (sector_name, trade_date, pct_above_sma50, index_vs_sma20,
                     return_1m, return_3m, sector_health_score, rotation_direction)
                VALUES
                    (:sector, :d, :pct, :ivs, :r1m, :r3m, :score, :dir)
                ON CONFLICT (sector_name, trade_date)
                DO UPDATE SET
                    pct_above_sma50    = EXCLUDED.pct_above_sma50,
                    index_vs_sma20     = EXCLUDED.index_vs_sma20,
                    return_1m          = EXCLUDED.return_1m,
                    return_3m          = EXCLUDED.return_3m,
                    sector_health_score = EXCLUDED.sector_health_score,
                    rotation_direction = EXCLUDED.rotation_direction
            """), {
                "sector": sector,
                "d":      str(trade_date),
                "pct":    round(pct_above_sma50, 2),
                "ivs":    round(index_vs_sma20, 4),
                "r1m":    round(return_1m, 4),
                "r3m":    round(return_3m, 4),
                "score":  round(score, 2),
                "dir":    direction,
            })
            written += 1

        db.commit()
        logger.info("[sector_rotation] compute_breadth %s: %d sectors written", trade_date, written)
        return written

    def compute_signal_flow(self, db: Session, week_start: date) -> int:
        """Compute sector_signal_flow rows for the ISO week starting on week_start."""
        week_end = week_start + timedelta(days=6)
        prev_week_start = week_start - timedelta(days=7)
        prev_week_end = week_start - timedelta(days=1)
        written = 0

        for sector, stocks in _SECTOR_STOCKS.items():
            if not stocks:
                continue
            placeholders = ",".join(f"'{s}'" for s in stocks)

            # This week's BUY signals
            this_week = db.execute(text(f"""
                SELECT ss.symbol, COUNT(*) AS cnt,
                       AVG(CASE WHEN sp.win_rate IS NOT NULL THEN sp.win_rate ELSE NULL END) AS avg_wr,
                       s.name AS strategy_name, COUNT(*) AS strategy_cnt
                FROM strategy_signals ss
                JOIN strategies s ON s.id = ss.strategy_id
                LEFT JOIN strategy_performance sp
                    ON sp.symbol = ss.symbol AND sp.strategy_id = ss.strategy_id
                WHERE ss.signal_type = 'BUY'
                  AND ss.signal_date BETWEEN :ws AND :we
                  AND ss.symbol IN ({placeholders})
                GROUP BY ss.symbol, s.name
            """), {"ws": str(week_start), "we": str(week_end)}).fetchall()

            signal_count = len(this_week)
            avg_win_rate: Optional[float] = None
            top_strategy: Optional[str] = None
            stocks_with_signals: list[str] = list({r[0] for r in this_week})

            if this_week:
                win_rates = [r[2] for r in this_week if r[2] is not None]
                if win_rates:
                    avg_win_rate = sum(win_rates) / len(win_rates)
                strategy_counts: dict[str, int] = {}
                for r in this_week:
                    strategy_counts[r[3]] = strategy_counts.get(r[3], 0) + r[4]
                top_strategy = max(strategy_counts, key=strategy_counts.get)

            # Previous week's count
            prev_week = db.execute(text(f"""
                SELECT COUNT(*) FROM strategy_signals
                WHERE signal_type = 'BUY'
                  AND signal_date BETWEEN :ws AND :we
                  AND symbol IN ({placeholders})
            """), {"ws": str(prev_week_start), "we": str(prev_week_end)}).scalar() or 0

            db.execute(text("""
                INSERT INTO sector_signal_flow
                    (sector_name, week_start, signal_count, prev_signal_count,
                     avg_win_rate, top_strategy, stocks_with_signals)
                VALUES
                    (:sector, :ws, :cnt, :prev, :wr, :strat, :syms)
                ON CONFLICT (sector_name, week_start)
                DO UPDATE SET
                    signal_count        = EXCLUDED.signal_count,
                    prev_signal_count   = EXCLUDED.prev_signal_count,
                    avg_win_rate        = EXCLUDED.avg_win_rate,
                    top_strategy        = EXCLUDED.top_strategy,
                    stocks_with_signals = EXCLUDED.stocks_with_signals
            """), {
                "sector": sector,
                "ws":     str(week_start),
                "cnt":    signal_count,
                "prev":   prev_week,
                "wr":     round(avg_win_rate, 4) if avg_win_rate is not None else None,
                "strat":  top_strategy,
                "syms":   ",".join(stocks_with_signals[:20]),
            })
            written += 1

        db.commit()
        logger.info("[sector_rotation] compute_signal_flow week=%s: %d sectors written", week_start, written)
        return written

    def get_market_phase(self, db: Session) -> str:
        """Determine market phase from the latest sector breadth data."""
        rows = db.execute(text("""
            SELECT sector_name, rotation_direction, sector_health_score
            FROM sector_breadth_daily
            WHERE trade_date = (SELECT MAX(trade_date) FROM sector_breadth_daily)
        """)).fetchall()

        if not rows:
            return "UNKNOWN"

        rotating_in  = sum(1 for r in rows if r[1] == "ROTATING_IN")
        rotating_out = sum(1 for r in rows if r[1] == "ROTATING_OUT")
        avg_score    = sum(r[2] for r in rows) / len(rows)

        if rotating_in >= 3 and avg_score >= 60:
            return "EXPANSION"
        if rotating_out >= 3 and avg_score < 40:
            return "CONTRACTION"
        # Differentiate RECOVERY vs SLOWDOWN by avg 1M return
        avg_1m = db.execute(text("""
            SELECT AVG(return_1m) FROM sector_breadth_daily
            WHERE trade_date = (SELECT MAX(trade_date) FROM sector_breadth_daily)
        """)).scalar() or 0.0
        return "RECOVERY" if avg_1m >= 0 else "SLOWDOWN"

    def get_sector_summary(self, db: Session) -> list[dict]:
        """Return merged breadth + signal flow for all sectors, latest available data."""
        breadth_rows = db.execute(text("""
            SELECT sector_name, trade_date, pct_above_sma50, index_vs_sma20,
                   return_1m, return_3m, sector_health_score, rotation_direction
            FROM sector_breadth_daily
            WHERE trade_date = (SELECT MAX(trade_date) FROM sector_breadth_daily)
            ORDER BY sector_health_score DESC
        """)).fetchall()

        # Week start for latest week in signal flow
        flow_rows = db.execute(text("""
            SELECT sector_name, week_start, signal_count, prev_signal_count,
                   avg_win_rate, top_strategy, stocks_with_signals
            FROM sector_signal_flow
            WHERE week_start = (SELECT MAX(week_start) FROM sector_signal_flow)
        """)).fetchall()

        flow_by_sector = {r[0]: r for r in flow_rows}

        result = []
        for b in breadth_rows:
            f = flow_by_sector.get(b[0])
            stocks = f[6].split(",") if f and f[6] else []
            result.append({
                "name":                  b[0],
                "rotation_direction":    b[7],
                "sector_health_score":   round(b[6], 1),
                "pct_above_sma50":       round(b[2], 1),
                "index_vs_sma20":        round(b[3], 2),
                "return_1m":             round(b[4], 2),
                "return_3m":             round(b[5], 2),
                "signal_count_this_week": f[2] if f else 0,
                "signal_count_prev_week": f[3] if f else 0,
                "avg_win_rate":           round(f[4], 4) if f and f[4] else None,
                "top_strategy":           f[5] if f else None,
                "stocks_with_signals":    [s.strip() for s in stocks if s.strip()],
            })
        return result
