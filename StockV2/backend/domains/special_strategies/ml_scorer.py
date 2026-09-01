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
_model_cache: dict = {}  # {special_strategy_id: model | _LOAD_FAILED}


def _model_path(special_strategy_id: int) -> str:
    return os.path.join(_MODEL_DIR, f"special_strategy_scorer_{special_strategy_id}.pkl")


def _metrics_path(special_strategy_id: int) -> str:
    return os.path.join(_MODEL_DIR, f"special_strategy_scorer_{special_strategy_id}_metrics.json")


def special_regime_to_code(regime: str) -> int:
    return _REGIME_MAP.get(regime, 3)


class SpecialMLScorer:
    """
    LightGBM classifier trained per-strategy on special_strategy_trades with isotonic calibration.
    Features: strategy_id, entry_month, entry_dow, regime_code,
              strategy_avg_win_rate, strategy_profit_factor, strategy_avg_pnl_pct,
              pe_ratio, pb_ratio, roe, debt_equity.
    One model file per special strategy: ml_models/special_strategy_scorer_{id}.pkl
    """

    def train(self, db: Session, special_strategy_id: int) -> dict:
        """Train on special_strategy_trades for one strategy. Returns metrics dict."""
        X, y = self._extract_features(db, special_strategy_id)
        if len(X) < MIN_TRAINING_SAMPLES:
            logger.warning(
                "[special_ml_scorer] strategy %d: insufficient samples: %d < %d",
                special_strategy_id, len(X), MIN_TRAINING_SAMPLES,
            )
            return {"samples": 0, "strategy_id": special_strategy_id}
        if len(np.unique(y)) < 2:
            logger.warning("[special_ml_scorer] strategy %d: only one class — skipping", special_strategy_id)
            return {"samples": 0, "strategy_id": special_strategy_id}

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

        base = LGBMClassifier(**_lgb)
        base.fit(X_train, y_train)

        classes = list(base.classes_)
        col = classes.index(1) if 1 in classes else None
        cal_probs = base.predict_proba(X_cal)[:, col] if col is not None else np.zeros(len(X_cal))

        auc_roc = float(roc_auc_score(y_cal, cal_probs)) if len(np.unique(y_cal)) > 1 else 0.5
        high_conf_mask = cal_probs >= 0.6
        precision_at_60 = float(y_cal[high_conf_mask].mean()) if high_conf_mask.sum() > 0 else None

        cal_method = "isotonic" if len(X) >= 500 else "sigmoid"
        model = CalibratedClassifierCV(LGBMClassifier(**_lgb), cv=5, method=cal_method)
        model.fit(X, y)

        os.makedirs(_MODEL_DIR, exist_ok=True)
        with open(_model_path(special_strategy_id), "wb") as f:
            pickle.dump(model, f)

        metrics = {
            "strategy_id": special_strategy_id,
            "auc_roc": round(auc_roc, 4),
            "precision_at_60": round(precision_at_60, 4) if precision_at_60 is not None else None,
            "high_conf_signals": int(high_conf_mask.sum()),
            "class_balance": round(float(y.mean()), 4),
            "samples": len(X),
            "trained_at": datetime.now().isoformat(),
        }
        with open(_metrics_path(special_strategy_id), "w") as f:
            json.dump(metrics, f)

        _model_cache[special_strategy_id] = model
        logger.info(
            "[special_ml_scorer] strategy %d: trained on %d samples, auc_roc=%.3f",
            special_strategy_id, len(X), auc_roc,
        )
        return metrics

    def train_all(self, db: Session) -> dict:
        """Train one model per active special strategy. Returns {strategy_id: metrics}."""
        ids = [r[0] for r in db.execute(text("SELECT id FROM special_strategies WHERE is_active = true")).fetchall()]
        results = {}
        for sid in ids:
            results[sid] = self.train(db, sid)
        return results

    def get_aggregate_status(self, db) -> dict:
        """Aggregate status across all per-special-strategy models."""
        ids = [r[0] for r in db.execute(text("SELECT id FROM special_strategies WHERE is_active = true")).fetchall()]
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

        Expected keys: strategy_id, entry_month, entry_dow, regime_code,
                       strategy_avg_win_rate, strategy_profit_factor, strategy_avg_pnl_pct
        """
        special_strategy_id = int(features["strategy_id"])
        model = self._load_model(special_strategy_id)
        if model is None:
            return None

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
            special_strategy_id,
            features["entry_month"],
            features["entry_dow"],
            features["regime_code"],
            features.get("strategy_avg_win_rate", 0.5),
            features.get("strategy_profit_factor", 1.0),
            features.get("strategy_avg_pnl_pct", 0.0),
            float(pe_ratio) if pe_ratio is not None else np.nan,
            float(pb_ratio) if pb_ratio is not None else np.nan,
            float(roe) if roe is not None else np.nan,
            float(debt_equity) if debt_equity is not None else np.nan,
        ]])
        try:
            probs = model.predict_proba(X_row)[0]
        except ValueError:
            _model_cache[special_strategy_id] = None
            logger.warning(
                "[special_ml_scorer] strategy %d: feature mismatch — needs retraining",
                special_strategy_id,
            )
            return None
        classes = list(model.classes_)
        if 1 not in classes:
            return 0.0
        col = classes.index(1)
        return round(float(probs[col]), 4)

    def _load_model(self, special_strategy_id: int):
        cached = _model_cache.get(special_strategy_id)
        if cached is _LOAD_FAILED:
            return None
        if cached is not None:
            return cached
        path = _model_path(special_strategy_id)
        if not os.path.exists(path):
            _model_cache[special_strategy_id] = _LOAD_FAILED
            return None
        try:
            with open(path, "rb") as f:
                _model_cache[special_strategy_id] = pickle.load(f)
            return _model_cache[special_strategy_id]
        except Exception as e:
            logger.warning("[special_ml_scorer] failed to load model for strategy %d: %s", special_strategy_id, e)
            _model_cache[special_strategy_id] = _LOAD_FAILED
            return None

    def _extract_features(self, db: Session, special_strategy_id: int):
        """11 features per special_strategy_trades row, filtered to one strategy."""
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
                COALESCE(ss.avg_pnl_pct_stat, 0.0)  AS strategy_avg_pnl_pct,
                fund.pe_ratio,
                fund.pb_ratio,
                fund.roe,
                fund.debt_equity
            FROM special_strategy_trades sst
            LEFT JOIN market_regime mr ON mr.date = sst.entry_date
            LEFT JOIN strategy_stats ss ON ss.special_strategy_id = sst.special_strategy_id
            LEFT JOIN LATERAL (
                SELECT pe_ratio, pb_ratio, roe, debt_equity
                FROM fundamentals
                WHERE symbol = sst.symbol AND data_as_of <= sst.entry_date
                ORDER BY data_as_of DESC LIMIT 1
            ) fund ON TRUE
            WHERE sst.entry_date IS NOT NULL
              AND sst.pnl_pct IS NOT NULL
              AND sst.special_strategy_id = :sid
        """), {"sid": special_strategy_id}).fetchall()

        if not rows:
            return np.array([]).reshape(0, 11), np.array([])

        X_list, y_list = [], []
        for r in rows:
            strategy_id   = int(r[0])
            entry_date    = r[1]
            regime        = r[2]
            pnl_pct       = float(r[3])
            avg_win_rate  = float(r[4]) if r[4] is not None else 0.5
            profit_factor = float(r[5]) if r[5] is not None else 1.0
            avg_pnl_pct   = float(r[6]) if r[6] is not None else 0.0
            pe_ratio      = float(r[7]) if r[7] is not None else np.nan
            pb_ratio      = float(r[8]) if r[8] is not None else np.nan
            roe           = float(r[9]) if r[9] is not None else np.nan
            debt_equity   = float(r[10]) if r[10] is not None else np.nan

            if isinstance(entry_date, str):
                from datetime import datetime as dt
                entry_date = dt.strptime(entry_date[:10], "%Y-%m-%d").date()

            regime_code = _REGIME_MAP.get(regime, 3)
            X_list.append([
                strategy_id, entry_date.month, entry_date.weekday(),
                regime_code, avg_win_rate, profit_factor, avg_pnl_pct,
                pe_ratio, pb_ratio, roe, debt_equity,
            ])
            y_list.append(1 if pnl_pct >= 10.0 else 0)

        return np.array(X_list), np.array(y_list)
