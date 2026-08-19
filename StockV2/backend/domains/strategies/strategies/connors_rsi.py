"""
Connors RSI (CRSI) — Larry Connors & Cesar Alvarez (2012)

A composite RSI with three independent components measuring different
aspects of mean reversion in high-quality trending stocks:

Component 1 — Price RSI(3):
  Short-term 3-period RSI. Fires very quickly at oversold conditions.

Component 2 — Streak RSI:
  Count consecutive up/down days (+1 per up, −1 per down).
  Apply RSI(2) to the streak series.
  This captures HOW LONG the stock has been in a one-directional move.

Component 3 — Percent Rank (100 periods):
  What % of the last 100 daily returns are smaller than today's return?
  = 0 means today is the worst day in 100 days.
  = 100 means today is the best day in 100 days.

CRSI = (RSI3 + StreakRSI + PercentRank) / 3

Connors' research: CRSI < 10 → extreme oversold, very high win rate on next 5 days
               CRSI < 20 → oversold, solid edge

BUY = CRSI < 20 (composite oversold)
      AND price above SMA(200) — only in quality uptrending stocks
      AND close > close[-5] (not in a full collapse, price starting to stabilize)
"""
import numpy as np
import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe

_CRSI_OVERSOLD = 20
_CRSI_EXTREME  = 10


def _rsi_series(series: pd.Series, period: int) -> pd.Series:
    delta = series.diff()
    gain  = delta.clip(lower=0).ewm(com=period - 1, adjust=False).mean()
    loss  = (-delta.clip(upper=0)).ewm(com=period - 1, adjust=False).mean().clip(lower=1e-10)
    return (100 - 100 / (1 + gain / loss)).fillna(50)


def _streak(close: pd.Series) -> pd.Series:
    """Consecutive up/down streak count."""
    cl  = close.values
    n   = len(cl)
    s   = np.zeros(n)
    for i in range(1, n):
        if cl[i] > cl[i - 1]:
            s[i] = max(s[i - 1], 0) + 1
        elif cl[i] < cl[i - 1]:
            s[i] = min(s[i - 1], 0) - 1
        # equal → streak resets to 0
    return pd.Series(s, index=close.index)


def _pct_rank_now(close: pd.Series, period: int = 100) -> float:
    """% of last `period` daily returns smaller than today's return."""
    pct = close.pct_change()
    arr = pct.values
    if len(arr) < period + 1:
        return 50.0
    today  = arr[-1]
    window = arr[-period - 1:-1]
    valid  = window[~np.isnan(window)]
    if len(valid) == 0 or np.isnan(today):
        return 50.0
    return float(np.sum(valid < today) / len(valid) * 100)


class ConnorsRSIStrategy(BaseStrategy):
    name = "Connors RSI"
    description = (
        "CRSI = (RSI3 + StreakRSI2 + PercentRank100) / 3. "
        "BUY when composite oversold (<20) in stocks above SMA200."
    )
    strategy_type = StrategyType.TECHNICAL
    timeframe     = Timeframe.DAILY
    min_holding_days = 3
    max_holding_days = 10
    weight           = 0.20

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 110 or "close" not in df.columns:
            return Signal(signal_type="NONE", conditions_failed=["Insufficient data (need 110+ bars)"])

        close = df["close"]

        # ── Three components ─────────────────────────────────────────────────────
        rsi3       = _rsi_series(close, 3)
        streak_ser = _streak(close)
        streak_rsi = _rsi_series(streak_ser, 2)
        pct_rank   = _pct_rank_now(close, 100)

        rsi3_now       = float(rsi3.iloc[-1])
        streak_rsi_now = float(streak_rsi.iloc[-1])

        if any(pd.isna(x) for x in [rsi3_now, streak_rsi_now]):
            return Signal(signal_type="NONE", conditions_failed=["CRSI not ready"])

        crsi = (rsi3_now + streak_rsi_now + pct_rank) / 3

        # ── SMA(200) quality filter ───────────────────────────────────────────
        sma_200    = float(close.rolling(200).mean().iloc[-1]) if len(df) >= 200 else None
        c_now      = float(close.iloc[-1])
        above_200  = (sma_200 is None) or (c_now > sma_200)

        # ── Price starting to stabilize (5-day stabilization check) ──────────
        c_5ago    = float(close.iloc[-6])
        stabilizing = c_now > c_5ago   # price higher than 5 days ago

        conditions_met    = []
        conditions_failed = []

        if crsi < _CRSI_EXTREME:
            conditions_met.append(
                f"CRSI={crsi:.1f} EXTREME oversold (<{_CRSI_EXTREME}) — "
                f"RSI3={rsi3_now:.1f} | StrRSI={streak_rsi_now:.1f} | PctRank={pct_rank:.1f}"
            )
        elif crsi < _CRSI_OVERSOLD:
            conditions_met.append(
                f"CRSI={crsi:.1f} oversold (<{_CRSI_OVERSOLD}) — "
                f"RSI3={rsi3_now:.1f} | StrRSI={streak_rsi_now:.1f} | PctRank={pct_rank:.1f}"
            )
        else:
            conditions_failed.append(
                f"CRSI={crsi:.1f} not oversold (need <{_CRSI_OVERSOLD}) — "
                f"RSI3={rsi3_now:.1f} | StrRSI={streak_rsi_now:.1f} | PctRank={pct_rank:.1f}"
            )

        if above_200:
            if sma_200:
                pct = ((c_now - sma_200) / sma_200) * 100
                conditions_met.append(f"Price {pct:.1f}% above SMA(200) — quality uptrend")
            else:
                conditions_met.append("SMA(200) not computed — filter skipped")
        else:
            conditions_failed.append(f"Price below SMA(200) ({sma_200:.2f}) — avoid bottom-fishing")

        if stabilizing:
            pct = ((c_now - c_5ago) / c_5ago) * 100
            conditions_met.append(f"Price stabilizing: {pct:+.1f}% vs 5 days ago")
        else:
            conditions_failed.append("Price still falling vs 5 days ago — not yet stabilizing")

        if crsi < _CRSI_OVERSOLD and above_200 and stabilizing:
            extreme_bonus = 0.10 if crsi < _CRSI_EXTREME else 0.0
            depth = max(0, _CRSI_OVERSOLD - crsi) / _CRSI_OVERSOLD
            confidence = round(min(0.62 + 0.18 * depth + extreme_bonus, 0.88), 4)
            return Signal(
                signal_type="BUY",
                confidence=confidence,
                risk_score=0.25,
                expected_upside_pct=7.0,
                stop_loss_pct=4.0,
                target_pct=7.0,
                holding_days=5,
                conditions_met=conditions_met,
            )

        return Signal(
            signal_type="NONE",
            conditions_met=conditions_met,
            conditions_failed=conditions_failed,
        )

    def get_required_indicators(self) -> list[str]:
        return ["close"]
