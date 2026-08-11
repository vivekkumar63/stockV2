import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class GapAndGoStrategy(BaseStrategy):
    name = "Gap and Go"
    description = "Buy on gap-up day when BB is squeezing and RSI is not overbought"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 2:
            return Signal("NONE")

        gap = df["gap_pct"].iloc[-1]
        rsi = df["rsi_14"].iloc[-1]
        bb_width = df["bb_width"].iloc[-1]
        bb_width_avg = df["bb_width_sma_20"].iloc[-1]

        if any(pd.isna(x) for x in [gap, rsi, bb_width, bb_width_avg]):
            return Signal("NONE")

        # Gap up + BB squeezing (coiling before breakout) + not overbought
        squeezing = bb_width < bb_width_avg
        if gap >= 0.5 and squeezing and rsi < 65:
            return Signal(
                signal_type="BUY",
                confidence=0.65,
                risk_score=0.50,
                expected_upside_pct=12.0,
                stop_loss_pct=6.0,
                target_pct=12.0,
                holding_days=10,
                conditions_met=[
                    f"Gap up {gap:.2f}%",
                    f"BB squeezing (width={bb_width:.4f} < avg={bb_width_avg:.4f})",
                    f"RSI={rsi:.1f} not overbought",
                ],
            )

        return Signal("NONE")

    def get_required_indicators(self) -> list[str]:
        return ["gap_pct", "rsi_14", "bb_width", "bb_width_sma_20"]
