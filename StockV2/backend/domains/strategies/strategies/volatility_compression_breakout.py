"""
Volatility Compression Breakout

Markets oscillate between expansion and contraction. When volatility compresses
to a multi-week low AND the stock is in an uptrend, it's a coiled spring.
The breakout that follows is often fast and high-probability.

This is more sophisticated than a simple BB squeeze check — it requires:
- BB width at a true multi-bar low (compression confirmed)
- 5-bar price range contracting (price coiling, not just BB math)
- Price above both SMA 20 and SMA 50 (uptrend preserved during compression)
- MACD histogram positive or improving (momentum not dying)
- Volume contracting during squeeze (no distribution — just waiting)
"""
import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe

_SQUEEZE_LOOKBACK = 20   # bars to define BB width low
_RANGE_LOOKBACK = 5      # bars for price range contraction check


class VolatilityCompressionBreakoutStrategy(BaseStrategy):
    name = "Volatility Compression Breakout"
    description = "Buy the coiled spring: BB width at multi-week low + price above trend + volume drying up"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY
    min_holding_days = 4
    max_holding_days = 16
    weight = 0.20

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        required = ["bb_width", "close", "high", "low", "sma_20", "sma_50", "macd_hist", "volume_ratio", "rsi_14"]
        if len(df) < _SQUEEZE_LOOKBACK + 5 or not all(c in df.columns for c in required):
            return Signal(signal_type="NONE", conditions_failed=["Insufficient data"])

        curr = df.iloc[-1]
        close = curr["close"]
        sma_20 = curr["sma_20"]
        sma_50 = curr["sma_50"]
        bb_width = curr["bb_width"]
        macd_hist = curr["macd_hist"]
        macd_hist_prev = df["macd_hist"].iloc[-3]  # 3 bars ago for trend
        volume_ratio = curr["volume_ratio"]
        rsi = curr["rsi_14"]

        if any(pd.isna(x) for x in [close, sma_20, sma_50, bb_width, macd_hist, volume_ratio, rsi]):
            return Signal(signal_type="NONE", conditions_failed=["Missing indicator values"])

        # Price range over last N bars (coiling check)
        recent = df.iloc[-_RANGE_LOOKBACK:]
        price_range_recent = recent["high"].max() - recent["low"].min()
        prior = df.iloc[-_SQUEEZE_LOOKBACK:-_RANGE_LOOKBACK]
        price_range_prior = prior["high"].max() - prior["low"].min()
        range_contraction = (price_range_recent / price_range_prior) if price_range_prior > 0 else 1.0

        # Is BB width at a true multi-bar low?
        bb_width_min = df["bb_width"].iloc[-_SQUEEZE_LOOKBACK:-1].min()
        bb_at_low = bb_width <= bb_width_min * 1.05  # within 5% of the squeeze low

        conditions_met = []
        conditions_failed = []

        # Condition 1: BB width at multi-bar low (true compression)
        if bb_at_low:
            conditions_met.append(
                f"BB width={bb_width:.4f} at {_SQUEEZE_LOOKBACK}-bar low (compression confirmed)"
            )
        else:
            conditions_failed.append(
                f"BB width={bb_width:.4f} not at squeeze low ({bb_width_min:.4f})"
            )

        # Condition 2: Price range contracting (coiling, not just BB math)
        if range_contraction < 0.70:
            conditions_met.append(
                f"Price range contracted {(1-range_contraction)*100:.0f}% vs prior period (coiling)"
            )
        else:
            conditions_failed.append(
                f"Price range not contracting enough ({range_contraction:.2f} ratio)"
            )

        # Condition 3: Price above SMA 20 and SMA 50 (compression in uptrend)
        if close > sma_20 and close > sma_50:
            conditions_met.append(
                f"Price above both SMA20={sma_20:.2f} and SMA50={sma_50:.2f}"
            )
        else:
            conditions_failed.append("Price not above both SMAs (downtrend compression)")

        # Condition 4: MACD histogram positive or improving (momentum alive)
        hist_improving = (not pd.isna(macd_hist_prev)) and (macd_hist > macd_hist_prev)
        if macd_hist > 0 or hist_improving:
            direction = "positive" if macd_hist > 0 else "improving"
            conditions_met.append(f"MACD histogram {direction} ({macd_hist:.5f}) — momentum intact")
        else:
            conditions_failed.append(f"MACD histogram declining ({macd_hist:.5f})")

        # Condition 5: Volume drying up during compression (healthy coil, no distribution)
        if volume_ratio < 0.85:
            conditions_met.append(
                f"Volume {volume_ratio:.2f}x average (drying up — no distribution)"
            )
        else:
            conditions_failed.append(
                f"Volume {volume_ratio:.2f}x (not contracting, possible distribution)"
            )

        if len(conditions_met) == 5:
            # The tighter the coil, the bigger the expected move
            compression_score = 1.0 - min(range_contraction / 0.70, 1.0)
            confidence = 0.67 + (0.16 * compression_score)
            return Signal(
                signal_type="BUY",
                confidence=round(confidence, 4),
                risk_score=0.28,
                expected_upside_pct=11.0,
                stop_loss_pct=4.0,  # Tight: compression breaks = setup done
                target_pct=11.0,
                holding_days=10,
                conditions_met=conditions_met,
            )

        return Signal(signal_type="NONE", conditions_met=conditions_met, conditions_failed=conditions_failed)

    def get_required_indicators(self) -> list[str]:
        return ["bb_width", "close", "high", "low", "sma_20", "sma_50", "macd_hist", "volume_ratio", "rsi_14"]
