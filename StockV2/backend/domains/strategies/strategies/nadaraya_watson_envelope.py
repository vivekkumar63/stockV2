"""
Nadaraya-Watson Envelope (jdehorty)

RQ kernel (h=8, α=8) regression + ±3·MAE bands.

BUY = price touched lower band last bar (close ≤ lower[-1] · 1.005)
      AND price now above lower band (bouncing off support)
      AND kernel estimate flat or rising (not in structural downtrend)
"""
import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


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
        required = ["close", "nw_yhat", "nw_upper", "nw_lower"]
        if len(df) < 50 or not all(c in df.columns for c in required):
            return Signal(signal_type="NONE", conditions_failed=["Insufficient data"])

        yhat_now   = float(df["nw_yhat"].iloc[-1])
        yhat_prev  = float(df["nw_yhat"].iloc[-2])
        upper_now  = float(df["nw_upper"].iloc[-1])
        lower_now  = float(df["nw_lower"].iloc[-1])
        lower_prev = float(df["nw_lower"].iloc[-2])
        c_now      = float(df["close"].iloc[-1])
        c_prev     = float(df["close"].iloc[-2])

        if any(pd.isna(x) for x in [yhat_now, upper_now, lower_now]):
            return Signal(signal_type="NONE", conditions_failed=["NW not ready"])

        near_lower    = c_prev <= lower_prev * 1.005
        above_lower   = c_now > lower_now
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
            conditions_failed.append(f"Price not at lower band (was {gap:+.1f}% above lower={lower_prev:.2f})")

        if above_lower:
            pct = ((c_now - lower_now) / lower_now) * 100
            conditions_met.append(f"Price bouncing: {pct:.2f}% above lower band ({lower_now:.2f})")
        else:
            conditions_failed.append(f"Price still below lower band ({lower_now:.2f})")

        if kernel_rising:
            slope = yhat_now - yhat_prev
            conditions_met.append(f"Kernel rising/flat: {yhat_prev:.2f} → {yhat_now:.2f} (slope={slope:+.3f})")
        else:
            conditions_failed.append(f"Kernel falling: {yhat_prev:.2f} → {yhat_now:.2f} — structural downtrend")

        mae     = (upper_now - yhat_now) / 3.0
        summary = f"NW: yhat={yhat_now:.2f} | upper={upper_now:.2f} | lower={lower_now:.2f} | MAE={mae:.2f}"

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

        return Signal(signal_type="NONE", conditions_met=conditions_met, conditions_failed=conditions_failed + [summary])

    def get_required_indicators(self) -> list[str]:
        return ["close", "nw_yhat", "nw_upper", "nw_lower"]
