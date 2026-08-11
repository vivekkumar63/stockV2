import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class ConsecutiveGreenReversalStrategy(BaseStrategy):
    name = "Consecutive Green Days Reversal"
    description = "Sell after 2+ consecutive green candles with RSI overbought — expects short-term pullback"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 3:
            return Signal("NONE")

        rsi = df["rsi_14"].iloc[-1]
        if pd.isna(rsi):
            return Signal("NONE")

        green_count = 0
        for i in range(-1, -len(df) - 1, -1):
            row = df.iloc[i]
            if row["close"] > row["open"]:
                green_count += 1
            else:
                break

        if green_count >= 2 and rsi > 65:
            total_gain = (df["close"].iloc[-1] - df["open"].iloc[-green_count]) / df["open"].iloc[-green_count] * 100
            return Signal(
                signal_type="SELL",
                confidence=0.60,
                risk_score=0.50,
                expected_upside_pct=0.0,
                stop_loss_pct=0.0,
                target_pct=0.0,
                holding_days=0,
                conditions_met=[
                    f"{green_count} consecutive green candles (+{total_gain:.1f}%)",
                    f"RSI={rsi:.1f} > 65 (overbought)",
                ],
            )

        return Signal("NONE")

    def get_required_indicators(self) -> list[str]:
        return ["rsi_14"]
