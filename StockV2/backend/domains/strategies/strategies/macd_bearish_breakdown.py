import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class MACDBearishBreakdownStrategy(BaseStrategy):
    name = "MACD Bearish Breakdown"
    description = "Sell when MACD crosses below signal line while price is below SMA20 — trend breakdown"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 2:
            return Signal("NONE")

        macd = df["macd"].iloc[-1]
        macd_sig = df["macd_signal"].iloc[-1]
        prev_macd = df["macd"].iloc[-2]
        prev_sig = df["macd_signal"].iloc[-2]
        close = df["close"].iloc[-1]
        sma20 = df["sma_20"].iloc[-1]

        if any(pd.isna(x) for x in [macd, macd_sig, prev_macd, prev_sig]):
            return Signal("NONE")

        macd_crossed_down = prev_macd >= prev_sig and macd < macd_sig
        below_sma = not pd.isna(sma20) and close < sma20

        if macd_crossed_down and below_sma:
            return Signal(
                signal_type="SELL",
                confidence=0.66,
                risk_score=0.55,
                expected_upside_pct=0.0,
                stop_loss_pct=0.0,
                target_pct=0.0,
                holding_days=0,
                conditions_met=[
                    f"MACD={macd:.4f} crossed below signal={macd_sig:.4f}",
                    f"Price={close:.2f} below SMA20={sma20:.2f}",
                ],
            )

        return Signal("NONE")

    def get_required_indicators(self) -> list[str]:
        return ["macd", "macd_signal", "sma_20"]
