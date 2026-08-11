import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class VolumeTrendPriceBreakoutStrategy(BaseStrategy):
    name = "Rising Volume Trend Breakout"
    description = "Buy when volume trend has been rising (5-bar change positive) AND price breaks above SMA10"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 2:
            return Signal("NONE")

        vol_trend = df["volume_sma_5bar_change"].iloc[-1]
        close = df["close"].iloc[-1]
        prev_close = df["close"].iloc[-2]
        sma10 = df["sma_10"].iloc[-1]
        prev_sma10 = df["sma_10"].iloc[-2]

        if any(pd.isna(x) for x in [vol_trend, close, prev_close, sma10, prev_sma10]):
            return Signal("NONE")

        volume_rising = vol_trend > 0
        price_broke_sma10 = prev_close <= prev_sma10 and close > sma10

        if volume_rising and price_broke_sma10:
            vol_ratio = df["volume_ratio"].iloc[-1]
            vol_note = f", vol_ratio={vol_ratio:.1f}x" if not pd.isna(vol_ratio) else ""
            return Signal(
                signal_type="BUY",
                confidence=0.64,
                risk_score=0.43,
                expected_upside_pct=10.0,
                stop_loss_pct=5.0,
                target_pct=10.0,
                holding_days=10,
                conditions_met=[
                    f"Price {prev_close:.2f}→{close:.2f} crossed above SMA10={sma10:.2f}",
                    f"Volume trend rising{vol_note}",
                ],
            )

        return Signal("NONE")

    def get_required_indicators(self) -> list[str]:
        return ["volume_sma_5bar_change", "sma_10"]
