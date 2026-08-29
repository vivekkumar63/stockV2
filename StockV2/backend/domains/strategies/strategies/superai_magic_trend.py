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


# ── Indicator helpers ──────────────────────────────────────────────────────────

def _wilder_smooth(arr: np.ndarray, period: int) -> np.ndarray:
    out = np.zeros(len(arr))
    if len(arr) <= period:
        return out
    out[period] = arr[1:period + 1].sum()
    for i in range(period + 1, len(arr)):
        out[i] = out[i - 1] - out[i - 1] / period + arr[i]
    return out


def _compute_psar(high: np.ndarray, low: np.ndarray,
                  af_start=0.02, af_step=0.02, af_max=0.2):
    """Parabolic SAR. Returns (psar_value, trend) for last bar."""
    n = len(high)
    psar = np.full(n, np.nan)
    ep   = np.zeros(n)
    af   = np.zeros(n)
    bull = np.ones(n, dtype=bool)

    psar[0] = low[0]
    ep[0]   = high[0]
    af[0]   = af_start

    for i in range(1, n):
        if bull[i - 1]:
            psar[i] = psar[i - 1] + af[i - 1] * (ep[i - 1] - psar[i - 1])
            psar[i] = min(psar[i], low[i - 1], low[max(0, i - 2)])
            if low[i] < psar[i]:           # reversal → bearish
                bull[i] = False
                psar[i] = ep[i - 1]
                ep[i]   = low[i]
                af[i]   = af_start
            else:
                bull[i] = True
                ep[i]   = max(ep[i - 1], high[i])
                af[i]   = min(af[i - 1] + af_step, af_max) if high[i] > ep[i - 1] else af[i - 1]
        else:
            psar[i] = psar[i - 1] + af[i - 1] * (ep[i - 1] - psar[i - 1])
            psar[i] = max(psar[i], high[i - 1], high[max(0, i - 2)])
            if high[i] > psar[i]:          # reversal → bullish
                bull[i] = True
                psar[i] = ep[i - 1]
                ep[i]   = high[i]
                af[i]   = af_start
            else:
                bull[i] = False
                ep[i]   = min(ep[i - 1], low[i])
                af[i]   = min(af[i - 1] + af_step, af_max) if low[i] < ep[i - 1] else af[i - 1]

    return psar[-1], bull[-1]


def _compute_vortex(high: np.ndarray, low: np.ndarray,
                    close: np.ndarray, period=14):
    """Returns (VI+, VI-)."""
    n = len(high)
    if n < period + 1:
        return 1.0, 1.0
    tr      = np.zeros(n)
    vmp     = np.zeros(n)
    vmm     = np.zeros(n)
    for i in range(1, n):
        tr[i]  = max(high[i] - low[i],
                     abs(high[i] - close[i - 1]),
                     abs(low[i]  - close[i - 1]))
        vmp[i] = abs(high[i] - low[i - 1])
        vmm[i] = abs(low[i]  - high[i - 1])
    s_tr  = tr[-period:].sum()
    s_vmp = vmp[-period:].sum()
    s_vmm = vmm[-period:].sum()
    if s_tr == 0:
        return 1.0, 1.0
    return s_vmp / s_tr, s_vmm / s_tr


def _compute_dmi(high: np.ndarray, low: np.ndarray,
                 close: np.ndarray, period=14):
    """Returns (+DI, -DI) using Wilder smoothing."""
    n = len(high)
    pdm = np.zeros(n)
    mdm = np.zeros(n)
    tr  = np.zeros(n)
    for i in range(1, n):
        up   = high[i]  - high[i - 1]
        down = low[i - 1] - low[i]
        tr[i] = max(high[i] - low[i],
                    abs(high[i] - close[i - 1]),
                    abs(low[i]  - close[i - 1]))
        if up > down and up > 0:
            pdm[i] = up
        if down > up and down > 0:
            mdm[i] = down
    s_pdm = _wilder_smooth(pdm, period)
    s_mdm = _wilder_smooth(mdm, period)
    s_tr  = _wilder_smooth(tr,  period)
    if s_tr[-1] == 0:
        return 25.0, 25.0
    return 100 * s_pdm[-1] / s_tr[-1], 100 * s_mdm[-1] / s_tr[-1]


def _compute_fisher(high: np.ndarray, low: np.ndarray, period=9):
    """Fisher Transform."""
    if len(high) < period:
        return 0.0
    highest = high[-period:].max()
    lowest  = low[-period:].min()
    if highest == lowest:
        return 0.0
    hl2   = (high[-1] + low[-1]) / 2
    value = np.clip(2 * (hl2 - lowest) / (highest - lowest) - 1, -0.999, 0.999)
    return float(0.5 * np.log((1 + value) / (1 - value)))


def _zlema(close: pd.Series, period=14) -> float:
    """Zero-Lag EMA = 2·EMA(n) − EMA(n//2)."""
    if len(close) < period:
        return float(close.iloc[-1])
    return float(
        2 * close.ewm(span=period, adjust=False).mean().iloc[-1]
        - close.ewm(span=max(period // 2, 1), adjust=False).mean().iloc[-1]
    )


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
            "close", "high", "low",
            "macd_hist", "rsi_14", "stoch_k", "stoch_d",
            "mfi_14", "adx_14", "supertrend", "supertrend_direction",
        ]
        if len(df) < 50 or not all(c in df.columns for c in required):
            return Signal(signal_type="NONE", conditions_failed=["Insufficient data"])

        curr  = df.iloc[-1]
        high  = df["high"].values
        low   = df["low"].values
        close = df["close"].values

        _core_cols = ["close", "rsi_14", "stoch_k", "stoch_d", "mfi_14",
                      "adx_14", "supertrend", "supertrend_direction", "macd_hist"]
        if any(pd.isna(curr[col]) for col in _core_cols):
            return Signal(signal_type="NONE", conditions_failed=["NaN in core values"])

        c       = float(curr["close"])
        rsi     = float(curr["rsi_14"])
        stoch_k = float(curr["stoch_k"])
        stoch_d = float(curr["stoch_d"])
        mfi     = float(curr["mfi_14"])
        adx     = float(curr["adx_14"])
        st      = float(curr["supertrend"])
        st_dir  = int(curr["supertrend_direction"])
        hist    = float(curr["macd_hist"])

        # ── Compute indicators not in precomputed set ──────────────────────────
        psar_val, psar_bull  = _compute_psar(high, low)
        vi_plus,  vi_minus   = _compute_vortex(high, low, close)
        plus_di,  minus_di   = _compute_dmi(high, low, close)
        fisher               = _compute_fisher(high, low)
        zl                   = _zlema(df["close"])
        mom_close            = float(df["close"].iloc[-11]) if len(df) > 11 else c  # 10-bar momentum

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
            "close", "high", "low",
            "macd_hist", "rsi_14", "stoch_k", "stoch_d",
            "mfi_14", "adx_14", "supertrend", "supertrend_direction",
        ]
