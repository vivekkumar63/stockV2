import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class ChartinkShortTermBreakout(BaseStrategy):
    """Chartink: Short Term Breakouts — price breaking 4-month high with volume surge and green candle."""
    name = "Chartink Short Term Breakout"
    description = "5-day close > 1.05x 120-day high + above-average volume + green candle"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY
    min_holding_days = 3
    max_holding_days = 15

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 30:
            return Signal("NONE")

        close = df["close"]
        volume = df["volume"]
        c = close.iloc[-1]
        c_prev = close.iloc[-2]
        v = float(volume.iloc[-1])

        lookback = min(120, len(df) - 1)
        max_5d = close.iloc[-5:].max()
        max_120d = close.iloc[-lookback - 1:-1].max()
        vol_sma5 = float(volume.iloc[-6:-1].mean()) if len(df) >= 6 else float("nan")

        met, failed = [], []

        if not pd.isna(max_120d) and max_120d > 0 and max_5d > max_120d * 1.05:
            met.append(f"5d high {max_5d:.1f} broke {lookback}d ceiling {max_120d:.1f} (+{(max_5d/max_120d-1)*100:.1f}%)")
        else:
            failed.append(f"No multi-month breakout ({max_5d:.1f} vs required {max_120d*1.05:.1f})")

        if not pd.isna(vol_sma5) and vol_sma5 > 0 and v > vol_sma5:
            met.append(f"Volume {v:,.0f} > 5d avg {vol_sma5:,.0f}")
        else:
            failed.append("Volume below 5-day average")

        if c > c_prev:
            met.append(f"Green candle +{(c/c_prev - 1)*100:.2f}%")
        else:
            failed.append(f"Red candle ({(c/c_prev - 1)*100:.2f}%)")

        if len(met) < 3:
            return Signal("NONE", conditions_met=met, conditions_failed=failed)

        pct_above = (max_5d / max_120d - 1) * 100
        confidence = min(0.92, 0.62 + pct_above / 25)

        return Signal(
            signal_type="BUY",
            confidence=round(confidence, 4),
            risk_score=0.45,
            expected_upside_pct=12.0,
            stop_loss_pct=6.0,
            target_pct=12.0,
            holding_days=10,
            conditions_met=met,
            conditions_failed=failed,
        )

    def get_required_indicators(self) -> list[str]:
        return ["close", "volume"]
