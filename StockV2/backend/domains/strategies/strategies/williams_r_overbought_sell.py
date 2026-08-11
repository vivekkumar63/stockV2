import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class WilliamsROverboughtSellStrategy(BaseStrategy):
    name = "Williams %R Overbought Reversal"
    description = "Sell when Williams %R crosses below -20 from overbought — fast topping signal"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 2:
            return Signal("NONE")

        wr = df["williams_r"].iloc[-1]
        prev_wr = df["williams_r"].iloc[-2]

        if pd.isna(wr) or pd.isna(prev_wr):
            return Signal("NONE")

        # Williams %R was in overbought (>-20) and crosses back down below -20
        if prev_wr >= -20 and wr < -20:
            rsi = df["rsi_14"].iloc[-1]
            rsi_note = f", RSI={rsi:.1f}" if not pd.isna(rsi) else ""
            return Signal(
                signal_type="SELL",
                confidence=0.62,
                risk_score=0.52,
                expected_upside_pct=0.0,
                stop_loss_pct=0.0,
                target_pct=0.0,
                holding_days=0,
                conditions_met=[f"Williams %R={wr:.1f} crossed below -20 from overbought{rsi_note}"],
            )

        return Signal("NONE")

    def get_required_indicators(self) -> list[str]:
        return ["williams_r"]
