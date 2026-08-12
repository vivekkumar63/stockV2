import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class Chartink52WeekLowBounce(BaseStrategy):
    """Chartink: 52-Week Low Bounce — price near 52-week low with RSI oversold + reversal signs."""
    name = "52-Week Low Bounce"
    description = "Price within 5% of 52-week low + RSI oversold + green candle + volume spike"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY
    min_holding_days = 3
    max_holding_days = 15

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 50:
            return Signal("NONE")

        r = df.iloc[-1]
        c = float(r["close"])
        o = float(r["open"])
        rsi = r["rsi_14"]
        vol_ratio = r["volume_ratio"]
        sma20 = r["sma_20"]

        if any(pd.isna(x) for x in [rsi, vol_ratio, sma20]):
            return Signal("NONE")

        low_52w = float(df["low"].min())
        high_52w = float(df["high"].max())

        met, failed = [], []

        pct_above_low = (c - low_52w) / low_52w * 100
        if pct_above_low <= 5.0:
            met.append(f"Within {pct_above_low:.1f}% of 52-week low {low_52w:.2f}")
        else:
            failed.append(f"{pct_above_low:.1f}% above 52-week low {low_52w:.2f}")

        if rsi < 40:
            met.append(f"RSI {rsi:.1f} oversold (< 40)")
        else:
            failed.append(f"RSI {rsi:.1f} not oversold")

        if c > o:
            met.append(f"Green reversal candle +{(c/o - 1)*100:.2f}%")
        else:
            failed.append("Red candle (no reversal yet)")

        if vol_ratio > 1.2:
            met.append(f"Volume surge {vol_ratio:.2f}x (buyers entering)")
        else:
            failed.append(f"Low volume {vol_ratio:.2f}x")

        prev_low = float(df["low"].iloc[-2])
        if float(df["low"].iloc[-1]) > prev_low:
            met.append(f"Higher low vs yesterday {prev_low:.2f} (floor holding)")
        else:
            failed.append(f"New low formed (still falling)")

        if len(met) < 3:
            return Signal("NONE", conditions_met=met, conditions_failed=failed)

        range_pct = (high_52w - low_52w) / low_52w * 100
        confidence = min(0.78, 0.50 + (5 - pct_above_low) / 30 + (len(met) - 3) * 0.05)

        return Signal(
            signal_type="BUY",
            confidence=round(confidence, 4),
            risk_score=0.60,
            expected_upside_pct=8.0,
            stop_loss_pct=5.0,
            target_pct=10.0,
            holding_days=10,
            conditions_met=met,
            conditions_failed=failed,
        )

    def get_required_indicators(self) -> list[str]:
        return ["rsi_14", "volume_ratio", "sma_20"]
