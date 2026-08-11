import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class MFIOverboughtSellStrategy(BaseStrategy):
    name = "MFI Overbought Reversal"
    description = "Sell when Money Flow Index crosses above 80 — buying pressure at extreme, reversal likely"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 2:
            return Signal("NONE")

        mfi = df["mfi_14"].iloc[-1]
        prev_mfi = df["mfi_14"].iloc[-2]

        if pd.isna(mfi) or pd.isna(prev_mfi):
            return Signal("NONE")

        if prev_mfi <= 80 and mfi > 80:
            rsi = df["rsi_14"].iloc[-1]
            rsi_note = f", RSI={rsi:.1f}" if not pd.isna(rsi) else ""
            return Signal(
                signal_type="SELL",
                confidence=0.63,
                risk_score=0.52,
                expected_upside_pct=0.0,
                stop_loss_pct=0.0,
                target_pct=0.0,
                holding_days=0,
                conditions_met=[f"MFI={mfi:.1f} crossed above 80 (buying pressure extreme){rsi_note}"],
            )

        return Signal("NONE")

    def get_required_indicators(self) -> list[str]:
        return ["mfi_14"]
