import logging
import os
import pickle
from typing import Optional

import numpy as np
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

MIN_TRAINING_SAMPLES = 50
MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "ml_models", "signal_scorer.pkl")

_REGIME_MAP = {
    "STRONG_BULL": 5,
    "BULL": 4,
    "SIDEWAYS": 3,
    "BEAR": 2,
    "STRONG_BEAR": 1,
    "HIGH_VOLATILITY": 0,
}


class MLSignalScorer:
    """
    ML-based signal profitability predictor.
    Trains GBC on Phase C signal_outcomes. Predicts probability for new signals.
    Features: confidence_score, regime_code, strategy_id, month, day_of_week.
    """

    def train(self, db: Session) -> int:
        """Train on signal_outcomes data and persist model. Returns n_samples."""
        X, y = self._extract_features(db)
        if len(X) < MIN_TRAINING_SAMPLES:
            logger.warning("[ml_scorer] insufficient training samples: %d < %d", len(X), MIN_TRAINING_SAMPLES)
            return 0

        if len(np.unique(y)) < 2:
            logger.warning("[ml_scorer] training data has only one class — skipping")
            return 0

        from sklearn.ensemble import GradientBoostingClassifier
        model = GradientBoostingClassifier(
            n_estimators=100,
            max_depth=3,
            learning_rate=0.1,
            random_state=42,
        )
        model.fit(X, y)

        os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
        with open(MODEL_PATH, "wb") as f:
            pickle.dump(model, f)

        logger.info("[ml_scorer] trained on %d samples", len(X))
        return len(X)

    def predict(self, features: dict) -> Optional[float]:
        """
        Predict probability in [0,1] that a signal will be profitable.
        Returns None if model not available.

        Expected keys: confidence_score, regime_code, strategy_id, month, day_of_week
        """
        model = self._load_model()
        if model is None:
            return None

        X_row = np.array([[
            features["confidence_score"],
            features["regime_code"],
            features["strategy_id"],
            features["month"],
            features["day_of_week"],
        ]])
        classes = list(model.classes_)
        if 1 not in classes:
            return 1.0  # model only saw profitable signals
        col = classes.index(1)
        prob = model.predict_proba(X_row)[0][col]
        return round(float(prob), 4)

    def _load_model(self):
        """Load persisted model or return None if not found."""
        if not os.path.exists(MODEL_PATH):
            return None
        try:
            with open(MODEL_PATH, "rb") as f:
                return pickle.load(f)
        except Exception as e:
            logger.warning("[ml_scorer] failed to load model: %s", e)
            return None

    def _extract_features(self, db: Session) -> tuple[np.ndarray, np.ndarray]:
        """JOIN signal_outcomes + strategy_signals + market_regime → (X, y)."""
        rows = db.execute(text("""
            SELECT
                ss.confidence_score,
                mr.regime,
                ss.strategy_id,
                so.signal_date,
                so.is_profitable
            FROM signal_outcomes so
            JOIN strategy_signals ss ON ss.id = so.signal_id
            LEFT JOIN market_regime mr ON mr.date = so.signal_date
            WHERE so.is_profitable IS NOT NULL
        """)).fetchall()

        if not rows:
            return np.array([]).reshape(0, 5), np.array([])

        X_list = []
        y_list = []
        for r in rows:
            conf_score = float(r[0]) if r[0] is not None else 0.5
            regime_code = _REGIME_MAP.get(r[1], 3)
            strat_id = int(r[2])
            sig_date = r[3]
            is_prof = bool(r[4])

            if isinstance(sig_date, str):
                from datetime import datetime
                sig_date = datetime.strptime(sig_date[:10], "%Y-%m-%d").date()

            X_list.append([conf_score, regime_code, strat_id, sig_date.month, sig_date.weekday()])
            y_list.append(1 if is_prof else 0)

        return np.array(X_list), np.array(y_list)
