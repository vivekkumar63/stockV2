import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class OBVAccumulationDipStrategy(BaseStrategy):
    name = "OBV Accumulation Dip"
    description = "Buy price dips where OBV is stable or rising - smart money accumulating"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY
    min_holding_days = 4
    max_holding_days = 15
    weight = 0.20

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        required = ["obv", "obv_sma_10", "close", "sma_20", "sma_50", "rsi_14", "volume_ratio"]
        if len(df) < 60 or not all(col in df.columns for col in required):
            return Signal(signal_type="NONE", conditions_failed=["Insufficient data"])

        curr = df.iloc[-1]
        obv = curr["obv"]
        obv_sma = curr["obv_sma_10"]
        close = curr["close"]
        sma_20 = curr["sma_20"]
        sma_50 = curr["sma_50"]
        rsi = curr["rsi_14"]
        volume_ratio = curr["volume_ratio"]

        if any(pd.isna(x) for x in [obv, obv_sma, close, sma_20, sma_50, rsi, volume_ratio]):
            return Signal(signal_type="NONE", conditions_failed=["Missing indicator values"])

        # Compare OBV now vs 10 bars ago to detect divergence
        if len(df) >= 11:
            obv_10_bars_ago = df["obv"].iloc[-11]
            price_10_bars_ago = df["close"].iloc[-11]
        else:
            return Signal(signal_type="NONE", conditions_failed=["Insufficient lookback"])

        price_change_pct = ((close - price_10_bars_ago) / price_10_bars_ago) * 100
        obv_change_pct = ((obv - obv_10_bars_ago) / abs(obv_10_bars_ago)) * 100 if obv_10_bars_ago != 0 else 0

        conditions_met = []
        conditions_failed = []

        # Filter 1: Bullish OBV divergence - price down but OBV flat or up (smart money buying)
        if price_change_pct < -1.0 and obv_change_pct >= -2.0:
            conditions_met.append(
                f"Bullish divergence: price {price_change_pct:.1f}% but OBV {obv_change_pct:.1f}%"
            )
        else:
            conditions_failed.append(
                f"No divergence: price {price_change_pct:.1f}%, OBV {obv_change_pct:.1f}%"
            )

        # Filter 2: OBV above its own SMA (overall accumulation trend)
        if obv > obv_sma:
            conditions_met.append("OBV above 10-period SMA (accumulation trend)")
        else:
            conditions_failed.append("OBV below SMA (distribution)")

        # Filter 3: Price above SMA 50 (still in uptrend context)
        if close > sma_50:
            pct = ((close - sma_50) / sma_50) * 100
            conditions_met.append(f"Price {pct:.1f}% above SMA50")
        else:
            conditions_failed.append("Price below SMA50")

        # Filter 4: RSI oversold or recovering (25-50 range)
        if 25 <= rsi <= 50:
            conditions_met.append(f"RSI={rsi:.1f} in dip zone")
        else:
            conditions_failed.append(f"RSI={rsi:.1f} not in dip zone")

        # Filter 5: Volume elevated (confirms accumulation is active)
        if volume_ratio > 1.4:
            conditions_met.append(f"Volume {volume_ratio:.1f}x average")
        else:
            conditions_failed.append(f"Volume {volume_ratio:.1f}x (low)")

        if len(conditions_met) == 5:
            divergence_strength = min(abs(price_change_pct - obv_change_pct) / 10, 1.0)
            confidence = 0.62 + (0.18 * divergence_strength)
            return Signal(
                signal_type="BUY",
                confidence=round(confidence, 4),
                risk_score=0.32,
                expected_upside_pct=9.0,
                stop_loss_pct=5.0,
                target_pct=9.0,
                holding_days=10,
                conditions_met=conditions_met,
            )

        return Signal(signal_type="NONE", conditions_met=conditions_met, conditions_failed=conditions_failed)

    def get_required_indicators(self) -> list[str]:
        return ["obv", "obv_sma_10", "close", "sma_20", "sma_50", "rsi_14", "volume_ratio"]
