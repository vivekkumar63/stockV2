# ML Model Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade both ML scorers to Calibrated Random Forest with richer features and post-training evaluation metrics (AUC-ROC, Precision@60%) visible on the ML Models page.

**Architecture:** Both scorers switch from GBC to `RandomForestClassifier(class_weight='balanced')` wrapped with `CalibratedClassifierCV(cv='prefit', method='sigmoid')` using an 80/20 train/calibration split. Normal scorer gets 3 new strategy-performance features via PostgreSQL window functions; special scorer gets 3 new features from the existing `special_strategy_performance` table. Metrics are saved to JSON sidecar files and surfaced through the status API and UI.

**Tech Stack:** scikit-learn RandomForestClassifier + CalibratedClassifierCV, PostgreSQL window functions, JSON sidecar files, React/TanStack Query

---

## File Map

| File | Action |
|------|--------|
| `backend/domains/intelligence/ml_scorer.py` | REWRITE — new features, RF+calibration, metrics sidecar, `train()` returns dict, `predict()` accepts optional `db` |
| `backend/domains/special_strategies/ml_scorer.py` | REWRITE — new features, RF+calibration, metrics sidecar, same changes |
| `backend/domains/intelligence/router.py` | MODIFY — ml-status reads sidecar, train returns full metrics, predict calls pass `db=db` |
| `backend/domains/special_strategies/router.py` | MODIFY — ml-status reads sidecar, train returns full metrics, `_enrich_with_performance` passes perf features to predict |
| `backend/tests/test_special_ml_scorer.py` | MODIFY — update assertions for new `train()` return type |
| `frontend/src/api/ml.ts` | MODIFY — add metric fields to both interfaces |
| `frontend/src/pages/MLModelsPage.tsx` | MODIFY — show metrics row on card |

---

## Task 1: Upgrade `MLSignalScorer` (normal strategies)

**Files:**
- Modify: `backend/domains/intelligence/ml_scorer.py`

- [ ] **Step 1: Write failing tests for new behaviour**

Update `backend/tests/test_ml_scorer.py` if it exists, or create it if not:

```python
# backend/tests/test_ml_scorer.py
import pytest
from unittest.mock import MagicMock, patch
from datetime import date
from domains.intelligence.ml_scorer import MLSignalScorer, regime_to_code


def test_regime_to_code_known():
    assert regime_to_code("BULL") == 4
    assert regime_to_code("STRONG_BULL") == 5


def test_regime_to_code_unknown_defaults_to_sideways():
    assert regime_to_code("UNKNOWN") == 3


def test_predict_returns_none_when_no_model(tmp_path):
    with patch("domains.intelligence.ml_scorer.MODEL_PATH", str(tmp_path / "missing.pkl")):
        import domains.intelligence.ml_scorer as m
        m._cached_model = None
        scorer = MLSignalScorer()
        result = scorer.predict({
            "confidence_score": 0.7, "regime_code": 4, "strategy_id": 1,
            "month": 6, "day_of_week": 2,
        })
        assert result is None


def test_train_returns_dict_with_samples_zero_when_insufficient():
    db = MagicMock()
    db.execute.return_value.fetchall.return_value = []
    scorer = MLSignalScorer()
    result = scorer.train(db)
    assert isinstance(result, dict)
    assert result["samples"] == 0


def test_train_returns_dict_with_samples_zero_when_single_class(tmp_path):
    db = MagicMock()
    # 60 rows, all profitable — only one class
    fake_rows = [
        (0.8, "BULL", 1, date(2023, i % 12 + 1, 1), True,
         0.6, 60, 0.55)
        for i in range(60)
    ]
    db.execute.return_value.fetchall.return_value = fake_rows
    with patch("domains.intelligence.ml_scorer.MODEL_PATH", str(tmp_path / "model.pkl")):
        import domains.intelligence.ml_scorer as m
        m._cached_model = None
        scorer = MLSignalScorer()
        result = scorer.train(db)
        assert result["samples"] == 0
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd C:/DLP_Repos/MyRepo/StockV2/backend
python -m pytest tests/test_ml_scorer.py -v 2>&1 | head -30
```

Expected: `ImportError` or assertion failures on the new return type.

- [ ] **Step 3: Rewrite `backend/domains/intelligence/ml_scorer.py`**

```python
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
            SELECT COUNT(*), AVG(so.is_profitable::float)
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
                AVG((so.is_profitable)::float) OVER (
                    PARTITION BY ss.strategy_id
                ) AS strategy_win_rate,
                COUNT(*) OVER (
                    PARTITION BY ss.strategy_id
                ) AS strategy_total_trades,
                COALESCE(
                    AVG((so.is_profitable)::float) OVER (
                        PARTITION BY ss.strategy_id
                        ORDER BY so.signal_date
                        ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING
                    ),
                    AVG((so.is_profitable)::float) OVER (PARTITION BY ss.strategy_id)
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
```

- [ ] **Step 4: Run tests**

```bash
cd C:/DLP_Repos/MyRepo/StockV2/backend
python -m pytest tests/test_ml_scorer.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Verify syntax**

```bash
cd C:/DLP_Repos/MyRepo/StockV2/backend
python -c "import ast; ast.parse(open('domains/intelligence/ml_scorer.py').read()); print('OK')"
```

Expected: `OK`

- [ ] **Step 6: Commit**

```bash
cd C:/DLP_Repos/MyRepo/StockV2
git add backend/domains/intelligence/ml_scorer.py backend/tests/test_ml_scorer.py
git commit -m "feat: upgrade MLSignalScorer to calibrated RandomForest with 8 features"
```

---

## Task 2: Upgrade `SpecialMLScorer`

**Files:**
- Modify: `backend/domains/special_strategies/ml_scorer.py`
- Modify: `backend/tests/test_special_ml_scorer.py`

- [ ] **Step 1: Update tests for new return type**

Replace `backend/tests/test_special_ml_scorer.py`:

```python
import pytest
from unittest.mock import MagicMock, patch
from datetime import date
from domains.special_strategies.ml_scorer import SpecialMLScorer, special_regime_to_code


def test_regime_to_code_known():
    assert special_regime_to_code("BULL") == 4
    assert special_regime_to_code("STRONG_BULL") == 5
    assert special_regime_to_code("BEAR") == 2


def test_regime_to_code_unknown_defaults_to_sideways():
    assert special_regime_to_code("UNKNOWN") == 3


def test_predict_returns_none_when_no_model(tmp_path):
    with patch("domains.special_strategies.ml_scorer.MODEL_PATH", str(tmp_path / "missing.pkl")):
        import domains.special_strategies.ml_scorer as m
        m._cached_model = None
        scorer = SpecialMLScorer()
        result = scorer.predict({
            "strategy_id": 1, "entry_month": 6, "entry_dow": 2,
            "regime_code": 4, "strategy_avg_win_rate": 0.6,
            "strategy_profit_factor": 1.5, "strategy_avg_pnl_pct": 3.2,
        })
        assert result is None


def test_train_returns_dict_with_samples_zero_when_insufficient():
    db = MagicMock()
    db.execute.return_value.fetchall.return_value = []
    scorer = SpecialMLScorer()
    result = scorer.train(db)
    assert isinstance(result, dict)
    assert result["samples"] == 0


def test_train_returns_dict_with_samples_zero_when_single_class(tmp_path):
    """All trades profitable → only one class → skipped."""
    db = MagicMock()
    fake_rows = [
        (1, date(2023, i % 12 + 1, 1), "BULL", 500.0, 0.65, 1.8, 4.2)
        for i in range(60)
    ]
    db.execute.return_value.fetchall.return_value = fake_rows
    with patch("domains.special_strategies.ml_scorer.MODEL_PATH", str(tmp_path / "model.pkl")):
        import domains.special_strategies.ml_scorer as m
        m._cached_model = None
        scorer = SpecialMLScorer()
        result = scorer.train(db)
        assert result["samples"] == 0
```

- [ ] **Step 2: Run tests to confirm failures**

```bash
cd C:/DLP_Repos/MyRepo/StockV2/backend
python -m pytest tests/test_special_ml_scorer.py -v 2>&1 | head -20
```

Expected: failures due to old `return 0` return type.

- [ ] **Step 3: Rewrite `backend/domains/special_strategies/ml_scorer.py`**

```python
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
        """CTE query: 7 features per special_backtest_trades row."""
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
                sbr.special_strategy_id,
                sbt.entry_date,
                mr.regime,
                sbt.pnl,
                COALESCE(ss.avg_win_rate, 0.5)      AS strategy_avg_win_rate,
                COALESCE(ss.avg_profit_factor, 1.0) AS strategy_profit_factor,
                COALESCE(ss.avg_pnl_pct_stat, 0.0)  AS strategy_avg_pnl_pct
            FROM special_backtest_trades sbt
            JOIN special_backtest_results sbr ON sbr.id = sbt.backtest_result_id
            LEFT JOIN market_regime mr ON mr.date = sbt.entry_date
            LEFT JOIN strategy_stats ss ON ss.special_strategy_id = sbr.special_strategy_id
            WHERE sbt.entry_date IS NOT NULL AND sbt.pnl IS NOT NULL
        """)).fetchall()

        if not rows:
            return np.array([]).reshape(0, 7), np.array([])

        X_list, y_list = [], []
        for r in rows:
            strategy_id = int(r[0])
            entry_date = r[1]
            regime = r[2]
            pnl = float(r[3])
            avg_win_rate = float(r[4]) if r[4] is not None else 0.5
            profit_factor = float(r[5]) if r[5] is not None else 1.0
            avg_pnl_pct = float(r[6]) if r[6] is not None else 0.0

            if isinstance(entry_date, str):
                from datetime import datetime as dt
                entry_date = dt.strptime(entry_date[:10], "%Y-%m-%d").date()

            regime_code = _REGIME_MAP.get(regime, 3)
            X_list.append([
                strategy_id, entry_date.month, entry_date.weekday(),
                regime_code, avg_win_rate, profit_factor, avg_pnl_pct,
            ])
            y_list.append(1 if pnl > 0 else 0)

        return np.array(X_list), np.array(y_list)
```

- [ ] **Step 4: Run tests**

```bash
cd C:/DLP_Repos/MyRepo/StockV2/backend
python -m pytest tests/test_special_ml_scorer.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd C:/DLP_Repos/MyRepo/StockV2
git add backend/domains/special_strategies/ml_scorer.py backend/tests/test_special_ml_scorer.py
git commit -m "feat: upgrade SpecialMLScorer to calibrated RandomForest with 7 features"
```

---

## Task 3: Update intelligence router

**Files:**
- Modify: `backend/domains/intelligence/router.py`

Two changes: (a) add `METRICS_PATH` import, (b) update two `predict()` call sites to pass `db=db`, (c) update `ml-status` to include metrics, (d) update `train` endpoint to return full metrics.

- [ ] **Step 1: Update ml_scorer import to include `METRICS_PATH`**

Find:
```python
from domains.intelligence.ml_scorer import (
    MLSignalScorer, regime_to_code,
    MODEL_PATH as NORMAL_ML_MODEL_PATH,
    MIN_TRAINING_SAMPLES as NORMAL_ML_MIN_SAMPLES,
)
```

Replace with:
```python
from domains.intelligence.ml_scorer import (
    MLSignalScorer, regime_to_code,
    MODEL_PATH as NORMAL_ML_MODEL_PATH,
    METRICS_PATH as NORMAL_ML_METRICS_PATH,
    MIN_TRAINING_SAMPLES as NORMAL_ML_MIN_SAMPLES,
)
```

- [ ] **Step 2: Add `import json` at the top of the file**

Find:
```python
import logging
import os
from datetime import date, datetime
from typing import Optional
```

Replace with:
```python
import json
import logging
import os
from datetime import date, datetime
from typing import Optional
```

- [ ] **Step 3: Update first `predict()` call site (individual opportunity score, around line 113)**

Find:
```python
        ml_prob = MLSignalScorer().predict({
            "confidence_score": 0.5,
            "regime_code": regime_to_code(regime),
            "strategy_id": strategy_id,
            "month": date.today().month,
            "day_of_week": date.today().weekday(),
        })
```

Replace with:
```python
        ml_prob = MLSignalScorer().predict({
            "confidence_score": 0.5,
            "regime_code": regime_to_code(regime),
            "strategy_id": strategy_id,
            "month": date.today().month,
            "day_of_week": date.today().weekday(),
        }, db=db)
```

- [ ] **Step 4: Update second `predict()` call site (bulk top-opportunities, around line 291)**

Find:
```python
        ml_prob = ml_scorer.predict({
            "confidence_score": confidence_score or 0.5,
            "regime_code":      regime_to_code(regime),
            "strategy_id":      strategy_id,
            "month":            today.month,
            "day_of_week":      today.weekday(),
        })
```

Replace with:
```python
        ml_prob = ml_scorer.predict({
            "confidence_score": confidence_score or 0.5,
            "regime_code":      regime_to_code(regime),
            "strategy_id":      strategy_id,
            "month":            today.month,
            "day_of_week":      today.weekday(),
        }, db=db)
```

- [ ] **Step 5: Update `GET /intelligence/ml-status` to include sidecar metrics**

Find:
```python
@router.get("/intelligence/ml-status")
def get_normal_ml_status(db: Session = Depends(get_db)):
    """Model file existence, last-trained timestamp, and available sample count."""
    exists = os.path.exists(NORMAL_ML_MODEL_PATH)
    last_trained = None
    if exists:
        last_trained = datetime.fromtimestamp(os.path.getmtime(NORMAL_ML_MODEL_PATH)).isoformat()
    samples = db.execute(
        text("SELECT COUNT(*) FROM signal_outcomes WHERE is_profitable IS NOT NULL")
    ).scalar() or 0
    return {"exists": exists, "last_trained": last_trained, "samples_available": int(samples)}
```

Replace with:
```python
@router.get("/intelligence/ml-status")
def get_normal_ml_status(db: Session = Depends(get_db)):
    """Model file existence, last-trained timestamp, sample count, and quality metrics."""
    exists = os.path.exists(NORMAL_ML_MODEL_PATH)
    last_trained = None
    metrics: dict = {}
    if exists:
        last_trained = datetime.fromtimestamp(os.path.getmtime(NORMAL_ML_MODEL_PATH)).isoformat()
        if os.path.exists(NORMAL_ML_METRICS_PATH):
            with open(NORMAL_ML_METRICS_PATH) as f:
                metrics = json.load(f)
    samples = db.execute(
        text("SELECT COUNT(*) FROM signal_outcomes WHERE is_profitable IS NOT NULL")
    ).scalar() or 0
    return {
        "exists": exists,
        "last_trained": last_trained,
        "samples_available": int(samples),
        "auc_roc": metrics.get("auc_roc"),
        "precision_at_60": metrics.get("precision_at_60"),
        "high_conf_signals": metrics.get("high_conf_signals"),
        "class_balance": metrics.get("class_balance"),
    }
```

- [ ] **Step 6: Update `POST /intelligence/train` to return full metrics**

Find:
```python
@router.post("/intelligence/train")
def train_normal_ml_model(db: Session = Depends(get_db)):
    """Train the normal-strategy ML model on signal_outcomes data."""
    scorer = MLSignalScorer()
    n = scorer.train(db)
    if n == 0:
        return {
            "status": "skipped", "samples": 0,
            "message": f"Need at least {NORMAL_ML_MIN_SAMPLES} labelled signal_outcomes rows",
        }
    return {"status": "ok", "samples": n, "message": f"Trained on {n} samples"}
```

Replace with:
```python
@router.post("/intelligence/train")
def train_normal_ml_model(db: Session = Depends(get_db)):
    """Train the normal-strategy ML model on signal_outcomes data."""
    scorer = MLSignalScorer()
    result = scorer.train(db)
    if result["samples"] == 0:
        return {
            "status": "skipped", "samples": 0,
            "message": f"Need at least {NORMAL_ML_MIN_SAMPLES} labelled signal_outcomes rows",
        }
    return {
        "status": "ok",
        "message": f"Trained on {result['samples']} samples",
        **result,
    }
```

- [ ] **Step 7: Verify syntax**

```bash
cd C:/DLP_Repos/MyRepo/StockV2/backend
python -c "import ast; ast.parse(open('domains/intelligence/router.py').read()); print('OK')"
```

Expected: `OK`

- [ ] **Step 8: Commit**

```bash
cd C:/DLP_Repos/MyRepo/StockV2
git add backend/domains/intelligence/router.py
git commit -m "feat: intelligence router returns full ML metrics and passes db to predict"
```

---

## Task 4: Update special strategies router

**Files:**
- Modify: `backend/domains/special_strategies/router.py`

- [ ] **Step 1: Update ml_scorer import to include `METRICS_PATH`**

Find:
```python
from domains.special_strategies.ml_scorer import (
    SpecialMLScorer, special_regime_to_code,
    MODEL_PATH as SPECIAL_ML_MODEL_PATH,
    MIN_TRAINING_SAMPLES as SPECIAL_ML_MIN_SAMPLES,
)
```

Replace with:
```python
from domains.special_strategies.ml_scorer import (
    SpecialMLScorer, special_regime_to_code,
    MODEL_PATH as SPECIAL_ML_MODEL_PATH,
    METRICS_PATH as SPECIAL_ML_METRICS_PATH,
    MIN_TRAINING_SAMPLES as SPECIAL_ML_MIN_SAMPLES,
)
```

- [ ] **Step 2: Add `import json` if not already present**

Check top of file for `import json`. It should already be there from a previous commit. If missing, add it after `import logging`.

- [ ] **Step 3: Update `_enrich_with_performance()` to pass performance features to `predict()`**

Find the scorer.predict() call block inside `_enrich_with_performance`:
```python
        ml_prob = None
        if s["strategy_id"] is not None:
            ml_prob = scorer.predict({
                "strategy_id": s["strategy_id"],
                "entry_month": today.month,
                "entry_dow": today.weekday(),
                "regime_code": regime_code,
            })
```

Replace with:
```python
        ml_prob = None
        if s["strategy_id"] is not None:
            ml_prob = scorer.predict({
                "strategy_id": s["strategy_id"],
                "entry_month": today.month,
                "entry_dow": today.weekday(),
                "regime_code": regime_code,
                "strategy_avg_win_rate":  float(p[3]) if p and p[3] is not None else 0.5,
                "strategy_profit_factor": float(p[7]) if p and p[7] is not None else 1.0,
                "strategy_avg_pnl_pct":   float(p[9]) if p and p[9] is not None else 0.0,
            })
```

- [ ] **Step 4: Update `GET /special/ml-status` to include sidecar metrics**

Find:
```python
@router.get("/special/ml-status")
def get_special_ml_status(db: Session = Depends(get_db)):
    """Model file existence, last-trained timestamp, and available sample count."""
    exists = os.path.exists(SPECIAL_ML_MODEL_PATH)
    last_trained = None
    if exists:
        last_trained = datetime.fromtimestamp(os.path.getmtime(SPECIAL_ML_MODEL_PATH)).isoformat()
    samples = db.execute(
        text("""
            SELECT COUNT(*) FROM special_backtest_trades
            WHERE entry_date IS NOT NULL AND pnl IS NOT NULL
        """)
    ).scalar() or 0
    return {"exists": exists, "last_trained": last_trained, "samples_available": int(samples)}
```

Replace with:
```python
@router.get("/special/ml-status")
def get_special_ml_status(db: Session = Depends(get_db)):
    """Model file existence, last-trained timestamp, sample count, and quality metrics."""
    exists = os.path.exists(SPECIAL_ML_MODEL_PATH)
    last_trained = None
    metrics: dict = {}
    if exists:
        last_trained = datetime.fromtimestamp(os.path.getmtime(SPECIAL_ML_MODEL_PATH)).isoformat()
        if os.path.exists(SPECIAL_ML_METRICS_PATH):
            with open(SPECIAL_ML_METRICS_PATH) as f:
                metrics = json.load(f)
    samples = db.execute(
        text("""
            SELECT COUNT(*) FROM special_backtest_trades
            WHERE entry_date IS NOT NULL AND pnl IS NOT NULL
        """)
    ).scalar() or 0
    return {
        "exists": exists,
        "last_trained": last_trained,
        "samples_available": int(samples),
        "auc_roc": metrics.get("auc_roc"),
        "precision_at_60": metrics.get("precision_at_60"),
        "high_conf_signals": metrics.get("high_conf_signals"),
        "class_balance": metrics.get("class_balance"),
    }
```

- [ ] **Step 5: Update `POST /special/ml/train` to return full metrics**

Find:
```python
@router.post("/special/ml/train")
def train_special_ml_model(db: Session = Depends(get_db)):
    """Train the special-strategy ML model on special_backtest_trades data."""
    scorer = SpecialMLScorer()
    n = scorer.train(db)
    if n == 0:
        return {
            "status": "skipped", "samples": 0,
            "message": f"Need at least {SPECIAL_ML_MIN_SAMPLES} labelled special_backtest_trades rows",
        }
    return {"status": "ok", "samples": n, "message": f"Trained on {n} samples"}
```

Replace with:
```python
@router.post("/special/ml/train")
def train_special_ml_model(db: Session = Depends(get_db)):
    """Train the special-strategy ML model on special_backtest_trades data."""
    scorer = SpecialMLScorer()
    result = scorer.train(db)
    if result["samples"] == 0:
        return {
            "status": "skipped", "samples": 0,
            "message": f"Need at least {SPECIAL_ML_MIN_SAMPLES} labelled special_backtest_trades rows",
        }
    return {
        "status": "ok",
        "message": f"Trained on {result['samples']} samples",
        **result,
    }
```

- [ ] **Step 6: Verify syntax**

```bash
cd C:/DLP_Repos/MyRepo/StockV2/backend
python -c "import ast; ast.parse(open('domains/special_strategies/router.py').read()); print('OK')"
```

Expected: `OK`

- [ ] **Step 7: Commit**

```bash
cd C:/DLP_Repos/MyRepo/StockV2
git add backend/domains/special_strategies/router.py
git commit -m "feat: special router returns full ML metrics, enrich passes perf features to predict"
```

---

## Task 5: Update frontend API types

**Files:**
- Modify: `frontend/src/api/ml.ts`

- [ ] **Step 1: Add metrics fields to both interfaces**

Replace the entire file content of `frontend/src/api/ml.ts`:

```typescript
import { apiFetch } from './client'

export interface MLModelStatus {
  exists: boolean
  last_trained: string | null
  samples_available: number
  auc_roc: number | null
  precision_at_60: number | null
  high_conf_signals: number | null
  class_balance: number | null
}

export interface MLTrainResult {
  status: 'ok' | 'skipped'
  samples: number
  message: string
  auc_roc?: number
  precision_at_60?: number
  high_conf_signals?: number
  class_balance?: number
}

export const getNormalMLStatus  = () => apiFetch<MLModelStatus>('/intelligence/ml-status')
export const trainNormalModel   = () => apiFetch<MLTrainResult>('/intelligence/train', { method: 'POST' })

export const getSpecialMLStatus = () => apiFetch<MLModelStatus>('/special/ml-status')
export const trainSpecialModel  = () => apiFetch<MLTrainResult>('/special/ml/train', { method: 'POST' })
```

- [ ] **Step 2: Commit**

```bash
cd C:/DLP_Repos/MyRepo/StockV2
git add frontend/src/api/ml.ts
git commit -m "feat: add metrics fields to MLModelStatus and MLTrainResult types"
```

---

## Task 6: Update MLModelsPage UI

**Files:**
- Modify: `frontend/src/pages/MLModelsPage.tsx`

- [ ] **Step 1: Add metrics display to ModelCard**

Replace the entire file content of `frontend/src/pages/MLModelsPage.tsx`:

```tsx
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  MLModelStatus,
  MLTrainResult,
  getNormalMLStatus,
  getSpecialMLStatus,
  trainNormalModel,
  trainSpecialModel,
} from '../api/ml'

function MetricsRow({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <div className="flex items-baseline justify-between text-sm">
      <span className="text-gray-500">{label}</span>
      <span className="font-mono text-gray-900 font-medium">{value}</span>
      <span className="text-xs text-gray-400 ml-2">{note}</span>
    </div>
  )
}

function ModelCard({
  title,
  description,
  queryKey,
  fetchStatus,
  triggerTrain,
}: {
  title: string
  description: string
  queryKey: string
  fetchStatus: () => Promise<MLModelStatus>
  triggerTrain: () => Promise<MLTrainResult>
}) {
  const qc = useQueryClient()
  const { data: status, isLoading: statusLoading } = useQuery({
    queryKey: [queryKey],
    queryFn: fetchStatus,
  })

  const { mutate: train, isPending, data: trainResult, error } = useMutation({
    mutationFn: triggerTrain,
    onSuccess: () => qc.invalidateQueries({ queryKey: [queryKey] }),
  })

  const metrics = trainResult?.status === 'ok' ? trainResult : status

  return (
    <div className="bg-white rounded-lg shadow p-6 flex flex-col gap-4 flex-1">
      <div>
        <h2 className="text-lg font-semibold text-gray-800">{title}</h2>
        <p className="text-sm text-gray-500 mt-1">{description}</p>
      </div>

      {statusLoading ? (
        <p className="text-sm text-gray-400">Loading status…</p>
      ) : status ? (
        <div className="space-y-1.5 text-sm">
          <div className="flex items-center gap-2">
            <span
              className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${status.exists ? 'bg-green-500' : 'bg-gray-400'}`}
            />
            <span className={status.exists ? 'text-green-700 font-medium' : 'text-gray-500'}>
              {status.exists ? 'Trained' : 'Not Trained'}
            </span>
            {status.last_trained && (
              <span className="text-gray-400 text-xs ml-auto">
                {new Date(status.last_trained).toLocaleString()}
              </span>
            )}
          </div>
          <div className="text-gray-500 text-xs">
            Samples available:{' '}
            <span className="font-mono text-gray-700">{status.samples_available}</span>
          </div>
        </div>
      ) : null}

      {metrics && metrics.auc_roc != null && (
        <div className="border border-gray-100 rounded-md p-3 space-y-1.5 bg-gray-50">
          <MetricsRow
            label="AUC-ROC"
            value={metrics.auc_roc.toFixed(3)}
            note="random=0.50, perfect=1.00"
          />
          {metrics.precision_at_60 != null && (
            <MetricsRow
              label="Precision @60%"
              value={`${(metrics.precision_at_60 * 100).toFixed(1)}%`}
              note="win rate on high-conf calls"
            />
          )}
          {metrics.high_conf_signals != null && (
            <MetricsRow
              label="High-conf signals"
              value={String(metrics.high_conf_signals)}
              note="predicted ≥60% in cal set"
            />
          )}
          {metrics.class_balance != null && (
            <MetricsRow
              label="Class balance"
              value={`${(metrics.class_balance * 100).toFixed(1)}%`}
              note="profitable in training data"
            />
          )}
        </div>
      )}

      {trainResult && (
        <div
          className={`text-sm rounded px-3 py-2 ${
            trainResult.status === 'ok'
              ? 'bg-green-50 text-green-800'
              : 'bg-yellow-50 text-yellow-800'
          }`}
        >
          {trainResult.message}
        </div>
      )}

      {error && (
        <div className="text-sm rounded px-3 py-2 bg-red-50 text-red-700">
          {(error as Error).message}
        </div>
      )}

      <button
        onClick={() => train()}
        disabled={isPending}
        className="mt-auto bg-blue-600 hover:bg-blue-700 disabled:bg-blue-300 text-white text-sm font-medium px-4 py-2 rounded transition-colors"
      >
        {isPending ? 'Training…' : 'Train Model'}
      </button>

      <p className="text-xs text-gray-400">
        Recommendations automatically use this model once trained.
      </p>
    </div>
  )
}

export function MLModelsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">ML Models</h1>
        <p className="text-gray-500 mt-1">
          Train models on historical trade outcomes to improve recommendation scoring.
        </p>
      </div>

      <div className="flex gap-6 flex-col sm:flex-row">
        <ModelCard
          title="Normal Strategies Model"
          description="Trained on signal_outcomes — predicts win probability for regular strategy signals."
          queryKey="normal-ml-status"
          fetchStatus={getNormalMLStatus}
          triggerTrain={trainNormalModel}
        />
        <ModelCard
          title="Special Strategies Model"
          description="Trained on special_backtest_trades — predicts win probability for special strategy signals."
          queryKey="special-ml-status"
          fetchStatus={getSpecialMLStatus}
          triggerTrain={trainSpecialModel}
        />
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Type-check**

```bash
cd C:/DLP_Repos/MyRepo/StockV2/frontend
npx tsc --noEmit 2>&1 | head -20
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
cd C:/DLP_Repos/MyRepo/StockV2
git add frontend/src/pages/MLModelsPage.tsx
git commit -m "feat: show AUC-ROC and Precision@60% metrics on ML Models page"
```

---

## Self-Review

**Spec coverage:**
- ✅ 8 features for normal (confidence_score, regime_code, strategy_id, month, day_of_week, strategy_win_rate, log_total_trades, strategy_recent_win_rate) → Task 1 `_extract_features`
- ✅ 7 features for special (strategy_id, entry_month, entry_dow, regime_code, strategy_avg_win_rate, strategy_profit_factor, strategy_avg_pnl_pct) → Task 2 `_extract_features`
- ✅ RandomForestClassifier + CalibratedClassifierCV → Tasks 1 & 2 `train()`
- ✅ 80/20 stratified split → Tasks 1 & 2 `train_test_split(..., stratify=y)`
- ✅ AUC-ROC, precision_at_60, class_balance metrics → Tasks 1 & 2
- ✅ JSON sidecar files → Tasks 1 & 2 (`METRICS_PATH`)
- ✅ `train()` returns dict → Tasks 1 & 2
- ✅ `predict()` auto-computes strategy stats via `db` param → Task 1
- ✅ Status endpoints include metrics → Tasks 3 & 4
- ✅ Train endpoints return full metrics → Tasks 3 & 4
- ✅ Frontend types updated → Task 5
- ✅ UI metrics rows displayed → Task 6

**No placeholders found.**

**Type consistency:**
- `metrics.get("auc_roc")` in router → matches key written in `train()` → consistent
- `features.get("strategy_avg_win_rate", 0.5)` in `SpecialMLScorer.predict()` → same key passed from `_enrich_with_performance()` → consistent
- `MLModelStatus.auc_roc: number | null` → backend returns `metrics.get("auc_roc")` which is `None` when no sidecar → consistent
- `p[3]` = win_rate, `p[7]` = profit_factor, `p[9]` = avg_pnl_pct in perf_map → matches the SELECT column order in `_enrich_with_performance()` SQL → verified consistent
