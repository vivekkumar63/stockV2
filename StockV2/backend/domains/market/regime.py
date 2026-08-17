"""
Market regime detection using stock-universe breadth.

Primary signals (in order of weight):
  1. pct_above_sma50  — fraction of universe with close > 50-day SMA (intermediate breadth)
  2. pct_above_sma200 — fraction of universe with close > 200-day SMA (long-term confirmation)
  3. avg_atr_ratio    — average daily range / close across universe (volatility override)
  4. advance_decline  — fraction advancing on this day (confidence modifier only)

Threshold values are documented constants — not magic numbers.
"""

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy import text

from ist import ist_today

logger = logging.getLogger(__name__)

# ── Breadth thresholds ────────────────────────────────────────────────────────
# All values are fraction of stock universe (0.0–1.0)

# SMA50 breadth thresholds
# 70%+ above 50-day SMA historically corresponds to strong bull markets
SMA50_STRONG_BULL = 0.70
SMA50_BULL        = 0.55   # 55–70%: normal bull phase
SMA50_BEAR        = 0.40   # below 40%: bearish breadth
SMA50_STRONG_BEAR = 0.25   # below 25%: very weak market

# SMA200 breadth (longer-term, used for confirmation only)
SMA200_STRONG_BULL = 0.65
SMA200_BULL        = 0.50
SMA200_BEAR        = 0.40
SMA200_STRONG_BEAR = 0.30

# ATR ratio threshold: average(ATR_14 / close * 100) across all stocks
# >3.5% average daily range = elevated volatility; overrides trend classification
HIGH_VOLATILITY_ATR_PCT = 3.5

# Minimum number of stocks required for a reliable breadth reading
MIN_STOCKS = 50

# Calendar days to load for SMA200 computation (~200 trading days + buffer)
HISTORY_LOAD_DAYS = 310


@dataclass
class RegimeResult:
    regime: str              # STRONG_BULL | BULL | SIDEWAYS | BEAR | STRONG_BEAR | HIGH_VOLATILITY
    confidence: float        # 0.0–1.0
    pct_above_sma50: float   # fraction of stocks above 50-day SMA
    pct_above_sma200: float  # fraction of stocks above 200-day SMA
    advance_decline_ratio: float  # fraction of stocks up on the latest day
    avg_atr_ratio: float     # average (ATR/close × 100) across universe
    stocks_counted: int
    as_of_date: date


class MarketRegimeEngine:
    """
    Detects broad market regime from price breadth of all available NSE stocks.

    Does not require a NIFTY index series — derives trend from the stock universe
    itself, which is actually more granular than a price-weighted index.

    Usage:
        engine = MarketRegimeEngine()
        result = engine.get_or_compute(db)   # uses cached value if today already computed
        result = engine.compute(db)           # always recomputes
    """

    def compute(self, db: Session, as_of_date: Optional[date] = None) -> RegimeResult:
        target = as_of_date or ist_today()
        cutoff = target - timedelta(days=HISTORY_LOAD_DAYS)

        rows = db.execute(
            text("""
                SELECT symbol, date, open, high, low, close
                FROM stock_prices_daily
                WHERE date >= :cutoff AND date <= :target
                ORDER BY symbol, date
            """),
            {"cutoff": str(cutoff), "target": str(target)},
        ).fetchall()

        if not rows:
            logger.warning("[RegimeEngine] no price data for %s", target)
            return self._fallback(target)

        df = pd.DataFrame(rows, columns=["symbol", "date", "open", "high", "low", "close"])
        df["date"] = pd.to_datetime(df["date"]).dt.date

        latest_date = df["date"].max()
        metrics: list[dict] = []

        for symbol, grp in df.groupby("symbol", sort=False):
            grp = grp.sort_values("date").reset_index(drop=True)
            closes = grp["close"].values.astype(float)
            n = len(closes)

            if n < 50:
                continue

            last_close = closes[-1]
            if last_close <= 0:
                continue

            sma50  = closes[-50:].mean()
            sma200 = closes[-200:].mean() if n >= 200 else closes.mean()

            # ATR approximation: mean high-low range over last 14 bars (Wilder-free, breadth use)
            highs = grp["high"].values[-15:].astype(float)
            lows  = grp["low"].values[-15:].astype(float)
            atr_approx = float((highs - lows).mean())
            atr_ratio  = atr_approx / last_close * 100

            # Advance/decline: did the stock close above open on the latest day?
            last_row = grp[grp["date"] == latest_date]
            advancing = (
                float(last_row["close"].iloc[0]) > float(last_row["open"].iloc[0])
                if not last_row.empty else False
            )

            metrics.append({
                "above_sma50":  last_close > sma50,
                "above_sma200": last_close > sma200,
                "advancing":    advancing,
                "atr_ratio":    atr_ratio,
            })

        if len(metrics) < MIN_STOCKS:
            logger.warning("[RegimeEngine] only %d stocks — below minimum %d", len(metrics), MIN_STOCKS)
            return self._fallback(latest_date)

        total       = len(metrics)
        pct_sma50   = sum(1 for m in metrics if m["above_sma50"])  / total
        pct_sma200  = sum(1 for m in metrics if m["above_sma200"]) / total
        adv_dec     = sum(1 for m in metrics if m["advancing"])     / total
        avg_atr     = sum(m["atr_ratio"] for m in metrics) / total

        regime, confidence = self._classify(pct_sma50, pct_sma200, adv_dec, avg_atr)

        return RegimeResult(
            regime=regime,
            confidence=round(confidence, 4),
            pct_above_sma50=round(pct_sma50, 4),
            pct_above_sma200=round(pct_sma200, 4),
            advance_decline_ratio=round(adv_dec, 4),
            avg_atr_ratio=round(avg_atr, 4),
            stocks_counted=total,
            as_of_date=latest_date,
        )

    def _classify(
        self, pct50: float, pct200: float, adv_dec: float, avg_atr: float
    ) -> tuple[str, float]:
        # HIGH_VOLATILITY overrides trend when average daily range is extreme
        if avg_atr >= HIGH_VOLATILITY_ATR_PCT:
            # Confidence grows proportionally above threshold
            excess = (avg_atr - HIGH_VOLATILITY_ATR_PCT) / HIGH_VOLATILITY_ATR_PCT
            conf   = min(1.0, 0.60 + excess * 0.40)
            return "HIGH_VOLATILITY", round(conf, 4)

        # A/D ratio adjusts confidence up/down by up to ±0.10
        adv_adj = (adv_dec - 0.50) * 0.20  # range: -0.10 to +0.10

        if pct50 >= SMA50_STRONG_BULL and pct200 >= SMA200_STRONG_BULL:
            base = 0.80 + (pct50 - SMA50_STRONG_BULL) / (1.0 - SMA50_STRONG_BULL) * 0.15
            return "STRONG_BULL", round(min(1.0, base + adv_adj), 4)

        if pct50 >= SMA50_BULL:
            progress = (pct50 - SMA50_BULL) / (SMA50_STRONG_BULL - SMA50_BULL)
            base = 0.60 + progress * 0.20 + (0.10 if pct200 >= SMA200_BULL else 0.0)
            return "BULL", round(min(0.85, base + adv_adj), 4)

        if pct50 <= SMA50_STRONG_BEAR and pct200 <= SMA200_STRONG_BEAR:
            base = 0.75 + (SMA50_STRONG_BEAR - pct50) / SMA50_STRONG_BEAR * 0.25
            return "STRONG_BEAR", round(min(1.0, base), 4)

        if pct50 <= SMA50_BEAR:
            progress = (SMA50_BEAR - pct50) / (SMA50_BEAR - SMA50_STRONG_BEAR)
            base = 0.60 + progress * 0.20
            return "BEAR", round(min(0.85, base), 4)

        # Middle band (40–55%): sideways / mixed
        distance_from_midpoint = abs(pct50 - 0.50)
        base = 0.45 + distance_from_midpoint * 0.80
        return "SIDEWAYS", round(min(0.70, base), 4)

    def get_or_compute(self, db: Session, as_of_date: Optional[date] = None) -> RegimeResult:
        """Return cached DB row if today already computed, else compute and persist."""
        target = as_of_date or ist_today()
        row = db.execute(
            text("SELECT * FROM market_regime WHERE date = :d LIMIT 1"),
            {"d": str(target)},
        ).fetchone()
        if row:
            return self._from_row(dict(row._mapping))
        result = self.compute(db, target)
        self.save(db, result)
        return result

    def save(self, db: Session, r: RegimeResult) -> None:
        db.execute(
            text("""
                INSERT OR REPLACE INTO market_regime
                (date, regime, confidence, pct_above_sma50, pct_above_sma200,
                 advance_decline_ratio, avg_atr_ratio, stocks_counted, computed_at)
                VALUES (:d, :regime, :conf, :sma50, :sma200, :adv, :atr, :n, CURRENT_TIMESTAMP)
            """),
            {
                "d": str(r.as_of_date), "regime": r.regime, "conf": r.confidence,
                "sma50": r.pct_above_sma50, "sma200": r.pct_above_sma200,
                "adv": r.advance_decline_ratio, "atr": r.avg_atr_ratio, "n": r.stocks_counted,
            },
        )
        db.commit()

    def get_history(self, db: Session, days: int = 30) -> list[RegimeResult]:
        rows = db.execute(
            text("""
                SELECT * FROM market_regime
                ORDER BY date DESC LIMIT :lim
            """),
            {"lim": days},
        ).fetchall()
        return [self._from_row(dict(r._mapping)) for r in rows]

    def _from_row(self, row: dict) -> RegimeResult:
        return RegimeResult(
            regime=row["regime"],
            confidence=row["confidence"] or 0.0,
            pct_above_sma50=row["pct_above_sma50"] or 0.0,
            pct_above_sma200=row["pct_above_sma200"] or 0.0,
            advance_decline_ratio=row["advance_decline_ratio"] or 0.0,
            avg_atr_ratio=row["avg_atr_ratio"] or 0.0,
            stocks_counted=row["stocks_counted"] or 0,
            as_of_date=date.fromisoformat(str(row["date"])[:10]),
        )

    def compute_bulk(
        self, db: Session, start_date: date, end_date: date
    ) -> dict[date, "RegimeResult"]:
        """
        Vectorized historical regime computation for a date range.

        Loads all price history in one query, computes SMA50/200 breadth via
        pandas rolling — one pass for the entire range. Used to backfill
        market_regime for regime-performance analysis.

        Returns mapping date → RegimeResult for every trading day in the range
        that has sufficient data. Skips dates where fewer than MIN_STOCKS qualify.
        """
        load_from = start_date - timedelta(days=HISTORY_LOAD_DAYS)
        rows = db.execute(
            text("""
                SELECT symbol, date, close
                FROM stock_prices_daily
                WHERE date >= :from AND date <= :to
                ORDER BY symbol, date
            """),
            {"from": str(load_from), "to": str(end_date)},
        ).fetchall()

        if not rows:
            return {}

        df = pd.DataFrame(rows, columns=["symbol", "date", "close"])
        df["date"] = pd.to_datetime(df["date"])
        df["close"] = df["close"].astype(float)

        pivot = df.pivot_table(index="date", columns="symbol", values="close", aggfunc="last")
        sma50  = pivot.rolling(50,  min_periods=50).mean()
        sma200 = pivot.rolling(200, min_periods=200).mean()

        results: dict[date, RegimeResult] = {}
        start_ts = pd.Timestamp(start_date)

        for ts in pivot.index:
            if ts < start_ts:
                continue

            close_row  = pivot.loc[ts]
            sma50_row  = sma50.loc[ts]
            sma200_row = sma200.loc[ts]

            valid50  = ~close_row.isna() & ~sma50_row.isna()
            total    = int(valid50.sum())
            if total < MIN_STOCKS:
                continue

            above50  = int((close_row[valid50] > sma50_row[valid50]).sum())

            valid200 = ~close_row.isna() & ~sma200_row.isna()
            total200 = int(valid200.sum())
            above200 = int((close_row[valid200] > sma200_row[valid200]).sum()) if total200 > 0 else 0

            pct50  = above50 / total
            pct200 = above200 / total200 if total200 > 0 else 0.0

            # ATR and A/D omitted for bulk mode (not available from close-only pivot)
            regime, confidence = self._classify(pct50, pct200, 0.5, 0.0)

            results[ts.date()] = RegimeResult(
                regime=regime,
                confidence=round(confidence, 4),
                pct_above_sma50=round(pct50, 4),
                pct_above_sma200=round(pct200, 4),
                advance_decline_ratio=0.5,
                avg_atr_ratio=0.0,
                stocks_counted=total,
                as_of_date=ts.date(),
            )

        logger.info("[RegimeEngine] bulk computed %d dates (%s → %s)", len(results), start_date, end_date)
        return results

    def save_bulk(self, db: Session, results: dict[date, "RegimeResult"]) -> int:
        """Insert regime records for dates not yet in market_regime. Returns rows inserted."""
        if not results:
            return 0
        min_d = str(min(results.keys()))
        max_d = str(max(results.keys()))
        existing = {
            str(r[0])
            for r in db.execute(
                text("SELECT date FROM market_regime WHERE date >= :s AND date <= :e"),
                {"s": min_d, "e": max_d},
            ).fetchall()
        }
        inserted = 0
        for d, r in sorted(results.items()):
            if str(d) in existing:
                continue
            db.execute(
                text("""
                    INSERT OR IGNORE INTO market_regime
                    (date, regime, confidence, pct_above_sma50, pct_above_sma200,
                     advance_decline_ratio, avg_atr_ratio, stocks_counted, computed_at)
                    VALUES (:d, :regime, :conf, :sma50, :sma200, :adv, :atr, :n, CURRENT_TIMESTAMP)
                """),
                {
                    "d": str(d), "regime": r.regime, "conf": r.confidence,
                    "sma50": r.pct_above_sma50, "sma200": r.pct_above_sma200,
                    "adv": r.advance_decline_ratio, "atr": r.avg_atr_ratio, "n": r.stocks_counted,
                },
            )
            inserted += 1
        db.commit()
        return inserted

    def _fallback(self, as_of_date: date) -> RegimeResult:
        return RegimeResult(
            regime="SIDEWAYS", confidence=0.0,
            pct_above_sma50=0.0, pct_above_sma200=0.0,
            advance_decline_ratio=0.0, avg_atr_ratio=0.0,
            stocks_counted=0, as_of_date=as_of_date,
        )
