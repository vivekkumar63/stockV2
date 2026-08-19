"""
Awesome Oscillator + Alligator (Bill Williams)

Bill Williams built a complete trading system where the Alligator tells you
WHEN to trade and the Awesome Oscillator tells you DIRECTION.

Alligator — three SMMA (Wilder's MA) lines of the midpoint (HL/2):
  Jaw    = SMMA(13) — slowest,  the Alligator's jaw
  Teeth  = SMMA(8)  — medium,   the teeth
  Lips   = SMMA(5)  — fastest,  the lips

  Alligator SLEEPING  = three lines intertwined (ranging market)
  Alligator WAKING UP = lines separating and ordering: Lips > Teeth > Jaw
  Alligator EATING    = fully separated, trending hard

Awesome Oscillator (AO):
  AO = SMA(midpoint, 5) − SMA(midpoint, 34)
  AO > 0 = bullish momentum
  AO < 0 = bearish momentum

BUY signals from Williams' theory:
  1. Alligator awake (Lips > Teeth > Jaw) — trend confirmed upward
  2. AO histogram crossed zero upward (fresh bullish momentum)
  3. Price above ALL three Alligator lines (price is "above the mouth")
"""
import numpy as np
import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


def _smma(series: pd.Series, period: int) -> pd.Series:
    """Smoothed Moving Average (Wilder's) = EWM with com=period-1."""
    return series.ewm(com=period - 1, adjust=False).mean()


class AwesomeOscillatorAlligatorStrategy(BaseStrategy):
    name = "Awesome Oscillator + Alligator"
    description = (
        "Bill Williams: AO zero-cross upward (bullish momentum) with Alligator "
        "awake and eating (Lips > Teeth > Jaw, price above all three lines)."
    )
    strategy_type = StrategyType.TECHNICAL
    timeframe     = Timeframe.DAILY
    min_holding_days = 4
    max_holding_days = 18
    weight           = 0.20

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        required = ["close", "high", "low"]
        if len(df) < 40 or not all(c in df.columns for c in required):
            return Signal(signal_type="NONE", conditions_failed=["Insufficient data"])

        close = df["close"]
        high  = df["high"]
        low   = df["low"]
        mid   = (high + low) / 2   # HL/2 midpoint

        # ── Alligator lines (unshifted for price comparison) ───────────────────
        jaw    = _smma(mid, 13)
        teeth  = _smma(mid, 8)
        lips   = _smma(mid, 5)

        # ── Awesome Oscillator ─────────────────────────────────────────────────
        ao = mid.rolling(5).mean() - mid.rolling(34).mean()

        # Current values
        c_now    = float(close.iloc[-1])
        jaw_now  = float(jaw.iloc[-1])
        teeth_now = float(teeth.iloc[-1])
        lips_now  = float(lips.iloc[-1])
        ao_now   = float(ao.iloc[-1])
        ao_prev  = float(ao.iloc[-2])

        if any(pd.isna(x) for x in [jaw_now, teeth_now, lips_now, ao_now]):
            return Signal(signal_type="NONE", conditions_failed=["Alligator not ready"])

        # ── Conditions ─────────────────────────────────────────────────────────

        # 1. Alligator awake and aligned upward
        alligator_awake = lips_now > teeth_now > jaw_now

        # 2. Price above all Alligator lines (price above the "mouth")
        price_above = c_now > lips_now > teeth_now > jaw_now

        # 3. AO crossed zero upward (fresh bullish momentum signal)
        ao_cross_up = ao_prev <= 0 and ao_now > 0

        # 4. AO positive and rising (saucer/continuation)
        ao_bullish_rising = ao_now > 0 and ao_now > ao_prev

        conditions_met    = []
        conditions_failed = []

        if alligator_awake:
            conditions_met.append(
                f"Alligator eating: Lips({lips_now:.2f}) > Teeth({teeth_now:.2f}) > Jaw({jaw_now:.2f})"
            )
        else:
            conditions_failed.append(
                f"Alligator sleeping/tangled: Lips={lips_now:.2f} Teeth={teeth_now:.2f} Jaw={jaw_now:.2f}"
            )

        if price_above:
            conditions_met.append(f"Price({c_now:.2f}) above all Alligator lines — trend confirmed")
        else:
            conditions_failed.append(f"Price not fully above Alligator lines")

        if ao_cross_up:
            conditions_met.append(f"AO zero-cross upward ({ao_prev:.3f} → {ao_now:.3f})")
        elif ao_bullish_rising:
            conditions_met.append(f"AO positive and rising ({ao_prev:.3f} → {ao_now:.3f})")
        else:
            conditions_failed.append(f"AO not bullish (AO={ao_now:.3f}, prev={ao_prev:.3f})")

        if alligator_awake and price_above and (ao_cross_up or ao_bullish_rising):
            fresh   = 1.0 if ao_cross_up else 0.5
            spread  = min((lips_now - jaw_now) / jaw_now * 10, 1.0)  # alligator spread
            confidence = round(min(0.62 + 0.15 * fresh + 0.10 * spread, 0.88), 4)
            return Signal(
                signal_type="BUY",
                confidence=confidence,
                risk_score=0.30,
                expected_upside_pct=10.0,
                stop_loss_pct=5.0,
                target_pct=10.0,
                holding_days=10,
                conditions_met=conditions_met,
            )

        return Signal(
            signal_type="NONE",
            conditions_met=conditions_met,
            conditions_failed=conditions_failed,
        )

    def get_required_indicators(self) -> list[str]:
        return ["close", "high", "low"]
