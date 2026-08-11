"""
Strategy template — copy this file, rename it (no leading _), fill in the class.

HOW TO ADD A NEW STRATEGY
--------------------------
1. cp _template.py  my_strategy.py
2. Rename the class, set a unique `name`, write generate_signal()
3. Restart the backend — auto-discovery picks it up, seeds it to the DB,
   and it immediately appears in the scan and strategy dropdown.

That's it. No imports to register, no lists to edit.

AVAILABLE INDICATOR COLUMNS (always present after IndicatorEngine.compute)
---------------------------------------------------------------------------
Price / OHLCV
  date, open, high, low, close, volume

Moving averages
  sma_5           — Simple MA 5
  sma_10          — Simple MA 10
  sma_20          — Simple MA 20
  sma_50          — Simple MA 50
  ema_9           — Exponential MA 9
  ema_21          — Exponential MA 21

Momentum
  rsi_14          — RSI 14  (0–100)
  rsi_5           — RSI 5   (0–100, faster — reacts quicker to short-term moves)
  roc_10          — Rate of Change 10  (%)
  macd            — MACD line  (12, 26)
  macd_signal     — Signal line  (9)
  macd_hist       — Histogram  (macd − signal)

Volatility / bands
  bb_upper        — Bollinger upper band  (20, 2σ)
  bb_middle       — Bollinger middle (SMA 20)
  bb_lower        — Bollinger lower band  (20, 2σ)
  atr_14          — Average True Range 14 (Wilder EWM)

Volume
  volume_sma_20   — Volume SMA 20
  volume_ratio    — volume / volume_sma_20  (>1 = above-average volume)

Trend
  adx_14              — ADX 14  (>25 = trending)
  supertrend          — SuperTrend line  (7, 3.0)
  supertrend_direction — 1.0 = bullish, -1.0 = bearish

Fast EMAs
  ema_5           — Exponential MA 5
  ema_10          — Exponential MA 10

On Balance Volume
  obv             — On Balance Volume (cumulative)
  obv_sma_10      — OBV SMA 10 (obv > obv_sma_10 = rising trend)

Bollinger Band Width
  bb_width        — (bb_upper - bb_lower) / bb_middle  (low = squeeze)
  bb_width_sma_20 — BB Width SMA 20 (bb_width < bb_width_sma_20 = squeezing)

Gap
  gap_pct         — (open - prev_close) / prev_close * 100  (% gap at open)

Stochastic (14, 3)
  stoch_k         — %K line  (0–100)
  stoch_d         — %D signal line  (3-period SMA of %K)

Volatility
  atr_ratio           — atr_14 / close * 100  (% of price; < 1 = very tight)
  atr_5bar_change     — atr_14 - atr_14.shift(5)  (positive = expanding volatility)

Volume trend
  volume_sma_5bar_change — volume_sma_20 - volume_sma_20.shift(5)  (positive = rising volume trend)

Additional oscillators
  mfi_14          — Money Flow Index 14  (0–100; < 20 oversold, > 80 overbought)
  cci_20          — Commodity Channel Index 20  (extremes: ±100)
  williams_r      — Williams %R 14  (-100–0; < -80 oversold, > -20 overbought)

All columns may contain NaN for early rows (warm-up period).
Always check pd.isna() before using a value.
"""

import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class MyStrategy(BaseStrategy):
    name = "My Strategy Name"           # REQUIRED: unique, shown in UI & DB
    description = "One-line description"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        # df is the full indicator-enriched price history up to today.
        # Use df.iloc[-1] for the latest bar, df.iloc[-2] for previous, etc.

        if len(df) < 2:
            return Signal("NONE")

        # ── Example: buy when RSI crosses below 30 ──────────────────────────
        rsi      = df["rsi_14"].iloc[-1]
        prev_rsi = df["rsi_14"].iloc[-2]

        if pd.isna(rsi) or pd.isna(prev_rsi):
            return Signal("NONE")

        if prev_rsi > 30 and rsi <= 30:
            return Signal(
                signal_type="BUY",
                confidence=0.65,            # 0–1, how sure you are
                risk_score=0.40,            # 0–1, higher = riskier
                expected_upside_pct=12.0,   # informational only
                stop_loss_pct=7.0,          # simulator exits if price falls this %
                target_pct=12.0,            # simulator exits if price rises this %
                holding_days=15,            # simulator force-exits after this many days
                conditions_met=[f"RSI {rsi:.1f} crossed below 30"],
            )

        return Signal("NONE")

    def get_required_indicators(self) -> list[str]:
        return ["rsi_14"]
