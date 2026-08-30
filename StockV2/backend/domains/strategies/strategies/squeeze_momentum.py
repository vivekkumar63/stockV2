"""
Squeeze Momentum (LazyBear)

BB inside KC = squeeze coiling. When BB expands beyond KC and linreg
momentum is positive/rising, the coil fires bullishly.

BUY = squeeze just released (ON→OFF) AND momentum > 0 AND momentum rising.
"""
import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


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
        required = ["close", "squeeze_on", "squeeze_mom"]
        if len(df) < 35 or not all(c in df.columns for c in required):
            return Signal(signal_type="NONE", conditions_failed=["Insufficient data"])

        sqz_now  = float(df["squeeze_on"].iloc[-1])
        sqz_prev = float(df["squeeze_on"].iloc[-2])
        val_now  = float(df["squeeze_mom"].iloc[-1])
        val_prev = float(df["squeeze_mom"].iloc[-2])

        if any(pd.isna(x) for x in [sqz_now, sqz_prev, val_now, val_prev]):
            return Signal(signal_type="NONE", conditions_failed=["Momentum not ready"])

        squeeze_fired = sqz_prev == 1.0 and sqz_now == 0.0
        momentum_up   = val_now > 0 and val_now > val_prev

        conditions_met    = []
        conditions_failed = []

        if squeeze_fired:
            conditions_met.append("Squeeze released: BB expanded beyond KC (coil fired)")
        elif sqz_now == 1.0:
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
            price    = float(df["close"].iloc[-1])
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

        return Signal(signal_type="NONE", conditions_met=conditions_met, conditions_failed=conditions_failed)

    def get_required_indicators(self) -> list[str]:
        return ["close", "squeeze_on", "squeeze_mom"]
