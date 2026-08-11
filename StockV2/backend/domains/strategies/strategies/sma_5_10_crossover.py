import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class SMA5_10CrossoverStrategy(BaseStrategy):
    name = "SMA Crossover (5/10)"
    description = "Fast SMA crossover: buy when SMA5 crosses above SMA10 — highest profit in external backtests"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 2:
            return Signal("NONE")

        curr_5, prev_5 = df["sma_5"].iloc[-1], df["sma_5"].iloc[-2]
        curr_10, prev_10 = df["sma_10"].iloc[-1], df["sma_10"].iloc[-2]

        if any(pd.isna(x) for x in [curr_5, prev_5, curr_10, prev_10]):
            return Signal("NONE")

        if prev_5 <= prev_10 and curr_5 > curr_10:
            return Signal(
                signal_type="BUY",
                confidence=0.68,
                risk_score=0.42,
                expected_upside_pct=10.0,
                stop_loss_pct=5.0,
                target_pct=10.0,
                holding_days=8,
                conditions_met=[f"SMA5={curr_5:.2f} crossed above SMA10={curr_10:.2f}"],
            )

        if prev_5 >= prev_10 and curr_5 < curr_10:
            return Signal(
                signal_type="SELL",
                confidence=0.68,
                risk_score=0.52,
                expected_upside_pct=0.0,
                stop_loss_pct=0.0,
                target_pct=0.0,
                holding_days=0,
                conditions_met=[f"SMA5={curr_5:.2f} crossed below SMA10={curr_10:.2f}"],
            )

        return Signal("NONE")

    def get_required_indicators(self) -> list[str]:
        return ["sma_5", "sma_10"]
