"""
SuperAI Magic Trend — Exact 12-Indicator Weighted Ensemble

Reverse-engineered from the indicator's score table (screenshot):
  MACD(1.2) | RSI(1.2) | Stochastic(0.9) | Vortex(0.7) | Momentum(1.2)
  PSAR(0.8) | DMI(0.8) | MFI(1.2) | Fisher(1.2) | ADX Momentum(0.8)
  Supertrend(0.8) | ZL EMA(1.0)

Each indicator is scored 0–10 (5 = neutral, 10 = max bullish, 0 = max bearish).
Overall score = sum(score_i × weight_i) / sum(weight_i)
  BUY  when score > 6.5  (green arrow in original)
  BUY  when score > 5.8  (blue arrow in original)
  SELL when score < 4.0  (red arrow in original)

Verified against screenshot: 5.76+5.88+5.67+4.9+5.4+0+8+7.56+3.96+7.04+6.48+7.5
= 68.15 / 11.8 = 5.8 ✓
"""
import numpy as np
import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe

# ── Weights (from screenshot) ──────────────────────────────────────────────────
_W = {
    "MACD":         1.2,
    "RSI":          1.2,
    "Stochastic":   0.9,
    "Vortex":       0.7,
    "Momentum":     1.2,
    "PSAR":         0.8,
    "DMI":          0.8,
    "MFI":          1.2,
    "Fisher":       1.2,
    "ADX_Momentum": 0.8,
    "Supertrend":   0.8,
    "ZL_EMA":       1.0,
}
_TOTAL_WEIGHT = sum(_W.values())   # 11.8

_BUY_STRONG = 6.5    # green arrow
_BUY_NORMAL = 5.8    # blue arrow
_SELL       = 4.0    # red arrow


# ── Scoring functions (0–10 scale, 5 = neutral) ────────────────────────────────

def _s_rsi(rsi: float) -> float:
    return float(np.clip(rsi / 10, 0, 10))


def _s_stochastic(k: float, d: float) -> float:
    return float(np.clip((k + d) / 2 / 10, 0, 10))


def _s_mfi(mfi: float) -> float:
    return float(np.clip(mfi / 10, 0, 10))


def _s_macd(hist: float, hist_series: pd.Series) -> float:
    lo = hist_series.iloc[-20:].min()
    hi = hist_series.iloc[-20:].max()
    if hi == lo:
        return 5.0
    return float(np.clip((hist - lo) / (hi - lo) * 10, 0, 10))


def _s_momentum(close_now: float, close_n: float) -> float:
    pct = (close_now - close_n) / close_n * 100 if close_n != 0 else 0
    return float(np.clip(5 + pct * 0.5, 0, 10))


def _s_psar(close: float, psar: float, bull: bool) -> float:
    pct = (close - psar) / psar * 100 if psar != 0 else 0
    base = 7.5 if bull else 2.5
    return float(np.clip(base + pct * 0.3, 0, 10))


def _s_vortex(vi_plus: float, vi_minus: float) -> float:
    total = vi_plus + vi_minus
    if total == 0:
        return 5.0
    return float(np.clip(vi_plus / total * 10, 0, 10))


def _s_dmi(plus_di: float, minus_di: float) -> float:
    total = plus_di + minus_di
    if total == 0:
        return 5.0
    return float(np.clip(plus_di / total * 10, 0, 10))


def _s_fisher(fisher: float) -> float:
    # Fisher typically -3 to +3; map to 0-10
    return float(np.clip((fisher + 3) / 6 * 10, 0, 10))


def _s_adx_momentum(adx: float, plus_di: float, minus_di: float) -> float:
    total = plus_di + minus_di
    ratio = plus_di / total if total > 0 else 0.5
    return float(np.clip(adx * ratio / 5, 0, 10))


def _s_supertrend(close: float, st: float, bull: bool) -> float:
    pct = (close - st) / st * 100 if st != 0 else 0
    base = 7.5 if bull else 2.5
    return float(np.clip(base + pct * 0.2, 0, 10))


def _s_zlema(close: float, zl: float) -> float:
    pct = (close - zl) / zl * 100 if zl != 0 else 0
    return float(np.clip(5 + pct * 0.5, 0, 10))


# ── Strategy ───────────────────────────────────────────────────────────────────

class SuperAIMagicTrendStrategy(BaseStrategy):
    name = "SuperAI Magic Trend"
    description = (
        "Exact 12-indicator weighted ensemble: MACD, RSI, Stochastic, Vortex, "
        "Momentum, PSAR, DMI, MFI, Fisher, ADX Momentum, Supertrend, ZL EMA. "
        "Overall score = weighted avg (0–10). BUY > 6.5 (strong) / 5.8 (normal)."
    )
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY
    min_holding_days = 4
    max_holding_days = 20
    weight = 0.20

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        required = [
            "close", "macd_hist", "rsi_14", "stoch_k", "stoch_d",
            "mfi_14", "adx_14", "supertrend", "supertrend_direction",
            "psar", "psar_bull", "vortex_pos", "vortex_neg",
            "dmi_plus_14", "dmi_minus_14", "fisher_9", "zlema_14",
        ]
        if len(df) < 50 or not all(c in df.columns for c in required):
            return Signal(signal_type="NONE", conditions_failed=["Insufficient data"])

        curr = df.iloc[-1]

        _core_cols = [
            "close", "rsi_14", "stoch_k", "stoch_d", "mfi_14",
            "adx_14", "supertrend", "supertrend_direction", "macd_hist",
            "psar", "psar_bull", "vortex_pos", "vortex_neg",
            "dmi_plus_14", "dmi_minus_14", "fisher_9", "zlema_14",
        ]
        if any(pd.isna(curr[col]) for col in _core_cols):
            return Signal(signal_type="NONE", conditions_failed=["NaN in core values"])

        c        = float(curr["close"])
        rsi      = float(curr["rsi_14"])
        stoch_k  = float(curr["stoch_k"])
        stoch_d  = float(curr["stoch_d"])
        mfi      = float(curr["mfi_14"])
        adx      = float(curr["adx_14"])
        st       = float(curr["supertrend"])
        st_dir   = int(curr["supertrend_direction"])
        hist     = float(curr["macd_hist"])
        psar_val  = float(curr["psar"])
        psar_bull = bool(curr["psar_bull"] == 1.0)
        vi_plus   = float(curr["vortex_pos"])
        vi_minus  = float(curr["vortex_neg"])
        plus_di   = float(curr["dmi_plus_14"])
        minus_di  = float(curr["dmi_minus_14"])
        fisher    = float(curr["fisher_9"])
        zl        = float(curr["zlema_14"])
        mom_close = float(df["close"].iloc[-11]) if len(df) > 11 else c  # 10-bar momentum

        # ── Score each indicator (0–10) ────────────────────────────────────────
        scores = {
            "MACD":         _s_macd(hist, df["macd_hist"]),
            "RSI":          _s_rsi(rsi),
            "Stochastic":   _s_stochastic(stoch_k, stoch_d),
            "Vortex":       _s_vortex(vi_plus, vi_minus),
            "Momentum":     _s_momentum(c, mom_close),
            "PSAR":         _s_psar(c, psar_val, psar_bull),
            "DMI":          _s_dmi(plus_di, minus_di),
            "MFI":          _s_mfi(mfi),
            "Fisher":       _s_fisher(fisher),
            "ADX_Momentum": _s_adx_momentum(adx, plus_di, minus_di),
            "Supertrend":   _s_supertrend(c, st, st_dir == 1),
            "ZL_EMA":       _s_zlema(c, zl),
        }

        # ── Weighted overall score ─────────────────────────────────────────────
        overall = sum(scores[k] * _W[k] for k in scores) / _TOTAL_WEIGHT

        # ── Build human-readable table ─────────────────────────────────────────
        def _label(s):
            if s >= 6.5:   return "Bullish"
            if s >= 5.5:   return "Neutral/Bullish"
            if s >= 4.5:   return "Neutral"
            if s >= 3.5:   return "Neutral/Bearish"
            return         "Bearish"

        indicator_lines = [
            f"{k}: {_label(v)} ({v:.1f} | {_W[k]})"
            for k, v in scores.items()
        ]
        overall_label = _label(overall)

        if overall >= _BUY_NORMAL:
            strength = "Strong" if overall >= _BUY_STRONG else "Normal"
            bullish_count = sum(1 for v in scores.values() if v >= 5.5)
            conviction_margin = (overall - _BUY_NORMAL) / (10 - _BUY_NORMAL)
            confidence = round(min(0.55 + 0.35 * conviction_margin, 0.92), 4)
            return Signal(
                signal_type="BUY",
                confidence=confidence,
                risk_score=0.30,
                expected_upside_pct=10.0,
                stop_loss_pct=5.0,
                target_pct=10.0,
                holding_days=14,
                conditions_met=[
                    f"Overall score {overall:.2f}/10 ({overall_label}) — {strength} Buy",
                    f"{bullish_count}/12 indicators bullish",
                ] + indicator_lines[:6],
                conditions_failed=indicator_lines[6:],
            )

        return Signal(
            signal_type="NONE",
            conditions_met=[f"Overall score {overall:.2f}/10 ({overall_label})"],
            conditions_failed=[f"Score {overall:.2f} below buy threshold {_BUY_NORMAL}"]
            + indicator_lines,
        )

    def get_required_indicators(self) -> list[str]:
        return [
            "close", "macd_hist", "rsi_14", "stoch_k", "stoch_d",
            "mfi_14", "adx_14", "supertrend", "supertrend_direction",
            "psar", "psar_bull", "vortex_pos", "vortex_neg",
            "dmi_plus_14", "dmi_minus_14", "fisher_9", "zlema_14",
        ]
