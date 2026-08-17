"""
Enhanced volume analysis module.

The existing IndicatorEngine already computes:
  volume_sma_20, volume_ratio, obv, obv_sma_10

This module builds on those columns and adds:
  - relative_volume_50  : volume / 50-day average (broader baseline)
  - volume_trend        : is the 10-bar OBV direction RISING / FALLING / FLAT
  - volume_spike        : today's volume > 3× 20-day average
  - breakout_confirmed  : price at 20-day high + volume > 1.5× average
  - price_volume_diverge: price and OBV moving in opposite directions (20-bar window)
  - relative_strength   : recent 5-day avg volume vs prior 5-day avg

All thresholds are named constants explained below.
"""

import logging
from dataclasses import dataclass
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# Volume ratio above this → flag as a spike (3× average is a meaningful outlier)
VOLUME_SPIKE_MULTIPLIER = 3.0

# Breakout volume confirmation: ratio must be ≥ this to count as real breakout
# 1.5× average ensures the breakout has participation, not just price drift
BREAKOUT_VOLUME_MIN_RATIO = 1.5

# How many bars to look back when measuring OBV trend direction
OBV_TREND_PERIOD = 10

# Breakout detection lookback: price at N-day high counts as a breakout attempt
BREAKOUT_LOOKBACK_BARS = 20

# Divergence detection window: compare price and OBV N bars apart
DIVERGENCE_LOOKBACK = 20

# % price change needed to call a "new high" or "new low" for divergence
DIVERGENCE_MIN_MOVE_PCT = 3.0

# Relative volume strength bands (5-day recent vs prior 5-day)
STRENGTH_STRONG_RATIO = 1.20   # 20%+ increase in avg volume = STRONG
STRENGTH_WEAK_RATIO   = 0.80   # 20%+ decrease in avg volume = WEAK


@dataclass
class VolumeProfile:
    volume_ratio_20: float         # vol / 20-day average
    volume_ratio_50: float         # vol / 50-day average
    volume_trend: str              # "RISING" | "FALLING" | "FLAT"
    volume_spike: bool             # today > 3× avg
    breakout_volume_confirmed: bool
    price_volume_divergence: str   # "BEARISH_DIVERGENCE" | "BULLISH_DIVERGENCE" | "NONE"
    obv_trend: str                 # "RISING" | "FALLING" | "FLAT"
    relative_strength: str         # "STRONG" | "NORMAL" | "WEAK"


class VolumeAnalysisEngine:
    """
    Computes enhanced volume metrics from a price DataFrame.

    Input df must contain: close, volume
    If pre-computed indicators are present (volume_sma_20, obv), they are used
    directly — otherwise they are computed here.
    """

    def analyze(self, df: pd.DataFrame) -> VolumeProfile:
        if len(df) < 30:
            return self._empty()

        vol    = df["volume"].values.astype(float)
        closes = df["close"].values.astype(float)
        n      = len(df)

        # ── Volume averages ───────────────────────────────────────────────────
        if "volume_sma_20" in df.columns:
            vol_sma_20 = float(df["volume_sma_20"].iloc[-1])
        else:
            vol_sma_20 = float(pd.Series(vol[-20:]).mean()) if n >= 20 else float(vol.mean())

        vol_sma_50 = float(pd.Series(vol[max(0, n - 50):]).mean()) if n >= 50 else float(vol.mean())

        current_vol = float(vol[-1])
        ratio_20    = current_vol / max(vol_sma_20, 1)
        ratio_50    = current_vol / max(vol_sma_50, 1)

        # ── OBV ───────────────────────────────────────────────────────────────
        if "obv" in df.columns:
            obv_series = df["obv"].values.astype(float)
        else:
            obv_series = self._compute_obv(vol, closes)

        obv_trend  = self._trend_direction(obv_series[-OBV_TREND_PERIOD - 1:], pct_threshold=5.0)
        vol_trend  = self._trend_direction(vol[-OBV_TREND_PERIOD:], pct_threshold=2.0)

        # ── Spike & breakout ──────────────────────────────────────────────────
        volume_spike = ratio_20 >= VOLUME_SPIKE_MULTIPLIER

        price_high_n = float(pd.Series(closes[-BREAKOUT_LOOKBACK_BARS:]).max())
        at_range_high = closes[-1] >= price_high_n * 0.995  # within 0.5% of range high
        breakout_confirmed = at_range_high and ratio_20 >= BREAKOUT_VOLUME_MIN_RATIO

        # ── Divergence ────────────────────────────────────────────────────────
        divergence = self._detect_divergence(closes, obv_series)

        # ── Recent vs prior volume strength ───────────────────────────────────
        relative_strength = "NORMAL"
        if n >= 10:
            recent_5 = float(pd.Series(vol[-5:]).mean())
            prior_5  = float(pd.Series(vol[-10:-5]).mean())
            if prior_5 > 0:
                ratio = recent_5 / prior_5
                if ratio >= STRENGTH_STRONG_RATIO:
                    relative_strength = "STRONG"
                elif ratio <= STRENGTH_WEAK_RATIO:
                    relative_strength = "WEAK"

        return VolumeProfile(
            volume_ratio_20=round(ratio_20, 3),
            volume_ratio_50=round(ratio_50, 3),
            volume_trend=vol_trend,
            volume_spike=volume_spike,
            breakout_volume_confirmed=breakout_confirmed,
            price_volume_divergence=divergence,
            obv_trend=obv_trend,
            relative_strength=relative_strength,
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _compute_obv(self, vol: "np.ndarray", closes: "np.ndarray") -> "np.ndarray":
        import numpy as np
        obv  = [0.0]
        for i in range(1, len(closes)):
            if closes[i] > closes[i - 1]:
                obv.append(obv[-1] + vol[i])
            elif closes[i] < closes[i - 1]:
                obv.append(obv[-1] - vol[i])
            else:
                obv.append(obv[-1])
        return pd.Series(obv).values

    def _trend_direction(self, series: "np.ndarray", pct_threshold: float = 5.0) -> str:
        """
        Simple trend: compare last value to first value in the window.
        Returns RISING / FALLING / FLAT based on pct_threshold.
        """
        if len(series) < 2:
            return "FLAT"
        first = float(series[0])
        last  = float(series[-1])
        if first == 0:
            return "FLAT"
        change_pct = (last - first) / abs(first) * 100
        if change_pct > pct_threshold:
            return "RISING"
        elif change_pct < -pct_threshold:
            return "FALLING"
        return "FLAT"

    def _detect_divergence(self, closes: "np.ndarray", obv: "np.ndarray") -> str:
        """
        Bearish divergence: price at new high but OBV lower than N bars ago.
        Bullish divergence: price at new low but OBV higher than N bars ago.
        Both require a minimum move of DIVERGENCE_MIN_MOVE_PCT% to filter noise.
        """
        n = DIVERGENCE_LOOKBACK
        if len(closes) < n + 2 or len(obv) < n + 2:
            return "NONE"

        price_now  = float(closes[-1])
        price_past = float(closes[-n])
        obv_now    = float(obv[-1])
        obv_past   = float(obv[-n])

        price_chg_pct = (price_now - price_past) / max(abs(price_past), 1e-9) * 100

        price_up = price_chg_pct >  DIVERGENCE_MIN_MOVE_PCT
        price_dn = price_chg_pct < -DIVERGENCE_MIN_MOVE_PCT

        obv_up = obv_now > obv_past * 1.02   # OBV grew by at least 2%
        obv_dn = obv_now < obv_past * 0.98   # OBV fell by at least 2%

        if price_up and obv_dn:
            return "BEARISH_DIVERGENCE"    # price rising but money not participating
        if price_dn and obv_up:
            return "BULLISH_DIVERGENCE"    # price falling but accumulation happening
        return "NONE"

    def _empty(self) -> VolumeProfile:
        return VolumeProfile(
            volume_ratio_20=1.0, volume_ratio_50=1.0,
            volume_trend="FLAT", volume_spike=False,
            breakout_volume_confirmed=False,
            price_volume_divergence="NONE",
            obv_trend="FLAT", relative_strength="NORMAL",
        )
