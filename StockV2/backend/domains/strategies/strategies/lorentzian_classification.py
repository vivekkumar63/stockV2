"""
Lorentzian Classification (KNN with Lorentzian Distance)

Faithful Python port of jdehorty's open-source Pine Script:
https://www.tradingview.com/script/WhBzgfDu-Machine-Learning-Lorentzian-Classification/

Algorithm (directly from the Pine source):

1. FEATURES — 5 normalized technical indicators form the "fingerprint" of each bar:
     f1 = RSI(14)
     f2 = Wave Trend(10, 11) on HLC3
     f3 = CCI(20)
     f4 = ADX(14)   [Pine uses ADX(20), we use adx_14 from precomputed set]
     f5 = RSI(9)

2. LORENTZIAN DISTANCE — for each historical bar i vs current bar:
     d(i) = Σ log(1 + |f_current[k] - f_history[i][k]|)   for k in 1..5

   Why not Euclidean? log(1+x) compresses large outliers (Black Swan events,
   FOMC gaps) that would otherwise dominate and "warp price-time".

3. ANN / KNN SEARCH — iterates history chronologically, every 4 bars:
     - Accept bar i if d(i) >= lastDistance (ensures chronological variety)
     - When k neighbors collected, reset lastDistance = distances[k*3/4]
       (75th-percentile reset allows slightly closer future neighbors)
     - This gives k neighbors distributed across time, not clustered in one era

4. TRAINING LABELS — at bar i, the label is the 4-bar forward direction:
     label[i] = +1 if close[i+4] > close[i]
     label[i] = -1 if close[i+4] < close[i]
     label[i] =  0 if equal

5. PREDICTION = sum of k neighbor labels (range: -k to +k)
     > 0 → bullish (more neighbors went up)
     < 0 → bearish

6. FILTERS (same defaults as Pine):
     Volatility: ATR(1) > ATR(10)  — expanding volatility, worth trading
     Regime:     10-bar slope >= -0.1  — not in a collapsing downtrend

7. BUY = prediction > 0 AND volatility filter AND regime filter
"""
import numpy as np
import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe

_N_NEIGHBORS     = 8       # k in KNN
_MAX_BARS_BACK   = 2000    # Pine default
_REGIME_THRESH   = -0.1    # Pine default regime filter threshold


# ── Feature helpers ────────────────────────────────────────────────────────────

def _wave_trend(hlc3: pd.Series, n1: int = 10, n2: int = 11) -> pd.Series:
    """Wave Trend oscillator (same as Pine's ml.n_wt)."""
    ema1 = hlc3.ewm(span=n1, adjust=False).mean()
    diff = hlc3 - ema1
    ema2 = diff.abs().ewm(span=n1, adjust=False).mean().clip(lower=1e-10)
    ci   = diff / (0.015 * ema2)
    return ci.ewm(span=n2, adjust=False).mean().fillna(0)


def _rsi_series(close: pd.Series, period: int) -> pd.Series:
    """Standard Wilder RSI (matches Pine's ta.rsi)."""
    delta = close.diff()
    gain  = delta.clip(lower=0).ewm(com=period - 1, adjust=False).mean()
    loss  = (-delta.clip(upper=0)).ewm(com=period - 1, adjust=False).mean().clip(lower=1e-10)
    return (100 - 100 / (1 + gain / loss)).fillna(50)


# ── Filter helpers ─────────────────────────────────────────────────────────────

def _volatility_filter(df: pd.DataFrame) -> bool:
    """Pine: ml.filter_volatility(1, 10) — ATR(1) > ATR(10)."""
    if len(df) < 12:
        return True
    h = df["high"].values
    l = df["low"].values
    c = df["close"].values
    tr = np.maximum.reduce([
        h[1:] - l[1:],
        np.abs(h[1:] - c[:-1]),
        np.abs(l[1:] - c[:-1]),
    ])
    return float(tr[-1]) > float(tr[-10:].mean())


def _regime_filter(close: pd.Series) -> bool:
    """
    Pine: ml.regime_filter(ohlc4, threshold=-0.1).
    Approximated as 10-bar normalized price slope >= threshold.
    Filters out significant downtrends; allows flat or rising markets.
    """
    if len(close) < 12:
        return True
    slope = (float(close.iloc[-1]) - float(close.iloc[-11])) / float(close.iloc[-11])
    return slope >= _REGIME_THRESH


# ── Core KNN with Lorentzian distance ─────────────────────────────────────────

def _run_knn(features: np.ndarray, labels: np.ndarray,
             n_neighbors: int, max_bars_back: int) -> tuple[int, list[int]]:
    """
    Approximate Nearest Neighbors search using Lorentzian distance.
    Mirrors the Pine for-loop exactly:
      - Iterate from oldest to newest (i=startIndex to sizeLoop)
      - Skip every 4th bar (i % 4 == 0 → skip, matching Pine's i % 4 != 0)
      - Accept bar if d >= lastDistance
      - When predictions exceed k: reset lastDistance to distances[k*3/4],
        then remove the oldest neighbor (array.shift)

    Returns (prediction, neighbor_labels_list)
    """
    n = len(features)
    current = features[-1]
    start   = max(0, n - max_bars_back)

    # Vectorized Lorentzian distances for all candidate bars at once
    # d_i = sum_k log(1 + |current[k] - history[i][k]|)
    candidate_idx = np.array([i for i in range(start, n - 5) if i % 4 != 0])
    if len(candidate_idx) == 0:
        return 0, []

    diffs     = np.abs(features[candidate_idx] - current)     # shape: (M, 5)
    all_dists = np.sum(np.log1p(diffs), axis=1)               # shape: (M,)

    last_distance:    float      = -1.0
    neighbor_dists:   list[float] = []
    neighbor_labels:  list[int]   = []

    for rel_i, abs_i in enumerate(candidate_idx):
        d = float(all_dists[rel_i])

        if d >= last_distance:
            last_distance = d
            neighbor_dists.append(d)
            neighbor_labels.append(int(labels[abs_i]))

            if len(neighbor_labels) > n_neighbors:
                # Pine: lastDistance = distances[round(k*3/4)]  (unsorted, by insertion order)
                cutoff_idx    = round(n_neighbors * 3 / 4)
                last_distance = neighbor_dists[cutoff_idx]
                neighbor_dists.pop(0)    # array.shift removes the OLDEST
                neighbor_labels.pop(0)

    return sum(neighbor_labels), neighbor_labels


# ── Strategy ───────────────────────────────────────────────────────────────────

class LorentzianClassificationStrategy(BaseStrategy):
    name = "Lorentzian Classification"
    description = (
        "KNN (k=8) with Lorentzian distance over 5 features: RSI(14), "
        "WaveTrend(10,11), CCI(20), ADX(14), RSI(9). Votes on 4-bar forward "
        "direction. Filters: volatility expansion + regime (non-downtrend)."
    )
    strategy_type = StrategyType.TECHNICAL
    timeframe     = Timeframe.DAILY
    min_holding_days = 3
    max_holding_days = 8   # Trained on 4-bar prediction horizon
    weight           = 0.20

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        required = ["close", "high", "low", "rsi_14", "cci_20", "adx_14"]
        if len(df) < 60 or not all(c in df.columns for c in required):
            return Signal(signal_type="NONE", conditions_failed=["Insufficient data"])

        close = df["close"]
        high  = df["high"]
        low   = df["low"]
        hlc3  = (high + low + close) / 3

        # ── Compute the 5 features for every bar ────────────────────────────────
        f1 = df["rsi_14"].values                     # RSI(14)
        f2 = _wave_trend(hlc3, 10, 11).values        # Wave Trend(10, 11)
        f3 = df["cci_20"].values                     # CCI(20)
        f4 = df["adx_14"].values                     # ADX(14)
        f5 = _rsi_series(close, 9).values            # RSI(9)

        features = np.column_stack([f1, f2, f3, f4, f5])

        # Replace any NaN in features with column means to avoid poisoning distances
        col_means = np.nanmean(features, axis=0)
        nan_mask  = np.isnan(features)
        features[nan_mask] = np.take(col_means, np.where(nan_mask)[1])

        # ── Training labels: 4-bar forward return ───────────────────────────────
        n      = len(df)
        labels = np.zeros(n, dtype=np.int8)
        c      = close.values
        for i in range(n - 4):
            if   c[i + 4] > c[i]: labels[i] =  1
            elif c[i + 4] < c[i]: labels[i] = -1

        # ── KNN prediction ───────────────────────────────────────────────────────
        prediction, neighbor_votes = _run_knn(features, labels, _N_NEIGHBORS, _MAX_BARS_BACK)

        # ── Filters ──────────────────────────────────────────────────────────────
        vol_ok    = _volatility_filter(df)
        regime_ok = _regime_filter(close)

        conditions_met    = []
        conditions_failed = []

        curr = features[-1]
        vote_str = f"KNN prediction={prediction:+d}/{_N_NEIGHBORS} neighbors"
        if prediction > 0:
            conditions_met.append(vote_str)
        else:
            conditions_failed.append(vote_str)

        if vol_ok:
            conditions_met.append("Volatility expanding (ATR1 > ATR10)")
        else:
            conditions_failed.append("Volatility contracting (ATR1 ≤ ATR10)")

        if regime_ok:
            conditions_met.append("Regime: trend/flat (slope ≥ -0.1)")
        else:
            conditions_failed.append("Regime: downtrend filtered out")

        if prediction > 0 and vol_ok and regime_ok:
            conviction = abs(prediction) / _N_NEIGHBORS   # 0.0 → 1.0
            confidence = round(min(0.55 + 0.35 * conviction, 0.92), 4)
            return Signal(
                signal_type="BUY",
                confidence=confidence,
                risk_score=0.35,
                expected_upside_pct=8.0,
                stop_loss_pct=5.0,
                target_pct=8.0,
                holding_days=6,
                conditions_met=conditions_met + [
                    f"Features — RSI14:{curr[0]:.1f} WT:{curr[1]:.1f} "
                    f"CCI:{curr[2]:.1f} ADX:{curr[3]:.1f} RSI9:{curr[4]:.1f}",
                    f"Votes: {neighbor_votes}",
                ],
            )

        return Signal(
            signal_type="NONE",
            conditions_met=conditions_met,
            conditions_failed=conditions_failed,
        )

    def get_required_indicators(self) -> list[str]:
        return ["close", "high", "low", "rsi_14", "cci_20", "adx_14"]
