import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class ChartinkNR4Pattern(BaseStrategy):
    """Chartink: NR4 — narrowest range of last 4 days, tighter coil than NR7."""
    name = "Chartink NR4 Range Compression"
    description = "Narrowest range of last 4 days + trend confirmation + volume filter"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY
    min_holding_days = 1
    max_holding_days = 5

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 22:
            return Signal("NONE")

        high = df["high"]
        low = df["low"]
        r = df.iloc[-1]
        c = float(r["close"])
        sma20 = r["sma_20"]
        rsi = r["rsi_14"]
        v = float(r["volume"])

        if any(pd.isna(x) for x in [sma20, rsi]):
            return Signal("NONE")

        ranges_last4 = [float(high.iloc[-i] - low.iloc[-i]) for i in range(1, 5)]
        today_range = ranges_last4[0]

        met, failed = [], []

        if today_range == min(ranges_last4):
            compression = 1 - (today_range / max(ranges_last4))
            met.append(f"NR4: range {today_range:.2f} is smallest of last 4 days ({compression*100:.0f}% compressed)")
        else:
            failed.append(f"Not NR4 (today {today_range:.2f}, min {min(ranges_last4):.2f})")

        if sma20 > 0 and c > sma20:
            met.append(f"Close {c:.1f} above SMA20 {sma20:.1f} (uptrend)")
        elif c < sma20:
            failed.append(f"Close {c:.1f} below SMA20 {sma20:.1f}")

        if 40 < rsi < 70:
            met.append(f"RSI {rsi:.1f} healthy (40-70, not extreme)")
        else:
            failed.append(f"RSI {rsi:.1f} extreme (outside 40-70)")

        if v >= 50000:
            met.append(f"Volume {v:,.0f} ≥ 50,000 (liquid)")
        else:
            failed.append(f"Low volume {v:,.0f}")

        if today_range < max(ranges_last4) * 0.5:
            met.append(f"Tight coil: NR4 range is <50% of 4-day max")
        else:
            failed.append(f"Moderate compression only")

        if len(met) < 3:
            return Signal("NONE", conditions_met=met, conditions_failed=failed)

        compression = 1 - (today_range / max(ranges_last4))
        confidence = min(0.80, 0.55 + compression * 0.20 + (len(met) - 3) * 0.04)

        return Signal(
            signal_type="BUY",
            confidence=round(confidence, 4),
            risk_score=0.40,
            expected_upside_pct=5.0,
            stop_loss_pct=2.0,
            target_pct=5.0,
            holding_days=3,
            conditions_met=met,
            conditions_failed=failed,
        )

    def get_required_indicators(self) -> list[str]:
        return ["sma_20", "rsi_14"]
