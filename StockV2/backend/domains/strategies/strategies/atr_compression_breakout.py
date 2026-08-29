import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe

_COMPRESSION_LOOKBACK = 14
_BREAKOUT_LOOKBACK = 10


class ATRCompressionBreakoutStrategy(BaseStrategy):
    name = "ATR Compression Breakout"
    description = "Buy when ATR compresses to a multi-bar low then price breaks above recent high with volume"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY
    weight = 0.18
    min_holding_days = 3
    max_holding_days = 12

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        required = ["atr_14", "close", "high", "low", "sma_20", "volume_ratio"]
        if len(df) < _COMPRESSION_LOOKBACK + 5 or not all(c in df.columns for c in required):
            return Signal("NONE")

        curr = df.iloc[-1]
        close = curr["close"]
        high = curr["high"]
        sma_20 = curr["sma_20"]
        atr = curr["atr_14"]
        volume_ratio = curr["volume_ratio"]

        if any(pd.isna(x) for x in [close, high, sma_20, atr, volume_ratio]):
            return Signal("NONE")

        # ATR compressed to near its recent low
        atr_history = df["atr_14"].iloc[-_COMPRESSION_LOOKBACK:-1]
        atr_min = atr_history.min()
        atr_compressed = atr <= atr_min * 1.10

        # Price breaks above recent N-bar high (excluding today)
        prior_highs = df["high"].iloc[-_BREAKOUT_LOOKBACK:-1]
        breakout_level = prior_highs.max()
        price_breakout = high > breakout_level

        # Uptrend context and volume expansion confirming the breakout
        in_uptrend = close > sma_20
        volume_expanding = volume_ratio > 1.3

        if atr_compressed and price_breakout and in_uptrend and volume_expanding:
            compression_ratio = 1.0 - min(atr / atr_min - 1.0, 0.5) / 0.5
            confidence = round(0.60 + 0.15 * compression_ratio, 4)
            return Signal(
                signal_type="BUY",
                confidence=confidence,
                risk_score=0.42,
                stop_loss_pct=5.0,
                target_pct=10.0,
                holding_days=8,
                conditions_met=[
                    f"ATR {atr:.2f} compressed to {_COMPRESSION_LOOKBACK}-bar low ({atr_min:.2f})",
                    f"Price {high:.2f} broke above {_BREAKOUT_LOOKBACK}-bar high {breakout_level:.2f}",
                    f"Volume {volume_ratio:.2f}x confirms breakout",
                ],
            )

        return Signal("NONE")

    def get_required_indicators(self) -> list[str]:
        return ["atr_14", "close", "high", "low", "sma_20", "volume_ratio"]
