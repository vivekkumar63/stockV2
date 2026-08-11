import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class PriceAboveBBUpperReversalStrategy(BaseStrategy):
    name = "Price Above BB Upper Reversal"
    description = "Sell when price closes above Bollinger upper band with RSI overbought"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 2:
            return Signal("NONE")

        close = df["close"].iloc[-1]
        bb_upper = df["bb_upper"].iloc[-1]
        bb_middle = df["bb_middle"].iloc[-1]
        rsi = df["rsi_14"].iloc[-1]

        if any(pd.isna(x) for x in [close, bb_upper, bb_middle, rsi]):
            return Signal("NONE")

        if close > bb_upper and rsi > 65:
            pct_above = (close - bb_upper) / bb_upper * 100
            return Signal(
                signal_type="SELL",
                confidence=0.65,
                risk_score=0.50,
                expected_upside_pct=0.0,
                stop_loss_pct=0.0,
                target_pct=0.0,
                holding_days=0,
                conditions_met=[
                    f"Close={close:.2f} above BB upper={bb_upper:.2f} ({pct_above:.2f}%)",
                    f"RSI={rsi:.1f} > 65",
                ],
            )

        return Signal("NONE")

    def get_required_indicators(self) -> list[str]:
        return ["bb_upper", "bb_middle", "rsi_14"]
