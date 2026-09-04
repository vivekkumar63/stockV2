"""BreakoutMLScorer — LightGBM trained on historical breakout trade outcomes.

Features extracted from each breakout entry (7 numeric features):
  volume_ratio, rsi, body_ratio, range_atr_ratio,
  conviction_score, breakout_pct, ema50_slope_pct

Label: pnl_pct > 0  (trade was profitable = "true" breakout)

Falls back to a calibrated rule-based score when fewer than MIN_SAMPLES
labeled trades are available (before enough backtest data is collected).
"""
from __future__ import annotations
import logging
import math
import pickle
from pathlib import Path

import numpy as np
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)
MODEL_PATH = Path(__file__).parent / "breakout_ml_model.pkl"
MIN_SAMPLES = 30


def _safe(v, default: float = 0.0) -> float:
    try:
        x = float(v)
        return x if math.isfinite(x) else default
    except (TypeError, ValueError):
        return default


def _features(sig: dict) -> list[float]:
    """Extract normalized feature vector from a breakout signal dict."""
    return [
        min(_safe(sig.get("volume_ratio"), 1.0), 5.0),          # 0: volume
        _safe(sig.get("rsi"), 50.0),                              # 1: RSI
        _safe(sig.get("body_ratio"), 0.5),                        # 2: candle body
        min(_safe(sig.get("range_atr_ratio"), 1.0), 4.0),        # 3: range/ATR
        float(_safe(sig.get("conviction_score"), 4)),             # 4: 4-6 signals
        _safe(sig.get("breakout_pct"), 1.0),                      # 5: % above resistance
        _safe(sig.get("ema50_slope_pct"), 0.0),                   # 6: EMA50 momentum
    ]


class BreakoutMLScorer:
    _model = None
    _loaded: bool = False

    @classmethod
    def _load(cls):
        if cls._loaded:
            return cls._model
        cls._loaded = True
        if MODEL_PATH.exists():
            try:
                with open(MODEL_PATH, "rb") as f:
                    cls._model = pickle.load(f)
                logger.info("[BreakoutMLScorer] model loaded from %s", MODEL_PATH)
            except Exception as e:
                logger.warning("[BreakoutMLScorer] load failed: %s", e)
        return cls._model

    @classmethod
    def _save(cls, model) -> None:
        try:
            with open(MODEL_PATH, "wb") as f:
                pickle.dump(model, f)
            cls._model = model
            cls._loaded = True
            logger.info("[BreakoutMLScorer] model saved to %s", MODEL_PATH)
        except Exception as e:
            logger.warning("[BreakoutMLScorer] save failed: %s", e)

    @classmethod
    def model_exists(cls) -> bool:
        return MODEL_PATH.exists()

    @classmethod
    def train(cls, db: Session) -> dict:
        """Train on stored breakout_backtest_trades. Returns status dict."""
        try:
            import lightgbm as lgb
            from sklearn.model_selection import cross_val_score
            from sklearn.pipeline import Pipeline
            from sklearn.preprocessing import StandardScaler
        except ImportError:
            from sklearn.ensemble import GradientBoostingClassifier
            lgb = None

        rows = db.execute(text("""
            SELECT volume_ratio, rsi, body_ratio, range_atr_ratio,
                   conviction_score, breakout_pct, ema50_slope_pct,
                   CASE WHEN pnl_pct > 0 THEN 1 ELSE 0 END AS label
            FROM breakout_backtest_trades
            WHERE pnl_pct IS NOT NULL
        """)).fetchall()

        n = len(rows) if rows else 0
        if n < MIN_SAMPLES:
            return {
                "trained": False, "samples": n,
                "reason": (
                    f"Need ≥{MIN_SAMPLES} labeled trades; have {n}. "
                    "Run breakout backtest on a few symbols first."
                ),
            }

        X = np.array([_features({
            "volume_ratio": r[0], "rsi": r[1], "body_ratio": r[2],
            "range_atr_ratio": r[3], "conviction_score": r[4],
            "breakout_pct": r[5], "ema50_slope_pct": r[6],
        }) for r in rows])
        y = np.array([int(r[7]) for r in rows])

        from sklearn.model_selection import cross_val_score
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import StandardScaler

        if lgb is not None:
            clf = Pipeline([
                ("scaler", StandardScaler()),
                ("clf", lgb.LGBMClassifier(
                    n_estimators=200, max_depth=4, learning_rate=0.05,
                    min_child_samples=max(5, n // 20), random_state=42,
                    verbose=-1,
                )),
            ])
        else:
            from sklearn.ensemble import GradientBoostingClassifier
            clf = Pipeline([
                ("scaler", StandardScaler()),
                ("clf", GradientBoostingClassifier(
                    n_estimators=150, max_depth=3, learning_rate=0.05, random_state=42
                )),
            ])

        n_folds = min(5, max(2, n // 10))
        cv = cross_val_score(clf, X, y, cv=n_folds)
        clf.fit(X, y)
        cls._save(clf)

        pos_rate = round(float(y.mean()), 3)
        feature_names = ["vol_ratio", "rsi", "body_ratio", "rng_atr",
                         "conviction", "breakout_pct", "ema50_slope"]
        importances: dict = {}
        try:
            raw_clf = clf.named_steps["clf"]
            if hasattr(raw_clf, "feature_importances_"):
                importances = dict(zip(feature_names, [round(float(v), 4) for v in raw_clf.feature_importances_]))
        except Exception:
            pass

        return {
            "trained": True,
            "samples": n,
            "cv_accuracy": round(float(cv.mean()), 3),
            "positive_rate": pos_rate,
            "feature_importances": importances,
        }

    @classmethod
    def predict(cls, signal: dict) -> float:
        """Return P(true breakout) in [0, 1]. Falls back to rule-based if no model."""
        model = cls._load()
        if model is not None:
            try:
                p = float(model.predict_proba(np.array([_features(signal)]))[0][1])
                return round(p, 3)
            except Exception as e:
                logger.debug("[BreakoutMLScorer] predict error: %s", e)
        return cls._rule_based(signal)

    @classmethod
    def _rule_based(cls, signal: dict) -> float:
        """Calibrated rule-based fallback for true-breakout probability."""
        score = 0.35  # base: random ~50%, discounted for fakeout prevalence

        conviction = int(_safe(signal.get("conviction_score"), 4))
        if conviction == 6:   score += 0.20
        elif conviction == 5: score += 0.12
        elif conviction == 4: score += 0.04

        vr = _safe(signal.get("volume_ratio"), 1.0)
        if vr >= 3.0:   score += 0.18
        elif vr >= 2.0: score += 0.12
        elif vr >= 1.5: score += 0.05

        rsi = _safe(signal.get("rsi"), 50.0)
        if 56 <= rsi <= 68:  score += 0.10   # momentum building, not overbought
        elif rsi > 70:        score -= 0.05   # overbought = fakeout risk

        bp = _safe(signal.get("breakout_pct"), 1.5)
        if bp < 0.8:    score += 0.08   # very fresh breakout
        elif bp < 2.0:  score += 0.03
        elif bp > 4.5:  score -= 0.12   # stale, likely to pull back

        slope = _safe(signal.get("ema50_slope_pct"), 0.0)
        if slope > 1.5:   score += 0.10   # strongly trending
        elif slope > 0.3: score += 0.05
        elif slope < -1:  score -= 0.08   # EMA going down = breakout suspect

        body = _safe(signal.get("body_ratio"), 0.5)
        if body > 0.70:   score += 0.07
        elif body > 0.50: score += 0.03

        rng_atr = _safe(signal.get("range_atr_ratio"), 1.0)
        if rng_atr > 1.5:  score += 0.05
        elif rng_atr < 0.5: score -= 0.05  # tiny candle = weak breakout

        return round(min(0.92, max(0.08, score)), 3)
