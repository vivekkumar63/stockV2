import pandas as pd

from domains.special_strategies.base import SpecialBaseStrategy, SpecialSignal


class SupertrendFlipStrategy(SpecialBaseStrategy):
    name = "Supertrend Flip"
    description = "Buy when Supertrend flips bullish (direction -1→+1). Sell when it flips bearish or 10% profit reached."

    def buy_signal(self, df: pd.DataFrame) -> SpecialSignal:
        if len(df) < 2:
            return SpecialSignal("NONE")
        prev_dir = df["supertrend_direction"].iloc[-2]
        curr_dir = df["supertrend_direction"].iloc[-1]
        curr_close = df["close"].iloc[-1]
        curr_st = df["supertrend"].iloc[-1]
        if any(pd.isna(v) for v in [prev_dir, curr_dir, curr_close, curr_st]):
            return SpecialSignal("NONE")
        if prev_dir == -1 and curr_dir == 1:
            gap_pct = round((curr_close - curr_st) / curr_st * 100, 2)
            confidence = min(1.0, 0.55 + abs(gap_pct) / 10)
            return SpecialSignal(
                signal_type="BUY",
                confidence=round(confidence, 4),
                conditions_met=[f"Supertrend flipped bullish (close={curr_close:.2f}, ST={curr_st:.2f})"],
            )
        return SpecialSignal("NONE")

    def sell_signal(self, df: pd.DataFrame, entry_price: float | None = None) -> bool:
        if len(df) < 2:
            return False
        curr_close = df["close"].iloc[-1]
        if entry_price is not None and not pd.isna(curr_close):
            if curr_close >= entry_price * 1.10:
                return True
        curr_dir = df["supertrend_direction"].iloc[-1]
        prev_dir = df["supertrend_direction"].iloc[-2]
        if any(pd.isna(v) for v in [prev_dir, curr_dir]):
            return False
        return prev_dir == 1 and curr_dir == -1
