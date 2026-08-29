"""
Elder Impulse System (Alexander Elder, "Come Into My Trading Room", 2002)

The system color-codes each bar based on TWO independent forces:
  • EMA(13) slope — represents market inertia / trend direction
  • MACD histogram slope — represents momentum acceleration/deceleration

Bar color (the "impulse"):
  GREEN  = EMA(13) rising  AND  MACD histogram rising  → both forces bullish, BUY
  RED    = EMA(13) falling AND  MACD histogram falling → both forces bearish, SELL
  BLUE   = mixed (one up, one down)                    → stand aside

The system's core insight: it takes TWO independent forces pulling in the same
direction to justify entering a trade. One is not enough.

BUY signal = current bar is GREEN (both forces up) AND was not GREEN before
             (entering a new bullish impulse, not riding a stale one)

Extra filter: price above EMA(13) confirms we're trading WITH the trend,
not against it.
"""
import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class ElderImpulseSystemStrategy(BaseStrategy):
    name = "Elder Impulse System"
    description = (
        "Two-force BUY: EMA(13) rising AND MACD histogram rising (green impulse bar). "
        "Elder's system — only enter when both inertia and momentum agree."
    )
    strategy_type = StrategyType.TECHNICAL
    timeframe     = Timeframe.DAILY
    min_holding_days = 3
    max_holding_days = 15
    weight           = 0.20

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        required = ["close", "macd_hist", "ema_13"]
        if len(df) < 20 or not all(c in df.columns for c in required):
            return Signal(signal_type="NONE", conditions_failed=["Insufficient data"])

        close     = df["close"]
        macd_hist = df["macd_hist"]

        ema13 = df["ema_13"]

        ema_now  = float(ema13.iloc[-1])
        ema_prev = float(ema13.iloc[-2])

        hist_now  = float(macd_hist.iloc[-1])
        hist_prev = float(macd_hist.iloc[-2])

        c_now = float(close.iloc[-1])

        if any(pd.isna(x) for x in [ema_now, ema_prev, hist_now, hist_prev]):
            return Signal(signal_type="NONE", conditions_failed=["Indicators not ready"])

        # Force 1: EMA(13) slope
        ema_rising = ema_now > ema_prev
        ema_slope  = (ema_now - ema_prev) / ema_prev * 100 if ema_prev else 0

        # Force 2: MACD histogram slope
        hist_rising = hist_now > hist_prev

        # Current impulse color
        def _impulse(ema_up: bool, hist_up: bool) -> str:
            if ema_up and hist_up:     return "GREEN"
            if not ema_up and not hist_up: return "RED"
            return "BLUE"

        impulse_now  = _impulse(ema_rising, hist_rising)
        ema_prev2    = float(ema13.iloc[-3])
        hist_prev2   = float(macd_hist.iloc[-3])
        impulse_prev = _impulse(ema_now > ema_prev, hist_prev > hist_prev2)

        # Extra: price above EMA(13)
        above_ema = c_now > ema_now

        conditions_met    = []
        conditions_failed = []

        if impulse_now == "GREEN":
            conditions_met.append(
                f"GREEN Impulse: EMA13 rising (+{ema_slope:.3f}%) AND MACD hist rising"
            )
        elif impulse_now == "RED":
            conditions_failed.append(
                "RED Impulse: both forces bearish — do not buy"
            )
        else:
            conditions_failed.append(
                f"BLUE Impulse: forces disagree (EMA {'↑' if ema_rising else '↓'}, "
                f"MACD hist {'↑' if hist_rising else '↓'})"
            )

        if impulse_now == "GREEN" and impulse_prev != "GREEN":
            conditions_met.append("Fresh GREEN: entering new bullish impulse (not stale)")
        elif impulse_now == "GREEN":
            conditions_met.append("Sustained GREEN impulse — trend continuing")

        if above_ema:
            pct = ((c_now - ema_now) / ema_now) * 100
            conditions_met.append(f"Price {pct:.2f}% above EMA(13) ({ema_now:.2f})")
        else:
            conditions_failed.append(f"Price below EMA(13) — trading against trend")

        if impulse_now == "GREEN" and above_ema:
            freshness  = 1.0 if impulse_prev != "GREEN" else 0.5
            ema_str    = min(abs(ema_slope) / 0.3, 1.0)
            confidence = round(min(0.62 + 0.15 * freshness + 0.10 * ema_str, 0.88), 4)
            return Signal(
                signal_type="BUY",
                confidence=confidence,
                risk_score=0.27,
                expected_upside_pct=9.0,
                stop_loss_pct=4.5,
                target_pct=9.0,
                holding_days=9,
                conditions_met=conditions_met + [
                    f"EMA13={ema_now:.2f} | MACD hist={hist_now:.5f} (prev={hist_prev:.5f})"
                ],
            )

        return Signal(
            signal_type="NONE",
            conditions_met=conditions_met,
            conditions_failed=conditions_failed,
        )

    def get_required_indicators(self) -> list[str]:
        return ["close", "macd_hist", "ema_13"]
