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
_MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "ml_models")

_REGIME_MAP = {
    "STRONG_BULL": 5,
    "BULL": 4,
    "SIDEWAYS": 3,
    "BEAR": 2,
    "STRONG_BEAR": 1,
    "HIGH_VOLATILITY": 0,
}

_LOAD_FAILED = object()
_model_cache: dict = {}  # {strategy_id: model | _LOAD_FAILED}


def _model_path(strategy_id: int) -> str:
    return os.path.join(_MODEL_DIR, f"strategy_scorer_{strategy_id}.pkl")


def _metrics_path(strategy_id: int) -> str:
    return os.path.join(_MODEL_DIR, f"strategy_scorer_{strategy_id}_metrics.json")


def regime_to_code(regime: str) -> int:
    return _REGIME_MAP.get(regime, 3)


class MLSignalScorer:
    """
    LightGBM classifier trained per-strategy on signal_outcomes with isotonic calibration.
    Features: confidence_score, regime_code, strategy_id, month, day_of_week,
              strategy_win_rate, log_total_trades, strategy_recent_win_rate,
              pe_ratio, pb_ratio, roe, debt_equity.
    One model file per strategy: ml_models/strategy_scorer_{id}.pkl
    """

    def train(self, db: Session, strategy_id: int) -> dict:
        """Train on signal_outcomes for one strategy. Returns metrics dict."""
        X, y = self._extract_features(db, strategy_id)
        if len(X) < MIN_TRAINING_SAMPLES:
            logger.warning(
                "[ml_scorer] strategy %d: insufficient samples: %d < %d",
                strategy_id, len(X), MIN_TRAINING_SAMPLES,
            )
            return {"samples": 0, "strategy_id": strategy_id}
        if len(np.unique(y)) < 2:
            logger.warning("[ml_scorer] strategy %d: only one class — skipping", strategy_id)
            return {"samples": 0, "strategy_id": strategy_id}
        if np.bincount(y).min() < 2:
            logger.warning("[ml_scorer] strategy %d: minority class has only 1 sample — skipping", strategy_id)
            return {"samples": 0, "strategy_id": strategy_id}

        from lightgbm import LGBMClassifier
        from sklearn.calibration import CalibratedClassifierCV
        from sklearn.metrics import roc_auc_score
        from sklearn.model_selection import train_test_split

        X_train, X_cal, y_train, y_cal = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=y
        )

        _lgb = dict(
            n_estimators=500,
            learning_rate=0.05,
            num_leaves=31,
            min_child_samples=20,
            class_weight="balanced",
            subsample=0.8,
            subsample_freq=1,
            colsample_bytree=0.8,
            reg_alpha=0.1,
            reg_lambda=1.0,
            random_state=42,
            n_jobs=-1,
            verbose=-1,
        )

        # Evaluate on holdout split for honest metrics
        base = LGBMClassifier(**_lgb)
        base.fit(X_train, y_train)

        classes = list(base.classes_)
        col = classes.index(1) if 1 in classes else None
        cal_probs = base.predict_proba(X_cal)[:, col] if col is not None else np.zeros(len(X_cal))

        auc_roc = float(roc_auc_score(y_cal, cal_probs)) if len(np.unique(y_cal)) > 1 else 0.5
        high_conf_mask = cal_probs >= 0.6
        precision_at_60 = float(y_cal[high_conf_mask].mean()) if high_conf_mask.sum() > 0 else None

        # Production model: isotonic calibration on full data
        # cv capped by minority class size so CalibratedClassifierCV never gets < cv examples per fold
        cv = min(5, int(np.bincount(y).min()))
        cal_method = "isotonic" if len(X) >= 500 else "sigmoid"
        model = CalibratedClassifierCV(LGBMClassifier(**_lgb), cv=cv, method=cal_method)
        model.fit(X, y)

        os.makedirs(_MODEL_DIR, exist_ok=True)
        with open(_model_path(strategy_id), "wb") as f:
            pickle.dump(model, f)

        metrics = {
            "strategy_id": strategy_id,
            "auc_roc": round(auc_roc, 4),
            "precision_at_60": round(precision_at_60, 4) if precision_at_60 is not None else None,
            "high_conf_signals": int(high_conf_mask.sum()),
            "class_balance": round(float(y.mean()), 4),
            "samples": len(X),
            "trained_at": datetime.now().isoformat(),
        }
        with open(_metrics_path(strategy_id), "w") as f:
            json.dump(metrics, f)

        _model_cache[strategy_id] = model
        logger.info(
            "[ml_scorer] strategy %d: trained on %d samples, auc_roc=%.3f",
            strategy_id, len(X), auc_roc,
        )
        return metrics

    def train_all(self, db: Session) -> dict:
        """Train one model per active strategy. Returns {strategy_id: metrics}."""
        ids = [r[0] for r in db.execute(text("SELECT id FROM strategies WHERE is_active = true")).fetchall()]
        results = {}
        for sid in ids:
            results[sid] = self.train(db, sid)
        return results

    def get_aggregate_status(self, db) -> dict:
        """Aggregate status across all per-strategy models."""
        ids = [r[0] for r in db.execute(text("SELECT id FROM strategies WHERE is_active = true")).fetchall()]
        trained, all_metrics = [], []
        for sid in ids:
            if os.path.exists(_model_path(sid)):
                trained.append(sid)
                mp = _metrics_path(sid)
                if os.path.exists(mp):
                    with open(mp) as f:
                        all_metrics.append(json.load(f))

        last_trained = max(
            (m["trained_at"] for m in all_metrics if m.get("trained_at")), default=None
        )
        aucs = [m["auc_roc"] for m in all_metrics if m.get("auc_roc") is not None]
        p60s = [m["precision_at_60"] for m in all_metrics if m.get("precision_at_60") is not None]
        return {
            "models_trained": len(trained),
            "models_total": len(ids),
            "last_trained": last_trained,
            "auc_roc": round(float(np.mean(aucs)), 4) if aucs else None,
            "precision_at_60": round(float(np.mean(p60s)), 4) if p60s else None,
            "high_conf_signals": sum(m.get("high_conf_signals", 0) for m in all_metrics),
            "class_balance": None,
        }

    def predict(self, features: dict, db=None, symbol: str = None) -> Optional[float]:
        """Return calibrated win-probability in [0,1], or None if no model for this strategy.

        Required keys: confidence_score, regime_code, strategy_id, month, day_of_week
        """
        strategy_id = int(features["strategy_id"])
        model = self._load_model(strategy_id)
        if model is None:
            return None

        strategy_win_rate = features.get("strategy_win_rate")
        log_total_trades = features.get("log_total_trades")
        strategy_recent_win_rate = features.get("strategy_recent_win_rate")

        if db is not None and strategy_win_rate is None:
            stats = self._get_strategy_stats(db, strategy_id)
            strategy_win_rate = stats["win_rate"]
            log_total_trades = stats["log_total_trades"]
            strategy_recent_win_rate = stats["recent_win_rate"]

        if strategy_win_rate is None:
            strategy_win_rate = 0.5
        if log_total_trades is None:
            log_total_trades = 2.0
        if strategy_recent_win_rate is None:
            strategy_recent_win_rate = strategy_win_rate

        pe_ratio = pb_ratio = roe = debt_equity = None
        if db is not None and symbol:
            fund_row = db.execute(
                text("""
                    SELECT pe_ratio, pb_ratio, roe, debt_equity
                    FROM fundamentals WHERE symbol = :sym
                    ORDER BY data_as_of DESC LIMIT 1
                """),
                {"sym": symbol},
            ).fetchone()
            if fund_row:
                pe_ratio, pb_ratio, roe, debt_equity = fund_row[0], fund_row[1], fund_row[2], fund_row[3]

        X_row = np.array([[
            features["confidence_score"],
            features["regime_code"],
            strategy_id,
            features["month"],
            features["day_of_week"],
            strategy_win_rate,
            log_total_trades,
            strategy_recent_win_rate,
            float(pe_ratio) if pe_ratio is not None else np.nan,
            float(pb_ratio) if pb_ratio is not None else np.nan,
            float(roe) if roe is not None else np.nan,
            float(debt_equity) if debt_equity is not None else np.nan,
        ]])

        try:
            probs = model.predict_proba(X_row)[0]
        except ValueError:
            _model_cache[strategy_id] = None
            logger.warning("[ml_scorer] strategy %d: feature mismatch — needs retraining", strategy_id)
            return None
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

    def _load_model(self, strategy_id: int):
        cached = _model_cache.get(strategy_id)
        if cached is _LOAD_FAILED:
            return None
        if cached is not None:
            return cached
        path = _model_path(strategy_id)
        if not os.path.exists(path):
            _model_cache[strategy_id] = _LOAD_FAILED
            return None
        try:
            with open(path, "rb") as f:
                _model_cache[strategy_id] = pickle.load(f)
            return _model_cache[strategy_id]
        except Exception as e:
            logger.warning("[ml_scorer] failed to load model for strategy %d: %s", strategy_id, e)
            _model_cache[strategy_id] = _LOAD_FAILED
            return None

    def _extract_features(self, db: Session, strategy_id: int):
        """12 features per signal_outcome row, filtered to one strategy."""
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
                ) AS strategy_recent_win_rate,
                fund.pe_ratio,
                fund.pb_ratio,
                fund.roe,
                fund.debt_equity
            FROM signal_outcomes so
            JOIN strategy_signals ss ON ss.id = so.signal_id
            LEFT JOIN market_regime mr ON mr.date = so.signal_date
            LEFT JOIN LATERAL (
                SELECT pe_ratio, pb_ratio, roe, debt_equity
                FROM fundamentals
                WHERE symbol = ss.symbol AND data_as_of <= so.signal_date
                ORDER BY data_as_of DESC LIMIT 1
            ) fund ON TRUE
            WHERE so.is_profitable IS NOT NULL AND ss.strategy_id = :sid
        """), {"sid": strategy_id}).fetchall()

        if not rows:
            return np.array([]).reshape(0, 12), np.array([])

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
            pe_ratio = float(r[8]) if r[8] is not None else np.nan
            pb_ratio = float(r[9]) if r[9] is not None else np.nan
            roe = float(r[10]) if r[10] is not None else np.nan
            debt_equity = float(r[11]) if r[11] is not None else np.nan

            if isinstance(sig_date, str):
                from datetime import datetime as dt
                sig_date = dt.strptime(sig_date[:10], "%Y-%m-%d").date()

            X_list.append([
                conf_score, regime_code, strat_id,
                sig_date.month, sig_date.weekday(),
                strategy_win_rate, log_total_trades, recent_win_rate,
                pe_ratio, pb_ratio, roe, debt_equity,
            ])
            y_list.append(1 if is_prof else 0)

        return np.array(X_list), np.array(y_list)
