import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class ChartinkNR7Uptrend(BaseStrategy):
    """Chartink: NR7 Uptrend — smallest daily range in 7 days inside a SMA10>SMA50 uptrend."""
    name = "NR7 Uptrend"
    description = "Narrowest trading range of last 7 days + SMA10>SMA50 trend + volume filter"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY
    min_holding_days = 2
    max_holding_days = 8

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 52:
            return Signal("NONE")

        high = df["high"]
        low = df["low"]
        close = df["close"]
        sma10 = df["sma_10"].iloc[-1]
        sma50 = df["sma_50"].iloc[-1]
        v = float(df["volume"].iloc[-1])

        if any(pd.isna(x) for x in [sma10, sma50]):
            return Signal("NONE")

        today_range = float(high.iloc[-1] - low.iloc[-1])
        ranges_last7 = [float(high.iloc[-i] - low.iloc[-i]) for i in range(1, 8)]

        met, failed = [], []

        if today_range == min(ranges_last7):
            met.append(f"NR7: today's range {today_range:.2f} is smallest of last 7 days")
        else:
            min_r = min(ranges_last7)
            failed.append(f"Not NR7 (today {today_range:.2f}, min {min_r:.2f})")

        if sma10 > sma50:
            met.append(f"Uptrend: SMA10 {sma10:.1f} > SMA50 {sma50:.1f}")
        else:
            failed.append(f"Downtrend: SMA10 < SMA50")

        if v >= 50000:
            met.append(f"Volume {v:,.0f} ≥ 50,000 (liquid)")
        else:
            failed.append(f"Low volume {v:,.0f} < 50,000")

        if len(met) < 3:
            return Signal("NONE", conditions_met=met, conditions_failed=failed)

        compression = 1 - (today_range / max(ranges_last7))
        confidence = min(0.82, 0.58 + compression * 0.25)

        return Signal(
            signal_type="BUY",
            confidence=round(confidence, 4),
            risk_score=0.35,
            expected_upside_pct=6.0,
            stop_loss_pct=3.0,
            target_pct=6.0,
            holding_days=5,
            conditions_met=met,
            conditions_failed=failed,
        )

    def get_required_indicators(self) -> list[str]:
        return ["sma_10", "sma_50"]
