import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class StochasticOverboughtSellStrategy(BaseStrategy):
    name = "Stochastic Overbought Reversal"
    description = "Sell when Stochastic %K crosses below %D from overbought zone (>80)"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 2:
            return Signal("NONE")

        k = df["stoch_k"].iloc[-1]
        d = df["stoch_d"].iloc[-1]
        prev_k = df["stoch_k"].iloc[-2]
        prev_d = df["stoch_d"].iloc[-2]

        if any(pd.isna(x) for x in [k, d, prev_k, prev_d]):
            return Signal("NONE")

        # %K crosses below %D while both were in overbought zone
        k_crossed_below = prev_k >= prev_d and k < d
        was_overbought = prev_k > 75

        if k_crossed_below and was_overbought:
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
                conditions_met=[
                    f"Stoch %K={k:.1f} crossed below %D={d:.1f} from overbought{rsi_note}",
                ],
            )

        return Signal("NONE")

    def get_required_indicators(self) -> list[str]:
        return ["stoch_k", "stoch_d"]
