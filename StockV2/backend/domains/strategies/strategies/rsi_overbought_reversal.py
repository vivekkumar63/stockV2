import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class RSIOverboughtReversalStrategy(BaseStrategy):
    name = "RSI Overbought Reversal"
    description = "Sell when RSI crosses above 70 — expects mean reversion from overbought"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 2:
            return Signal("NONE")

        rsi = df["rsi_14"].iloc[-1]
        prev_rsi = df["rsi_14"].iloc[-2]

        if pd.isna(rsi) or pd.isna(prev_rsi):
            return Signal("NONE")

        if prev_rsi <= 70 and rsi > 70:
            return Signal(
                signal_type="SELL",
                confidence=0.63,
                risk_score=0.55,
                expected_upside_pct=0.0,
                stop_loss_pct=0.0,
                target_pct=0.0,
                holding_days=0,
                conditions_met=[f"RSI {rsi:.1f} crossed above 70 (overbought)"],
            )

        return Signal("NONE")

    def get_required_indicators(self) -> list[str]:
        return ["rsi_14"]
