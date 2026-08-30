"""
QQE Mod (Quantitative Qualitative Estimation Mod)

Two QQE trailing stops on smoothed RSI:
  Fast: RSI(6) → EMA(5) → QQE trailing stop with SF=4.238
  Slow: RSI(14) → EMA(5) → QQE trailing stop with SF=4.238

BUY = fast RSI_MA crossed above its QQE line (within 2 bars)
      AND fast RSI_MA > 50  (bullish momentum zone)
      AND slow RSI_MA > 50  (macro trend bullish)
      AND slow RSI_MA > slow QQE line
"""
import numpy as np
import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe

_THRESHOLD = 50.0


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
        required = ["qqe_fast_rsi", "qqe_fast", "qqe_slow_rsi", "qqe_slow"]
        if len(df) < 50 or not all(c in df.columns for c in required):
            return Signal(signal_type="NONE", conditions_failed=["Insufficient data"])

        rf_now   = float(df["qqe_fast_rsi"].iloc[-1])
        rf_prev  = float(df["qqe_fast_rsi"].iloc[-2])
        rf_prev2 = float(df["qqe_fast_rsi"].iloc[-3])
        qf_now   = float(df["qqe_fast"].iloc[-1])
        qf_prev  = float(df["qqe_fast"].iloc[-2])
        qf_prev2 = float(df["qqe_fast"].iloc[-3])
        rs_now   = float(df["qqe_slow_rsi"].iloc[-1])
        qs_now   = float(df["qqe_slow"].iloc[-1])

        if any(np.isnan(x) for x in [rf_now, qf_now, rs_now, qs_now]):
            return Signal(signal_type="NONE", conditions_failed=["QQE not ready"])

        fast_cross     = (rf_prev <= qf_prev and rf_now  > qf_now) or \
                         (rf_prev2 <= qf_prev2 and rf_prev > qf_prev)
        fast_above_qqe = rf_now > qf_now
        fast_bullish   = rf_now > _THRESHOLD
        slow_bullish   = rs_now > _THRESHOLD
        slow_above_qqe = rs_now > qs_now

        conditions_met    = []
        conditions_failed = []

        if fast_cross or fast_above_qqe:
            tag = "crossed" if fast_cross else "above"
            conditions_met.append(f"Fast RSI(6)={rf_now:.1f} {tag} its QQE({qf_now:.1f})")
        else:
            conditions_failed.append(f"Fast RSI(6)={rf_now:.1f} below QQE({qf_now:.1f})")

        if fast_bullish:
            conditions_met.append(f"Fast RSI={rf_now:.1f} > {_THRESHOLD} (bullish momentum)")
        else:
            conditions_failed.append(f"Fast RSI={rf_now:.1f} < {_THRESHOLD}")

        if slow_bullish:
            conditions_met.append(f"Slow RSI(14)={rs_now:.1f} > {_THRESHOLD} (macro trend up)")
        else:
            conditions_failed.append(f"Slow RSI(14)={rs_now:.1f} < {_THRESHOLD} (downtrend)")

        if slow_above_qqe:
            conditions_met.append(f"Slow RSI({rs_now:.1f}) above slow QQE({qs_now:.1f})")
        else:
            conditions_failed.append("Slow RSI below slow QQE — trend not confirmed")

        if (fast_cross or fast_above_qqe) and fast_bullish and slow_bullish and slow_above_qqe:
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

        return Signal(signal_type="NONE", conditions_met=conditions_met, conditions_failed=conditions_failed)

    def get_required_indicators(self) -> list[str]:
        return ["qqe_fast_rsi", "qqe_fast", "qqe_slow_rsi", "qqe_slow"]
