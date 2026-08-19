import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class EMAGoldenStackPullbackStrategy(BaseStrategy):
    name = "EMA Golden Stack Pullback"
    description = "Buy pullbacks to EMA21 when EMA9 > EMA21 > EMA50 (full bullish alignment)"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY
    min_holding_days = 4
    max_holding_days = 14
    weight = 0.20

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        required = ["ema_9", "ema_21", "ema_50", "close", "rsi_14", "volume_ratio", "macd_hist"]
        if len(df) < 60 or not all(col in df.columns for col in required):
            return Signal(signal_type="NONE", conditions_failed=["Insufficient data"])

        curr = df.iloc[-1]
        ema_9 = curr["ema_9"]
        ema_21 = curr["ema_21"]
        ema_50 = curr["ema_50"]
        close = curr["close"]
        rsi = curr["rsi_14"]
        volume_ratio = curr["volume_ratio"]
        macd_hist = curr["macd_hist"]

        if any(pd.isna(x) for x in [ema_9, ema_21, ema_50, close, rsi, volume_ratio, macd_hist]):
            return Signal(signal_type="NONE", conditions_failed=["Missing indicator values"])

        conditions_met = []
        conditions_failed = []

        # Filter 1: Full bullish EMA stack
        if ema_9 > ema_21 > ema_50:
            conditions_met.append(f"EMA stack bullish (9={ema_9:.2f} > 21={ema_21:.2f} > 50={ema_50:.2f})")
        else:
            conditions_failed.append("EMA stack not fully bullish")

        # Filter 2: Price pulled back to EMA21 (within 2% above)
        pct_from_ema21 = ((close - ema_21) / ema_21) * 100
        if 0 <= pct_from_ema21 <= 2.0:
            conditions_met.append(f"Price {pct_from_ema21:.1f}% above EMA21 (touching support)")
        else:
            conditions_failed.append(f"Price {pct_from_ema21:.1f}% from EMA21 (not a pullback)")

        # Filter 3: RSI in mid-zone (not oversold, just refreshed)
        if 38 <= rsi <= 58:
            conditions_met.append(f"RSI={rsi:.1f} in healthy pullback zone")
        else:
            conditions_failed.append(f"RSI={rsi:.1f} outside healthy range")

        # Filter 4: MACD histogram above 0 (momentum still positive)
        if macd_hist > 0:
            conditions_met.append(f"MACD histogram positive ({macd_hist:.4f})")
        else:
            conditions_failed.append("MACD histogram negative (momentum fading)")

        # Filter 5: Volume below average on pullback (healthy consolidation, not panic selling)
        if 0.5 <= volume_ratio <= 1.2:
            conditions_met.append(f"Low-volume pullback ({volume_ratio:.1f}x) - healthy consolidation")
        else:
            conditions_failed.append(f"Volume {volume_ratio:.1f}x - not a healthy pullback")

        if len(conditions_met) == 5:
            proximity_score = (2.0 - pct_from_ema21) / 2.0  # Closer to EMA21 = higher confidence
            confidence = 0.65 + (0.15 * proximity_score)
            return Signal(
                signal_type="BUY",
                confidence=round(confidence, 4),
                risk_score=0.30,
                expected_upside_pct=9.0,
                stop_loss_pct=4.0,  # Tight: EMA21 is your support, break = invalidated
                target_pct=9.0,
                holding_days=10,
                conditions_met=conditions_met,
            )

        return Signal(signal_type="NONE", conditions_met=conditions_met, conditions_failed=conditions_failed)

    def get_required_indicators(self) -> list[str]:
        return ["ema_9", "ema_21", "ema_50", "close", "rsi_14", "volume_ratio", "macd_hist"]
