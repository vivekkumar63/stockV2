import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class SupertrendRSIResetStrategy(BaseStrategy):
    name = "SuperTrend RSI Reset"
    description = "Buy when SuperTrend is bullish and RSI resets to mid-zone after pullback"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY
    min_holding_days = 3
    max_holding_days = 12
    weight = 0.20

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        required = ["supertrend_direction", "supertrend", "rsi_14", "close", "volume_ratio", "cci_20"]
        if len(df) < 60 or not all(col in df.columns for col in required):
            return Signal(signal_type="NONE", conditions_failed=["Insufficient data"])

        curr = df.iloc[-1]
        st_dir = curr["supertrend_direction"]
        st_line = curr["supertrend"]
        rsi = curr["rsi_14"]
        close = curr["close"]
        volume_ratio = curr["volume_ratio"]
        cci = curr["cci_20"]

        if any(pd.isna(x) for x in [st_dir, st_line, rsi, close, volume_ratio, cci]):
            return Signal(signal_type="NONE", conditions_failed=["Missing indicator values"])

        # Look back to confirm RSI was recently oversold (in last 5 bars)
        recent_rsi_min = df["rsi_14"].iloc[-6:-1].min() if len(df) >= 6 else rsi
        rsi_was_oversold = recent_rsi_min < 38

        conditions_met = []
        conditions_failed = []

        # Filter 1: SuperTrend is bullish (direction = 1)
        if st_dir == 1:
            pct_above_st = ((close - st_line) / st_line) * 100
            conditions_met.append(f"SuperTrend bullish, price {pct_above_st:.1f}% above line")
        else:
            conditions_failed.append("SuperTrend bearish")

        # Filter 2: RSI recently was oversold and is now recovering (35-52 range)
        if rsi_was_oversold and 35 <= rsi <= 52:
            conditions_met.append(f"RSI reset: was oversold (min={recent_rsi_min:.1f}), now {rsi:.1f}")
        else:
            conditions_failed.append(f"RSI not resetting (current={rsi:.1f}, recent min={recent_rsi_min:.1f})")

        # Filter 3: Price above SuperTrend line
        if close > st_line:
            conditions_met.append(f"Close={close:.2f} above SuperTrend={st_line:.2f}")
        else:
            conditions_failed.append("Price below SuperTrend line")

        # Filter 4: Volume confirming (buying pressure returning)
        if volume_ratio > 1.2:
            conditions_met.append(f"Volume {volume_ratio:.1f}x average (demand returning)")
        else:
            conditions_failed.append(f"Volume {volume_ratio:.1f}x (weak demand)")

        # Filter 5: CCI recovering (not deeply negative)
        if cci > -80:
            conditions_met.append(f"CCI={cci:.1f} recovering (not deeply negative)")
        else:
            conditions_failed.append(f"CCI={cci:.1f} too negative")

        if len(conditions_met) == 5:
            rsi_recovery = (rsi - 35) / 17  # How far from oversold (0 = just left 35, 1 = at 52)
            confidence = 0.63 + (0.15 * rsi_recovery)
            return Signal(
                signal_type="BUY",
                confidence=round(confidence, 4),
                risk_score=0.33,
                expected_upside_pct=8.0,
                stop_loss_pct=4.5,
                target_pct=8.0,
                holding_days=8,
                conditions_met=conditions_met,
            )

        return Signal(signal_type="NONE", conditions_met=conditions_met, conditions_failed=conditions_failed)

    def get_required_indicators(self) -> list[str]:
        return ["supertrend_direction", "supertrend", "rsi_14", "close", "volume_ratio", "cci_20"]
