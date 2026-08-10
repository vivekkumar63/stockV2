import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class EMACrossoverStrategy(BaseStrategy):
    name = "EMA Crossover (9/21)"
    description = "Buy when EMA 9 crosses above EMA 21, sell when it crosses below"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY
    min_holding_days = 5
    max_holding_days = 20

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 2 or "ema_9" not in df.columns or "ema_21" not in df.columns:
            return Signal("NONE")
        curr_9, prev_9 = df["ema_9"].iloc[-1], df["ema_9"].iloc[-2]
        curr_21, prev_21 = df["ema_21"].iloc[-1], df["ema_21"].iloc[-2]
        if any(pd.isna(x) for x in [curr_9, prev_9, curr_21, prev_21]):
            return Signal("NONE")
        if prev_9 <= prev_21 and curr_9 > curr_21:
            return Signal(
                signal_type="BUY",
                confidence=0.60,
                risk_score=0.45,
                expected_upside_pct=10.0,
                stop_loss_pct=6.0,
                target_pct=12.0,
                holding_days=12,
                conditions_met=[f"EMA9={curr_9:.2f} crossed above EMA21={curr_21:.2f}"],
            )
        if prev_9 >= prev_21 and curr_9 < curr_21:
            return Signal(
                signal_type="SELL",
                confidence=0.60,
                risk_score=0.55,
                expected_upside_pct=0.0,
                stop_loss_pct=0.0,
                target_pct=0.0,
                holding_days=0,
                conditions_met=[f"EMA9={curr_9:.2f} crossed below EMA21={curr_21:.2f}"],
            )
        return Signal("NONE")

    def get_required_indicators(self) -> list[str]:
        return ["ema_9", "ema_21"]
