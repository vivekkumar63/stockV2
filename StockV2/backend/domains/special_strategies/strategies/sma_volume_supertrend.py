"""
SMA 50/200 Golden Cross + Volume + SuperTrend Swing Strategy

Source: Kadia et al. (2026) "Swing Trading Strategy using Simple Moving Average
Crossovers, Traded Volume and Super Trend Confirmations Integrated in Machine
Learning", IJSAT Vol 17, Issue 1.  DOI: 10.71097/IJSAT.v17.i1.10391

Core idea (Section 3.3–3.5):
  - SMA crossover identifies trend direction (eq. 1)
  - Traded volume confirms signal strength: valid only when V_i > ATV_t (eq. 3)
  - SuperTrend (ATR-based, Section 3.5) confirms trend bias and filters whipsaws

Buy signal — Golden Cross (all 3 required):
  1. SMA50 crosses above SMA200 (bullish crossover)
  2. Current volume > 20-bar average traded volume (ATV, eq. 2–3)
  3. SuperTrend direction is BULLISH (price above SuperTrend line)

Sell signal — any one is sufficient:
  1. Death Cross: SMA50 crosses below SMA200
  2. SuperTrend flips to BEARISH (direction -1 on current bar after being +1)
     AND volume confirms (volume > ATV) — high-volume reversals are more reliable
"""

import pandas as pd

from domains.special_strategies.base import SpecialBaseStrategy, SpecialSignal


class SmaVolumeSupertrendStrategy(SpecialBaseStrategy):
    name = "SMA 50/200 + Volume + SuperTrend Swing"
    description = (
        "Buy on SMA50/200 Golden Cross with volume above average (ATV) and SuperTrend bullish. "
        "Sell on Death Cross (SMA50 crosses below SMA200) or SuperTrend flips bearish with volume spike. "
        "Based on Kadia et al. IJSAT 2026."
    )

    # Minimum bars needed: SMA200 warm-up + 2 bars to detect crossover
    _MIN_BARS = 202

    def buy_signal(self, df: pd.DataFrame) -> SpecialSignal:
        if len(df) < self._MIN_BARS:
            return SpecialSignal("NONE")

        sma50_curr  = df["sma_50"].iloc[-1]
        sma50_prev  = df["sma_50"].iloc[-2]
        sma200_curr = df["sma_200"].iloc[-1]
        sma200_prev = df["sma_200"].iloc[-2]
        vol_curr    = df["volume"].iloc[-1]
        atv         = df["volume_sma_20"].iloc[-1]   # Average Traded Volume (ATV)
        st_dir      = df["supertrend_direction"].iloc[-1]
        st_line     = df["supertrend"].iloc[-1]
        close       = df["close"].iloc[-1]

        if any(pd.isna(v) for v in [sma50_curr, sma50_prev, sma200_curr, sma200_prev,
                                     vol_curr, atv, st_dir, st_line, close]):
            return SpecialSignal("NONE")

        met: list[str] = []
        failed: list[str] = []

        # 1. Golden Cross: SMA50 crosses above SMA200
        golden_cross = sma50_prev <= sma200_prev and sma50_curr > sma200_curr
        if golden_cross:
            gap_pct = round((sma50_curr - sma200_curr) / sma200_curr * 100, 3)
            met.append(f"Golden Cross: SMA50({sma50_curr:.2f}) crossed above SMA200({sma200_curr:.2f}) gap={gap_pct}%")
        else:
            if sma50_curr > sma200_curr:
                failed.append(f"SMA50({sma50_curr:.2f}) already above SMA200 — no fresh crossover")
            else:
                failed.append(f"SMA50({sma50_curr:.2f}) <= SMA200({sma200_curr:.2f}) — no Golden Cross")

        # 2. Volume confirmation: current volume > ATV (eq. 3 from paper)
        vol_ratio = round(vol_curr / atv, 2) if atv > 0 else 0.0
        if vol_curr > atv:
            met.append(f"Volume({vol_curr:.0f}) > ATV({atv:.0f}) — ratio {vol_ratio}x")
        else:
            failed.append(f"Volume({vol_curr:.0f}) <= ATV({atv:.0f}) — weak participation")

        # 3. SuperTrend bullish: price above SuperTrend line
        st_bull = int(st_dir) == 1
        if st_bull:
            dist_pct = round((close - st_line) / st_line * 100, 2)
            met.append(f"SuperTrend BULLISH — price({close:.2f}) above ST({st_line:.2f}) +{dist_pct}%")
        else:
            met.append("") if False else failed.append(
                f"SuperTrend BEARISH — price({close:.2f}) below ST line({st_line:.2f})"
            )

        if failed:
            return SpecialSignal("NONE", conditions_met=met, conditions_failed=failed)

        # Confidence scales with volume ratio and SMA gap
        sma_gap_pct = abs(sma50_curr - sma200_curr) / sma200_curr * 100
        confidence = min(0.95, 0.70 + min(0.15, vol_ratio * 0.05) + min(0.10, sma_gap_pct * 0.02))
        return SpecialSignal(
            signal_type="BUY",
            confidence=round(confidence, 4),
            conditions_met=met,
            conditions_failed=[],
        )

    def sell_signal(self, df: pd.DataFrame, entry_price: float | None = None) -> bool:
        if len(df) < 3:
            return False

        sma50_curr  = df["sma_50"].iloc[-1]
        sma50_prev  = df["sma_50"].iloc[-2]
        sma200_curr = df["sma_200"].iloc[-1]
        sma200_prev = df["sma_200"].iloc[-2]
        st_dir_curr = df["supertrend_direction"].iloc[-1]
        st_dir_prev = df["supertrend_direction"].iloc[-2]
        vol_curr    = df["volume"].iloc[-1]
        atv         = df["volume_sma_20"].iloc[-1]

        if any(pd.isna(v) for v in [sma50_curr, sma200_curr, st_dir_curr, vol_curr, atv]):
            return False

        # Exit condition 1: Death Cross — SMA50 crosses below SMA200
        if (not pd.isna(sma50_prev) and not pd.isna(sma200_prev)
                and sma50_prev >= sma200_prev and sma50_curr < sma200_curr):
            return True

        # Exit condition 2: SuperTrend flips bearish AND volume confirms the reversal
        st_flip_bearish = int(st_dir_prev) == 1 and int(st_dir_curr) == -1
        if st_flip_bearish and vol_curr > atv:
            return True

        return False
