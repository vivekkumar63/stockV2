import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class EMA5_10CrossoverStrategy(BaseStrategy):
    name = "EMA Crossover (5/10)"
    description = "Fast EMA crossover: buy when EMA5 crosses above EMA10, sell on bearish cross"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 2:
            return Signal("NONE")

        curr_5, prev_5 = df["ema_5"].iloc[-1], df["ema_5"].iloc[-2]
        curr_10, prev_10 = df["ema_10"].iloc[-1], df["ema_10"].iloc[-2]

        if any(pd.isna(x) for x in [curr_5, prev_5, curr_10, prev_10]):
            return Signal("NONE")

        if prev_5 <= prev_10 and curr_5 > curr_10:
            rsi = df["rsi_14"].iloc[-1]
            rsi_note = f", RSI={rsi:.1f}" if not pd.isna(rsi) else ""
            return Signal(
                signal_type="BUY",
                confidence=0.58,
                risk_score=0.48,
                expected_upside_pct=8.0,
                stop_loss_pct=4.0,
                target_pct=8.0,
                holding_days=6,
                conditions_met=[f"EMA5={curr_5:.2f} crossed above EMA10={curr_10:.2f}{rsi_note}"],
            )

        if prev_5 >= prev_10 and curr_5 < curr_10:
            return Signal(
                signal_type="SELL",
                confidence=0.58,
                risk_score=0.52,
                expected_upside_pct=0.0,
                stop_loss_pct=0.0,
                target_pct=0.0,
                holding_days=0,
                conditions_met=[f"EMA5={curr_5:.2f} crossed below EMA10={curr_10:.2f}"],
            )

        return Signal("NONE")

    def get_required_indicators(self) -> list[str]:
        return ["ema_5", "ema_10"]
