import pandas as pd

from domains.special_strategies.base import SpecialBaseStrategy, SpecialSignal


class AdxDirectionalStrategy(SpecialBaseStrategy):
    name = "ADX Directional (DMI Cross)"
    description = "Buy when ADX > 25 and +DI crosses above -DI (strong trending move). Sell when -DI crosses above +DI, ADX drops below 20, or 10% profit."

    def buy_signal(self, df: pd.DataFrame) -> SpecialSignal:
        if len(df) < 2:
            return SpecialSignal("NONE")
        curr_adx = df["adx_14"].iloc[-1]
        prev_dmi_plus = df["dmi_plus_14"].iloc[-2]
        prev_dmi_minus = df["dmi_minus_14"].iloc[-2]
        curr_dmi_plus = df["dmi_plus_14"].iloc[-1]
        curr_dmi_minus = df["dmi_minus_14"].iloc[-1]
        if any(pd.isna(v) for v in [curr_adx, prev_dmi_plus, prev_dmi_minus, curr_dmi_plus, curr_dmi_minus]):
            return SpecialSignal("NONE")
        if curr_adx > 25 and prev_dmi_plus <= prev_dmi_minus and curr_dmi_plus > curr_dmi_minus:
            gap = round(curr_dmi_plus - curr_dmi_minus, 2)
            confidence = min(1.0, 0.5 + (curr_adx - 25) / 50 + gap / 40)
            return SpecialSignal(
                signal_type="BUY",
                confidence=round(confidence, 4),
                conditions_met=[
                    f"ADX({curr_adx:.1f}) > 25",
                    f"+DI({curr_dmi_plus:.1f}) crossed above -DI({curr_dmi_minus:.1f})",
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
        curr_adx = df["adx_14"].iloc[-1]
        prev_dmi_plus = df["dmi_plus_14"].iloc[-2]
        prev_dmi_minus = df["dmi_minus_14"].iloc[-2]
        curr_dmi_plus = df["dmi_plus_14"].iloc[-1]
        curr_dmi_minus = df["dmi_minus_14"].iloc[-1]
        if any(pd.isna(v) for v in [curr_adx, prev_dmi_plus, prev_dmi_minus, curr_dmi_plus, curr_dmi_minus]):
            return False
        dmi_bearish_cross = prev_dmi_minus <= prev_dmi_plus and curr_dmi_minus > curr_dmi_plus
        return dmi_bearish_cross or curr_adx < 20
