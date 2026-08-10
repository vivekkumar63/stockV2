import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class RSIOversoldStrategy(BaseStrategy):
    name = "RSI Oversold/Overbought"
    description = "Buy when RSI < 30 (oversold), sell when RSI > 70 (overbought)"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY
    min_holding_days = 5
    max_holding_days = 15

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if df.empty or "rsi_14" not in df.columns:
            return Signal("NONE")
        rsi = df["rsi_14"].iloc[-1]
        if pd.isna(rsi):
            return Signal("NONE")
        if rsi < 30:
            confidence = min(1.0, (30 - rsi) / 20 + 0.5)
            return Signal(
                signal_type="BUY",
                confidence=round(confidence, 4),
                risk_score=0.40,
                expected_upside_pct=10.0,
                stop_loss_pct=7.0,
                target_pct=12.0,
                holding_days=10,
                conditions_met=[f"RSI={rsi:.1f} < 30 (oversold)"],
            )
        if rsi > 70:
            confidence = min(1.0, (rsi - 70) / 20 + 0.5)
            return Signal(
                signal_type="SELL",
                confidence=round(confidence, 4),
                risk_score=0.60,
                expected_upside_pct=0.0,
                stop_loss_pct=0.0,
                target_pct=0.0,
                holding_days=0,
                conditions_met=[f"RSI={rsi:.1f} > 70 (overbought)"],
            )
        return Signal("NONE")

    def get_required_indicators(self) -> list[str]:
        return ["rsi_14"]
