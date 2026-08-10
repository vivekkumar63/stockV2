import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class SuperTrendStrategy(BaseStrategy):
    name = "SuperTrend"
    description = "Buy when SuperTrend flips bullish (direction -1→1), sell on bearish flip"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY
    min_holding_days = 15
    max_holding_days = 45

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 2 or "supertrend_direction" not in df.columns:
            return Signal("NONE")
        curr_dir = df["supertrend_direction"].iloc[-1]
        prev_dir = df["supertrend_direction"].iloc[-2]
        if pd.isna(curr_dir) or pd.isna(prev_dir):
            return Signal("NONE")
        if prev_dir == -1.0 and curr_dir == 1.0:
            return Signal(
                signal_type="BUY",
                confidence=0.72,
                risk_score=0.40,
                expected_upside_pct=15.0,
                stop_loss_pct=7.0,
                target_pct=18.0,
                holding_days=25,
                conditions_met=["SuperTrend flipped bullish (direction: -1 → 1)"],
            )
        if prev_dir == 1.0 and curr_dir == -1.0:
            return Signal(
                signal_type="SELL",
                confidence=0.72,
                risk_score=0.60,
                expected_upside_pct=0.0,
                stop_loss_pct=0.0,
                target_pct=0.0,
                holding_days=0,
                conditions_met=["SuperTrend flipped bearish (direction: 1 → -1)"],
            )
        return Signal("NONE")

    def get_required_indicators(self) -> list[str]:
        return ["supertrend_direction"]
