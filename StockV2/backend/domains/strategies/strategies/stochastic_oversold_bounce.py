import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class StochasticOversoldBounceStrategy(BaseStrategy):
    name = "Stochastic Oversold Bounce"
    description = "Buy stochastic %K crossing above %D from oversold zone in an uptrend"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY
    min_holding_days = 3
    max_holding_days = 10
    weight = 0.20

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        required = ["stoch_k", "stoch_d", "sma_50", "close", "rsi_14", "volume_ratio", "adx_14"]
        if len(df) < 60 or not all(col in df.columns for col in required):
            return Signal(signal_type="NONE", conditions_failed=["Insufficient data"])

        curr = df.iloc[-1]
        prev = df.iloc[-2]

        stoch_k = curr["stoch_k"]
        stoch_d = curr["stoch_d"]
        prev_k = prev["stoch_k"]
        prev_d = prev["stoch_d"]
        close = curr["close"]
        sma_50 = curr["sma_50"]
        rsi = curr["rsi_14"]
        volume_ratio = curr["volume_ratio"]
        adx = curr["adx_14"]

        if any(pd.isna(x) for x in [stoch_k, stoch_d, prev_k, prev_d, close, sma_50, rsi, volume_ratio, adx]):
            return Signal(signal_type="NONE", conditions_failed=["Missing indicator values"])

        conditions_met = []
        conditions_failed = []

        # Filter 1: Stochastic %K crossing above %D (bullish crossover)
        if prev_k <= prev_d and stoch_k > stoch_d:
            conditions_met.append(f"Stoch K={stoch_k:.1f} crossed above D={stoch_d:.1f}")
        else:
            conditions_failed.append(f"No stoch crossover (K={stoch_k:.1f}, D={stoch_d:.1f})")

        # Filter 2: Both stoch lines in oversold zone (<25 relaxed from 20 for more signals)
        if stoch_k < 25 and stoch_d < 25:
            conditions_met.append(f"Stoch in oversold zone (K={stoch_k:.1f}, D={stoch_d:.1f})")
        else:
            conditions_failed.append(f"Stoch not in oversold zone")

        # Filter 3: Price above SMA 50 (uptrend)
        if close > sma_50:
            pct = ((close - sma_50) / sma_50) * 100
            conditions_met.append(f"Price {pct:.1f}% above SMA50")
        else:
            conditions_failed.append("Price below SMA50 (downtrend)")

        # Filter 4: RSI not extreme (30-55 zone = pullback, not collapse)
        if 28 <= rsi <= 55:
            conditions_met.append(f"RSI={rsi:.1f} in pullback zone")
        else:
            conditions_failed.append(f"RSI={rsi:.1f} outside pullback zone")

        # Filter 5: Volume confirmation
        if volume_ratio > 1.3:
            conditions_met.append(f"Volume {volume_ratio:.1f}x average")
        else:
            conditions_failed.append(f"Volume {volume_ratio:.1f}x (insufficient)")

        if len(conditions_met) == 5:
            crossover_depth = (25 - stoch_k) / 25
            confidence = 0.62 + min(0.20 * crossover_depth, 0.20)
            return Signal(
                signal_type="BUY",
                confidence=round(confidence, 4),
                risk_score=0.35,
                expected_upside_pct=7.0,
                stop_loss_pct=5.0,
                target_pct=7.0,
                holding_days=7,
                conditions_met=conditions_met,
            )

        return Signal(signal_type="NONE", conditions_met=conditions_met, conditions_failed=conditions_failed)

    def get_required_indicators(self) -> list[str]:
        return ["stoch_k", "stoch_d", "sma_50", "close", "rsi_14", "volume_ratio", "adx_14"]
