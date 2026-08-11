import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class ROCMomentumCrossStrategy(BaseStrategy):
    name = "ROC Momentum Cross"
    description = "Buy when Rate of Change crosses from negative to positive; sell on negative cross"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 2:
            return Signal("NONE")

        roc = df["roc_10"].iloc[-1]
        prev_roc = df["roc_10"].iloc[-2]

        if pd.isna(roc) or pd.isna(prev_roc):
            return Signal("NONE")

        if prev_roc <= 0 and roc > 0:
            close = df["close"].iloc[-1]
            sma20 = df["sma_20"].iloc[-1]
            sma_note = f", above SMA20" if not pd.isna(sma20) and close > sma20 else ""
            return Signal(
                signal_type="BUY",
                confidence=0.61,
                risk_score=0.44,
                expected_upside_pct=9.0,
                stop_loss_pct=5.0,
                target_pct=9.0,
                holding_days=10,
                conditions_met=[f"ROC(10)={roc:.2f}% crossed positive from {prev_roc:.2f}%{sma_note}"],
            )

        if prev_roc >= 0 and roc < 0:
            return Signal(
                signal_type="SELL",
                confidence=0.60,
                risk_score=0.52,
                expected_upside_pct=0.0,
                stop_loss_pct=0.0,
                target_pct=0.0,
                holding_days=0,
                conditions_met=[f"ROC(10)={roc:.2f}% crossed negative from {prev_roc:.2f}%"],
            )

        return Signal("NONE")

    def get_required_indicators(self) -> list[str]:
        return ["roc_10"]
