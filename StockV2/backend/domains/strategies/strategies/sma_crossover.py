import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class SMACrossoverStrategy(BaseStrategy):
    name = "SMA Crossover (20/50)"
    description = "Golden Cross (SMA20 crosses above SMA50) buy; Death Cross sell"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY
    min_holding_days = 20
    max_holding_days = 60

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 2 or "sma_20" not in df.columns or "sma_50" not in df.columns:
            return Signal("NONE")
        curr_20, prev_20 = df["sma_20"].iloc[-1], df["sma_20"].iloc[-2]
        curr_50, prev_50 = df["sma_50"].iloc[-1], df["sma_50"].iloc[-2]
        if any(pd.isna(x) for x in [curr_20, prev_20, curr_50, prev_50]):
            return Signal("NONE")
        if prev_20 <= prev_50 and curr_20 > curr_50:
            return Signal(
                signal_type="BUY",
                confidence=0.70,
                risk_score=0.35,
                expected_upside_pct=20.0,
                stop_loss_pct=8.0,
                target_pct=20.0,
                holding_days=40,
                conditions_met=["Golden Cross: SMA20 crossed above SMA50"],
            )
        if prev_20 >= prev_50 and curr_20 < curr_50:
            return Signal(
                signal_type="SELL",
                confidence=0.70,
                risk_score=0.65,
                expected_upside_pct=0.0,
                stop_loss_pct=0.0,
                target_pct=0.0,
                holding_days=0,
                conditions_met=["Death Cross: SMA20 crossed below SMA50"],
            )
        return Signal("NONE")

    def get_required_indicators(self) -> list[str]:
        return ["sma_20", "sma_50"]
