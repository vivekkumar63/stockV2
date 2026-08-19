"""
QQE Mod (Quantitative Qualitative Estimation Mod)

Port of the Mihkel Oot Pine Script (CC BY-NC-SA 4.0).
Two QQE lines (fast + slow) each built from a smoothed RSI with an
ATR-style trailing stop applied ON the RSI itself:

1. RSI(period) → smooth with EMA(5)
2. ATR of the smoothed RSI:
     AtrRsi = |rsi_ma - rsi_ma[1]|
     MaAtr  = EMA(AtrRsi, wilders)    where wilders = period*2 - 1
     dar    = EMA(MaAtr,  wilders) * SF
3. QQE trailing stop on rsi_ma:
     if rsi_ma >= qqe[prev]: qqe = max(qqe[prev], rsi_ma - dar)
     else:                   qqe = min(qqe[prev], rsi_ma + dar)

Fast : RSI(6),  SF=4.238
Slow : RSI(14), SF=4.238

BUY = fast rsi_ma crossed above fast qqe (within 2 bars)
      AND fast rsi_ma > 50  (fast QQE in bullish zone)
      AND slow rsi_ma > 50  (macro trend bullish)
      AND slow rsi_ma > slow qqe  (slow QQE also confirming)
"""
import numpy as np
import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe

_FAST_RSI  = 6
_FAST_SF   = 4.238
_SLOW_RSI  = 14
_SLOW_SF   = 4.238
_SMOOTHING = 5
_THRESHOLD = 50.0


def _rsi_series(close: pd.Series, period: int) -> pd.Series:
    delta = close.diff()
    gain  = delta.clip(lower=0).ewm(com=period - 1, adjust=False).mean()
    loss  = (-delta.clip(upper=0)).ewm(com=period - 1, adjust=False).mean().clip(lower=1e-10)
    return (100 - 100 / (1 + gain / loss)).fillna(50)


def _qqe(close: pd.Series, rsi_period: int, sf: float,
         smoothing: int = _SMOOTHING) -> tuple[np.ndarray, np.ndarray]:
    """Returns (qqe_line, rsi_ma) as numpy arrays."""
    rsi    = _rsi_series(close, rsi_period)
    rsi_ma = rsi.ewm(span=smoothing, adjust=False).mean()

    wilders = rsi_period * 2 - 1
    atr_rsi = rsi_ma.diff().abs()
    ma_atr  = atr_rsi.ewm(com=wilders - 1, adjust=False).mean()
    dar     = ma_atr.ewm(com=wilders - 1, adjust=False).mean() * sf

    rsi_arr = rsi_ma.values
    dar_arr = dar.values
    n       = len(rsi_arr)

    qqe_arr = np.zeros(n)
    qqe_arr[0] = rsi_arr[0]

    for i in range(1, n):
        r = rsi_arr[i]
        d = float(dar_arr[i]) if not np.isnan(dar_arr[i]) else 0.0
        prev = qqe_arr[i - 1]
        if r >= prev:
            qqe_arr[i] = max(prev, r - d)
        else:
            qqe_arr[i] = min(prev, r + d)

    return qqe_arr, rsi_arr


class QQEModStrategy(BaseStrategy):
    name = "QQE Mod"
    description = (
        "Two QQE trailing stops on smoothed RSI: fast RSI(6)/SF4.2 and slow "
        "RSI(14)/SF4.2. BUY when fast RSI crosses above its QQE line and both "
        "fast and slow RSI are above 50."
    )
    strategy_type = StrategyType.TECHNICAL
    timeframe     = Timeframe.DAILY
    min_holding_days = 3
    max_holding_days = 12
    weight           = 0.20

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 50 or "close" not in df.columns:
            return Signal(signal_type="NONE", conditions_failed=["Insufficient data"])

        close = df["close"]

        qqe_fast, rsi_fast = _qqe(close, _FAST_RSI, _FAST_SF)
        qqe_slow, rsi_slow = _qqe(close, _SLOW_RSI, _SLOW_SF)

        rf_now  = float(rsi_fast[-1])
        rf_prev = float(rsi_fast[-2])
        rf_prev2 = float(rsi_fast[-3])
        qf_now  = float(qqe_fast[-1])
        qf_prev = float(qqe_fast[-2])
        qf_prev2 = float(qqe_fast[-3])

        rs_now  = float(rsi_slow[-1])
        qs_now  = float(qqe_slow[-1])

        if any(np.isnan(x) for x in [rf_now, qf_now, rs_now, qs_now]):
            return Signal(signal_type="NONE", conditions_failed=["QQE not ready"])

        # Fast RSI crossed above its QQE line within last 2 bars (slight lookback for robustness)
        fast_cross = (
            (rf_prev <= qf_prev and rf_now  > qf_now) or   # current bar
            (rf_prev2 <= qf_prev2 and rf_prev > qf_prev)   # previous bar
        )
        fast_above_qqe = rf_now > qf_now          # currently in bullish mode
        fast_bullish   = rf_now > _THRESHOLD       # above midline
        slow_bullish   = rs_now > _THRESHOLD       # macro trend up
        slow_above_qqe = rs_now > qs_now           # slow QQE confirming

        conditions_met    = []
        conditions_failed = []

        if fast_cross or fast_above_qqe:
            tag = "crossed" if fast_cross else "above"
            conditions_met.append(
                f"Fast RSI({_FAST_RSI})={rf_now:.1f} {tag} its QQE({qf_now:.1f})"
            )
        else:
            conditions_failed.append(
                f"Fast RSI({_FAST_RSI})={rf_now:.1f} below QQE({qf_now:.1f})"
            )

        if fast_bullish:
            conditions_met.append(f"Fast RSI={rf_now:.1f} > {_THRESHOLD} (bullish momentum)")
        else:
            conditions_failed.append(f"Fast RSI={rf_now:.1f} < {_THRESHOLD}")

        if slow_bullish:
            conditions_met.append(f"Slow RSI({_SLOW_RSI})={rs_now:.1f} > {_THRESHOLD} (macro trend up)")
        else:
            conditions_failed.append(f"Slow RSI({_SLOW_RSI})={rs_now:.1f} < {_THRESHOLD} (downtrend)")

        if slow_above_qqe:
            conditions_met.append(f"Slow RSI({rs_now:.1f}) above slow QQE({qs_now:.1f})")
        else:
            conditions_failed.append(f"Slow RSI below slow QQE — trend not confirmed")

        if (fast_cross or fast_above_qqe) and fast_bullish and slow_bullish and slow_above_qqe:
            # Confidence scales with distance of both RSIs above their levels
            fast_margin = min((rf_now - _THRESHOLD) / 25, 1.0)
            slow_margin = min((rs_now - _THRESHOLD) / 25, 1.0)
            confidence  = round(min(0.60 + 0.15 * fast_margin + 0.15 * slow_margin, 0.88), 4)
            return Signal(
                signal_type="BUY",
                confidence=confidence,
                risk_score=0.28,
                expected_upside_pct=8.5,
                stop_loss_pct=4.5,
                target_pct=8.5,
                holding_days=8,
                conditions_met=conditions_met,
            )

        return Signal(
            signal_type="NONE",
            conditions_met=conditions_met,
            conditions_failed=conditions_failed,
        )

    def get_required_indicators(self) -> list[str]:
        return ["close"]
