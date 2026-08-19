"""
UT Bot Alerts (by Keevenv)

One of the most-followed indicators on TradingView. Core logic:
1. ATR Trailing Stop — a dynamic support/resistance line that flips direction
   when price closes on the other side.
2. HMA (Hull Moving Average) trend filter — price must be above HMA(50) for longs.

The trailing stop:
  nLoss = keyValue * ATR(atrPeriod)
  If close > prev_stop AND prev_close > prev_stop: stop = max(prev_stop, close - nLoss)
  If close < prev_stop AND prev_close < prev_stop: stop = min(prev_stop, close + nLoss)
  If close > prev_stop: stop = close - nLoss
  Else:                 stop = close + nLoss

BUY  = close crosses ABOVE the trailing stop (pos flips to +1) AND close > HMA(50)
"""
import numpy as np
import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe

_KEY_VALUE  = 1.0   # ATR sensitivity (Pine default)
_ATR_PERIOD = 10    # ATR period (Pine default)
_HMA_PERIOD = 50    # Trend filter


def _wma(series: pd.Series, period: int) -> pd.Series:
    w = np.arange(1, period + 1, dtype=float)
    return series.rolling(period).apply(lambda x: np.dot(x, w) / w.sum(), raw=True)


def _hma(series: pd.Series, period: int) -> pd.Series:
    half    = max(period // 2, 1)
    sqrt_p  = max(int(np.sqrt(period)), 1)
    raw     = 2 * _wma(series, half) - _wma(series, period)
    return _wma(raw, sqrt_p)


def _atr_trailing_stop(close: np.ndarray, atr: np.ndarray, key_value: float) -> np.ndarray:
    n_loss   = key_value * atr
    trailing = np.zeros(len(close))
    trailing[0] = close[0]
    for i in range(1, len(close)):
        c, pc, pt, nl = close[i], close[i - 1], trailing[i - 1], n_loss[i]
        if   c > pt and pc > pt: trailing[i] = max(pt, c - nl)
        elif c < pt and pc < pt: trailing[i] = min(pt, c + nl)
        elif c > pt:             trailing[i] = c - nl
        else:                    trailing[i] = c + nl
    return trailing


class UTBotStrategy(BaseStrategy):
    name = "UT Bot"
    description = (
        "ATR trailing stop that flips on close-side crosses, filtered by HMA(50) uptrend. "
        "BUY when price crosses above the trailing stop in an uptrend."
    )
    strategy_type = StrategyType.TECHNICAL
    timeframe     = Timeframe.DAILY
    min_holding_days = 3
    max_holding_days = 15
    weight           = 0.20

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        required = ["close", "high", "low", "atr_14"]
        if len(df) < _HMA_PERIOD + 20 or not all(c in df.columns for c in required):
            return Signal(signal_type="NONE", conditions_failed=["Insufficient data"])

        close = df["close"]
        atr   = df["atr_14"].values   # Use precomputed ATR(14) ≈ ATR(10)

        trailing = _atr_trailing_stop(close.values, atr, _KEY_VALUE)
        hma      = _hma(close, _HMA_PERIOD)

        c_now   = float(close.iloc[-1])
        c_prev  = float(close.iloc[-2])
        ts_now  = trailing[-1]
        ts_prev = trailing[-2]
        hma_now = float(hma.iloc[-1])

        if any(pd.isna(x) for x in [hma_now]):
            return Signal(signal_type="NONE", conditions_failed=["HMA not ready"])

        # BUY: close crossed above the trailing stop this bar
        crossed_above = c_prev <= ts_prev and c_now > ts_now
        above_hma     = c_now > hma_now

        conditions_met    = []
        conditions_failed = []

        if crossed_above:
            conditions_met.append(f"Price crossed above ATR trailing stop ({ts_now:.2f})")
        else:
            gap = ((c_now - ts_now) / ts_now) * 100
            conditions_failed.append(f"No crossover (price {gap:+.1f}% vs trailing stop)")

        if above_hma:
            conditions_met.append(f"Price {c_now:.2f} above HMA({_HMA_PERIOD})={hma_now:.2f}")
        else:
            conditions_failed.append(f"Price below HMA({_HMA_PERIOD})={hma_now:.2f}")

        if crossed_above and above_hma:
            gap_pct = ((c_now - ts_now) / ts_now) * 100
            confidence = round(min(0.62 + gap_pct * 0.02, 0.88), 4)
            return Signal(
                signal_type="BUY",
                confidence=confidence,
                risk_score=0.32,
                expected_upside_pct=9.0,
                stop_loss_pct=5.0,
                target_pct=9.0,
                holding_days=10,
                conditions_met=conditions_met,
            )

        return Signal(signal_type="NONE", conditions_met=conditions_met, conditions_failed=conditions_failed)

    def get_required_indicators(self) -> list[str]:
        return ["close", "high", "low", "atr_14"]
