import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class RSIMACDConfluenceBuyStrategy(BaseStrategy):
    name = "RSI + MACD Confluence Buy"
    description = "Buy when RSI is oversold AND MACD histogram turns from negative to positive — double confirmation"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 2:
            return Signal("NONE")

        rsi = df["rsi_14"].iloc[-1]
        macd_hist = df["macd_hist"].iloc[-1]
        prev_hist = df["macd_hist"].iloc[-2]

        if any(pd.isna(x) for x in [rsi, macd_hist, prev_hist]):
            return Signal("NONE")

        hist_turned_positive = prev_hist <= 0 and macd_hist > 0
        rsi_oversold = rsi < 45

        if hist_turned_positive and rsi_oversold:
            return Signal(
                signal_type="BUY",
                confidence=0.70,
                risk_score=0.40,
                expected_upside_pct=13.0,
                stop_loss_pct=6.0,
                target_pct=13.0,
                holding_days=15,
                conditions_met=[
                    f"MACD histogram turned positive ({prev_hist:.4f} → {macd_hist:.4f})",
                    f"RSI={rsi:.1f} < 45 (oversold confirmation)",
                ],
            )

        return Signal("NONE")

    def get_required_indicators(self) -> list[str]:
        return ["rsi_14", "macd_hist"]
