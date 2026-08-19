"""
Chaikin Money Flow (CMF) — Marc Chaikin

CMF measures the amount of Money Flow Volume over a set period.
The key insight: WHERE price closes within the bar's range tells you who won.

Money Flow Multiplier (MFM):
  = (close − low − (high − close)) / (high − low)
  = (2·close − high − low) / (high − low)
  Range: −1 (close at low, bears won) to +1 (close at high, bulls won)

Money Flow Volume (MFV) = MFM × volume

CMF = sum(MFV, N) / sum(volume, N)   [N = 20 bars]
  > 0 = more money flowing in (accumulation)
  < 0 = more money flowing out (distribution)
  > +0.25 = strong accumulation (institutional buying)
  < −0.25 = strong distribution (institutional selling)

BUY = CMF crosses above 0 (confirmed buying pressure)
      AND CMF > 0 for at least current bar (not just a flicker)
      AND Price above SMA(50) (uptrend context)
      AND RSI(14) > 40 (momentum not dead)
"""
import numpy as np
import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe

_CMF_PERIOD = 20


class ChaikinMoneyFlowStrategy(BaseStrategy):
    name = "Chaikin Money Flow"
    description = (
        "CMF(20) zero-cross: where close lands in the bar range × volume reveals "
        "institutional accumulation. BUY when CMF turns positive + above SMA50."
    )
    strategy_type = StrategyType.TECHNICAL
    timeframe     = Timeframe.DAILY
    min_holding_days = 4
    max_holding_days = 18
    weight           = 0.20

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        required = ["close", "high", "low", "volume", "sma_50", "rsi_14"]
        if len(df) < _CMF_PERIOD + 5 or not all(c in df.columns for c in required):
            return Signal(signal_type="NONE", conditions_failed=["Insufficient data"])

        close  = df["close"]
        high   = df["high"]
        low    = df["low"]
        volume = df["volume"]

        # ── CMF ────────────────────────────────────────────────────────────────
        hl_range = (high - low).clip(lower=1e-10)
        mfm = (2 * close - high - low) / hl_range
        mfv = mfm * volume

        cmf = (mfv.rolling(_CMF_PERIOD).sum() /
               volume.rolling(_CMF_PERIOD).sum().clip(lower=1e-10))

        cmf_now  = float(cmf.iloc[-1])
        cmf_prev = float(cmf.iloc[-2])
        sma_50   = float(df["sma_50"].iloc[-1])
        rsi      = float(df["rsi_14"].iloc[-1])
        c_now    = float(close.iloc[-1])

        if any(pd.isna(x) for x in [cmf_now, cmf_prev, sma_50, rsi]):
            return Signal(signal_type="NONE", conditions_failed=["CMF not ready"])

        # CMF crossed zero upward (from negative to positive)
        cmf_cross_up = cmf_prev <= 0 and cmf_now > 0

        # Strong accumulation (above 0.1 threshold)
        strong_accumulation = cmf_now > 0.10

        above_sma50 = c_now > sma_50
        rsi_ok      = rsi > 40

        conditions_met    = []
        conditions_failed = []

        if cmf_cross_up:
            conditions_met.append(
                f"CMF zero-cross: {cmf_prev:.3f} → {cmf_now:.3f} (money flowing IN)"
            )
        elif cmf_now > 0:
            conditions_met.append(
                f"CMF positive: {cmf_now:.3f} (accumulation ongoing)"
            )
        else:
            conditions_failed.append(
                f"CMF={cmf_now:.3f} negative (distribution/outflow)"
            )

        if strong_accumulation:
            conditions_met.append(
                f"Strong accumulation: CMF={cmf_now:.3f} > 0.10 (institutional buying)"
            )
        elif cmf_now > 0:
            conditions_met.append(f"Mild accumulation: CMF={cmf_now:.3f}")

        if above_sma50:
            pct = ((c_now - sma_50) / sma_50) * 100
            conditions_met.append(f"Price {pct:.1f}% above SMA50 (uptrend)")
        else:
            conditions_failed.append("Price below SMA50 — distribution in downtrend")

        if rsi_ok:
            conditions_met.append(f"RSI(14)={rsi:.1f} > 40 (momentum alive)")
        else:
            conditions_failed.append(f"RSI(14)={rsi:.1f} ≤ 40 (weak momentum)")

        if (cmf_cross_up or cmf_now > 0) and above_sma50 and rsi_ok:
            intensity  = min(cmf_now / 0.3, 1.0)    # max at CMF=0.30
            cross_bonus = 0.08 if cmf_cross_up else 0.0
            confidence  = round(min(0.58 + 0.22 * intensity + cross_bonus, 0.88), 4)
            return Signal(
                signal_type="BUY",
                confidence=confidence,
                risk_score=0.30,
                expected_upside_pct=9.0,
                stop_loss_pct=4.5,
                target_pct=9.0,
                holding_days=10,
                conditions_met=conditions_met,
            )

        return Signal(
            signal_type="NONE",
            conditions_met=conditions_met,
            conditions_failed=conditions_failed,
        )

    def get_required_indicators(self) -> list[str]:
        return ["close", "high", "low", "volume", "sma_50", "rsi_14"]
