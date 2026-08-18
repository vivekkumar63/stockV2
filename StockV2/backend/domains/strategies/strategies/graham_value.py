import math
import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe

_GRAHAM_MULTIPLIER  = 22.5   # Graham's constant: sqrt(22.5 × EPS × BV)
_PRICE_TO_GRAHAM    = 1.3    # price must be < 1.3 × Graham Number
_PE_MAX             = 15.0   # value zone PE threshold
_PB_MAX             = 1.5    # near-book PB threshold
_CONF_MIN           = 0.4    # minimum confidence (deep value)
_CONF_MAX           = 1.0    # maximum confidence cap


class GrahamValueStrategy(BaseStrategy):
    name = "Graham Value"
    description = (
        "Benjamin Graham Number: buy when price < 1.3× Graham Number "
        "and PE < 15 and PB < 1.5. Graham Number = sqrt(22.5 × EPS × BookValue)."
    )
    strategy_type = StrategyType.FUNDAMENTAL
    timeframe = Timeframe.DAILY
    min_holding_days = 30
    max_holding_days = 180
    weight = 0.05

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if not fundamentals:
            return Signal("NONE")

        eps = fundamentals.get("eps")
        pb  = fundamentals.get("pb_ratio")
        pe  = fundamentals.get("pe_ratio")

        if df.empty:
            return Signal("NONE")

        close = float(df["close"].iloc[-1])
        if close <= 0:
            return Signal("NONE")

        met    = []
        missed = []

        # Compute Graham Number (requires eps > 0 and pb > 0)
        graham_num = None
        if eps is not None and pb is not None and eps > 0 and pb > 0:
            book_value = close / pb
            val = _GRAHAM_MULTIPLIER * eps * book_value
            if val > 0:
                graham_num = math.sqrt(val)

        if graham_num and close < _PRICE_TO_GRAHAM * graham_num:
            met.append(f"Price {close:.0f} < {_PRICE_TO_GRAHAM}× Graham {graham_num:.0f}")
        else:
            missed.append(f"Price not below Graham Number × {_PRICE_TO_GRAHAM}")

        if pe is not None and pe < _PE_MAX:
            met.append(f"PE {pe:.1f} < {_PE_MAX:.0f} (value zone)")
        else:
            missed.append(f"PE >= {_PE_MAX:.0f} or unknown")

        if pb is not None and pb < _PB_MAX:
            met.append(f"PB {pb:.2f} < {_PB_MAX} (near book)")
        else:
            missed.append(f"PB >= {_PB_MAX} or unknown")

        if len(met) == 3:
            margin = ((_PRICE_TO_GRAHAM * graham_num) - close) / (_PRICE_TO_GRAHAM * graham_num) if graham_num else 0
            confidence = round(min(_CONF_MAX, max(_CONF_MIN, 0.60 + margin)), 4)
            return Signal(
                signal_type="BUY",
                confidence=confidence,
                risk_score=0.25,
                expected_upside_pct=30.0,
                stop_loss_pct=7.0,
                target_pct=30.0,
                holding_days=60,
                conditions_met=met,
                conditions_failed=missed,
            )
        return Signal("NONE", conditions_met=met, conditions_failed=missed)

    def get_required_indicators(self) -> list[str]:
        return []
