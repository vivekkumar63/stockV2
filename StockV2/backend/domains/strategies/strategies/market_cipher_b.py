"""
Market Cipher B (VuManChu Cipher B)

One of TradingView's most-followed paid indicators, open-source version.
Core signals:
1. Wave Trend (9, 13) on HLC3 — momentum oscillator measuring deviation from EMA
2. Blue dot  = WT1 crosses ABOVE WT2 from deeply oversold zone (< -53)
3. Red dot   = WT1 crosses BELOW WT2 from overbought (> +53) [ignored here]
4. RSI-MFI   = (RSI(close - open, 60) - 50) * 150 — money flow confirmation

The oversold crossover is the institutional "capitulation reversal" pattern.
When WT2 dips below -53 then WT1 crosses WT2 upward, big money is re-entering.

BUY = WT1 crosses above WT2 AND WT2 was below -53 at time of cross
      AND RSI-MFI > -20 (money flow not deeply negative)
"""
import numpy as np
import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe

_WT_N1    = 9     # Channel length (EMA)
_WT_N2    = 13    # Average length (EMA of CI)
_OVERSOLD = -53   # WT oversold threshold


def _wave_trend(hlc3: pd.Series, n1: int, n2: int) -> tuple[pd.Series, pd.Series]:
    """WT1 = EMA of CI, WT2 = SMA(WT1, 4). Matches Pine ml.n_wt exactly."""
    ema1 = hlc3.ewm(span=n1, adjust=False).mean()
    diff = hlc3 - ema1
    ema2 = diff.abs().ewm(span=n1, adjust=False).mean().clip(lower=1e-10)
    ci   = diff / (0.015 * ema2)
    wt1  = ci.ewm(span=n2, adjust=False).mean()
    wt2  = wt1.rolling(4).mean()
    return wt1, wt2


def _rsi_series(series: pd.Series, period: int) -> pd.Series:
    delta = series.diff()
    gain  = delta.clip(lower=0).ewm(com=period - 1, adjust=False).mean()
    loss  = (-delta.clip(upper=0)).ewm(com=period - 1, adjust=False).mean().clip(lower=1e-10)
    return (100 - 100 / (1 + gain / loss)).fillna(50)


class MarketCipherBStrategy(BaseStrategy):
    name = "Market Cipher B"
    description = (
        "VuManChu Cipher B: WaveTrend(9,13) crossover from oversold (<-53), "
        "confirmed by RSI-MFI money flow. Blue dot institutional reversal setup."
    )
    strategy_type = StrategyType.TECHNICAL
    timeframe     = Timeframe.DAILY
    min_holding_days = 3
    max_holding_days = 12
    weight           = 0.20

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        required = ["close", "high", "low", "open"]
        if len(df) < 30 or not all(c in df.columns for c in required):
            return Signal(signal_type="NONE", conditions_failed=["Insufficient data"])

        close = df["close"]
        high  = df["high"]
        low   = df["low"]
        open_ = df["open"]
        hlc3  = (high + low + close) / 3

        wt1, wt2 = _wave_trend(hlc3, _WT_N1, _WT_N2)

        # RSI-MFI: momentum of close−open (body direction) over 60 bars, normalized
        rsimfi = (_rsi_series(close - open_, 60) - 50) * 150

        wt1_now  = float(wt1.iloc[-1])
        wt1_prev = float(wt1.iloc[-2])
        wt2_now  = float(wt2.iloc[-1])
        wt2_prev = float(wt2.iloc[-2])
        rsimfi_now = float(rsimfi.iloc[-1])

        if any(pd.isna(x) for x in [wt1_now, wt2_now, rsimfi_now]):
            return Signal(signal_type="NONE", conditions_failed=["Indicators not ready"])

        # WT1 crosses above WT2 (Blue dot trigger)
        wt_cross_up = wt1_prev <= wt2_prev and wt1_now > wt2_now

        # Cross originated from oversold zone (WT2 was < -53 at time of cross)
        from_oversold = wt2_prev < _OVERSOLD or wt1_prev < _OVERSOLD

        # Money flow not deeply negative
        money_flow_ok = rsimfi_now > -20

        conditions_met    = []
        conditions_failed = []

        if wt_cross_up:
            conditions_met.append(
                f"WT crossover: WT1({wt1_now:.1f}) crossed above WT2({wt2_now:.1f})"
            )
        else:
            conditions_failed.append(
                f"No WT crossover (WT1={wt1_now:.1f} vs WT2={wt2_now:.1f})"
            )

        if from_oversold:
            conditions_met.append(
                f"Cross from oversold zone (WT2={wt2_prev:.1f} < {_OVERSOLD}) — blue dot"
            )
        else:
            conditions_failed.append(
                f"Not from oversold (WT2={wt2_prev:.1f}, needs < {_OVERSOLD})"
            )

        if money_flow_ok:
            conditions_met.append(f"RSI-MFI={rsimfi_now:.1f} > -20 (money flow OK)")
        else:
            conditions_failed.append(f"RSI-MFI={rsimfi_now:.1f} ≤ -20 (negative money flow)")

        if wt_cross_up and from_oversold and money_flow_ok:
            # Deeper oversold → more violent reversal → higher conviction
            oversold_depth = max(0.0, min((-wt2_prev - 53) / 47, 1.0))
            confidence = round(min(0.60 + 0.22 * oversold_depth, 0.88), 4)
            return Signal(
                signal_type="BUY",
                confidence=confidence,
                risk_score=0.33,
                expected_upside_pct=8.0,
                stop_loss_pct=5.0,
                target_pct=8.0,
                holding_days=7,
                conditions_met=conditions_met,
            )

        return Signal(
            signal_type="NONE",
            conditions_met=conditions_met,
            conditions_failed=conditions_failed,
        )

    def get_required_indicators(self) -> list[str]:
        return ["close", "high", "low", "open"]
