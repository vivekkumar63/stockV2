import pandas as pd

from domains.special_strategies.base import SpecialBaseStrategy, SpecialSignal


class RsiMomentumStrategy(SpecialBaseStrategy):
    name = "RSI Momentum + EMA50"
    description = "Buy when RSI-14 crosses above 60 with price above EMA-50. Sell when RSI drops below 50 or price closes below EMA-50 or 10% profit."

    def buy_signal(self, df: pd.DataFrame) -> SpecialSignal:
        if len(df) < 2:
            return SpecialSignal("NONE")
        prev_rsi = df["rsi_14"].iloc[-2]
        curr_rsi = df["rsi_14"].iloc[-1]
        curr_close = df["close"].iloc[-1]
        curr_ema50 = df["ema_50"].iloc[-1]
        if any(pd.isna(v) for v in [prev_rsi, curr_rsi, curr_close, curr_ema50]):
            return SpecialSignal("NONE")
        if prev_rsi <= 60 and curr_rsi > 60 and curr_close > curr_ema50:
            confidence = min(1.0, 0.5 + (curr_rsi - 60) / 40)
            return SpecialSignal(
                signal_type="BUY",
                confidence=round(confidence, 4),
                conditions_met=[
                    f"RSI14({curr_rsi:.1f}) crossed above 60",
                    f"Price({curr_close:.2f}) above EMA50({curr_ema50:.2f})",
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
        curr_rsi = df["rsi_14"].iloc[-1]
        curr_ema50 = df["ema_50"].iloc[-1]
        if pd.isna(curr_rsi) or pd.isna(curr_ema50) or pd.isna(curr_close):
            return False
        return curr_rsi < 50 or curr_close < curr_ema50
