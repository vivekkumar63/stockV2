import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class VolatilityBreakoutStrategy(BaseStrategy):
    name = "Volatility Breakout"
    description = "Buy when price breaks above 20-day high with volume confirmation (>1.5x)"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY
    weight = 0.15
    min_holding_days = 3
    max_holding_days = 7

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 21 or "volume_ratio" not in df.columns:
            return Signal("NONE")
        row = df.iloc[-1]
        volume_ratio = row["volume_ratio"]
        close = row["close"]
        prev_close = df["close"].iloc[-2]
        high_20 = df["close"].iloc[-21:-1].max()
        if any(pd.isna(x) for x in [volume_ratio, close, high_20]):
            return Signal("NONE")
        if prev_close <= high_20 and close > high_20 and volume_ratio > 1.5:
            return Signal(
                signal_type="BUY",
                confidence=0.62,
                risk_score=0.50,
                expected_upside_pct=7.0,
                stop_loss_pct=5.0,
                target_pct=8.0,
                holding_days=5,
                conditions_met=[
                    f"Close {close:.2f} broke above 20d high {high_20:.2f}",
                    f"Volume ratio {volume_ratio:.2f}x (> 1.5x)",
                ],
            )
        return Signal("NONE")

    def get_required_indicators(self) -> list[str]:
        return ["volume_ratio"]
