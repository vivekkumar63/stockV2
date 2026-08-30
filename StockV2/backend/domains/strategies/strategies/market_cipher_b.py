"""
Market Cipher B (VuManChu Cipher B)

WaveTrend(9,13) crossover from oversold (<-53) + RSI-MFI(60) confirmation.

BUY = WT1 crosses above WT2 AND WT2 was below -53 (blue dot)
      AND RSI-MFI > -20 (money flow not deeply negative)
"""
import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe

_OVERSOLD = -53


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
        required = ["mc_wt1", "mc_wt2", "rsimfi_60"]
        if len(df) < 30 or not all(c in df.columns for c in required):
            return Signal(signal_type="NONE", conditions_failed=["Insufficient data"])

        wt1_now    = float(df["mc_wt1"].iloc[-1])
        wt1_prev   = float(df["mc_wt1"].iloc[-2])
        wt2_now    = float(df["mc_wt2"].iloc[-1])
        wt2_prev   = float(df["mc_wt2"].iloc[-2])
        rsimfi_now = float(df["rsimfi_60"].iloc[-1])

        if any(pd.isna(x) for x in [wt1_now, wt2_now, rsimfi_now]):
            return Signal(signal_type="NONE", conditions_failed=["Indicators not ready"])

        wt_cross_up   = wt1_prev <= wt2_prev and wt1_now > wt2_now
        from_oversold = wt2_prev < _OVERSOLD or wt1_prev < _OVERSOLD
        money_flow_ok = rsimfi_now > -20

        conditions_met    = []
        conditions_failed = []

        if wt_cross_up:
            conditions_met.append(f"WT crossover: WT1({wt1_now:.1f}) crossed above WT2({wt2_now:.1f})")
        else:
            conditions_failed.append(f"No WT crossover (WT1={wt1_now:.1f} vs WT2={wt2_now:.1f})")

        if from_oversold:
            conditions_met.append(f"Cross from oversold zone (WT2={wt2_prev:.1f} < {_OVERSOLD}) — blue dot")
        else:
            conditions_failed.append(f"Not from oversold (WT2={wt2_prev:.1f}, needs < {_OVERSOLD})")

        if money_flow_ok:
            conditions_met.append(f"RSI-MFI={rsimfi_now:.1f} > -20 (money flow OK)")
        else:
            conditions_failed.append(f"RSI-MFI={rsimfi_now:.1f} ≤ -20 (negative money flow)")

        if wt_cross_up and from_oversold and money_flow_ok:
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

        return Signal(signal_type="NONE", conditions_met=conditions_met, conditions_failed=conditions_failed)

    def get_required_indicators(self) -> list[str]:
        return ["mc_wt1", "mc_wt2", "rsimfi_60"]
