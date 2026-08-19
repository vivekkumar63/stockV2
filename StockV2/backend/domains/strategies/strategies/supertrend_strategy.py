import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class SuperTrendStrategy(BaseStrategy):
    name = "SuperTrend"
    description = "Buy when SuperTrend flips from bearish to bullish; sell on reverse"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY
    weight = 0.15
    min_holding_days = 3
    max_holding_days = 20

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 2 or "supertrend_direction" not in df.columns:
            return Signal("NONE")
        curr = df["supertrend_direction"].iloc[-1]
        prev = df["supertrend_direction"].iloc[-2]
        if any(pd.isna(x) for x in [curr, prev]):
            return Signal("NONE")
        if prev < 0 and curr > 0:
            return Signal(
                signal_type="BUY",
                confidence=0.75,
                risk_score=0.40,
                stop_loss_pct=5.0,
                target_pct=12.0,
                holding_days=12,
                conditions_met=["SuperTrend flipped bullish"],
            )
        if prev > 0 and curr < 0:
            return Signal(
                signal_type="SELL",
                confidence=0.75,
                conditions_met=["SuperTrend flipped bearish"],
            )
        return Signal("NONE")

    def get_required_indicators(self) -> list[str]:
        return ["supertrend_direction"]
