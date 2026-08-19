"""
Squeeze Momentum (LazyBear)

One of TradingView's most-used indicators. Core idea:
- When Bollinger Bands contract INSIDE Keltner Channels, the market is "coiling"
  (low volatility compression). This is the squeeze ON state.
- When BB expands beyond KC, the coil is released. Direction is determined by
  the linear regression momentum value.

Squeeze ON  = BB lower > KC lower  AND  BB upper < KC upper
Squeeze OFF = opposite — volatility is expanding again

Momentum value = linreg(close − avg(midpoint_HL, SMA(close, 20)), 20)
  > 0 and rising = bull momentum  → BUY when squeeze just fired
  < 0 or falling = bear / neutral

BUY = squeeze just released (ON→OFF this bar) AND momentum > 0 AND momentum rising
"""
import numpy as np
import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe

_LENGTH  = 20
_MULT_BB = 2.0
_MULT_KC = 1.5


def _wilder_atr(high: np.ndarray, low: np.ndarray, close: np.ndarray,
                period: int) -> np.ndarray:
    n = len(high)
    tr = np.zeros(n)
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        tr[i] = max(high[i] - low[i],
                    abs(high[i] - close[i - 1]),
                    abs(low[i]  - close[i - 1]))
    atr = pd.Series(tr).ewm(com=period - 1, adjust=False).mean().values
    return atr


def _linreg_val(series: pd.Series, period: int) -> pd.Series:
    """Rolling linear regression value at offset-0 (current bar). Matches Pine ta.linreg."""
    arr = series.values
    out = np.full(len(arr), np.nan)
    x   = np.arange(period, dtype=float)
    for i in range(period - 1, len(arr)):
        y = arr[i - period + 1: i + 1]
        if np.any(np.isnan(y)):
            continue
        coeffs  = np.polyfit(x, y, 1)
        out[i]  = np.polyval(coeffs, period - 1)   # value at rightmost bar
    return pd.Series(out, index=series.index)


class SqueezeMomentumStrategy(BaseStrategy):
    name = "Squeeze Momentum"
    description = (
        "LazyBear's Squeeze Momentum: BB inside KC = squeeze coiling; "
        "BB expansion + positive/rising linreg momentum = BUY."
    )
    strategy_type = StrategyType.TECHNICAL
    timeframe     = Timeframe.DAILY
    min_holding_days = 3
    max_holding_days = 15
    weight           = 0.20

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        required = ["close", "high", "low"]
        if len(df) < _LENGTH + 15 or not all(c in df.columns for c in required):
            return Signal(signal_type="NONE", conditions_failed=["Insufficient data"])

        close = df["close"]
        high  = df["high"].values
        low   = df["low"].values
        cl    = close.values

        # ── Bollinger Bands (BB) ─────────────────────────────────────────────────
        sma    = close.rolling(_LENGTH).mean()
        std    = close.rolling(_LENGTH).std(ddof=0)
        bb_upper = sma + _MULT_BB * std
        bb_lower = sma - _MULT_BB * std

        # ── Keltner Channel (KC): same SMA ± ATR (Wilder's) ─────────────────────
        atr_kc   = pd.Series(_wilder_atr(high, low, cl, _LENGTH), index=df.index)
        kc_upper = sma + _MULT_KC * atr_kc
        kc_lower = sma - _MULT_KC * atr_kc

        # ── Squeeze detection ────────────────────────────────────────────────────
        sqz_on = (bb_lower > kc_lower) & (bb_upper < kc_upper)

        # ── Momentum value = linreg of delta ────────────────────────────────────
        highest_high = df["high"].rolling(_LENGTH).max()
        lowest_low   = df["low"].rolling(_LENGTH).min()
        delta = close - ((highest_high + lowest_low) / 2 + sma) / 2
        val   = _linreg_val(delta, _LENGTH)

        sqz_now  = bool(sqz_on.iloc[-1])
        sqz_prev = bool(sqz_on.iloc[-2])
        val_now  = float(val.iloc[-1])
        val_prev = float(val.iloc[-2])

        if pd.isna(val_now) or pd.isna(val_prev):
            return Signal(signal_type="NONE", conditions_failed=["Momentum not ready"])

        # BUY: squeeze just fired (ON → OFF) + momentum positive and rising
        squeeze_fired = sqz_prev and not sqz_now
        momentum_up   = val_now > 0 and val_now > val_prev

        conditions_met    = []
        conditions_failed = []

        if squeeze_fired:
            conditions_met.append("Squeeze released: BB expanded beyond KC (coil fired)")
        elif sqz_now:
            conditions_failed.append("Squeeze still ON — BB inside KC, waiting for expansion")
        else:
            conditions_failed.append("No fresh squeeze release (already expanded)")

        if val_now > 0:
            conditions_met.append(f"Momentum positive (linreg={val_now:.3f})")
        else:
            conditions_failed.append(f"Momentum negative (linreg={val_now:.3f})")

        if val_now > val_prev:
            conditions_met.append(f"Momentum rising ({val_prev:.3f} → {val_now:.3f})")
        else:
            conditions_failed.append(f"Momentum declining ({val_prev:.3f} → {val_now:.3f})")

        if squeeze_fired and momentum_up:
            price = float(close.iloc[-1])
            strength = min(abs(val_now) / max(price * 0.005, 0.001), 1.0)
            confidence = round(min(0.62 + 0.20 * strength, 0.88), 4)
            return Signal(
                signal_type="BUY",
                confidence=confidence,
                risk_score=0.30,
                expected_upside_pct=9.0,
                stop_loss_pct=4.5,
                target_pct=9.0,
                holding_days=8,
                conditions_met=conditions_met,
            )

        return Signal(
            signal_type="NONE",
            conditions_met=conditions_met,
            conditions_failed=conditions_failed,
        )

    def get_required_indicators(self) -> list[str]:
        return ["close", "high", "low"]
