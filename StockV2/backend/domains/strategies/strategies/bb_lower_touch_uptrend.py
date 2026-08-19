import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class BBLowerTouchUptrendStrategy(BaseStrategy):
    name = "Bollinger Lower Touch Uptrend"
    description = "Buy when price tags the lower BB in an uptrend with Williams %R oversold confirmation"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY
    min_holding_days = 3
    max_holding_days = 12
    weight = 0.20

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        required = ["bb_lower", "bb_middle", "close", "sma_50", "rsi_14", "williams_r", "volume_ratio"]
        if len(df) < 60 or not all(col in df.columns for col in required):
            return Signal(signal_type="NONE", conditions_failed=["Insufficient data"])

        curr = df.iloc[-1]
        bb_lower = curr["bb_lower"]
        bb_middle = curr["bb_middle"]
        close = curr["close"]
        sma_50 = curr["sma_50"]
        rsi = curr["rsi_14"]
        williams_r = curr["williams_r"]
        volume_ratio = curr["volume_ratio"]

        if any(pd.isna(x) for x in [bb_lower, bb_middle, close, sma_50, rsi, williams_r, volume_ratio]):
            return Signal(signal_type="NONE", conditions_failed=["Missing indicator values"])

        conditions_met = []
        conditions_failed = []

        # Filter 1: Price tagging lower BB (within 1.5% above it)
        pct_from_bb_lower = ((close - bb_lower) / bb_lower) * 100
        if 0 <= pct_from_bb_lower <= 1.5:
            conditions_met.append(f"Price {pct_from_bb_lower:.1f}% above lower BB (tagging support)")
        else:
            conditions_failed.append(f"Price {pct_from_bb_lower:.1f}% from lower BB (not tagging)")

        # Filter 2: Price above SMA 50 (dip within an uptrend, not a breakdown)
        if close > sma_50:
            pct_above = ((close - sma_50) / sma_50) * 100
            conditions_met.append(f"Price {pct_above:.1f}% above SMA50 (uptrend intact)")
        else:
            conditions_failed.append("Price below SMA50 (breakdown, not dip)")

        # Filter 3: RSI oversold (confirming the dip is real)
        if rsi < 38:
            conditions_met.append(f"RSI={rsi:.1f} oversold (confirming dip)")
        else:
            conditions_failed.append(f"RSI={rsi:.1f} not oversold")

        # Filter 4: Williams %R oversold (double confirmation of short-term oversold)
        if williams_r < -70:
            conditions_met.append(f"Williams %R={williams_r:.1f} oversold")
        else:
            conditions_failed.append(f"Williams %R={williams_r:.1f} not oversold")

        # Filter 5: Volume above average (demand at support)
        if volume_ratio > 1.3:
            conditions_met.append(f"Volume {volume_ratio:.1f}x average at support")
        else:
            conditions_failed.append(f"Volume {volume_ratio:.1f}x (no demand at support)")

        if len(conditions_met) == 5:
            # BB middle is the natural target (mean reversion)
            bb_target_pct = ((bb_middle - close) / close) * 100
            rsi_depth = (38 - rsi) / 38
            confidence = 0.65 + (0.15 * rsi_depth)
            return Signal(
                signal_type="BUY",
                confidence=round(confidence, 4),
                risk_score=0.30,
                expected_upside_pct=round(bb_target_pct, 1),
                stop_loss_pct=4.0,  # Below the lower BB = setup invalidated
                target_pct=min(bb_target_pct + 1.0, 10.0),
                holding_days=8,
                conditions_met=conditions_met,
            )

        return Signal(signal_type="NONE", conditions_met=conditions_met, conditions_failed=conditions_failed)

    def get_required_indicators(self) -> list[str]:
        return ["bb_lower", "bb_middle", "close", "sma_50", "rsi_14", "williams_r", "volume_ratio"]
