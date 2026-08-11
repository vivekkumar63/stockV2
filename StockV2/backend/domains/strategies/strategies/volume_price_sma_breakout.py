import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class VolumePriceSMABreakoutStrategy(BaseStrategy):
    name = "Volume + Price SMA Breakout"
    description = "Buy when price crosses above SMA20 with above-average volume — confirms the breakout is real"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 2:
            return Signal("NONE")

        close = df["close"].iloc[-1]
        prev_close = df["close"].iloc[-2]
        sma20 = df["sma_20"].iloc[-1]
        prev_sma20 = df["sma_20"].iloc[-2]
        vol_ratio = df["volume_ratio"].iloc[-1]

        if any(pd.isna(x) for x in [close, prev_close, sma20, prev_sma20, vol_ratio]):
            return Signal("NONE")

        price_crossed_above = prev_close <= prev_sma20 and close > sma20
        volume_confirmed = vol_ratio >= 1.5

        if price_crossed_above and volume_confirmed:
            rsi = df["rsi_14"].iloc[-1]
            rsi_note = f", RSI={rsi:.1f}" if not pd.isna(rsi) else ""
            return Signal(
                signal_type="BUY",
                confidence=0.66,
                risk_score=0.42,
                expected_upside_pct=11.0,
                stop_loss_pct=5.5,
                target_pct=11.0,
                holding_days=12,
                conditions_met=[
                    f"Price {prev_close:.2f}→{close:.2f} crossed above SMA20={sma20:.2f}",
                    f"Volume {vol_ratio:.1f}x above avg{rsi_note}",
                ],
            )

        return Signal("NONE")

    def get_required_indicators(self) -> list[str]:
        return ["sma_20", "volume_ratio"]
