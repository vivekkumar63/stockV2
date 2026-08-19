"""
MACD Bullish Divergence

The edge: price makes a lower low but MACD histogram makes a higher low.
This means selling momentum is exhausted even as price dips further —
institutions are quietly absorbing shares. One of the most reliable reversal
signals a technician has. NOT a simple MACD crossover (that already exists).
"""
import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe

_LOOKBACK = 15  # bars to scan for the divergence pattern


class MACDBullishDivergenceStrategy(BaseStrategy):
    name = "MACD Bullish Divergence"
    description = (
        "Price makes lower low, MACD histogram makes higher low — "
        "momentum exhaustion before reversal"
    )
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY
    min_holding_days = 5
    max_holding_days = 18
    weight = 0.20

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        required = ["macd_hist", "close", "sma_50", "rsi_14", "volume_ratio"]
        if len(df) < _LOOKBACK + 5 or not all(c in df.columns for c in required):
            return Signal(signal_type="NONE", conditions_failed=["Insufficient data"])

        window = df.iloc[-_LOOKBACK:]
        curr = df.iloc[-1]
        close = curr["close"]
        sma_50 = curr["sma_50"]
        rsi = curr["rsi_14"]
        volume_ratio = curr["volume_ratio"]
        hist_now = curr["macd_hist"]

        if any(pd.isna(x) for x in [close, sma_50, rsi, volume_ratio, hist_now]):
            return Signal(signal_type="NONE", conditions_failed=["Missing indicator values"])

        conditions_met = []
        conditions_failed = []

        # --- Divergence detection ---
        # Find the prior local low in price within the window (exclude last 3 bars)
        scan = window.iloc[:-3]
        prior_price_low_idx = scan["close"].idxmin()
        prior_price_low = scan.loc[prior_price_low_idx, "close"]
        prior_hist_at_low = scan.loc[prior_price_low_idx, "macd_hist"]

        # Condition 1: Current price is lower than the prior low (price made new low)
        if close < prior_price_low:
            conditions_met.append(
                f"Price lower low: {close:.2f} < prior {prior_price_low:.2f}"
            )
        else:
            conditions_failed.append(
                f"No price lower low ({close:.2f} vs prior {prior_price_low:.2f})"
            )

        # Condition 2: MACD histogram is HIGHER (less negative) than at the prior price low
        # This is the divergence: selling momentum is weakening
        if hist_now > prior_hist_at_low:
            conditions_met.append(
                f"MACD divergence: hist {hist_now:.5f} > prior {prior_hist_at_low:.5f} (momentum exhaustion)"
            )
        else:
            conditions_failed.append(
                f"No MACD divergence (hist {hist_now:.5f} <= prior {prior_hist_at_low:.5f})"
            )

        # Condition 3: Price still above SMA 50 (divergence in an uptrend = high quality)
        if close > sma_50:
            pct = ((close - sma_50) / sma_50) * 100
            conditions_met.append(f"Price {pct:.1f}% above SMA50 (uptrend context)")
        else:
            conditions_failed.append("Price below SMA50 (lower quality divergence)")

        # Condition 4: RSI in oversold-to-neutral zone (25-50)
        if 25 <= rsi <= 52:
            conditions_met.append(f"RSI={rsi:.1f} in reversal zone")
        else:
            conditions_failed.append(f"RSI={rsi:.1f} outside reversal zone")

        # Condition 5: Volume confirming (buyers showing up)
        if volume_ratio > 1.2:
            conditions_met.append(f"Volume {volume_ratio:.1f}x average (demand returning)")
        else:
            conditions_failed.append(f"Volume {volume_ratio:.1f}x (weak confirmation)")

        if len(conditions_met) == 5:
            divergence_gap = abs(hist_now - prior_hist_at_low)
            normalized_gap = min(divergence_gap / 0.01, 1.0)
            confidence = 0.68 + (0.15 * normalized_gap)
            return Signal(
                signal_type="BUY",
                confidence=round(min(confidence, 0.90), 4),
                risk_score=0.30,
                expected_upside_pct=10.0,
                stop_loss_pct=5.0,
                target_pct=10.0,
                holding_days=12,
                conditions_met=conditions_met,
            )

        return Signal(signal_type="NONE", conditions_met=conditions_met, conditions_failed=conditions_failed)

    def get_required_indicators(self) -> list[str]:
        return ["macd_hist", "close", "sma_50", "rsi_14", "volume_ratio"]
