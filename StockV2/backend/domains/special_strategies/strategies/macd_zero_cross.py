import pandas as pd

from domains.special_strategies.base import SpecialBaseStrategy, SpecialSignal


class MacdZeroCrossStrategy(SpecialBaseStrategy):
    name = "MACD Histogram Zero-Cross"
    description = "Buy when MACD histogram crosses from negative to positive (zero-line cross). Sell when histogram turns negative again or 10% profit."

    def buy_signal(self, df: pd.DataFrame) -> SpecialSignal:
        if len(df) < 2:
            return SpecialSignal("NONE")
        prev_hist = df["macd_hist"].iloc[-2]
        curr_hist = df["macd_hist"].iloc[-1]
        if any(pd.isna(v) for v in [prev_hist, curr_hist]):
            return SpecialSignal("NONE")
        if prev_hist <= 0 and curr_hist > 0:
            confidence = min(1.0, 0.5 + abs(curr_hist) / 2)
            return SpecialSignal(
                signal_type="BUY",
                confidence=round(confidence, 4),
                conditions_met=[f"MACD histogram crossed above zero ({curr_hist:.4f})"],
            )
        return SpecialSignal("NONE")

    def sell_signal(self, df: pd.DataFrame, entry_price: float | None = None) -> bool:
        if len(df) < 2:
            return False
        curr_close = df["close"].iloc[-1]
        if entry_price is not None and not pd.isna(curr_close):
            if curr_close >= entry_price * 1.10:
                return True
        prev_hist = df["macd_hist"].iloc[-2]
        curr_hist = df["macd_hist"].iloc[-1]
        if any(pd.isna(v) for v in [prev_hist, curr_hist]):
            return False
        return prev_hist >= 0 and curr_hist < 0
