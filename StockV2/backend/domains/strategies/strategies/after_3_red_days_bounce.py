import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class After3RedDaysBounceStrategy(BaseStrategy):
    name = "After 3 Red Days Bounce"
    description = "Buy after exactly 3+ consecutive red candles with RSI oversold — deeper pullback = stronger bounce"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 4:
            return Signal("NONE")

        rsi = df["rsi_14"].iloc[-1]
        if pd.isna(rsi):
            return Signal("NONE")

        red_count = 0
        for i in range(-1, -len(df) - 1, -1):
            row = df.iloc[i]
            if row["close"] < row["open"]:
                red_count += 1
            else:
                break

        if red_count >= 3 and rsi < 40:
            total_drop = (df["close"].iloc[-1] - df["open"].iloc[-red_count]) / df["open"].iloc[-red_count] * 100
            return Signal(
                signal_type="BUY",
                confidence=0.66,
                risk_score=0.40,
                expected_upside_pct=12.0,
                stop_loss_pct=6.0,
                target_pct=12.0,
                holding_days=10,
                conditions_met=[
                    f"{red_count} consecutive red candles",
                    f"Total drop {total_drop:.1f}%, RSI={rsi:.1f}",
                ],
            )

        return Signal("NONE")

    def get_required_indicators(self) -> list[str]:
        return ["rsi_14"]
