"""
Stochastic RSI

Tobias Ehlers (2002). A second-order oscillator: applies Stochastic math to
RSI rather than price. This makes it more sensitive than either RSI or
Stochastic alone, and oscillates between 0 and 100 instead of 0–100 raw.

Algorithm:
  1. RSI(14) computed on close
  2. Stochastic of the RSI over 14 bars:
       stoch_rsi = (rsi − lowest_rsi_14) / (highest_rsi_14 − lowest_rsi_14)
  3. Smooth with two 3-bar SMAs:
       %K = SMA(stoch_rsi, 3) × 100
       %D = SMA(%K, 3)

  %K and %D oscillate 0–100.
  Oversold zone: < 20
  Overbought zone: > 80

BUY = %K crosses above %D from the oversold zone (< 20)
      AND price is above SMA(50) to avoid bottom-fishing in a downtrend
      AND RSI(14) > 30 (not in extreme panic — confirms reversal)
"""
import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe

_OVERSOLD = 20.0


class StochasticRSIStrategy(BaseStrategy):
    name = "Stochastic RSI"
    description = (
        "Ehlers' StochRSI(14,14,3,3): %K crosses above %D from oversold (<20), "
        "filtered by price above SMA50 and RSI>30. Second-order momentum reversal."
    )
    strategy_type = StrategyType.TECHNICAL
    timeframe     = Timeframe.DAILY
    min_holding_days = 3
    max_holding_days = 12
    weight           = 0.20

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        required = ["close", "sma_50", "rsi_14", "stoch_rsi_k", "stoch_rsi_d"]
        if len(df) < 40 or not all(c in df.columns for c in required):
            return Signal(signal_type="NONE", conditions_failed=["Insufficient data"])

        close  = df["close"]
        sma_50 = float(df["sma_50"].iloc[-1])
        rsi    = df["rsi_14"]

        k_now  = float(df["stoch_rsi_k"].iloc[-1])
        k_prev = float(df["stoch_rsi_k"].iloc[-2])
        d_now  = float(df["stoch_rsi_d"].iloc[-1])
        d_prev = float(df["stoch_rsi_d"].iloc[-2])
        rsi_now = float(rsi.iloc[-1])
        c_now   = float(close.iloc[-1])

        if any(pd.isna(x) for x in [k_now, d_now, sma_50]):
            return Signal(signal_type="NONE", conditions_failed=["StochRSI not ready"])

        # %K crosses above %D
        k_cross = k_prev <= d_prev and k_now > d_now

        # Cross occurred from oversold territory
        was_oversold = d_prev < _OVERSOLD or k_prev < _OVERSOLD

        # Trend filter
        above_sma50 = c_now > sma_50

        # RSI not in panic (at least starting to recover)
        rsi_recovering = rsi_now > 30

        conditions_met    = []
        conditions_failed = []

        if k_cross:
            conditions_met.append(
                f"StochRSI %K({k_now:.1f}) crossed above %D({d_now:.1f})"
            )
        else:
            conditions_failed.append(
                f"No %K/%D cross (K={k_now:.1f}, D={d_now:.1f})"
            )

        if was_oversold:
            conditions_met.append(
                f"Cross from oversold zone (K was {k_prev:.1f}, D was {d_prev:.1f} < {_OVERSOLD})"
            )
        else:
            conditions_failed.append(
                f"Not from oversold (K={k_prev:.1f}, D={d_prev:.1f}, need < {_OVERSOLD})"
            )

        if above_sma50:
            pct = ((c_now - sma_50) / sma_50) * 100
            conditions_met.append(f"Price {pct:.1f}% above SMA50 (uptrend intact)")
        else:
            conditions_failed.append("Price below SMA50 — downtrend, avoid")

        if rsi_recovering:
            conditions_met.append(f"RSI(14)={rsi_now:.1f} > 30 (not in extreme panic)")
        else:
            conditions_failed.append(f"RSI(14)={rsi_now:.1f} ≤ 30 (extreme oversold, wait)")

        if k_cross and was_oversold and above_sma50 and rsi_recovering:
            depth   = max(0, _OVERSOLD - min(k_prev, d_prev)) / _OVERSOLD
            confidence = round(min(0.62 + 0.20 * depth, 0.87), 4)
            return Signal(
                signal_type="BUY",
                confidence=confidence,
                risk_score=0.30,
                expected_upside_pct=8.0,
                stop_loss_pct=4.5,
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
        return ["close", "sma_50", "rsi_14", "stoch_rsi_k", "stoch_rsi_d"]
