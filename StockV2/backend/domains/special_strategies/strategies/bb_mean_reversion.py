import pandas as pd

from domains.special_strategies.base import SpecialBaseStrategy, SpecialSignal


class BbMeanReversionStrategy(SpecialBaseStrategy):
    name = "BB Mean Reversion"
    description = "Buy when price closes below lower Bollinger Band with RSI-14 < 40. Sell when price reaches BB middle or 10% profit."

    def buy_signal(self, df: pd.DataFrame) -> SpecialSignal:
        if len(df) < 2:
            return SpecialSignal("NONE")
        curr_close = df["close"].iloc[-1]
        prev_close = df["close"].iloc[-2]
        curr_bb_lower = df["bb_lower"].iloc[-1]
        curr_rsi = df["rsi_14"].iloc[-1]
        if any(pd.isna(v) for v in [curr_close, prev_close, curr_bb_lower, curr_rsi]):
            return SpecialSignal("NONE")
        # Price closes below lower band (not just touches — it actually closed below)
        if curr_close < curr_bb_lower and curr_rsi < 40:
            band_pct = round((curr_bb_lower - curr_close) / curr_bb_lower * 100, 2)
            confidence = min(1.0, 0.5 + band_pct / 5 + (40 - curr_rsi) / 80)
            return SpecialSignal(
                signal_type="BUY",
                confidence=round(confidence, 4),
                conditions_met=[
                    f"Close({curr_close:.2f}) below BB lower({curr_bb_lower:.2f})",
                    f"RSI14({curr_rsi:.1f}) < 40",
                ],
            )
        return SpecialSignal("NONE")

    def sell_signal(self, df: pd.DataFrame, entry_price: float | None = None) -> bool:
        if len(df) < 1:
            return False
        curr_close = df["close"].iloc[-1]
        if entry_price is not None and not pd.isna(curr_close):
            if curr_close >= entry_price * 1.10:
                return True
        curr_bb_middle = df["bb_middle"].iloc[-1]
        if pd.isna(curr_close) or pd.isna(curr_bb_middle):
            return False
        return curr_close >= curr_bb_middle
