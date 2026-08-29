import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe

_MIN_VOLUME_RATIO = 1.5


class BBSqueezeStrategy(BaseStrategy):
    name = "Bollinger Band Squeeze"
    description = "Buy when price breaks above upper BB with volume confirmation"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY
    weight = 0.15
    min_holding_days = 2
    max_holding_days = 10

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 1:
            return Signal("NONE")
        for col in ("close", "bb_upper", "volume_ratio"):
            if col not in df.columns:
                return Signal("NONE")
        row = df.iloc[-1]
        close = row["close"]
        bb_upper = row["bb_upper"]
        volume_ratio = row["volume_ratio"]
        if any(pd.isna(x) for x in [close, bb_upper, volume_ratio]):
            return Signal("NONE")
        if close > bb_upper and volume_ratio > _MIN_VOLUME_RATIO:
            confidence = min(1.0, 0.55 + (volume_ratio - _MIN_VOLUME_RATIO) / 5.0)
            return Signal(
                signal_type="BUY",
                confidence=round(confidence, 4),
                risk_score=0.55,
                stop_loss_pct=5.0,
                target_pct=10.0,
                holding_days=7,
                conditions_met=[
                    f"Price {close:.2f} broke above BB upper {bb_upper:.2f}",
                    f"Volume ratio {volume_ratio:.2f}x confirms breakout",
                ],
            )
        return Signal("NONE")

    def get_required_indicators(self) -> list[str]:
        return ["bb_upper", "volume_ratio"]
