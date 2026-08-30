import pandas as pd

from domains.special_strategies.base import SpecialBaseStrategy, SpecialSignal


class SqueezeMomentumStrategy(SpecialBaseStrategy):
    name = "Squeeze Momentum Breakout"
    description = "Buy when BB/KC squeeze releases with bullish momentum (squeeze_on False, squeeze_mom > 0). Sell when momentum turns negative or 10% profit."

    def buy_signal(self, df: pd.DataFrame) -> SpecialSignal:
        if len(df) < 2:
            return SpecialSignal("NONE")
        prev_squeeze = df["squeeze_on"].iloc[-2]
        curr_squeeze = df["squeeze_on"].iloc[-1]
        curr_mom = df["squeeze_mom"].iloc[-1]
        prev_mom = df["squeeze_mom"].iloc[-2]
        if any(pd.isna(v) for v in [prev_squeeze, curr_squeeze, curr_mom, prev_mom]):
            return SpecialSignal("NONE")
        # Squeeze just released (was on, now off) with rising positive momentum
        squeeze_released = bool(prev_squeeze) and not bool(curr_squeeze)
        if squeeze_released and curr_mom > 0:
            confidence = min(1.0, 0.55 + abs(curr_mom) / (abs(curr_mom) + 0.5))
            return SpecialSignal(
                signal_type="BUY",
                confidence=round(confidence, 4),
                conditions_met=[
                    "Squeeze released (BB expanded beyond KC)",
                    f"Bullish momentum ({curr_mom:.4f})",
                ],
            )
        return SpecialSignal("NONE")

    def sell_signal(self, df: pd.DataFrame, entry_price: float | None = None) -> bool:
        if len(df) < 2:
            return False
        curr_close = df["close"].iloc[-1]
        if entry_price is not None and not pd.isna(curr_close):
            if curr_close >= entry_price * 1.10:
                return True
        prev_mom = df["squeeze_mom"].iloc[-2]
        curr_mom = df["squeeze_mom"].iloc[-1]
        if any(pd.isna(v) for v in [prev_mom, curr_mom]):
            return False
        return prev_mom >= 0 and curr_mom < 0
