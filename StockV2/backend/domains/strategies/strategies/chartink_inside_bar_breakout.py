import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class ChartinkInsideBarBreakout(BaseStrategy):
    """Chartink: Inside Bar — today's range inside previous day's range (NR4 variant), compression setup."""
    name = "Inside Bar Compression"
    description = "Today high < prev high + today low > prev low (inside bar) in uptrend = coiled spring"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY
    min_holding_days = 1
    max_holding_days = 5

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 22:
            return Signal("NONE")

        r = df.iloc[-1]
        r_prev = df.iloc[-2]
        r_prev2 = df.iloc[-3]

        h0 = float(r["high"])
        lo0 = float(r["low"])
        c0 = float(r["close"])
        h1 = float(r_prev["high"])
        lo1 = float(r_prev["low"])
        sma20 = r["sma_20"]
        sma50 = r["sma_50"]
        rsi = r["rsi_14"]
        atr = r["atr_14"]

        if any(pd.isna(x) for x in [sma20, sma50, rsi, atr]):
            return Signal("NONE")

        met, failed = [], []

        if h0 < h1 and lo0 > lo1:
            compression = 1 - ((h0 - lo0) / (h1 - lo1))
            met.append(f"Inside bar: range {h0 - lo0:.2f} within prev {h1 - lo1:.2f} ({compression*100:.0f}% compressed)")
        else:
            failed.append(f"Not an inside bar (H:{h0:.1f} vs prev H:{h1:.1f}, L:{lo0:.1f} vs prev L:{lo1:.1f})")

        if sma20 > sma50:
            met.append(f"Uptrend: SMA20 {sma20:.1f} > SMA50 {sma50:.1f}")
        else:
            failed.append(f"Not in uptrend (SMA20 < SMA50)")

        if c0 > sma20:
            met.append(f"Close {c0:.1f} above SMA20 {sma20:.1f}")
        else:
            failed.append(f"Close {c0:.1f} below SMA20 {sma20:.1f}")

        if 40 < rsi < 70:
            met.append(f"RSI {rsi:.1f} in healthy range (40-70)")
        else:
            failed.append(f"RSI {rsi:.1f} outside 40-70 range")

        prev_range = h1 - lo1
        avg_range = float(df["high"].tail(10).values - df["low"].tail(10).values) if False else None
        if prev_range > atr * 0.8:
            met.append(f"Prev candle had meaningful range {prev_range:.2f}")
        else:
            failed.append(f"Prev range {prev_range:.2f} too small vs ATR {atr:.2f}")

        if len(met) < 3:
            return Signal("NONE", conditions_met=met, conditions_failed=failed)

        if h1 > 0:
            compression_ratio = 1 - ((h0 - lo0) / (h1 - lo1))
        else:
            compression_ratio = 0
        confidence = min(0.80, 0.52 + compression_ratio * 0.20 + (len(met) - 3) * 0.04)

        return Signal(
            signal_type="BUY",
            confidence=round(confidence, 4),
            risk_score=0.40,
            expected_upside_pct=5.0,
            stop_loss_pct=2.5,
            target_pct=5.0,
            holding_days=3,
            conditions_met=met,
            conditions_failed=failed,
        )

    def get_required_indicators(self) -> list[str]:
        return ["sma_20", "sma_50", "rsi_14", "atr_14"]
