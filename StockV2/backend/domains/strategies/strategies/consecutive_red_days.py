import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class ConsecutiveRedDaysStrategy(BaseStrategy):
    name = "Consecutive Red Days Reversal"
    description = "Buy after 2+ consecutive red candles with RSI showing oversold conditions"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 3:
            return Signal("NONE")

        rsi = df["rsi_14"].iloc[-1]
        if pd.isna(rsi):
            return Signal("NONE")

        # Count consecutive red candles at the tail
        red_count = 0
        for i in range(-1, -len(df) - 1, -1):
            row = df.iloc[i]
            if row["close"] < row["open"]:
                red_count += 1
            else:
                break

        if red_count >= 2 and rsi < 45:
            close = df["close"].iloc[-1]
            sma20 = df["sma_20"].iloc[-1]
            near_support = not pd.isna(sma20) and close > sma20 * 0.92

            return Signal(
                signal_type="BUY",
                confidence=0.62,
                risk_score=0.42,
                expected_upside_pct=10.0,
                stop_loss_pct=6.0,
                target_pct=10.0,
                holding_days=8,
                conditions_met=[
                    f"{red_count} consecutive red candles",
                    f"RSI={rsi:.1f} < 45",
                ] + (["Close near SMA20 support"] if near_support else []),
            )

        return Signal("NONE")

    def get_required_indicators(self) -> list[str]:
        return ["rsi_14", "sma_20"]
