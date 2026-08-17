"""
Support and Resistance level detection from OHLCV price history.

Three level types detected:
  1. Swing pivots   — fractal highs/lows where price reversed (n bars each side)
  2. Static levels  — 52-week high/low, previous month high/low
  3. Dynamic levels — SMA20, SMA50, SMA200 (moving support/resistance)

Strength (0–1) reflects how significant the level is:
  - SMAs and 52w extremes get fixed strength by significance
  - Swing levels get higher strength when multiple pivots cluster near the same price

Nearby levels within CLUSTER_BAND_PCT of each other are merged (keep strongest).
"""

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)

# Fractal lookback: a pivot high requires n bars lower on each side
SWING_N = 5

# Levels within this % band of each other are considered the same zone
CLUSTER_BAND_PCT = 0.8

# Maximum swing levels to retain per side (too many → noise)
MAX_SWING_PER_SIDE = 8

# Calendar days of history to load (needs 52-week = ~260 trading days)
HISTORY_LOAD_DAYS = 420


@dataclass
class SRLevel:
    price: float
    level_type: str    # "SUPPORT" | "RESISTANCE"
    level_source: str  # "SWING_HIGH" | "SWING_LOW" | "SMA20" | "SMA50" | "SMA200"
                       # | "52W_HIGH" | "52W_LOW" | "PREV_MONTH_HIGH" | "PREV_MONTH_LOW"
    strength: float    # 0.0–1.0
    distance_pct: float  # (level - current_price) / current_price * 100
                         # negative → below price (support), positive → above (resistance)


@dataclass
class SRResult:
    symbol: str
    current_price: float
    as_of_date: date
    levels: list[SRLevel] = field(default_factory=list)
    nearest_support: Optional[SRLevel] = None
    nearest_resistance: Optional[SRLevel] = None
    support_distance_pct: Optional[float] = None      # negative
    resistance_distance_pct: Optional[float] = None   # positive


class SupportResistanceEngine:
    """
    Computes support and resistance levels for a single symbol.
    Pure pandas/numpy — no external TA libraries required.
    """

    def compute(self, db: Session, symbol: str, as_of_date: Optional[date] = None) -> SRResult:
        from ist import ist_today
        target = as_of_date or ist_today()
        cutoff = target - timedelta(days=HISTORY_LOAD_DAYS)

        rows = db.execute(
            text("""
                SELECT date, open, high, low, close
                FROM stock_prices_daily
                WHERE symbol = :sym AND date >= :cutoff AND date <= :target
                ORDER BY date ASC
            """),
            {"sym": symbol.upper(), "cutoff": str(cutoff), "target": str(target)},
        ).fetchall()

        if len(rows) < 30:
            return SRResult(symbol=symbol, current_price=0.0, as_of_date=target)

        df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close"])
        for col in ["open", "high", "low", "close"]:
            df[col] = df[col].astype(float)

        current_price = float(df["close"].iloc[-1])
        if current_price <= 0:
            return SRResult(symbol=symbol, current_price=0.0, as_of_date=target)

        levels: list[SRLevel] = []
        levels += self._static_levels(df, current_price)
        levels += self._sma_levels(df, current_price)
        levels += self._swing_levels(df, current_price)
        levels  = self._cluster(levels, current_price)

        supports    = sorted([l for l in levels if l.level_type == "SUPPORT"],
                             key=lambda x: x.distance_pct, reverse=True)   # closest first
        resistances = sorted([l for l in levels if l.level_type == "RESISTANCE"],
                             key=lambda x: x.distance_pct)                  # closest first

        return SRResult(
            symbol=symbol,
            current_price=round(current_price, 2),
            as_of_date=target,
            levels=levels,
            nearest_support=supports[0] if supports else None,
            nearest_resistance=resistances[0] if resistances else None,
            support_distance_pct=supports[0].distance_pct if supports else None,
            resistance_distance_pct=resistances[0].distance_pct if resistances else None,
        )

    # ── Level detectors ───────────────────────────────────────────────────────

    def _static_levels(self, df: pd.DataFrame, current_price: float) -> list[SRLevel]:
        levels = []
        highs  = df["high"]
        lows   = df["low"]
        n      = len(df)

        # 52-week extremes (~250 trading days)
        bars_52w = min(250, n)
        high_52w = float(highs.iloc[-bars_52w:].max())
        low_52w  = float(lows.iloc[-bars_52w:].min())

        # Previous month extremes (~22 trading days)
        bars_month = min(22, n)
        high_month = float(highs.iloc[-bars_month:].max())
        low_month  = float(lows.iloc[-bars_month:].min())

        specs = [
            (high_52w,  "52W_HIGH",         0.85),
            (low_52w,   "52W_LOW",          0.85),
            (high_month,"PREV_MONTH_HIGH",  0.50),
            (low_month, "PREV_MONTH_LOW",   0.50),
        ]
        for price, source, strength in specs:
            if price <= 0:
                continue
            dist = (price - current_price) / current_price * 100
            lvl_type = "RESISTANCE" if price >= current_price else "SUPPORT"
            levels.append(SRLevel(price=round(price, 2), level_type=lvl_type,
                                  level_source=source, strength=strength,
                                  distance_pct=round(dist, 2)))
        return levels

    def _sma_levels(self, df: pd.DataFrame, current_price: float) -> list[SRLevel]:
        levels  = []
        closes  = df["close"]
        n       = len(closes)

        # Longer SMAs are stronger S/R than shorter ones
        for period, source, strength in [(20, "SMA20", 0.45), (50, "SMA50", 0.60), (200, "SMA200", 0.75)]:
            if n < period:
                continue
            sma_val  = float(closes.iloc[-period:].mean())
            dist     = (sma_val - current_price) / current_price * 100
            lvl_type = "RESISTANCE" if sma_val >= current_price else "SUPPORT"
            levels.append(SRLevel(price=round(sma_val, 2), level_type=lvl_type,
                                  level_source=source, strength=strength,
                                  distance_pct=round(dist, 2)))
        return levels

    def _swing_levels(self, df: pd.DataFrame, current_price: float) -> list[SRLevel]:
        """
        Fractal pivot detection.
        Swing high at bar i: high[i] > high[i±k] for k=1..SWING_N
        Swing low  at bar i: low[i]  < low[i±k]  for k=1..SWING_N
        Only considers bars with enough left/right context.
        """
        n     = SWING_N
        highs = df["high"].values.astype(float)
        lows  = df["low"].values.astype(float)
        total = len(df)

        swing_highs: list[float] = []
        swing_lows:  list[float] = []

        for i in range(n, total - n):
            if (all(highs[i] > highs[i - k] for k in range(1, n + 1)) and
                    all(highs[i] > highs[i + k] for k in range(1, n + 1))):
                swing_highs.append(float(highs[i]))

            if (all(lows[i] < lows[i - k] for k in range(1, n + 1)) and
                    all(lows[i] < lows[i + k] for k in range(1, n + 1))):
                swing_lows.append(float(lows[i]))

        levels: list[SRLevel] = []

        # Retain the most recent pivots (more recent = more relevant)
        for price in swing_highs[-MAX_SWING_PER_SIDE:]:
            strength = self._cluster_strength(price, swing_highs)
            dist     = (price - current_price) / current_price * 100
            lvl_type = "RESISTANCE" if price >= current_price else "SUPPORT"
            levels.append(SRLevel(price=round(price, 2), level_type=lvl_type,
                                  level_source="SWING_HIGH", strength=strength,
                                  distance_pct=round(dist, 2)))

        for price in swing_lows[-MAX_SWING_PER_SIDE:]:
            strength = self._cluster_strength(price, swing_lows)
            dist     = (price - current_price) / current_price * 100
            lvl_type = "RESISTANCE" if price >= current_price else "SUPPORT"
            levels.append(SRLevel(price=round(price, 2), level_type=lvl_type,
                                  level_source="SWING_LOW", strength=strength,
                                  distance_pct=round(dist, 2)))

        return levels

    def _cluster_strength(self, price: float, all_prices: list[float]) -> float:
        """Strength = how many other pivots fall within the cluster band (normalised to 0–1)."""
        band = price * CLUSTER_BAND_PCT / 100
        count = sum(1 for p in all_prices if abs(p - price) <= band)
        # 5 pivots in the same zone = maximum strength; fewer → proportional
        return round(min(1.0, count / 5), 2)

    # ── Post-processing ───────────────────────────────────────────────────────

    def _cluster(self, levels: list[SRLevel], current_price: float) -> list[SRLevel]:
        """Merge levels within CLUSTER_BAND_PCT of each other — keep the strongest."""
        if not levels:
            return levels

        sorted_lvls = sorted(levels, key=lambda x: x.price)
        used = [False] * len(sorted_lvls)
        merged: list[SRLevel] = []

        for i, lvl in enumerate(sorted_lvls):
            if used[i]:
                continue
            group = [lvl]
            for j in range(i + 1, len(sorted_lvls)):
                if abs(sorted_lvls[j].price - lvl.price) / max(lvl.price, 1e-9) * 100 <= CLUSTER_BAND_PCT:
                    group.append(sorted_lvls[j])
                    used[j] = True
            merged.append(max(group, key=lambda x: x.strength))

        return merged
