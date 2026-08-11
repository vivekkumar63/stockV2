import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class PriceBelowBBLowerStrategy(BaseStrategy):
    name = "Price Below BB Lower"
    description = "Buy when price closes below Bollinger lower band with RSI oversold"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 2:
            return Signal("NONE")

        close = df["close"].iloc[-1]
        bb_lower = df["bb_lower"].iloc[-1]
        bb_middle = df["bb_middle"].iloc[-1]
        rsi = df["rsi_14"].iloc[-1]

        if any(pd.isna(x) for x in [close, bb_lower, bb_middle, rsi]):
            return Signal("NONE")

        if close < bb_lower and rsi < 40:
            pct_below = (bb_lower - close) / bb_lower * 100
            return Signal(
                signal_type="BUY",
                confidence=0.70,
                risk_score=0.38,
                expected_upside_pct=10.0,
                stop_loss_pct=5.0,
                target_pct=10.0,
                holding_days=10,
                conditions_met=[
                    f"Close={close:.2f} below BB lower={bb_lower:.2f} ({pct_below:.2f}%)",
                    f"RSI={rsi:.1f} < 40",
                ],
            )

        return Signal("NONE")

    def get_required_indicators(self) -> list[str]:
        return ["bb_lower", "bb_middle", "rsi_14"]
