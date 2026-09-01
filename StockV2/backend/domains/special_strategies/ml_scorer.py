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
MODEL_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "ml_models", "special_signal_scorer.pkl"
)
METRICS_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "ml_models", "special_signal_scorer_metrics.json"
)

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


def special_regime_to_code(regime: str) -> int:
    return _REGIME_MAP.get(regime, 3)


class SpecialMLScorer:
    """
    Calibrated RandomForest trained on special_backtest_trades.
    Features: strategy_id, entry_month, entry_dow, regime_code,
              strategy_avg_win_rate, strategy_profit_factor, strategy_avg_pnl_pct.
    """

    def train(self, db: Session) -> dict:
        """Train on special_backtest_trades, calibrate, save model + metrics. Returns metrics dict."""
        X, y = self._extract_features(db)
        if len(X) < MIN_TRAINING_SAMPLES:
            logger.warning(
                "[special_ml_scorer] insufficient training samples: %d < %d", len(X), MIN_TRAINING_SAMPLES
            )
            return {"samples": 0}
        if len(np.unique(y)) < 2:
            logger.warning("[special_ml_scorer] training data has only one class — skipping")
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

        classes = list(base.classes_)
        if 1 in classes:
            col = classes.index(1)
            cal_probs = base.predict_proba(X_cal)[:, col]
        else:
            cal_probs = np.zeros(len(X_cal))

        auc_roc = float(roc_auc_score(y_cal, cal_probs)) if len(np.unique(y_cal)) > 1 else 0.5
        high_conf_mask = cal_probs >= 0.6
        precision_at_60 = float(y_cal[high_conf_mask].mean()) if high_conf_mask.sum() > 0 else None

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
        logger.info("[special_ml_scorer] trained on %d samples, auc_roc=%.3f", len(X), auc_roc)
        return metrics

    def predict(self, features: dict) -> Optional[float]:
        """Return calibrated win-probability in [0,1], or None if model not available.

        Expected keys: strategy_id, entry_month, entry_dow, regime_code,
                       strategy_avg_win_rate, strategy_profit_factor, strategy_avg_pnl_pct
        """
        model = self._load_model()
        if model is None:
            return None
        X_row = np.array([[
            features["strategy_id"],
            features["entry_month"],
            features["entry_dow"],
            features["regime_code"],
            features.get("strategy_avg_win_rate", 0.5),
            features.get("strategy_profit_factor", 1.0),
            features.get("strategy_avg_pnl_pct", 0.0),
        ]])
        probs = model.predict_proba(X_row)[0]
        classes = list(model.classes_)
        if 1 not in classes:
            return 0.0
        col = classes.index(1)
        return round(float(probs[col]), 4)

    def _load_model(self):
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
            logger.warning("[special_ml_scorer] failed to load model: %s", e)
            _cached_model = _LOAD_FAILED
            return None

    def _extract_features(self, db: Session):
        """CTE query: 7 features per special_strategy_trades row.

        Label: pnl_pct >= 10 (trade closed at ≥10% profit = success).
        Source: special_strategy_trades populated by precompute (not manual backtests).
        """
        rows = db.execute(text("""
            WITH strategy_stats AS (
                SELECT special_strategy_id,
                       AVG(win_rate)      AS avg_win_rate,
                       AVG(profit_factor) AS avg_profit_factor,
                       AVG(avg_pnl_pct)   AS avg_pnl_pct_stat
                FROM special_strategy_performance
                WHERE win_rate IS NOT NULL
                GROUP BY special_strategy_id
            )
            SELECT
                sst.special_strategy_id,
                sst.entry_date,
                mr.regime,
                sst.pnl_pct,
                COALESCE(ss.avg_win_rate, 0.5)      AS strategy_avg_win_rate,
                COALESCE(ss.avg_profit_factor, 1.0) AS strategy_profit_factor,
                COALESCE(ss.avg_pnl_pct_stat, 0.0)  AS strategy_avg_pnl_pct
            FROM special_strategy_trades sst
            LEFT JOIN market_regime mr ON mr.date = sst.entry_date
            LEFT JOIN strategy_stats ss ON ss.special_strategy_id = sst.special_strategy_id
            WHERE sst.entry_date IS NOT NULL AND sst.pnl_pct IS NOT NULL
        """)).fetchall()

        if not rows:
            return np.array([]).reshape(0, 7), np.array([])

        X_list, y_list = [], []
        for r in rows:
            strategy_id   = int(r[0])
            entry_date    = r[1]
            regime        = r[2]
            pnl_pct       = float(r[3])
            avg_win_rate  = float(r[4]) if r[4] is not None else 0.5
            profit_factor = float(r[5]) if r[5] is not None else 1.0
            avg_pnl_pct   = float(r[6]) if r[6] is not None else 0.0

            if isinstance(entry_date, str):
                from datetime import datetime as dt
                entry_date = dt.strptime(entry_date[:10], "%Y-%m-%d").date()

            regime_code = _REGIME_MAP.get(regime, 3)
            X_list.append([
                strategy_id, entry_date.month, entry_date.weekday(),
                regime_code, avg_win_rate, profit_factor, avg_pnl_pct,
            ])
            y_list.append(1 if pnl_pct >= 10.0 else 0)

        return np.array(X_list), np.array(y_list)
