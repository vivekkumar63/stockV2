import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class CCIOverboughtSellStrategy(BaseStrategy):
    name = "CCI Overbought Reversal"
    description = "Sell when CCI crosses back below +100 from overbought — momentum exhaustion signal"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 2:
            return Signal("NONE")

        cci = df["cci_20"].iloc[-1]
        prev_cci = df["cci_20"].iloc[-2]

        if pd.isna(cci) or pd.isna(prev_cci):
            return Signal("NONE")

        # CCI was above +100 and now crosses back down (exhaustion from overbought)
        if prev_cci >= 100 and cci < 100:
            return Signal(
                signal_type="SELL",
                confidence=0.62,
                risk_score=0.52,
                expected_upside_pct=0.0,
                stop_loss_pct=0.0,
                target_pct=0.0,
                holding_days=0,
                conditions_met=[f"CCI={cci:.1f} crossed back below +100 from overbought ({prev_cci:.1f})"],
            )

        return Signal("NONE")

    def get_required_indicators(self) -> list[str]:
        return ["cci_20"]
