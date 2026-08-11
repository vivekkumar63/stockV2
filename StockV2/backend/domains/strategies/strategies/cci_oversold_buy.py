import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class CCIOversoldBuyStrategy(BaseStrategy):
    name = "CCI Oversold Bounce"
    description = "Buy when CCI crosses below -100 then back above — commodity channel oversold reversal"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 2:
            return Signal("NONE")

        cci = df["cci_20"].iloc[-1]
        prev_cci = df["cci_20"].iloc[-2]

        if pd.isna(cci) or pd.isna(prev_cci):
            return Signal("NONE")

        # CCI was below -100 and now crosses back up (bounce out of oversold)
        if prev_cci <= -100 and cci > -100:
            return Signal(
                signal_type="BUY",
                confidence=0.63,
                risk_score=0.43,
                expected_upside_pct=9.0,
                stop_loss_pct=5.0,
                target_pct=9.0,
                holding_days=8,
                conditions_met=[f"CCI={cci:.1f} crossed back above -100 from oversold ({prev_cci:.1f})"],
            )

        return Signal("NONE")

    def get_required_indicators(self) -> list[str]:
        return ["cci_20"]
