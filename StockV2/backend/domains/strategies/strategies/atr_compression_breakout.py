import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class ATRCompressionBreakoutStrategy(BaseStrategy):
    name = "ATR Compression Breakout"
    description = "Buy when ATR reaches 20-day low AND BB is squeezing — coiling spring before explosive move"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 21:
            return Signal("NONE")

        atr = df["atr_14"].iloc[-1]
        atr_20d_min = df["atr_14"].iloc[-20:].min()
        bb_width = df["bb_width"].iloc[-1]
        bb_width_avg = df["bb_width_sma_20"].iloc[-1]
        close = df["close"].iloc[-1]
        sma20 = df["sma_20"].iloc[-1]

        if any(pd.isna(x) for x in [atr, atr_20d_min, bb_width, bb_width_avg]):
            return Signal("NONE")

        # ATR near 20-day low = compression
        atr_compressed = atr <= atr_20d_min * 1.1
        # BB squeezing
        bb_squeezing = bb_width < bb_width_avg
        # Price above SMA20 = bullish bias
        bullish_bias = not pd.isna(sma20) and close > sma20

        if atr_compressed and bb_squeezing and bullish_bias:
            return Signal(
                signal_type="BUY",
                confidence=0.67,
                risk_score=0.40,
                expected_upside_pct=15.0,
                stop_loss_pct=5.0,
                target_pct=15.0,
                holding_days=12,
                conditions_met=[
                    f"ATR={atr:.2f} near 20d low={atr_20d_min:.2f} (compressed)",
                    f"BB squeezing (width={bb_width:.4f} < avg={bb_width_avg:.4f})",
                    f"Price above SMA20",
                ],
            )

        return Signal("NONE")

    def get_required_indicators(self) -> list[str]:
        return ["atr_14", "bb_width", "bb_width_sma_20", "sma_20"]
