import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe

_LOOKBACK = 20
_MIN_ROWS = _LOOKBACK + 1
_MIN_VOLUME_RATIO = 1.5


class VolatilityBreakoutStrategy(BaseStrategy):
    name = "Volatility Breakout"
    description = "Buy when price breaks above the 20-day high with volume confirmation"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY
    weight = 0.15
    min_holding_days = 2
    max_holding_days = 10

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < _MIN_ROWS:
            return Signal("NONE")
        for col in ("close", "volume_ratio"):
            if col not in df.columns:
                return Signal("NONE")
        curr_close = df["close"].iloc[-1]
        volume_ratio = df["volume_ratio"].iloc[-1]
        if any(pd.isna(x) for x in [curr_close, volume_ratio]):
            return Signal("NONE")
        high_20 = df["close"].iloc[-(_LOOKBACK + 1):-1].max()
        if curr_close > high_20 and volume_ratio > _MIN_VOLUME_RATIO:
            confidence = min(1.0, 0.60 + (volume_ratio - _MIN_VOLUME_RATIO) / 5.0)
            return Signal(
                signal_type="BUY",
                confidence=round(confidence, 4),
                risk_score=0.50,
                stop_loss_pct=5.0,
                target_pct=10.0,
                holding_days=7,
                conditions_met=[
                    f"Price {curr_close:.2f} broke above 20d high {high_20:.2f}",
                    f"Volume ratio {volume_ratio:.2f}x confirms breakout",
                ],
            )
        return Signal("NONE")

    def get_required_indicators(self) -> list[str]:
        return ["volume_ratio"]
