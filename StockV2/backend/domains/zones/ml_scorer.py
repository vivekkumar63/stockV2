"""MLZoneScorer — GBM trained on zone backtest outcomes to predict setup quality.

Features extracted from zone_analysis_results (10 numeric features).
Labels come from zone_backtest_results: total_pnl_pct > 0 → 1 (profitable).

Falls back to a calibrated rule-based formula when fewer than MIN_SAMPLES
labeled backtest results are available.
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
MODEL_PATH = Path(__file__).parent / "zone_ml_model.pkl"
MIN_SAMPLES = 30

_POS_CODE = {
    "in_demand": 5, "near_demand": 4, "breakout": 3,
    "neutral": 2, "near_supply": 1, "in_supply": 0,
}


def _safe(v, default: float = 0.0) -> float:
    try:
        x = float(v)
        return x if math.isfinite(x) else default
    except (TypeError, ValueError):
        return default


def _features(row: dict) -> list[float]:
    return [
        _safe(row.get("long_setup_score")),
        _safe(row.get("short_setup_score")),
        _safe(row.get("best_demand_score")),
        _safe(row.get("best_supply_score")),
        _safe(row.get("best_long_rr")),
        _safe(row.get("best_short_rr")),
        _safe(row.get("rvol_at_compute"), 1.0),
        float(_POS_CODE.get(str(row.get("position_tag") or "neutral"), 2)),
        _safe(row.get("pct_from_52w_low")),
        -_safe(row.get("pct_from_52w_high")),  # negate: closer to 52W high = positive
    ]


def _build_reason(row: dict, ml_conf: float, rj: dict) -> str:
    parts: list[str] = []
    ls     = _safe(row.get("long_setup_score"))
    rr     = _safe(row.get("best_long_rr"))
    rvol   = _safe(row.get("rvol_at_compute"), 1.0)
    pos    = str(row.get("position_tag") or "neutral")
    ms     = rj.get("market_structure", "sideways")
    candle = rj.get("candle_signal", "NONE")

    if ml_conf >= 0.70:
        parts.append(f"High ML confidence ({ml_conf:.0%})")
    elif ml_conf >= 0.55:
        parts.append(f"Moderate ML confidence ({ml_conf:.0%})")

    pos_text = {
        "in_demand": "Price inside demand zone",
        "near_demand": "Near demand zone",
        "breakout": "Breaking above supply",
        "near_supply": "Approaching supply",
    }
    if pos in pos_text:
        parts.append(pos_text[pos])

    if ls >= 75:
        parts.append(f"Strong long setup ({int(ls)}/100)")
    elif ls >= 50:
        parts.append(f"Good long setup ({int(ls)}/100)")

    if rr >= 3:
        parts.append(f"Excellent R:R (1:{rr:.1f})")
    elif rr >= 2:
        parts.append(f"Good R:R (1:{rr:.1f})")

    if rvol >= 2.0:
        parts.append(f"Strong volume ({rvol:.1f}×)")
    elif rvol >= 1.5:
        parts.append(f"Elevated volume ({rvol:.1f}×)")

    if ms == "bullish":
        parts.append("Bullish trend")
    elif ms == "bearish":
        parts.append("Caution: bearish trend")

    candle_text = {
        "hammer": "Hammer reversal",
        "bullish_engulfing": "Bullish engulfing",
        "shooting_star": "Shooting star",
        "bearish_engulfing": "Bearish engulfing",
        "doji": "Doji indecision",
    }
    if candle and candle != "NONE" and candle in candle_text:
        parts.append(candle_text[candle])

    return " · ".join(parts) if parts else "Zone alignment"


class MLZoneScorer:
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
                logger.info("[MLZoneScorer] model loaded from %s", MODEL_PATH)
            except Exception as e:
                logger.warning("[MLZoneScorer] load failed: %s", e)
        return cls._model

    @classmethod
    def _save(cls, model) -> None:
        try:
            with open(MODEL_PATH, "wb") as f:
                pickle.dump(model, f)
            cls._model = model
            cls._loaded = True
            logger.info("[MLZoneScorer] model saved to %s", MODEL_PATH)
        except Exception as e:
            logger.warning("[MLZoneScorer] save failed: %s", e)

    @classmethod
    def model_exists(cls) -> bool:
        return MODEL_PATH.exists()

    @classmethod
    def train(cls, db: Session) -> dict:
        """Train GBM on backtest outcomes. Returns status dict."""
        from sklearn.ensemble import GradientBoostingClassifier
        from sklearn.model_selection import cross_val_score
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import StandardScaler

        rows = db.execute(text("""
            SELECT DISTINCT ON (br.id)
                z.long_setup_score, z.short_setup_score, z.best_demand_score,
                z.best_supply_score, z.best_long_rr, z.best_short_rr,
                z.rvol_at_compute, z.position_tag, z.pct_from_52w_low, z.pct_from_52w_high,
                CASE WHEN br.total_pnl_pct > 0 THEN 1 ELSE 0 END AS label
            FROM zone_backtest_results br
            JOIN zone_analysis_results z ON z.symbol = br.symbol
                AND z.computed_date <= br.from_date
            WHERE br.total_trades >= 3
            ORDER BY br.id, z.computed_date DESC
        """)).fetchall()

        n = len(rows) if rows else 0
        if n < MIN_SAMPLES:
            return {
                "trained": False, "samples": n,
                "reason": (
                    f"Need ≥{MIN_SAMPLES} labeled backtests; have {n}. "
                    "Run 'All Stocks' backtest first."
                ),
            }

        X = np.array([_features({
            "long_setup_score": r[0], "short_setup_score": r[1],
            "best_demand_score": r[2], "best_supply_score": r[3],
            "best_long_rr": r[4], "best_short_rr": r[5],
            "rvol_at_compute": r[6], "position_tag": r[7],
            "pct_from_52w_low": r[8], "pct_from_52w_high": r[9],
        }) for r in rows])
        y = np.array([int(r[10]) for r in rows])

        clf = Pipeline([
            ("scaler", StandardScaler()),
            ("clf", GradientBoostingClassifier(n_estimators=100, max_depth=3, random_state=42)),
        ])
        n_folds = min(5, max(2, n // 10))
        cv = cross_val_score(clf, X, y, cv=n_folds)
        clf.fit(X, y)
        cls._save(clf)

        pos_rate = round(float(y.mean()), 3)
        return {
            "trained": True,
            "samples": n,
            "cv_accuracy": round(float(cv.mean()), 3),
            "positive_rate": pos_rate,
        }

    @classmethod
    def predict(cls, row: dict) -> float:
        """Return P(profitable) in [0, 1]. Falls back to rule-based if no model."""
        model = cls._load()
        if model is not None:
            try:
                p = float(model.predict_proba(np.array([_features(row)]))[0][1])
                return round(p, 3)
            except Exception as e:
                logger.debug("[MLZoneScorer] predict error: %s", e)
        return cls._rule_based(row)

    @classmethod
    def _rule_based(cls, row: dict) -> float:
        score = 0.0
        ls   = _safe(row.get("long_setup_score"))
        rr   = _safe(row.get("best_long_rr"))
        rvol = _safe(row.get("rvol_at_compute"), 1.0)
        pos  = str(row.get("position_tag") or "neutral")
        p52l = _safe(row.get("pct_from_52w_low"))

        if ls >= 75:    score += 0.30
        elif ls >= 50:  score += 0.15

        if rr >= 3:     score += 0.25
        elif rr >= 2:   score += 0.15
        elif rr >= 1.5: score += 0.08

        if rvol >= 2.0:   score += 0.15
        elif rvol >= 1.5: score += 0.08

        score += {
            "in_demand": 0.20, "near_demand": 0.12, "breakout": 0.10,
            "neutral": 0.05, "near_supply": 0.0, "in_supply": 0.0,
        }.get(pos, 0.05)

        if 0 < p52l <= 5:    score += 0.10
        elif 5 < p52l <= 15: score += 0.05

        return round(min(0.95, max(0.05, score)), 3)
