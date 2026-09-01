import logging
import os
import pickle
from typing import Optional

import numpy as np
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

MIN_TRAINING_SAMPLES = 50
MODEL_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "ml_models", "special_signal_scorer.pkl"
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
    def train(self, db: Session) -> int:
        X, y = self._extract_features(db)
        if len(X) < MIN_TRAINING_SAMPLES:
            logger.warning(
                "[special_ml_scorer] insufficient training samples: %d < %d", len(X), MIN_TRAINING_SAMPLES
            )
            return 0
        if len(np.unique(y)) < 2:
            logger.warning("[special_ml_scorer] training data has only one class — skipping")
            return 0

        from sklearn.ensemble import GradientBoostingClassifier
        model = GradientBoostingClassifier(
            n_estimators=100, max_depth=3, learning_rate=0.1, random_state=42
        )
        model.fit(X, y)

        os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
        with open(MODEL_PATH, "wb") as f:
            pickle.dump(model, f)

        global _cached_model
        _cached_model = model
        logger.info("[special_ml_scorer] trained on %d samples", len(X))
        return len(X)

    def predict(self, features: dict) -> Optional[float]:
        """Return win-probability in [0,1], or None if model not available.

        Expected keys: strategy_id, entry_month, entry_dow, regime_code
        """
        model = self._load_model()
        if model is None:
            return None
        X_row = np.array([[
            features["strategy_id"],
            features["entry_month"],
            features["entry_dow"],
            features["regime_code"],
        ]])
        classes = list(model.classes_)
        if 1 not in classes:
            return 0.0
        col = classes.index(1)
        return round(float(model.predict_proba(X_row)[0][col]), 4)

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
        rows = db.execute(text("""
            SELECT
                sbr.special_strategy_id,
                sbt.entry_date,
                mr.regime,
                sbt.pnl
            FROM special_backtest_trades sbt
            JOIN special_backtest_results sbr ON sbr.id = sbt.backtest_result_id
            LEFT JOIN market_regime mr ON mr.date = sbt.entry_date
            WHERE sbt.entry_date IS NOT NULL AND sbt.pnl IS NOT NULL
        """)).fetchall()

        if not rows:
            return np.array([]).reshape(0, 4), np.array([])

        X_list, y_list = [], []
        for r in rows:
            strategy_id = int(r[0])
            entry_date = r[1]
            regime = r[2]
            pnl = float(r[3])

            if isinstance(entry_date, str):
                from datetime import datetime
                entry_date = datetime.strptime(entry_date[:10], "%Y-%m-%d").date()

            regime_code = _REGIME_MAP.get(regime, 3)
            X_list.append([strategy_id, entry_date.month, entry_date.weekday(), regime_code])
            y_list.append(1 if pnl > 0 else 0)

        return np.array(X_list), np.array(y_list)
