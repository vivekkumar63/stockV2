"""
Ichimoku Cloud (Goichi Hosoda, 1969)

The most comprehensive single-indicator trading system ever built.
Five lines derived purely from high/low/close over different periods:

  Tenkan-sen (9)  = midpoint of 9-bar range  → fast conversion line
  Kijun-sen  (26) = midpoint of 26-bar range → slow base line
  Senkou A        = (Tenkan + Kijun) / 2, shifted 26 bars ahead
  Senkou B  (52)  = midpoint of 52-bar range, shifted 26 bars ahead
  Chikou Span     = current close, plotted 26 bars back

The cloud (Kumo) = area between Senkou A and B
  Green cloud (A > B) = bullish
  Red cloud   (B > A) = bearish

Classic "3-way buy" signal (strong buy in Ichimoku theory):
  1. TK Cross: Tenkan crosses ABOVE Kijun
  2. Price above cloud (close > max(cloud_top))
  3. Cloud is GREEN (Senkou A > Senkou B at current bar)

The cloud visible at bar t was computed at bar t−26 (since it's displaced forward).
"""
import numpy as np
import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe

_TENKAN  = 9
_KIJUN   = 26
_SENKOU_B = 52
_DISP    = 26


class IchimokuCloudStrategy(BaseStrategy):
    name = "Ichimoku Cloud"
    description = (
        "Full Ichimoku 3-way buy: TK cross (Tenkan above Kijun) + "
        "price above cloud + green cloud (Senkou A > B)."
    )
    strategy_type = StrategyType.TECHNICAL
    timeframe     = Timeframe.DAILY
    min_holding_days = 5
    max_holding_days = 25
    weight           = 0.20

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < _SENKOU_B + _DISP + 10 or "close" not in df.columns:
            return Signal(signal_type="NONE", conditions_failed=["Insufficient data (need 90+ bars)"])

        high  = df["high"]
        low   = df["low"]
        close = df["close"]

        # Core lines
        tenkan = (high.rolling(_TENKAN).max() + low.rolling(_TENKAN).min()) / 2
        kijun  = (high.rolling(_KIJUN).max()  + low.rolling(_KIJUN).min())  / 2
        span_a = (tenkan + kijun) / 2
        span_b = (high.rolling(_SENKOU_B).max() + low.rolling(_SENKOU_B).min()) / 2

        # Cloud visible at current bar = Span A/B computed 26 bars ago
        cloud_a = float(span_a.iloc[-_DISP - 1])
        cloud_b = float(span_b.iloc[-_DISP - 1])

        t_now  = float(tenkan.iloc[-1])
        t_prev = float(tenkan.iloc[-2])
        k_now  = float(kijun.iloc[-1])
        k_prev = float(kijun.iloc[-2])
        c_now  = float(close.iloc[-1])

        if any(pd.isna(x) for x in [t_now, k_now, cloud_a, cloud_b]):
            return Signal(signal_type="NONE", conditions_failed=["Ichimoku not ready"])

        cloud_top = max(cloud_a, cloud_b)
        cloud_bot = min(cloud_a, cloud_b)

        # Future cloud (what cloud looks like 26 bars from now)
        future_a = float(span_a.iloc[-1])
        future_b = float(span_b.iloc[-1])

        # ── Signal conditions ────────────────────────────────────────────────────
        # 1. TK Cross (Tenkan crosses above Kijun) — allow within last 2 bars
        tk_cross = (t_prev <= k_prev and t_now > k_now)
        tk_above  = t_now > k_now    # currently bullish even without fresh cross

        # 2. Price above cloud
        above_cloud = c_now > cloud_top

        # 3. Green cloud (bullish cloud at current bar)
        green_cloud = cloud_a > cloud_b

        # 4. Future cloud also green (upcoming cloud is bullish — extra conviction)
        future_green = future_a > future_b

        conditions_met    = []
        conditions_failed = []

        if tk_cross:
            conditions_met.append(
                f"TK Cross: Tenkan({t_now:.2f}) crossed above Kijun({k_now:.2f})"
            )
        elif tk_above:
            conditions_met.append(
                f"TK Bullish: Tenkan({t_now:.2f}) > Kijun({k_now:.2f})"
            )
        else:
            conditions_failed.append(
                f"TK Bearish: Tenkan({t_now:.2f}) < Kijun({k_now:.2f})"
            )

        if above_cloud:
            pct = ((c_now - cloud_top) / cloud_top) * 100
            conditions_met.append(
                f"Price {pct:.1f}% above cloud (top={cloud_top:.2f}, bot={cloud_bot:.2f})"
            )
        else:
            conditions_failed.append(
                f"Price inside/below cloud (close={c_now:.2f}, top={cloud_top:.2f})"
            )

        if green_cloud:
            conditions_met.append(
                f"Green cloud: Span A({cloud_a:.2f}) > Span B({cloud_b:.2f}) — bullish"
            )
        else:
            conditions_failed.append(
                f"Red cloud: Span A({cloud_a:.2f}) < Span B({cloud_b:.2f}) — bearish"
            )

        if future_green:
            conditions_met.append("Future cloud (26 bars ahead) is green — sustained bull")
        else:
            conditions_failed.append("Future cloud turning red — weakening trend")

        # Require at minimum: TK bullish + above cloud + green cloud
        if tk_above and above_cloud and green_cloud:
            bonus = 1.0 if tk_cross else 0.0   # fresh cross adds conviction
            fg    = 1.0 if future_green else 0.0
            confidence = round(min(0.62 + 0.12 * bonus + 0.10 * fg, 0.90), 4)
            return Signal(
                signal_type="BUY",
                confidence=confidence,
                risk_score=0.28,
                expected_upside_pct=11.0,
                stop_loss_pct=5.0,
                target_pct=11.0,
                holding_days=15,
                conditions_met=conditions_met,
            )

        return Signal(
            signal_type="NONE",
            conditions_met=conditions_met,
            conditions_failed=conditions_failed,
        )

    def get_required_indicators(self) -> list[str]:
        return ["close", "high", "low"]
