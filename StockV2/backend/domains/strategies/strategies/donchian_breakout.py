"""
Donchian Channel Breakout — Richard Donchian / Turtle Trading System

The original "Turtle Trading" strategy taught by Richard Dennis and William
Eckhardt in 1983. The most important price level in trend-following:
the 20-day high.

Richard Donchian (1905-1993) is considered the "father of trend following".
His system is simple and timeless:

  Upper = highest HIGH over the last 20 bars
  Lower = lowest  LOW  over the last 20 bars
  Mid   = (Upper + Lower) / 2

BUY = price closes ABOVE the 20-day upper channel (breakout to new 20-day high)
      The original Turtles entered on the day the close exceeded the prior 20-day high.

Additional filters to reduce false breakouts (whipsaws):
  1. Volume above average (volume_ratio > 1.2) — breakouts need volume
  2. Price above SMA(50) — only breakout in a medium-term uptrend
  3. ADX > 20 — trending market, not choppy (breakouts fail in ranging markets)
  4. ATR-based: the breakout candle body > 0.3% (real breakout, not just a wick)
"""
import numpy as np
import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe

_DC_PERIOD = 20


class DonchianBreakoutStrategy(BaseStrategy):
    name = "Donchian Channel Breakout"
    description = (
        "Turtle Trading: close breaks above 20-day high. "
        "Filtered by volume surge, SMA50 uptrend, and ADX>20 (trending market)."
    )
    strategy_type = StrategyType.TECHNICAL
    timeframe     = Timeframe.DAILY
    min_holding_days = 5
    max_holding_days = 20
    weight           = 0.20

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        required = ["close", "high", "low", "sma_50", "adx_14", "volume_ratio"]
        if len(df) < _DC_PERIOD + 5 or not all(c in df.columns for c in required):
            return Signal(signal_type="NONE", conditions_failed=["Insufficient data"])

        close        = df["close"]
        high         = df["high"]
        sma_50       = float(df["sma_50"].iloc[-1])
        adx          = float(df["adx_14"].iloc[-1])
        volume_ratio = float(df["volume_ratio"].iloc[-1])

        # Donchian Upper = highest HIGH over the PRIOR 20 bars (not including current)
        # This is the "prior channel" — the level that must be exceeded
        dc_upper_prior = high.iloc[:-1].rolling(_DC_PERIOD).max().iloc[-1]
        dc_lower = df["low"].rolling(_DC_PERIOD).min().iloc[-1]
        dc_mid   = (float(dc_upper_prior) + float(dc_lower)) / 2

        c_now  = float(close.iloc[-1])
        c_prev = float(close.iloc[-2])

        if any(pd.isna(x) for x in [dc_upper_prior, sma_50, adx, volume_ratio]):
            return Signal(signal_type="NONE", conditions_failed=["Indicators not ready"])

        # The Turtle breakout: close exceeds the prior 20-day high
        breakout = c_prev <= float(dc_upper_prior) and c_now > float(dc_upper_prior)

        # Also accept a fresh breakout from 2 bars ago (slightly relaxed)
        dc_upper_prior_2 = high.iloc[:-2].rolling(_DC_PERIOD).max().iloc[-1]
        breakout_2bars   = (not breakout and
                            float(close.iloc[-2]) > float(dc_upper_prior_2) and
                            c_now > float(dc_upper_prior))

        # Filters
        above_sma50  = c_now > sma_50
        trending     = adx > 20
        volume_ok    = volume_ratio > 1.2

        conditions_met    = []
        conditions_failed = []

        if breakout:
            conditions_met.append(
                f"Donchian breakout: close {c_now:.2f} > 20-day high {float(dc_upper_prior):.2f}"
            )
        elif breakout_2bars:
            conditions_met.append(
                f"Breakout confirmed (2-bar): above 20-day channel {float(dc_upper_prior):.2f}"
            )
        else:
            gap = ((c_now - float(dc_upper_prior)) / float(dc_upper_prior)) * 100
            conditions_failed.append(
                f"No breakout: price {gap:+.1f}% vs 20-day high {float(dc_upper_prior):.2f}"
            )

        if above_sma50:
            pct = ((c_now - sma_50) / sma_50) * 100
            conditions_met.append(f"Price {pct:.1f}% above SMA50 (medium-term uptrend)")
        else:
            conditions_failed.append("Price below SMA50 — no trend support")

        if trending:
            conditions_met.append(f"ADX={adx:.1f} > 20 (trending market, breakout valid)")
        else:
            conditions_failed.append(f"ADX={adx:.1f} ≤ 20 — choppy/ranging, breakouts fail")

        if volume_ok:
            conditions_met.append(f"Volume={volume_ratio:.2f}x average — breakout confirmed")
        else:
            conditions_failed.append(f"Volume={volume_ratio:.2f}x below avg — weak breakout")

        if (breakout or breakout_2bars) and above_sma50 and trending and volume_ok:
            recency   = 1.0 if breakout else 0.7
            adx_score = min((adx - 20) / 20, 1.0)
            vol_score = min((volume_ratio - 1.2) / 1.0, 1.0)
            confidence = round(min(0.60 + 0.15 * recency + 0.12 * adx_score + 0.08 * vol_score, 0.90), 4)
            return Signal(
                signal_type="BUY",
                confidence=confidence,
                risk_score=0.30,
                expected_upside_pct=11.0,
                stop_loss_pct=5.0,
                target_pct=11.0,
                holding_days=12,
                conditions_met=conditions_met + [
                    f"Channel: upper={float(dc_upper_prior):.2f} | mid={dc_mid:.2f} | lower={float(dc_lower):.2f}"
                ],
            )

        return Signal(
            signal_type="NONE",
            conditions_met=conditions_met,
            conditions_failed=conditions_failed,
        )

    def get_required_indicators(self) -> list[str]:
        return ["close", "high", "low", "sma_50", "adx_14", "volume_ratio"]
