import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class StochasticCrossGapUpStrategy(BaseStrategy):
    name = "Stochastic Cross + Gap Up"
    description = "Buy when Stochastic %K crosses above %D on a gap-up day — momentum confirmed by both indicators"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 2:
            return Signal("NONE")

        k = df["stoch_k"].iloc[-1]
        d = df["stoch_d"].iloc[-1]
        prev_k = df["stoch_k"].iloc[-2]
        prev_d = df["stoch_d"].iloc[-2]
        gap = df["gap_pct"].iloc[-1]

        if any(pd.isna(x) for x in [k, d, prev_k, prev_d, gap]):
            return Signal("NONE")

        k_crossed_above = prev_k <= prev_d and k > d
        gap_up = gap >= 0.3
        stoch_not_overbought = k < 80  # avoid buying at extreme overbought

        if k_crossed_above and gap_up and stoch_not_overbought:
            return Signal(
                signal_type="BUY",
                confidence=0.64,
                risk_score=0.45,
                expected_upside_pct=10.0,
                stop_loss_pct=5.0,
                target_pct=10.0,
                holding_days=8,
                conditions_met=[
                    f"Stoch %K={k:.1f} crossed above %D={d:.1f}",
                    f"Gap up {gap:.2f}%",
                ],
            )

        return Signal("NONE")

    def get_required_indicators(self) -> list[str]:
        return ["stoch_k", "stoch_d", "gap_pct"]
