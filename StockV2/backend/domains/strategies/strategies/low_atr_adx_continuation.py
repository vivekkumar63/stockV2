import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class LowATRHighADXContinuationStrategy(BaseStrategy):
    name = "Low ATR + High ADX Continuation"
    description = "Buy when ATR ratio < 1% (tight price action) AND ADX > 25 (trending) — calm trending stocks"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 2:
            return Signal("NONE")

        atr_ratio = df["atr_ratio"].iloc[-1]
        adx = df["adx_14"].iloc[-1]
        close = df["close"].iloc[-1]
        sma20 = df["sma_20"].iloc[-1]

        if any(pd.isna(x) for x in [atr_ratio, adx]):
            return Signal("NONE")

        low_volatility = atr_ratio < 1.5
        strong_trend = adx > 25
        bullish = not pd.isna(sma20) and close > sma20

        if low_volatility and strong_trend and bullish:
            return Signal(
                signal_type="BUY",
                confidence=0.66,
                risk_score=0.38,
                expected_upside_pct=12.0,
                stop_loss_pct=4.0,
                target_pct=12.0,
                holding_days=15,
                conditions_met=[
                    f"ATR ratio={atr_ratio:.2f}% (tight, low noise)",
                    f"ADX={adx:.1f} > 25 (strong trend)",
                    f"Price above SMA20",
                ],
            )

        return Signal("NONE")

    def get_required_indicators(self) -> list[str]:
        return ["atr_ratio", "adx_14", "sma_20"]
