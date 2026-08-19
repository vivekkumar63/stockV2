import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class MACDCrossoverStrategy(BaseStrategy):
    name = "MACD Crossover"
    description = "Buy on MACD histogram crossing from negative to positive; sell on reverse"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY
    weight = 0.15
    min_holding_days = 3
    max_holding_days = 15

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 2 or "macd_hist" not in df.columns:
            return Signal("NONE")
        curr = df["macd_hist"].iloc[-1]
        prev = df["macd_hist"].iloc[-2]
        if any(pd.isna(x) for x in [curr, prev]):
            return Signal("NONE")
        if prev < 0 < curr:
            return Signal(
                signal_type="BUY",
                confidence=0.70,
                risk_score=0.45,
                stop_loss_pct=6.0,
                target_pct=12.0,
                holding_days=10,
                conditions_met=[f"MACD hist crossed above zero: {prev:.3f} → {curr:.3f}"],
            )
        if prev > 0 > curr:
            return Signal(
                signal_type="SELL",
                confidence=0.70,
                conditions_met=[f"MACD hist crossed below zero: {prev:.3f} → {curr:.3f}"],
            )
        return Signal("NONE")

    def get_required_indicators(self) -> list[str]:
        return ["macd_hist"]
