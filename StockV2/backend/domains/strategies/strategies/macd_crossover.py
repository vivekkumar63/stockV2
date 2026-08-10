import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class MACDCrossoverStrategy(BaseStrategy):
    name = "MACD Crossover"
    description = "Buy when MACD histogram turns positive (bullish crossover), sell on bearish crossover"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY
    min_holding_days = 10
    max_holding_days = 30

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 2 or "macd_hist" not in df.columns:
            return Signal("NONE")
        curr = df["macd_hist"].iloc[-1]
        prev = df["macd_hist"].iloc[-2]
        if pd.isna(curr) or pd.isna(prev):
            return Signal("NONE")
        if prev < 0 and curr >= 0:
            return Signal(
                signal_type="BUY",
                confidence=0.65,
                risk_score=0.45,
                expected_upside_pct=12.0,
                stop_loss_pct=7.0,
                target_pct=15.0,
                holding_days=20,
                conditions_met=["MACD histogram turned positive (bullish crossover)"],
            )
        if prev > 0 and curr <= 0:
            return Signal(
                signal_type="SELL",
                confidence=0.65,
                risk_score=0.55,
                expected_upside_pct=0.0,
                stop_loss_pct=0.0,
                target_pct=0.0,
                holding_days=0,
                conditions_met=["MACD histogram turned negative (bearish crossover)"],
            )
        return Signal("NONE")

    def get_required_indicators(self) -> list[str]:
        return ["macd_hist"]
