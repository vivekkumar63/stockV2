import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class ChartinkNR7Bearish(BaseStrategy):
    """Chartink: NR7 Bearish — narrowest range in 7 days inside a downtrend, breakdown setup."""
    name = "NR7 Bearish Breakdown"
    description = "Narrowest range of 7 days + SMA20<SMA50 downtrend + RSI<50 = breakdown setup"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY
    min_holding_days = 2
    max_holding_days = 7

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 52:
            return Signal("NONE")

        high = df["high"]
        low = df["low"]
        c = float(df["close"].iloc[-1])
        sma20 = df["sma_20"].iloc[-1]
        sma50 = df["sma_50"].iloc[-1]
        rsi = df["rsi_14"].iloc[-1]
        v = float(df["volume"].iloc[-1])

        if any(pd.isna(x) for x in [sma20, sma50, rsi]):
            return Signal("NONE")

        today_range = float(high.iloc[-1] - low.iloc[-1])
        ranges_last7 = [float(high.iloc[-i] - low.iloc[-i]) for i in range(1, 8)]

        met, failed = [], []

        if today_range == min(ranges_last7):
            met.append(f"NR7: range {today_range:.2f} is smallest of last 7 days")
        else:
            failed.append(f"Not NR7 (range {today_range:.2f}, min {min(ranges_last7):.2f})")

        if sma20 < sma50:
            met.append(f"Downtrend: SMA20 {sma20:.1f} < SMA50 {sma50:.1f}")
        else:
            failed.append(f"Not in downtrend (SMA20 > SMA50)")

        if rsi < 50:
            met.append(f"RSI {rsi:.1f} < 50 (bearish momentum)")
        else:
            failed.append(f"RSI {rsi:.1f} ≥ 50")

        if c < sma20:
            met.append(f"Close {c:.1f} below SMA20 {sma20:.1f}")
        else:
            failed.append(f"Close {c:.1f} above SMA20")

        if v >= 50000:
            met.append(f"Volume {v:,.0f} ≥ 50,000")
        else:
            failed.append(f"Low volume {v:,.0f}")

        if len(met) < 4:
            return Signal("NONE", conditions_met=met, conditions_failed=failed)

        compression = 1 - (today_range / max(ranges_last7))
        confidence = min(0.82, 0.55 + compression * 0.25 + (50 - rsi) / 100)

        return Signal(
            signal_type="SELL",
            confidence=round(confidence, 4),
            risk_score=0.55,
            expected_upside_pct=0.0,
            stop_loss_pct=0.0,
            target_pct=0.0,
            holding_days=0,
            conditions_met=met,
            conditions_failed=failed,
        )

    def get_required_indicators(self) -> list[str]:
        return ["sma_20", "sma_50", "rsi_14"]
