import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class SMA10_20CrossoverStrategy(BaseStrategy):
    name = "SMA Crossover (10/20)"
    description = "Medium-term SMA crossover: buy when SMA10 crosses above SMA20"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 2:
            return Signal("NONE")

        curr_10, prev_10 = df["sma_10"].iloc[-1], df["sma_10"].iloc[-2]
        curr_20, prev_20 = df["sma_20"].iloc[-1], df["sma_20"].iloc[-2]

        if any(pd.isna(x) for x in [curr_10, prev_10, curr_20, prev_20]):
            return Signal("NONE")

        if prev_10 <= prev_20 and curr_10 > curr_20:
            return Signal(
                signal_type="BUY",
                confidence=0.62,
                risk_score=0.43,
                expected_upside_pct=12.0,
                stop_loss_pct=6.0,
                target_pct=12.0,
                holding_days=12,
                conditions_met=[f"SMA10={curr_10:.2f} crossed above SMA20={curr_20:.2f}"],
            )

        if prev_10 >= prev_20 and curr_10 < curr_20:
            return Signal(
                signal_type="SELL",
                confidence=0.62,
                risk_score=0.55,
                expected_upside_pct=0.0,
                stop_loss_pct=0.0,
                target_pct=0.0,
                holding_days=0,
                conditions_met=[f"SMA10={curr_10:.2f} crossed below SMA20={curr_20:.2f}"],
            )

        return Signal("NONE")

    def get_required_indicators(self) -> list[str]:
        return ["sma_10", "sma_20"]
