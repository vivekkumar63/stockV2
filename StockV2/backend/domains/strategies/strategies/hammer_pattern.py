import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class HammerPatternStrategy(BaseStrategy):
    name = "Hammer / Pin Bar Bounce"
    description = "Buy on hammer candle (long lower wick ≥ 2x body, small upper wick) after a pullback"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 5:
            return Signal("NONE")

        bar = df.iloc[-1]
        candle_range = bar["high"] - bar["low"]
        if candle_range <= 0:
            return Signal("NONE")

        body = abs(bar["close"] - bar["open"])
        lower_wick = min(bar["open"], bar["close"]) - bar["low"]
        upper_wick = bar["high"] - max(bar["open"], bar["close"])

        # Hammer: small body, long lower wick ≥ 2x body, small upper wick
        small_body = body < candle_range * 0.35
        long_lower = lower_wick >= body * 2.0
        small_upper = upper_wick <= body * 0.5

        if not (small_body and long_lower and small_upper):
            return Signal("NONE")

        # Requires preceding downtrend (close 3 bars ago > current close)
        prior_trend_down = df["close"].iloc[-4] > df["close"].iloc[-1]
        rsi = df["rsi_14"].iloc[-1]
        rsi_ok = pd.isna(rsi) or rsi < 60

        if prior_trend_down and rsi_ok:
            rsi_note = f", RSI={rsi:.1f}" if not pd.isna(rsi) else ""
            return Signal(
                signal_type="BUY",
                confidence=0.63,
                risk_score=0.43,
                expected_upside_pct=8.0,
                stop_loss_pct=bar["low"] / bar["close"] * 100 - 100 + 0.5,  # just below the wick low
                target_pct=8.0,
                holding_days=6,
                conditions_met=[
                    f"Hammer: body={body:.2f}, lower_wick={lower_wick:.2f}, upper_wick={upper_wick:.2f}{rsi_note}",
                ],
            )

        return Signal("NONE")

    def get_required_indicators(self) -> list[str]:
        return ["rsi_14"]
