"""
Capitulation Reversal

Capitulation is when retail panic sellers dump everything at once — volume
explodes 3x+ and price plunges. But in a healthy stock (above SMA50),
institutions step in on that spike to absorb shares cheaply.

The tell: a massive volume day (3x+), followed by declining volume as price
stabilizes or recovers. The storm has passed. Professionals then enter on
the quiet day after the storm — that's this strategy.

This is fundamentally different from a simple "volume spike reversal" —
it requires the specific pattern of spike THEN drying, AND the stock must
be structurally sound (above SMA50).
"""
import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe

_SPIKE_LOOKBACK = 7       # bars to look back for the capitulation spike
_SPIKE_THRESHOLD = 2.8    # volume must have been 2.8x+ average
_DRY_UP_THRESHOLD = 1.1   # current volume must be < 1.1x average (calm after storm)


class CapitulationReversalStrategy(BaseStrategy):
    name = "Capitulation Reversal"
    description = "Buy the calm after the storm: volume spike 3x+ in last week, now drying up in an uptrend"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY
    min_holding_days = 4
    max_holding_days = 14
    weight = 0.20

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        required = ["volume_ratio", "close", "sma_50", "rsi_14", "macd_hist", "atr_ratio"]
        if len(df) < _SPIKE_LOOKBACK + 5 or not all(c in df.columns for c in required):
            return Signal(signal_type="NONE", conditions_failed=["Insufficient data"])

        curr = df.iloc[-1]
        close = curr["close"]
        sma_50 = curr["sma_50"]
        rsi = curr["rsi_14"]
        volume_ratio_now = curr["volume_ratio"]
        macd_hist = curr["macd_hist"]
        atr_ratio = curr["atr_ratio"]

        if any(pd.isna(x) for x in [close, sma_50, rsi, volume_ratio_now, macd_hist]):
            return Signal(signal_type="NONE", conditions_failed=["Missing indicator values"])

        # Scan recent window for the capitulation spike
        recent_window = df.iloc[-_SPIKE_LOOKBACK:-1]  # exclude today
        max_recent_vol_ratio = recent_window["volume_ratio"].max()
        spike_bar = recent_window.loc[recent_window["volume_ratio"].idxmax()]
        spike_close = spike_bar["close"]
        spike_vol_ratio = spike_bar["volume_ratio"]

        conditions_met = []
        conditions_failed = []

        # Condition 1: There was a capitulation spike in the recent window
        if max_recent_vol_ratio >= _SPIKE_THRESHOLD:
            conditions_met.append(
                f"Capitulation spike: {spike_vol_ratio:.1f}x volume in last {_SPIKE_LOOKBACK} bars"
            )
        else:
            conditions_failed.append(
                f"No capitulation spike (max vol ratio={max_recent_vol_ratio:.1f}x, need {_SPIKE_THRESHOLD}x)"
            )

        # Condition 2: Volume has dried up NOW (the storm has passed)
        if volume_ratio_now < _DRY_UP_THRESHOLD:
            conditions_met.append(f"Volume now {volume_ratio_now:.2f}x average (calm after storm)")
        else:
            conditions_failed.append(
                f"Volume still {volume_ratio_now:.2f}x average (selling not finished)"
            )

        # Condition 3: Price recovered from the spike low (didn't keep falling)
        if close >= spike_close:
            recovery_pct = ((close - spike_close) / spike_close) * 100
            conditions_met.append(f"Price recovered {recovery_pct:.1f}% from capitulation bar")
        else:
            conditions_failed.append(f"Price still below capitulation bar (not stabilized)")

        # Condition 4: Price above SMA 50 (capitulation happened in a fundamentally good stock)
        if close > sma_50:
            pct_above = ((close - sma_50) / sma_50) * 100
            conditions_met.append(f"Price {pct_above:.1f}% above SMA50 (structure intact)")
        else:
            conditions_failed.append("Price below SMA50 (structural damage)")

        # Condition 5: RSI recovering (not free-falling)
        if 28 <= rsi <= 55:
            conditions_met.append(f"RSI={rsi:.1f} stabilizing after capitulation")
        else:
            conditions_failed.append(f"RSI={rsi:.1f} not in recovery range")

        if len(conditions_met) == 5:
            recovery_score = min(((close - spike_close) / spike_close) / 0.05, 1.0)
            spike_score = min((spike_vol_ratio - _SPIKE_THRESHOLD) / 3.0, 1.0)
            confidence = 0.66 + (0.10 * recovery_score) + (0.10 * spike_score)
            return Signal(
                signal_type="BUY",
                confidence=round(min(confidence, 0.92), 4),
                risk_score=0.32,
                expected_upside_pct=10.0,
                stop_loss_pct=5.0,
                target_pct=10.0,
                holding_days=10,
                conditions_met=conditions_met,
            )

        return Signal(signal_type="NONE", conditions_met=conditions_met, conditions_failed=conditions_failed)

    def get_required_indicators(self) -> list[str]:
        return ["volume_ratio", "close", "sma_50", "rsi_14", "macd_hist", "atr_ratio"]
