import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class RSIMACDDoubleSellStrategy(BaseStrategy):
    name = "RSI + MACD Double Sell"
    description = "Sell when RSI is overbought AND MACD just crossed bearish — two-indicator topping signal"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 2:
            return Signal("NONE")

        rsi = df["rsi_14"].iloc[-1]
        macd = df["macd"].iloc[-1]
        macd_sig = df["macd_signal"].iloc[-1]
        prev_macd = df["macd"].iloc[-2]
        prev_sig = df["macd_signal"].iloc[-2]

        if any(pd.isna(x) for x in [rsi, macd, macd_sig, prev_macd, prev_sig]):
            return Signal("NONE")

        macd_crossed_down = prev_macd >= prev_sig and macd < macd_sig
        rsi_overbought = rsi > 65

        if macd_crossed_down and rsi_overbought:
            return Signal(
                signal_type="SELL",
                confidence=0.70,
                risk_score=0.55,
                expected_upside_pct=0.0,
                stop_loss_pct=0.0,
                target_pct=0.0,
                holding_days=0,
                conditions_met=[
                    f"MACD bearish cross ({prev_macd:.4f} → {macd:.4f})",
                    f"RSI={rsi:.1f} > 65 (overbought)",
                ],
            )

        return Signal("NONE")

    def get_required_indicators(self) -> list[str]:
        return ["rsi_14", "macd", "macd_signal"]
