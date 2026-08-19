"""
Chandelier Exit (Chuck LeBeau / Alexander Elder)

Named after a chandelier because it "hangs down from the ceiling" of the
highest recent high. Unlike SuperTrend which uses midline + ATR, the
Chandelier Exit hangs from the HIGHEST CLOSE (not the midline) —
making it a more responsive trailing stop for confirmed trends.

Chandelier Exit Long  = highest close(22) − ATR(22) × 3.0
Chandelier Exit Short = lowest  close(22) + ATR(22) × 3.0

A classic "Long" signal fires when:
  price crosses ABOVE the Chandelier Short line (new uptrend)
  — because the short stop just got taken out, signaling the bears lost.

Or as a trend continuation: staying above Chandelier Long confirms trend.

BUY signal:
  1. Price recently crossed ABOVE Chandelier Exit Long (within last 2 bars)
     — the uptrend just confirmed, trailing stop now below us
  2. Price is above EMA(22) — trend confirmation
  3. Close > Chandelier Long (currently in "long" mode, not stopped out)
"""
import numpy as np
import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe

_PERIOD    = 22
_MULT      = 3.0


def _wilder_atr(high: np.ndarray, low: np.ndarray, close: np.ndarray,
                period: int) -> np.ndarray:
    n  = len(high)
    tr = np.zeros(n)
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        tr[i] = max(high[i] - low[i],
                    abs(high[i] - close[i - 1]),
                    abs(low[i]  - close[i - 1]))
    return pd.Series(tr).ewm(com=period - 1, adjust=False).mean().values


class ChandelierExitStrategy(BaseStrategy):
    name = "Chandelier Exit"
    description = (
        "LeBeau's Chandelier Exit: highest close(22) − ATR(22)×3. "
        "BUY when price crosses above the exit line (fresh uptrend confirmation)."
    )
    strategy_type = StrategyType.TECHNICAL
    timeframe     = Timeframe.DAILY
    min_holding_days = 4
    max_holding_days = 20
    weight           = 0.20

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        required = ["close", "high", "low"]
        if len(df) < _PERIOD + 10 or not all(c in df.columns for c in required):
            return Signal(signal_type="NONE", conditions_failed=["Insufficient data"])

        close = df["close"]
        high  = df["high"].values
        low   = df["low"].values
        cl    = close.values

        atr = _wilder_atr(high, low, cl, _PERIOD)

        # Chandelier Long: hangs from highest close
        highest_close = close.rolling(_PERIOD).max().values
        chandelier    = highest_close - _MULT * atr

        # EMA(22) for trend filter
        ema_22 = close.ewm(span=_PERIOD, adjust=False).mean()

        ch_now  = float(chandelier[-1])
        ch_prev = float(chandelier[-2])
        c_now   = float(cl[-1])
        c_prev  = float(cl[-2])
        ema_now = float(ema_22.iloc[-1])

        if any(np.isnan(x) for x in [ch_now, ch_prev, ema_now]):
            return Signal(signal_type="NONE", conditions_failed=["Chandelier not ready"])

        # Price just crossed above the Chandelier Long line (within 2 bars)
        fresh_cross = (
            (c_prev <= ch_prev and c_now > ch_now) or     # current bar cross
            (float(cl[-3]) <= float(chandelier[-3]) and c_prev > ch_prev)  # prev bar cross
        )

        # Currently above Chandelier (in long mode)
        above_chandelier = c_now > ch_now

        # Above EMA(22) — trend filter
        above_ema = c_now > ema_now

        conditions_met    = []
        conditions_failed = []

        if fresh_cross:
            conditions_met.append(
                f"Price crossed above Chandelier Exit ({c_now:.2f} > {ch_now:.2f}) — uptrend started"
            )
        elif above_chandelier:
            gap = ((c_now - ch_now) / ch_now) * 100
            conditions_met.append(
                f"Price {gap:.1f}% above Chandelier Exit ({ch_now:.2f}) — trend intact"
            )
        else:
            conditions_failed.append(
                f"Price ({c_now:.2f}) below Chandelier ({ch_now:.2f}) — stopped out"
            )

        if above_ema:
            pct = ((c_now - ema_now) / ema_now) * 100
            conditions_met.append(f"Price {pct:.1f}% above EMA({_PERIOD}) ({ema_now:.2f})")
        else:
            conditions_failed.append(f"Price below EMA({_PERIOD}) ({ema_now:.2f})")

        if above_chandelier and above_ema:
            recency   = 1.0 if fresh_cross else 0.4
            gap_pct   = (c_now - ch_now) / ch_now
            confidence = round(min(0.60 + 0.20 * recency + 0.10 * min(gap_pct * 10, 1.0), 0.88), 4)
            return Signal(
                signal_type="BUY",
                confidence=confidence,
                risk_score=0.28,
                expected_upside_pct=10.0,
                stop_loss_pct=5.0,
                target_pct=10.0,
                holding_days=12,
                conditions_met=conditions_met + [
                    f"ATR({_PERIOD})={float(atr[-1]):.2f} | Chandelier={ch_now:.2f}"
                ],
            )

        return Signal(
            signal_type="NONE",
            conditions_met=conditions_met,
            conditions_failed=conditions_failed,
        )

    def get_required_indicators(self) -> list[str]:
        return ["close", "high", "low"]
