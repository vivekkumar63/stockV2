import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class BBSqueezeStrategy(BaseStrategy):
    name = "Bollinger Band Squeeze"
    description = "Buy on close breakout above BB upper band with elevated volume (>1.5x)"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY
    weight = 0.15
    min_holding_days = 5
    max_holding_days = 20

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if df.empty or "bb_upper" not in df.columns:
            return Signal("NONE")
        row = df.iloc[-1]
        close, bb_upper, volume_ratio = row["close"], row["bb_upper"], row["volume_ratio"]
        if any(pd.isna(x) for x in [close, bb_upper, volume_ratio]):
            return Signal("NONE")
        if close > bb_upper and volume_ratio > 1.5:
            confidence = min(1.0, 0.55 + (volume_ratio - 1.5) * 0.08)
            return Signal(
                signal_type="BUY",
                confidence=round(confidence, 4),
                risk_score=0.50,
                expected_upside_pct=8.0,
                stop_loss_pct=5.0,
                target_pct=10.0,
                holding_days=8,
                conditions_met=[
                    f"Close {close:.2f} > BB Upper {bb_upper:.2f}",
                    f"Volume ratio {volume_ratio:.2f}x (> 1.5x)",
                ],
            )
        return Signal("NONE")

    def get_required_indicators(self) -> list[str]:
        return ["bb_upper", "volume_ratio"]
