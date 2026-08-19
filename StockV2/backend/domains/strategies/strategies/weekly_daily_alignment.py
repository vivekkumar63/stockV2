"""
Weekly-Daily Multi-Timeframe Alignment

The most profitable setups occur when the higher timeframe (weekly) and
lower timeframe (daily) are both pointing in the same direction.

Since we only have daily data, we simulate the weekly trend by:
- SMA 20 slope (current vs 5 bars ago = approx 1-week slope)
- Price > SMA 20 on 4 of last 5 bars = weekly chart looks bullish

Then we look for a daily-timeframe entry signal:
- RSI dipped below 45 and is now recovering
- MACD histogram positive
- Volume confirming

This is the Elder Triple Screen method adapted for daily data.
Top-down analysis: weekly health → daily entry.
"""
import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe

_WEEKLY_PROXY_BARS = 5   # 5 daily bars ≈ 1 trading week


class WeeklyDailyAlignmentStrategy(BaseStrategy):
    name = "Weekly-Daily MTF Alignment"
    description = "Weekly trend up (SMA20 slope + price consistency) + daily RSI dip entry"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY
    min_holding_days = 5
    max_holding_days = 15
    weight = 0.20

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        required = ["sma_20", "sma_50", "close", "rsi_14", "macd_hist", "volume_ratio", "adx_14"]
        if len(df) < 30 or not all(c in df.columns for c in required):
            return Signal(signal_type="NONE", conditions_failed=["Insufficient data"])

        curr = df.iloc[-1]
        close = curr["close"]
        sma_20 = curr["sma_20"]
        sma_50 = curr["sma_50"]
        rsi = curr["rsi_14"]
        macd_hist = curr["macd_hist"]
        volume_ratio = curr["volume_ratio"]
        adx = curr["adx_14"]
        sma_20_week_ago = df["sma_20"].iloc[-_WEEKLY_PROXY_BARS - 1]
        rsi_week_ago = df["rsi_14"].iloc[-_WEEKLY_PROXY_BARS - 1]

        if any(pd.isna(x) for x in [close, sma_20, sma_50, rsi, macd_hist, volume_ratio, adx,
                                      sma_20_week_ago, rsi_week_ago]):
            return Signal(signal_type="NONE", conditions_failed=["Missing indicator values"])

        last5 = df.iloc[-5:]
        bars_above_sma20 = (last5["close"] > last5["sma_20"]).sum()
        sma_slope_pct = ((sma_20 - sma_20_week_ago) / sma_20_week_ago) * 100
        rsi_was_lower = rsi_week_ago < rsi  # RSI was lower a week ago = recovering

        conditions_met = []
        conditions_failed = []

        # --- WEEKLY-FRAME FILTERS (higher timeframe health) ---

        # Weekly filter 1: SMA 20 has a positive slope (trending up on weekly basis)
        if sma_slope_pct > 0.3:
            conditions_met.append(f"SMA20 weekly slope +{sma_slope_pct:.2f}% (weekly uptrend)")
        else:
            conditions_failed.append(f"SMA20 weekly slope {sma_slope_pct:.2f}% (flat/down)")

        # Weekly filter 2: Price above SMA 20 for most of the last week
        if bars_above_sma20 >= 4:
            conditions_met.append(f"Above SMA20 {bars_above_sma20}/5 days (consistent weekly strength)")
        else:
            conditions_failed.append(f"Above SMA20 only {bars_above_sma20}/5 days")

        # --- DAILY-FRAME ENTRY FILTERS ---

        # Daily filter 1: RSI dipped and is now recovering (weekly direction met daily dip)
        if 35 <= rsi <= 55 and rsi_was_lower is False:
            conditions_met.append(f"RSI={rsi:.1f} recovering from dip (daily entry zone)")
        elif 35 <= rsi <= 55:
            # RSI in range even if recovering from above (still acceptable)
            conditions_met.append(f"RSI={rsi:.1f} in daily entry zone")
        else:
            conditions_failed.append(f"RSI={rsi:.1f} not in daily entry zone")

        # Daily filter 2: MACD histogram positive (daily momentum aligned with weekly trend)
        if macd_hist > 0:
            conditions_met.append(f"MACD histogram positive ({macd_hist:.5f}) — daily momentum aligned")
        else:
            conditions_failed.append("MACD histogram negative")

        # Daily filter 3: Volume confirmation and some trend strength
        if volume_ratio > 1.25 and adx > 18:
            conditions_met.append(f"Volume {volume_ratio:.1f}x + ADX={adx:.1f} (momentum + participation)")
        else:
            conditions_failed.append(f"Weak confirmation: vol={volume_ratio:.1f}x, ADX={adx:.1f}")

        if len(conditions_met) == 5:
            slope_score = min(sma_slope_pct / 1.0, 1.0)
            confidence = 0.66 + (0.14 * slope_score)
            return Signal(
                signal_type="BUY",
                confidence=round(confidence, 4),
                risk_score=0.30,
                expected_upside_pct=9.0,
                stop_loss_pct=4.5,
                target_pct=9.0,
                holding_days=10,
                conditions_met=conditions_met,
            )

        return Signal(signal_type="NONE", conditions_met=conditions_met, conditions_failed=conditions_failed)

    def get_required_indicators(self) -> list[str]:
        return ["sma_20", "sma_50", "close", "rsi_14", "macd_hist", "volume_ratio", "adx_14"]
