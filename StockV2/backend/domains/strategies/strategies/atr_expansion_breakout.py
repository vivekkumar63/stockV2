import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class ATRExpansionBreakoutStrategy(BaseStrategy):
    name = "ATR Expansion Breakout"
    description = "Buy when volatility suddenly expands (ATR rising vs 5 bars ago) with price above SMA20 — breakout confirmed"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 7:
            return Signal("NONE")

        atr_change = df["atr_5bar_change"].iloc[-1]
        prev_atr_change = df["atr_5bar_change"].iloc[-2]
        close = df["close"].iloc[-1]
        sma20 = df["sma_20"].iloc[-1]
        atr = df["atr_14"].iloc[-1]

        if any(pd.isna(x) for x in [atr_change, prev_atr_change, close]):
            return Signal("NONE")

        # Volatility just started expanding (was flat/contracting, now expanding)
        just_expanded = prev_atr_change <= 0 and atr_change > 0
        bullish_bias = not pd.isna(sma20) and close > sma20

        if just_expanded and bullish_bias:
            return Signal(
                signal_type="BUY",
                confidence=0.63,
                risk_score=0.48,
                expected_upside_pct=12.0,
                stop_loss_pct=6.0,
                target_pct=12.0,
                holding_days=10,
                conditions_met=[
                    f"ATR expanding ({atr:.2f} vs 5-bar avg, +{atr_change:.2f})",
                    f"Price above SMA20",
                ],
            )

        return Signal("NONE")

    def get_required_indicators(self) -> list[str]:
        return ["atr_5bar_change", "atr_14", "sma_20"]
