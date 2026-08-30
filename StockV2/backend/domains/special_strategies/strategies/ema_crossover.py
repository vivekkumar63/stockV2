import pandas as pd

from domains.special_strategies.base import SpecialBaseStrategy, SpecialSignal


class EmaCrossoverStrategy(SpecialBaseStrategy):
    name = "EMA 9/21 Crossover"
    description = "Buy when EMA9 crosses above EMA21 (golden cross). Sell when EMA9 crosses below EMA21 (death cross) or 10% profit reached."

    def buy_signal(self, df: pd.DataFrame) -> SpecialSignal:
        if len(df) < 3:
            return SpecialSignal("NONE")
        prev9 = df["ema_9"].iloc[-2]
        prev21 = df["ema_21"].iloc[-2]
        curr9 = df["ema_9"].iloc[-1]
        curr21 = df["ema_21"].iloc[-1]
        if any(pd.isna(v) for v in [prev9, prev21, curr9, curr21]):
            return SpecialSignal("NONE")
        if prev9 <= prev21 and curr9 > curr21:
            gap_pct = round((curr9 - curr21) / curr21 * 100, 2)
            confidence = min(1.0, 0.5 + abs(gap_pct) / 5)
            return SpecialSignal(
                signal_type="BUY",
                confidence=round(confidence, 4),
                conditions_met=[f"EMA9({curr9:.2f}) crossed above EMA21({curr21:.2f})"],
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
        # Death cross: EMA9 crosses below EMA21
        prev9 = df["ema_9"].iloc[-2]
        prev21 = df["ema_21"].iloc[-2]
        curr9 = df["ema_9"].iloc[-1]
        curr21 = df["ema_21"].iloc[-1]
        if any(pd.isna(v) for v in [prev9, prev21, curr9, curr21]):
            return False
        return prev9 >= prev21 and curr9 < curr21
