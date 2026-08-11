import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class ADXMomentumStrategy(BaseStrategy):
    name = "ADX Momentum"
    description = "Buy when ADX shows strong trend, price above SMA20, RSI in momentum zone (40-65)"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 2:
            return Signal("NONE")

        adx = df["adx_14"].iloc[-1]
        close = df["close"].iloc[-1]
        sma20 = df["sma_20"].iloc[-1]
        rsi = df["rsi_14"].iloc[-1]

        if any(pd.isna(x) for x in [adx, close, sma20, rsi]):
            return Signal("NONE")

        trending = adx > 25
        price_above_ma = close > sma20
        rsi_momentum = 40 <= rsi <= 65

        if trending and price_above_ma and rsi_momentum:
            return Signal(
                signal_type="BUY",
                confidence=0.65,
                risk_score=0.45,
                expected_upside_pct=15.0,
                stop_loss_pct=7.0,
                target_pct=15.0,
                holding_days=20,
                conditions_met=[
                    f"ADX={adx:.1f} > 25 (strong trend)",
                    f"Price={close:.2f} above SMA20={sma20:.2f}",
                    f"RSI={rsi:.1f} in momentum zone (40-65)",
                ],
            )

        return Signal("NONE")

    def get_required_indicators(self) -> list[str]:
        return ["adx_14", "sma_20", "rsi_14"]
