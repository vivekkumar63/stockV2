import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class StochasticOversoldBuyStrategy(BaseStrategy):
    name = "Stochastic Oversold Bounce"
    description = "Buy when Stochastic %K crosses above %D from oversold zone (<20)"
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

        # %K crosses above %D while both were in oversold zone
        k_crossed_above = prev_k <= prev_d and k > d
        was_oversold = prev_k < 25

        if k_crossed_above and was_oversold:
            rsi = df["rsi_14"].iloc[-1]
            rsi_note = f", RSI={rsi:.1f}" if not pd.isna(rsi) else ""
            return Signal(
                signal_type="BUY",
                confidence=0.63,
                risk_score=0.43,
                expected_upside_pct=9.0,
                stop_loss_pct=5.0,
                target_pct=9.0,
                holding_days=8,
                conditions_met=[
                    f"Stoch %K={k:.1f} crossed above %D={d:.1f} from oversold{rsi_note}",
                ],
            )

        return Signal("NONE")

    def get_required_indicators(self) -> list[str]:
        return ["stoch_k", "stoch_d"]
