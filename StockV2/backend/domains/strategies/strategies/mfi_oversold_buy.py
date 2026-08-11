import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class MFIOversoldBuyStrategy(BaseStrategy):
    name = "MFI Oversold Bounce"
    description = "Buy when Money Flow Index crosses below 20 — selling pressure exhausted, reversal likely"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 2:
            return Signal("NONE")

        mfi = df["mfi_14"].iloc[-1]
        prev_mfi = df["mfi_14"].iloc[-2]

        if pd.isna(mfi) or pd.isna(prev_mfi):
            return Signal("NONE")

        if prev_mfi >= 20 and mfi < 20:
            rsi = df["rsi_14"].iloc[-1]
            rsi_note = f", RSI={rsi:.1f}" if not pd.isna(rsi) else ""
            return Signal(
                signal_type="BUY",
                confidence=0.64,
                risk_score=0.42,
                expected_upside_pct=9.0,
                stop_loss_pct=5.0,
                target_pct=9.0,
                holding_days=8,
                conditions_met=[f"MFI={mfi:.1f} crossed below 20 (money flow exhausted){rsi_note}"],
            )

        return Signal("NONE")

    def get_required_indicators(self) -> list[str]:
        return ["mfi_14"]
