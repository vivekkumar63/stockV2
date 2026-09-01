# ML Training UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A dedicated "ML Models" page where users can train and monitor two independent ML models (normal strategies + special strategies), with recommendations automatically using the trained model scores.

**Architecture:** `SpecialMLScorer` mirrors the existing `MLSignalScorer` pattern — same GBC model, same module-level cache sentinel, different feature set (strategy_id, entry_month, entry_dow, regime_code) trained on `special_backtest_trades`. Two new endpoints per model (status + train). A single new frontend page renders two cards.

**Tech Stack:** Python, FastAPI, scikit-learn, SQLAlchemy, React, TypeScript, TanStack Query, Tailwind CSS

---

## File Map

| File | Action |
|------|--------|
| `backend/domains/special_strategies/ml_scorer.py` | CREATE — SpecialMLScorer class |
| `backend/tests/test_special_ml_scorer.py` | CREATE — unit tests |
| `backend/domains/intelligence/router.py` | MODIFY — add 2 endpoints + import os |
| `backend/domains/special_strategies/router.py` | MODIFY — add 2 endpoints + update _enrich_with_performance |
| `frontend/src/api/ml.ts` | CREATE — 4 API functions |
| `frontend/src/api/special.ts` | MODIFY — add ml_probability to SpecialRecommendation |
| `frontend/src/pages/MLModelsPage.tsx` | CREATE — two-card page |
| `frontend/src/components/NavBar.tsx` | MODIFY — add nav link |
| `frontend/src/App.tsx` | MODIFY — add route |

---

## Task 1: SpecialMLScorer

**Files:**
- Create: `backend/domains/special_strategies/ml_scorer.py`
- Create: `backend/tests/test_special_ml_scorer.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_special_ml_scorer.py`:

```python
import pytest
from unittest.mock import MagicMock, patch
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
        m._cached_model = None   # reset cache
        scorer = SpecialMLScorer()
        result = scorer.predict({
            "strategy_id": 1, "entry_month": 6,
            "entry_dow": 2, "regime_code": 4,
        })
        assert result is None


def test_train_returns_zero_when_insufficient_samples():
    db = MagicMock()
    db.execute.return_value.fetchall.return_value = []   # no rows
    scorer = SpecialMLScorer()
    n = scorer.train(db)
    assert n == 0


def test_train_returns_zero_when_single_class(tmp_path):
    """If all trades are profitable (or all unprofitable), training is skipped."""
    import numpy as np
    from datetime import date
    db = MagicMock()
    # 60 rows, all profitable (pnl > 0)
    fake_rows = [(1, date(2023, i % 12 + 1, 1), "BULL", 500.0) for i in range(60)]
    db.execute.return_value.fetchall.return_value = fake_rows

    with patch("domains.special_strategies.ml_scorer.MODEL_PATH", str(tmp_path / "model.pkl")):
        import domains.special_strategies.ml_scorer as m
        m._cached_model = None
        scorer = SpecialMLScorer()
        n = scorer.train(db)
        assert n == 0   # skipped — only one class
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd C:/DLP_Repos/MyRepo/StockV2/backend
python -m pytest tests/test_special_ml_scorer.py -v 2>&1 | head -30
```

Expected: `ImportError` or `ModuleNotFoundError` — file doesn't exist yet.

- [ ] **Step 3: Create `backend/domains/special_strategies/ml_scorer.py`**

```python
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
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd C:/DLP_Repos/MyRepo/StockV2/backend
python -m pytest tests/test_special_ml_scorer.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd C:/DLP_Repos/MyRepo/StockV2
git add backend/domains/special_strategies/ml_scorer.py backend/tests/test_special_ml_scorer.py
git commit -m "feat: add SpecialMLScorer trained on special_backtest_trades"
```

---

## Task 2: Normal ML endpoints in intelligence router

**Files:**
- Modify: `backend/domains/intelligence/router.py`

- [ ] **Step 1: Add `import os` and update ml_scorer import**

In `backend/domains/intelligence/router.py`, change line 3 (the `import logging` block) to add `import os` and extend the ml_scorer import to include `MODEL_PATH` and `MIN_TRAINING_SAMPLES`:

Find:
```python
import logging
from datetime import date
from typing import Optional
```
Replace with:
```python
import logging
import os
from datetime import date, datetime
from typing import Optional
```

Find:
```python
from domains.intelligence.ml_scorer import MLSignalScorer, regime_to_code
```
Replace with:
```python
from domains.intelligence.ml_scorer import (
    MLSignalScorer, regime_to_code,
    MODEL_PATH as NORMAL_ML_MODEL_PATH,
    MIN_TRAINING_SAMPLES as NORMAL_ML_MIN_SAMPLES,
)
```

- [ ] **Step 2: Add the two new endpoints**

Append to the end of `backend/domains/intelligence/router.py`:

```python

# ── ML Model management ───────────────────────────────────────────────────────

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

- [ ] **Step 3: Verify the backend starts without errors**

```bash
cd C:/DLP_Repos/MyRepo/StockV2/backend
python -c "from domains.intelligence.router import router; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
cd C:/DLP_Repos/MyRepo/StockV2
git add backend/domains/intelligence/router.py
git commit -m "feat: add GET /intelligence/ml-status and POST /intelligence/train endpoints"
```

---

## Task 3: Special ML endpoints + enrich update

**Files:**
- Modify: `backend/domains/special_strategies/router.py`

- [ ] **Step 1: Add imports to special router**

In `backend/domains/special_strategies/router.py`, find the existing imports block at the top:

```python
import json
import logging
import threading
from datetime import date
from typing import Optional
```

Replace with:

```python
import json
import logging
import os
import threading
from datetime import date, datetime
from typing import Optional
```

Find:
```python
from domains.special_strategies.scanner import SpecialScanner
from domains.special_strategies.simulator import SpecialSimulator
```

Replace with:

```python
from domains.special_strategies.ml_scorer import (
    SpecialMLScorer, special_regime_to_code,
    MODEL_PATH as SPECIAL_ML_MODEL_PATH,
    MIN_TRAINING_SAMPLES as SPECIAL_ML_MIN_SAMPLES,
)
from domains.special_strategies.scanner import SpecialScanner
from domains.special_strategies.simulator import SpecialSimulator
```

- [ ] **Step 2: Update `_enrich_with_performance()` to attach `ml_probability`**

Find the function `_enrich_with_performance` in `backend/domains/special_strategies/router.py`. It currently ends with:

```python
    result.sort(key=lambda r: (r["win_rate"] or 0, r["confidence"]), reverse=True)
    return result
```

Replace the entire function body (everything from `def _enrich_with_performance` to the closing `return result`) with:

```python
def _enrich_with_performance(signals: list[dict], db: Session) -> list[dict]:
    """Join scan signals with precomputed performance metrics and ML probability."""
    if not signals:
        return []
    strategy_ids = list({s["strategy_id"] for s in signals if s["strategy_id"] is not None})
    perf_rows = db.execute(
        text("""
            SELECT symbol, special_strategy_id, total_trades, win_rate, cagr,
                   sharpe_ratio, max_drawdown, profit_factor, total_pnl, avg_pnl_pct
            FROM special_strategy_performance
            WHERE special_strategy_id = ANY(:sids)
        """),
        {"sids": strategy_ids},
    ).fetchall()
    perf_map: dict[tuple, tuple] = {(r[0], r[1]): r for r in perf_rows}

    regime_row = db.execute(
        text("SELECT regime FROM market_regime ORDER BY date DESC LIMIT 1")
    ).fetchone()
    regime_code = special_regime_to_code(regime_row[0]) if regime_row else 3

    scorer = SpecialMLScorer()
    today = date.today()

    result = []
    for s in signals:
        p = perf_map.get((s["symbol"], s["strategy_id"]))
        ml_prob = None
        if s["strategy_id"] is not None:
            ml_prob = scorer.predict({
                "strategy_id": s["strategy_id"],
                "entry_month": today.month,
                "entry_dow": today.weekday(),
                "regime_code": regime_code,
            })
        result.append({
            **s,
            "total_trades":   p[2] if p else None,
            "win_rate":       p[3] if p else None,
            "cagr":           p[4] if p else None,
            "sharpe_ratio":   p[5] if p else None,
            "max_drawdown":   p[6] if p else None,
            "profit_factor":  p[7] if p else None,
            "total_pnl":      p[8] if p else None,
            "avg_pnl_pct":    p[9] if p else None,
            "ml_probability": ml_prob,
        })
    result.sort(key=lambda r: (r["win_rate"] or 0, r["confidence"]), reverse=True)
    return result
```

- [ ] **Step 3: Add the two new endpoints**

Append to the end of `backend/domains/special_strategies/router.py`:

```python

# ── ML Model management ───────────────────────────────────────────────────────

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

- [ ] **Step 4: Verify the special router imports cleanly**

```bash
cd C:/DLP_Repos/MyRepo/StockV2/backend
python -c "from domains.special_strategies.router import router; print('OK')"
```

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
cd C:/DLP_Repos/MyRepo/StockV2
git add backend/domains/special_strategies/router.py
git commit -m "feat: add special ML endpoints and ml_probability to recommendations"
```

---

## Task 4: Frontend API module

**Files:**
- Create: `frontend/src/api/ml.ts`
- Modify: `frontend/src/api/special.ts`

- [ ] **Step 1: Create `frontend/src/api/ml.ts`**

```typescript
import { apiFetch } from './client'

export interface MLModelStatus {
  exists: boolean
  last_trained: string | null
  samples_available: number
}

export interface MLTrainResult {
  status: 'ok' | 'skipped'
  samples: number
  message: string
}

export const getNormalMLStatus  = () => apiFetch<MLModelStatus>('/intelligence/ml-status')
export const trainNormalModel   = () => apiFetch<MLTrainResult>('/intelligence/train', { method: 'POST' })

export const getSpecialMLStatus = () => apiFetch<MLModelStatus>('/special/ml-status')
export const trainSpecialModel  = () => apiFetch<MLTrainResult>('/special/ml/train', { method: 'POST' })
```

- [ ] **Step 2: Add `ml_probability` to `SpecialRecommendation` in `frontend/src/api/special.ts`**

Find:
```typescript
export interface SpecialRecommendation extends SpecialScanResult {
  total_trades: number | null
  win_rate: number | null
  cagr: number | null
  sharpe_ratio: number | null
  max_drawdown: number | null
  profit_factor: number | null
  total_pnl: number | null
  avg_pnl_pct: number | null
}
```

Replace with:
```typescript
export interface SpecialRecommendation extends SpecialScanResult {
  total_trades: number | null
  win_rate: number | null
  cagr: number | null
  sharpe_ratio: number | null
  max_drawdown: number | null
  profit_factor: number | null
  total_pnl: number | null
  avg_pnl_pct: number | null
  ml_probability: number | null
}
```

- [ ] **Step 3: Commit**

```bash
cd C:/DLP_Repos/MyRepo/StockV2
git add frontend/src/api/ml.ts frontend/src/api/special.ts
git commit -m "feat: add ML API functions and ml_probability to SpecialRecommendation type"
```

---

## Task 5: MLModelsPage

**Files:**
- Create: `frontend/src/pages/MLModelsPage.tsx`

- [ ] **Step 1: Create the page**

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

  return (
    <div className="bg-white rounded-lg shadow p-6 flex flex-col gap-4 flex-1">
      <div>
        <h2 className="text-lg font-semibold text-gray-800">{title}</h2>
        <p className="text-sm text-gray-500 mt-1">{description}</p>
      </div>

      {statusLoading ? (
        <p className="text-sm text-gray-400">Loading status…</p>
      ) : status ? (
        <div className="space-y-2 text-sm">
          <div className="flex items-center gap-2">
            <span
              className={`w-2.5 h-2.5 rounded-full ${status.exists ? 'bg-green-500' : 'bg-gray-400'}`}
            />
            <span className={status.exists ? 'text-green-700 font-medium' : 'text-gray-500'}>
              {status.exists ? 'Trained' : 'Not Trained'}
            </span>
          </div>
          <div className="text-gray-600">
            Last trained:{' '}
            <span className="font-mono text-gray-800">
              {status.last_trained
                ? new Date(status.last_trained).toLocaleString()
                : '—'}
            </span>
          </div>
          <div className="text-gray-600">
            Samples available:{' '}
            <span className="font-mono text-gray-800">{status.samples_available}</span>
          </div>
        </div>
      ) : null}

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

- [ ] **Step 2: Commit**

```bash
cd C:/DLP_Repos/MyRepo/StockV2
git add frontend/src/pages/MLModelsPage.tsx
git commit -m "feat: add MLModelsPage with two model cards"
```

---

## Task 6: Wire up navigation and routing

**Files:**
- Modify: `frontend/src/components/NavBar.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Add nav link to NavBar**

In `frontend/src/components/NavBar.tsx`, find:
```tsx
      <NavLink to="/sector-rotation" className={link}>Sectors</NavLink>
```
Replace with:
```tsx
      <NavLink to="/sector-rotation" className={link}>Sectors</NavLink>
      <NavLink to="/ml-models" className={link}>ML Models</NavLink>
```

- [ ] **Step 2: Add import and route to App.tsx**

In `frontend/src/App.tsx`, find:
```tsx
import { SectorRotationPage } from './pages/SectorRotationPage'
```
Replace with:
```tsx
import { SectorRotationPage } from './pages/SectorRotationPage'
import { MLModelsPage } from './pages/MLModelsPage'
```

Find:
```tsx
              <Route path="/sector-rotation" element={<SectorRotationPage />} />
```
Replace with:
```tsx
              <Route path="/sector-rotation" element={<SectorRotationPage />} />
              <Route path="/ml-models" element={<MLModelsPage />} />
```

- [ ] **Step 3: Verify TypeScript compiles**

```bash
cd C:/DLP_Repos/MyRepo/StockV2/frontend
npx tsc --noEmit 2>&1 | head -30
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
cd C:/DLP_Repos/MyRepo/StockV2
git add frontend/src/components/NavBar.tsx frontend/src/App.tsx
git commit -m "feat: add ML Models nav link and route"
```

---

## Self-Review

**Spec coverage:**
- ✅ Normal strategies: `GET /intelligence/ml-status` + `POST /intelligence/train` → Task 2
- ✅ Special strategies: `SpecialMLScorer` → Task 1; `GET /special/ml-status` + `POST /special/ml/train` → Task 3
- ✅ Recommendations auto-use model: `_enrich_with_performance` updated → Task 3
- ✅ Frontend two-card page → Task 5
- ✅ Nav + route → Task 6
- ✅ `ml_probability` field on `SpecialRecommendation` → Task 4

**No placeholders found.**

**Type consistency:**
- `MLModelStatus`, `MLTrainResult` defined in Task 4, used in Task 5 — consistent
- `SpecialMLScorer.predict()` expects `{strategy_id, entry_month, entry_dow, regime_code}` — same dict used in `_enrich_with_performance` → Task 3
- `special_regime_to_code` exported from `ml_scorer.py` → Task 1, imported in router → Task 3
- `MODEL_PATH`, `MIN_TRAINING_SAMPLES` exported from both scorer files, imported in routers — consistent
