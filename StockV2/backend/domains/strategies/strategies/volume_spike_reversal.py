import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class VolumeSpikeReversalStrategy(BaseStrategy):
    name = "Volume Spike Reversal"
    description = "Sell on blow-off top: volume >2x average with RSI overbought. Buy on capitulation: volume >2x with RSI oversold"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 2:
            return Signal("NONE")

        vol_ratio = df["volume_ratio"].iloc[-1]
        rsi = df["rsi_14"].iloc[-1]
        close = df["close"].iloc[-1]
        prev_close = df["close"].iloc[-2]

        if any(pd.isna(x) for x in [vol_ratio, rsi, close, prev_close]):
            return Signal("NONE")

        day_change = (close - prev_close) / prev_close * 100
        huge_volume = vol_ratio >= 2.0

        # Capitulation: huge volume + big red candle + oversold → buy reversal
        if huge_volume and day_change <= -2.0 and rsi < 38:
            return Signal(
                signal_type="BUY",
                confidence=0.65,
                risk_score=0.48,
                expected_upside_pct=10.0,
                stop_loss_pct=6.0,
                target_pct=10.0,
                holding_days=8,
                conditions_met=[
                    f"Volume {vol_ratio:.1f}x avg (capitulation volume)",
                    f"Day change {day_change:.1f}%, RSI={rsi:.1f} oversold",
                ],
            )

        # Blow-off top: huge volume + big green candle + overbought → sell
        if huge_volume and day_change >= 2.0 and rsi > 65:
            return Signal(
                signal_type="SELL",
                confidence=0.63,
                risk_score=0.52,
                expected_upside_pct=0.0,
                stop_loss_pct=0.0,
                target_pct=0.0,
                holding_days=0,
                conditions_met=[
                    f"Volume {vol_ratio:.1f}x avg (blow-off volume)",
                    f"Day change +{day_change:.1f}%, RSI={rsi:.1f} overbought",
                ],
            )

        return Signal("NONE")

    def get_required_indicators(self) -> list[str]:
        return ["volume_ratio", "rsi_14"]
