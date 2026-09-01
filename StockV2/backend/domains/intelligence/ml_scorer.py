import json
import logging
import os
import pickle
from datetime import datetime
from typing import Optional

import numpy as np
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

MIN_TRAINING_SAMPLES = 50
MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "ml_models", "signal_scorer.pkl")
METRICS_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "ml_models", "signal_scorer_metrics.json")

_REGIME_MAP = {
    "STRONG_BULL": 5,
    "BULL": 4,
    "SIDEWAYS": 3,
    "BEAR": 2,
    "STRONG_BEAR": 1,
    "HIGH_VOLATILITY": 0,
}

# Module-level cache — load attempted at most once per process.
_LOAD_FAILED = object()
_cached_model: object = None


def regime_to_code(regime: str) -> int:
    return _REGIME_MAP.get(regime, 3)


class MLSignalScorer:
    """
    ML-based signal profitability predictor.
    Calibrated RandomForest trained on signal_outcomes.
    Features: confidence_score, regime_code, strategy_id, month, day_of_week,
              strategy_win_rate, log_total_trades, strategy_recent_win_rate.
    """

    def train(self, db: Session) -> dict:
        """Train on signal_outcomes, calibrate, save model + metrics. Returns metrics dict."""
        X, y = self._extract_features(db)
        if len(X) < MIN_TRAINING_SAMPLES:
            logger.warning("[ml_scorer] insufficient training samples: %d < %d", len(X), MIN_TRAINING_SAMPLES)
            return {"samples": 0}
        if len(np.unique(y)) < 2:
            logger.warning("[ml_scorer] training data has only one class — skipping")
            return {"samples": 0}

        from sklearn.calibration import CalibratedClassifierCV
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.metrics import roc_auc_score
        from sklearn.model_selection import train_test_split

        X_train, X_cal, y_train, y_cal = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=y
        )

        base = RandomForestClassifier(
            n_estimators=300,
            max_depth=8,
            min_samples_leaf=5,
            class_weight="balanced",
            random_state=42,
            n_jobs=-1,
        )
        base.fit(X_train, y_train)

        # Evaluation on calibration split (before calibration fitting)
        classes = list(base.classes_)
        if 1 in classes:
            col = classes.index(1)
            cal_probs = base.predict_proba(X_cal)[:, col]
        else:
            cal_probs = np.zeros(len(X_cal))

        auc_roc = float(roc_auc_score(y_cal, cal_probs)) if len(np.unique(y_cal)) > 1 else 0.5
        high_conf_mask = cal_probs >= 0.6
        precision_at_60 = float(y_cal[high_conf_mask].mean()) if high_conf_mask.sum() > 0 else None

        # Calibrate
        model = CalibratedClassifierCV(base, cv="prefit", method="sigmoid")
        model.fit(X_cal, y_cal)

        os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
        with open(MODEL_PATH, "wb") as f:
            pickle.dump(model, f)

        metrics = {
            "auc_roc": round(auc_roc, 4),
            "precision_at_60": round(precision_at_60, 4) if precision_at_60 is not None else None,
            "high_conf_signals": int(high_conf_mask.sum()),
            "class_balance": round(float(y.mean()), 4),
            "samples": len(X),
            "trained_at": datetime.now().isoformat(),
        }
        with open(METRICS_PATH, "w") as f:
            json.dump(metrics, f)

        global _cached_model
        _cached_model = model
        logger.info("[ml_scorer] trained on %d samples, auc_roc=%.3f", len(X), auc_roc)
        return metrics

    def predict(self, features: dict, db=None) -> Optional[float]:
        """Return calibrated win-probability in [0,1], or None if model not available.

        Required keys: confidence_score, regime_code, strategy_id, month, day_of_week
        Optional keys (auto-computed from db if absent):
            strategy_win_rate, log_total_trades, strategy_recent_win_rate
        """
        model = self._load_model()
        if model is None:
            return None

        strategy_win_rate = features.get("strategy_win_rate")
        log_total_trades = features.get("log_total_trades")
        strategy_recent_win_rate = features.get("strategy_recent_win_rate")

        if db is not None and strategy_win_rate is None:
            stats = self._get_strategy_stats(db, int(features["strategy_id"]))
            strategy_win_rate = stats["win_rate"]
            log_total_trades = stats["log_total_trades"]
            strategy_recent_win_rate = stats["recent_win_rate"]

        if strategy_win_rate is None:
            strategy_win_rate = 0.5
        if log_total_trades is None:
            log_total_trades = 2.0
        if strategy_recent_win_rate is None:
            strategy_recent_win_rate = strategy_win_rate

        X_row = np.array([[
            features["confidence_score"],
            features["regime_code"],
            features["strategy_id"],
            features["month"],
            features["day_of_week"],
            strategy_win_rate,
            log_total_trades,
            strategy_recent_win_rate,
        ]])

        probs = model.predict_proba(X_row)[0]
        classes = list(model.classes_)
        if 1 not in classes:
            return 0.0
        col = classes.index(1)
        return round(float(probs[col]), 4)

    def _get_strategy_stats(self, db, strategy_id: int) -> dict:
        """Query win rate, trade count, and recent win rate for a strategy."""
        row = db.execute(text("""
            SELECT COUNT(*), AVG(so.is_profitable::int::float)
            FROM signal_outcomes so
            JOIN strategy_signals ss ON ss.id = so.signal_id
            WHERE ss.strategy_id = :sid AND so.is_profitable IS NOT NULL
        """), {"sid": strategy_id}).fetchone()
        total = int(row[0]) if row and row[0] else 0
        win_rate = float(row[1]) if row and row[1] is not None else 0.5

        recent = db.execute(text("""
            SELECT so.is_profitable
            FROM signal_outcomes so
            JOIN strategy_signals ss ON ss.id = so.signal_id
            WHERE ss.strategy_id = :sid AND so.is_profitable IS NOT NULL
            ORDER BY so.signal_date DESC LIMIT 20
        """), {"sid": strategy_id}).fetchall()
        recent_win_rate = (
            float(sum(bool(r[0]) for r in recent)) / len(recent)
            if recent else win_rate
        )
        return {
            "win_rate": win_rate,
            "log_total_trades": float(np.log1p(total)),
            "recent_win_rate": recent_win_rate,
        }

    def _load_model(self):
        """Load persisted model or return None. Loads at most once per process."""
        global _cached_model
        if _cached_model is _LOAD_FAILED:
            return None
        if _cached_model is not None:
            return _cached_model
        if not os.path.exists(MODEL_PATH):
            _cached_model = _LOAD_FAILED
            return None
        try:
            with open(MODEL_PATH, "rb") as f:
                _cached_model = pickle.load(f)
            return _cached_model
        except Exception as e:
            logger.warning("[ml_scorer] failed to load model: %s", e)
            _cached_model = _LOAD_FAILED
            return None

    def _extract_features(self, db: Session):
        """Window-function query: 8 features per signal_outcome row."""
        rows = db.execute(text("""
            SELECT
                ss.confidence_score,
                mr.regime,
                ss.strategy_id,
                so.signal_date,
                so.is_profitable,
                AVG((so.is_profitable)::int::float) OVER (
                    PARTITION BY ss.strategy_id
                ) AS strategy_win_rate,
                COUNT(*) OVER (
                    PARTITION BY ss.strategy_id
                ) AS strategy_total_trades,
                COALESCE(
                    AVG((so.is_profitable)::int::float) OVER (
                        PARTITION BY ss.strategy_id
                        ORDER BY so.signal_date
                        ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING
                    ),
                    AVG((so.is_profitable)::int::float) OVER (PARTITION BY ss.strategy_id)
                ) AS strategy_recent_win_rate
            FROM signal_outcomes so
            JOIN strategy_signals ss ON ss.id = so.signal_id
            LEFT JOIN market_regime mr ON mr.date = so.signal_date
            WHERE so.is_profitable IS NOT NULL
        """)).fetchall()

        if not rows:
            return np.array([]).reshape(0, 8), np.array([])

        X_list, y_list = [], []
        for r in rows:
            conf_score = float(r[0]) if r[0] is not None else 0.5
            regime_code = _REGIME_MAP.get(r[1], 3)
            strat_id = int(r[2])
            sig_date = r[3]
            is_prof = bool(r[4])
            strategy_win_rate = float(r[5]) if r[5] is not None else 0.5
            log_total_trades = float(np.log1p(int(r[6]))) if r[6] is not None else 2.0
            recent_win_rate = float(r[7]) if r[7] is not None else strategy_win_rate

            if isinstance(sig_date, str):
                from datetime import datetime as dt
                sig_date = dt.strptime(sig_date[:10], "%Y-%m-%d").date()

            X_list.append([
                conf_score, regime_code, strat_id,
                sig_date.month, sig_date.weekday(),
                strategy_win_rate, log_total_trades, recent_win_rate,
            ])
            y_list.append(1 if is_prof else 0)

        return np.array(X_list), np.array(y_list)
