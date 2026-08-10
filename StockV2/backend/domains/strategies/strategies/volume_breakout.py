import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class VolumeBreakoutStrategy(BaseStrategy):
    name = "Volume Breakout"
    description = "Buy on strong volume surge (>2.5x average) with positive price action"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY
    weight = 0.15
    min_holding_days = 3
    max_holding_days = 10

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 2 or "volume_ratio" not in df.columns:
            return Signal("NONE")
        row = df.iloc[-1]
        volume_ratio = row["volume_ratio"]
        close = row["close"]
        prev_close = df["close"].iloc[-2]
        if any(pd.isna(x) for x in [volume_ratio, close, prev_close]):
            return Signal("NONE")
        if volume_ratio > 2.5 and close > prev_close:
            confidence = min(1.0, 0.50 + (volume_ratio - 2.5) / 5.0)
            return Signal(
                signal_type="BUY",
                confidence=round(confidence, 4),
                risk_score=0.50,
                expected_upside_pct=6.0,
                stop_loss_pct=5.0,
                target_pct=8.0,
                holding_days=5,
                conditions_met=[
                    f"Volume ratio {volume_ratio:.2f}x (> 2.5x average)",
                    f"Price up: {prev_close:.2f} → {close:.2f}",
                ],
            )
        return Signal("NONE")

    def get_required_indicators(self) -> list[str]:
        return ["volume_ratio"]
