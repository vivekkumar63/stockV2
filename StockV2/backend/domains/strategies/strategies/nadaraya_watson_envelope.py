"""
Nadaraya-Watson Envelope (jdehorty)

Faithful port of jdehorty's open-source Pine Script:
https://www.tradingview.com/script/Iko0E7bF-Nadaraya-Watson-Envelope-Non-Repainting/

The Rational Quadratic (RQ) kernel is a member of the Matérn class of kernels:
  K(i) = (1 + i² / (2 · α · h²))^(−α)

where:
  h = 8    — bandwidth (controls smoothness; larger = smoother)
  α = 8    — relative weight of large-distance vs small-distance (shape)
  i = lag  — bars ago from current bar

yhat = Σ K(i) · close[i] / Σ K(i)  summed over i = 0..lookback

Upper band = yhat + mult · MAE
Lower band = yhat − mult · MAE
where MAE = mean absolute error between close and yhat over the window.

BUY = price touched the lower band last bar (close ≤ lower[−1] · 1.005)
      AND price is now above lower band (bouncing off support)
      AND kernel estimate is flat or rising (not in structural downtrend)
"""
import numpy as np
import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe

_H    = 8.0    # Bandwidth
_R    = 8.0    # Relative weight (alpha)
_MULT = 3.0    # Band multiplier based on MAE
_LOOK = 100    # Practical lookback (RQ kernel decays to < 0.001 beyond ~35 bars)


def _rq_weights(lookback: int, h: float, r: float) -> np.ndarray:
    i = np.arange(lookback, dtype=float)
    return (1.0 + i ** 2 / (2.0 * r * h ** 2)) ** (-r)


def _nw_estimate(close_arr: np.ndarray, h: float, r: float,
                 lookback: int) -> tuple[np.ndarray, float]:
    """
    Returns (yhat[lookback], mae).
    yhat[0] = oldest bar estimate, yhat[-1] = current bar estimate.
    MAE = mean |close − yhat| over the window.
    """
    n    = len(close_arr)
    look = min(lookback, n)
    w    = _rq_weights(look, h, r)

    yhat = np.zeros(look)
    for j in range(look):
        bar_end   = n - j
        bar_start = max(0, bar_end - look)
        seg       = close_arr[bar_start: bar_end][::-1]   # newest-first
        ww        = w[:len(seg)]
        yhat[look - 1 - j] = np.dot(ww, seg) / ww.sum()

    mae = float(np.mean(np.abs(close_arr[-look:] - yhat)))
    return yhat, mae


class NadarayaWatsonEnvelopeStrategy(BaseStrategy):
    name = "Nadaraya-Watson Envelope"
    description = (
        "jdehorty's RQ kernel smoother: yhat ± 3·MAE forms dynamic bands. "
        "BUY when price bounces off lower band with flat/rising kernel estimate."
    )
    strategy_type = StrategyType.TECHNICAL
    timeframe     = Timeframe.DAILY
    min_holding_days = 3
    max_holding_days = 15
    weight           = 0.20

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 50 or "close" not in df.columns:
            return Signal(signal_type="NONE", conditions_failed=["Insufficient data"])

        cl = df["close"].values

        yhat, mae = _nw_estimate(cl, _H, _R, min(_LOOK, len(cl)))

        yhat_now  = float(yhat[-1])
        yhat_prev = float(yhat[-2])
        upper_now = yhat_now  + _MULT * mae
        lower_now = yhat_now  - _MULT * mae
        lower_prev = yhat_prev - _MULT * mae

        c_now  = float(cl[-1])
        c_prev = float(cl[-2])

        # BUY conditions
        # 1. Price touched lower band last bar (within 0.5% tolerance)
        near_lower = c_prev <= lower_prev * 1.005

        # 2. Price is now recovering above lower band
        above_lower = c_now > lower_now

        # 3. Kernel estimate flat or rising (not in structural downtrend)
        kernel_rising = yhat_now >= yhat_prev * 0.9995

        conditions_met    = []
        conditions_failed = []

        if near_lower:
            gap = ((c_prev - lower_prev) / lower_prev) * 100
            conditions_met.append(
                f"Price touched lower band (close={c_prev:.2f}, lower={lower_prev:.2f}, gap={gap:+.2f}%)"
            )
        else:
            gap = ((c_prev - lower_prev) / lower_prev) * 100
            conditions_failed.append(
                f"Price not at lower band (was {gap:+.1f}% above lower={lower_prev:.2f})"
            )

        if above_lower:
            pct = ((c_now - lower_now) / lower_now) * 100
            conditions_met.append(f"Price bouncing: {pct:.2f}% above lower band ({lower_now:.2f})")
        else:
            conditions_failed.append(f"Price still below lower band ({lower_now:.2f})")

        if kernel_rising:
            slope = yhat_now - yhat_prev
            conditions_met.append(
                f"Kernel rising/flat: {yhat_prev:.2f} → {yhat_now:.2f} (slope={slope:+.3f})"
            )
        else:
            conditions_failed.append(
                f"Kernel falling: {yhat_prev:.2f} → {yhat_now:.2f} — structural downtrend"
            )

        summary = (
            f"NW: yhat={yhat_now:.2f} | upper={upper_now:.2f} | "
            f"lower={lower_now:.2f} | MAE={mae:.2f}"
        )

        if near_lower and above_lower and kernel_rising:
            band_width = upper_now - lower_now
            bounce     = (c_now - lower_now) / band_width if band_width > 0 else 0.0
            confidence = round(min(0.60 + 0.25 * min(bounce * 4, 1.0), 0.87), 4)
            return Signal(
                signal_type="BUY",
                confidence=confidence,
                risk_score=0.28,
                expected_upside_pct=7.0,
                stop_loss_pct=4.0,
                target_pct=7.0,
                holding_days=7,
                conditions_met=conditions_met + [summary],
            )

        return Signal(
            signal_type="NONE",
            conditions_met=conditions_met,
            conditions_failed=conditions_failed + [summary],
        )

    def get_required_indicators(self) -> list[str]:
        return ["close"]
