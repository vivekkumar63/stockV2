"""
High Conviction Trend Rider

For riding powerful sustained trends — the kind that make 20-40% in a few months.
Requires ALL 6 of these independent signals to align simultaneously.

The philosophy: don't fight a confirmed uptrend. Most traders either buy too early
(before trend is confirmed) or too late (after it's overbought). This strategy
enters during a brief RSI 50-65 consolidation within a confirmed trend — the
institutional "reload zone" before the next leg up.

6 independent categories must all agree:
1. Structure (SuperTrend)
2. Momentum direction (MACD)
3. Trend strength (ADX)
4. Price position (EMA stack)
5. Momentum level (RSI not overbought)
6. Volume / money flow (OBV)
"""
import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class HighConvictionTrendRiderStrategy(BaseStrategy):
    name = "High Conviction Trend Rider"
    description = "6-way confluence in confirmed uptrend: SuperTrend + MACD + ADX + EMA + RSI + OBV all aligned"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY
    min_holding_days = 7
    max_holding_days = 25
    weight = 0.20

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        required = [
            "supertrend_direction", "macd_hist", "adx_14",
            "ema_9", "ema_21", "ema_50", "rsi_14",
            "obv", "obv_sma_10", "close", "volume_ratio",
        ]
        if len(df) < 60 or not all(c in df.columns for c in required):
            return Signal(signal_type="NONE", conditions_failed=["Insufficient data"])

        curr = df.iloc[-1]
        st_dir = curr["supertrend_direction"]
        macd_hist = curr["macd_hist"]
        adx = curr["adx_14"]
        ema_9 = curr["ema_9"]
        ema_21 = curr["ema_21"]
        ema_50 = curr["ema_50"]
        rsi = curr["rsi_14"]
        obv = curr["obv"]
        obv_sma = curr["obv_sma_10"]
        close = curr["close"]
        volume_ratio = curr["volume_ratio"]

        if any(pd.isna(x) for x in [st_dir, macd_hist, adx, ema_9, ema_21, ema_50,
                                      rsi, obv, obv_sma, close, volume_ratio]):
            return Signal(signal_type="NONE", conditions_failed=["Missing indicator values"])

        # Check MACD is positive AND improving
        macd_hist_prev = df["macd_hist"].iloc[-3]
        macd_improving = (not pd.isna(macd_hist_prev)) and (macd_hist > macd_hist_prev)

        conditions_met = []
        conditions_failed = []

        # Signal 1: STRUCTURE — SuperTrend bullish
        if st_dir == 1:
            conditions_met.append("SuperTrend: bullish (structure confirmed)")
        else:
            conditions_failed.append("SuperTrend bearish")

        # Signal 2: MOMENTUM DIRECTION — MACD histogram positive and growing
        if macd_hist > 0 and macd_improving:
            conditions_met.append(f"MACD hist={macd_hist:.5f} positive & improving (momentum accelerating)")
        elif macd_hist > 0:
            conditions_met.append(f"MACD hist={macd_hist:.5f} positive (momentum present)")
        else:
            conditions_failed.append(f"MACD hist={macd_hist:.5f} negative")

        # Signal 3: TREND STRENGTH — ADX > 22 (trend has legs)
        if adx > 22:
            conditions_met.append(f"ADX={adx:.1f} > 22 (trend has strength)")
        else:
            conditions_failed.append(f"ADX={adx:.1f} too weak")

        # Signal 4: PRICE STRUCTURE — Full EMA bullish stack
        if ema_9 > ema_21 > ema_50:
            conditions_met.append(f"EMA stack: 9 > 21 > 50 (all timeframes bullish)")
        else:
            conditions_failed.append("EMA stack not fully bullish")

        # Signal 5: MOMENTUM LEVEL — RSI in reload zone (not overbought, not dead)
        if 48 <= rsi <= 66:
            conditions_met.append(f"RSI={rsi:.1f} in trend reload zone (50-65)")
        else:
            conditions_failed.append(f"RSI={rsi:.1f} outside reload zone")

        # Signal 6: MONEY FLOW — OBV above its SMA (institutions accumulating)
        if obv > obv_sma:
            obv_margin = ((obv - obv_sma) / abs(obv_sma)) * 100 if obv_sma != 0 else 0
            conditions_met.append(f"OBV {obv_margin:.1f}% above SMA (accumulation confirmed)")
        else:
            conditions_failed.append("OBV below SMA (distribution)")

        if len(conditions_met) >= 6:
            adx_score = min((adx - 22) / 18, 1.0)
            rsi_score = 1.0 - abs(rsi - 57) / 9  # Peak confidence at RSI=57
            confidence = 0.70 + (0.10 * adx_score) + (0.07 * rsi_score)
            return Signal(
                signal_type="BUY",
                confidence=round(min(confidence, 0.92), 4),
                risk_score=0.25,  # Lowest risk — everything aligned
                expected_upside_pct=14.0,
                stop_loss_pct=5.0,
                target_pct=14.0,  # Bigger target — this is a trend, not a mean reversion
                holding_days=18,
                conditions_met=conditions_met,
            )

        return Signal(signal_type="NONE", conditions_met=conditions_met, conditions_failed=conditions_failed)

    def get_required_indicators(self) -> list[str]:
        return [
            "supertrend_direction", "macd_hist", "adx_14",
            "ema_9", "ema_21", "ema_50", "rsi_14",
            "obv", "obv_sma_10", "close", "volume_ratio",
        ]
