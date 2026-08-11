import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class WilliamsROversoldBuyStrategy(BaseStrategy):
    name = "Williams %R Oversold Bounce"
    description = "Buy when Williams %R crosses above -80 from oversold — fast reversal signal"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 2:
            return Signal("NONE")

        wr = df["williams_r"].iloc[-1]
        prev_wr = df["williams_r"].iloc[-2]

        if pd.isna(wr) or pd.isna(prev_wr):
            return Signal("NONE")

        # Williams %R was in oversold (<-80) and crosses back up above -80
        if prev_wr <= -80 and wr > -80:
            rsi = df["rsi_14"].iloc[-1]
            rsi_note = f", RSI={rsi:.1f}" if not pd.isna(rsi) else ""
            return Signal(
                signal_type="BUY",
                confidence=0.62,
                risk_score=0.43,
                expected_upside_pct=8.0,
                stop_loss_pct=5.0,
                target_pct=8.0,
                holding_days=6,
                conditions_met=[f"Williams %R={wr:.1f} crossed above -80 from oversold{rsi_note}"],
            )

        return Signal("NONE")

    def get_required_indicators(self) -> list[str]:
        return ["williams_r"]
