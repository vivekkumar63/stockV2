import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class MeanReversionDeviationStrategy(BaseStrategy):
    name = "Mean Reversion Deviation"
    description = "Buy when price is >3% below SMA20, sell when >3% above — fades extreme deviations"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 2:
            return Signal("NONE")

        close = df["close"].iloc[-1]
        sma20 = df["sma_20"].iloc[-1]
        rsi = df["rsi_14"].iloc[-1]

        if any(pd.isna(x) for x in [close, sma20]):
            return Signal("NONE")

        deviation_pct = (close - sma20) / sma20 * 100

        if deviation_pct <= -3.0 and (pd.isna(rsi) or rsi < 55):
            return Signal(
                signal_type="BUY",
                confidence=0.62,
                risk_score=0.40,
                expected_upside_pct=8.0,
                stop_loss_pct=5.0,
                target_pct=8.0,
                holding_days=7,
                conditions_met=[
                    f"Price {deviation_pct:.1f}% below SMA20 (oversold deviation)",
                ],
            )

        if deviation_pct >= 3.0 and (pd.isna(rsi) or rsi > 55):
            return Signal(
                signal_type="SELL",
                confidence=0.60,
                risk_score=0.50,
                expected_upside_pct=0.0,
                stop_loss_pct=0.0,
                target_pct=0.0,
                holding_days=0,
                conditions_met=[
                    f"Price {deviation_pct:.1f}% above SMA20 (overbought deviation)",
                ],
            )

        return Signal("NONE")

    def get_required_indicators(self) -> list[str]:
        return ["sma_20", "rsi_14"]
