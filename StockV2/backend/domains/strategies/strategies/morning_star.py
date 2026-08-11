import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class MorningStarStrategy(BaseStrategy):
    name = "Morning Star Reversal"
    description = "Buy on morning star 3-candle reversal: bearish candle → small/doji candle → bullish candle"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 5:
            return Signal("NONE")

        bar1 = df.iloc[-3]   # first candle: should be bearish
        bar2 = df.iloc[-2]   # middle candle: small/doji
        bar3 = df.iloc[-1]   # last candle: should be bullish

        def body(bar):
            return abs(bar["close"] - bar["open"])

        def candle_range(bar):
            return bar["high"] - bar["low"]

        r1, r2, r3 = candle_range(bar1), candle_range(bar2), candle_range(bar3)
        b1, b2, b3 = body(bar1), body(bar2), body(bar3)

        if r1 <= 0 or r2 <= 0 or r3 <= 0:
            return Signal("NONE")

        # Candle 1: meaningful bearish candle
        bar1_bearish = bar1["close"] < bar1["open"] and b1 > r1 * 0.5
        # Candle 2: small body (indecision / doji)
        bar2_small = b2 < r2 * 0.3
        # Candle 3: meaningful bullish candle that closes above midpoint of candle 1
        bar3_bullish = bar3["close"] > bar3["open"] and b3 > r3 * 0.5
        bar3_recovers = bar3["close"] > (bar1["open"] + bar1["close"]) / 2

        if bar1_bearish and bar2_small and bar3_bullish and bar3_recovers:
            rsi = df["rsi_14"].iloc[-1]
            rsi_note = f", RSI={rsi:.1f}" if not pd.isna(rsi) else ""
            return Signal(
                signal_type="BUY",
                confidence=0.67,
                risk_score=0.42,
                expected_upside_pct=11.0,
                stop_loss_pct=6.0,
                target_pct=11.0,
                holding_days=10,
                conditions_met=[
                    f"Morning star: bearish({bar1['close']:.2f}) → doji({bar2['close']:.2f}) → bullish({bar3['close']:.2f}){rsi_note}",
                ],
            )

        return Signal("NONE")

    def get_required_indicators(self) -> list[str]:
        return ["rsi_14"]
