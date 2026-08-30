import pandas as pd

from domains.special_strategies.base import SpecialBaseStrategy, SpecialSignal


class Ema50200CrossoverStrategy(SpecialBaseStrategy):
    name = "EMA 50/200 Crossover"
    description = (
        "Buy when EMA50 crosses above SMA200 (golden cross). "
        "Sell when EMA50 crosses below SMA200 (death cross) or 10% profit reached."
    )

    def buy_signal(self, df: pd.DataFrame) -> SpecialSignal:
        if len(df) < 3:
            return SpecialSignal("NONE")
        prev50 = df["ema_50"].iloc[-2]
        prev200 = df["sma_200"].iloc[-2]
        curr50 = df["ema_50"].iloc[-1]
        curr200 = df["sma_200"].iloc[-1]
        if any(pd.isna(v) for v in [prev50, prev200, curr50, curr200]):
            return SpecialSignal("NONE")
        if prev50 <= prev200 and curr50 > curr200:
            gap_pct = round((curr50 - curr200) / curr200 * 100, 2)
            confidence = min(1.0, 0.6 + abs(gap_pct) / 5)
            return SpecialSignal(
                signal_type="BUY",
                confidence=round(confidence, 4),
                conditions_met=[f"EMA50({curr50:.2f}) crossed above SMA200({curr200:.2f})"],
            )
        return SpecialSignal("NONE")

    def sell_signal(self, df: pd.DataFrame, entry_price: float | None = None) -> bool:
        if len(df) < 3:
            return False
        curr_close = df["close"].iloc[-1]
        # 10% profit target
        if entry_price is not None and not pd.isna(curr_close):
            if curr_close >= entry_price * 1.10:
                return True
        # Death cross: EMA50 crosses below SMA200
        prev50 = df["ema_50"].iloc[-2]
        prev200 = df["sma_200"].iloc[-2]
        curr50 = df["ema_50"].iloc[-1]
        curr200 = df["sma_200"].iloc[-1]
        if any(pd.isna(v) for v in [prev50, prev200, curr50, curr200]):
            return False
        return prev50 >= prev200 and curr50 < curr200
