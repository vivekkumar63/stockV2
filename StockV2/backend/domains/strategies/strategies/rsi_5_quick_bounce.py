import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class RSI5QuickBounceStrategy(BaseStrategy):
    name = "RSI-5 Quick Bounce"
    description = "Buy when short-period RSI(5) crosses below 20 — very fast oversold signal for short holds"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 2:
            return Signal("NONE")

        rsi5 = df["rsi_5"].iloc[-1]
        prev_rsi5 = df["rsi_5"].iloc[-2]

        if pd.isna(rsi5) or pd.isna(prev_rsi5):
            return Signal("NONE")

        if prev_rsi5 >= 20 and rsi5 < 20:
            rsi14 = df["rsi_14"].iloc[-1]
            rsi14_note = f", RSI14={rsi14:.1f}" if not pd.isna(rsi14) else ""
            return Signal(
                signal_type="BUY",
                confidence=0.60,
                risk_score=0.45,
                expected_upside_pct=5.0,
                stop_loss_pct=4.0,
                target_pct=5.0,
                holding_days=3,
                conditions_met=[f"RSI(5)={rsi5:.1f} crossed below 20 (extreme short-term oversold){rsi14_note}"],
            )

        return Signal("NONE")

    def get_required_indicators(self) -> list[str]:
        return ["rsi_5"]
