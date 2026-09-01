# ML Training UI — Design Spec

**Date:** 2026-09-01

## Overview

A dedicated "ML Models" page that lets users train and monitor two independent ML models:
one for normal strategy signals and one for special strategy signals. After training,
both recommendations flows automatically use the trained model — no extra steps required.

---

## Backend: Normal Strategies ML

### Existing code
`MLSignalScorer` in `backend/domains/intelligence/ml_scorer.py` already implements:
- `train(db) -> int` — trains GradientBoostingClassifier on `signal_outcomes`, saves to `ml_models/signal_scorer.pkl`
- `predict(features) -> float | None` — returns win-probability in [0,1], already called inside `opportunity_scorer.py`

No changes needed to `opportunity_scorer.py`. Once the pkl exists, the score flows automatically into `top-opportunities` and `opportunity-score` responses.

### New endpoints in `backend/domains/intelligence/router.py`

| Method | Path | Description |
|--------|------|-------------|
| GET | `/intelligence/ml-status` | Returns model existence, last-trained timestamp (file mtime), and available sample count from `signal_outcomes` |
| POST | `/intelligence/train` | Calls `MLSignalScorer().train(db)`, returns `{ status, samples, message }`. Returns `status: "skipped"` if fewer than 50 samples. |

### Status response shape
```json
{
  "exists": true,
  "last_trained": "2026-09-01T10:22:00",
  "samples_available": 312
}
```

### Train response shape
```json
{ "status": "ok", "samples": 312, "message": "Trained on 312 samples" }
```

---

## Backend: Special Strategies ML

### New file: `backend/domains/special_strategies/ml_scorer.py`

Class `SpecialMLScorer`, same pattern as `MLSignalScorer`:

**Training data:** `special_backtest_trades` (one row per trade), joined with:
- `special_backtest_results` → `special_strategy_id`
- `market_regime` on `entry_date` → regime label

**Features:**
| Feature | Source |
|---------|--------|
| `strategy_id` | `special_backtest_results.special_strategy_id` |
| `entry_month` | month of `entry_date` |
| `entry_dow` | weekday of `entry_date` |
| `regime_code` | mapped from `market_regime.regime` (STRONG_BULL=5 … HIGH_VOLATILITY=0) |

**Label:** `pnl > 0` → 1 (profitable), else 0

**Model:** `GradientBoostingClassifier(n_estimators=100, max_depth=3, learning_rate=0.1)`

**Saved to:** `ml_models/special_signal_scorer.pkl`

**Min samples:** 50 (same as normal)

**Module-level cache:** same `_LOAD_FAILED` sentinel pattern as normal scorer — load attempted once per process.

### New endpoints in `backend/domains/special_strategies/router.py`

| Method | Path | Description |
|--------|------|-------------|
| GET | `/special/ml-status` | Model existence, last-trained timestamp, available sample count from `special_backtest_trades` |
| POST | `/special/ml/train` | Calls `SpecialMLScorer().train(db)`, same response shape as normal |

### Integration into recommendations

`_enrich_with_performance()` in `router.py` updated to call `SpecialMLScorer().predict()` for each result and attach `ml_probability: float | None`. If model doesn't exist, field is `null` — additive, no breaking change.

---

## Frontend

### New page: `frontend/src/pages/MLModelsPage.tsx`

Two model cards rendered side by side (stacked on mobile):

```
┌─────────────────────────────┐  ┌─────────────────────────────┐
│  Normal Strategies Model    │  │  Special Strategies Model   │
│                             │  │                             │
│  Status:  ● Not Trained     │  │  Status:  ● Not Trained     │
│  Last trained:  —           │  │  Last trained:  —           │
│  Samples available:  312    │  │  Samples available:  87     │
│                             │  │                             │
│  [  Train Model  ]          │  │  [  Train Model  ]          │
│                             │  │                             │
│  Recommendations auto-use   │  │  Recommendations auto-use   │
│  this model once trained.   │  │  this model once trained.   │
└─────────────────────────────┘  └─────────────────────────────┘
```

**Status dot:** gray = not trained / no pkl, green = trained (pkl exists)

**Train button behaviour:**
- Shows spinner while POST is in flight
- On success: refreshes status card (new timestamp + sample count), shows inline success message
- On failure (< 50 samples, or server error): shows inline error string

### New API file: `frontend/src/api/ml.ts`

```typescript
export interface MLModelStatus {
  exists: boolean
  last_trained: string | null
  samples_available: number
}

export interface MLTrainResult {
  status: "ok" | "skipped"
  samples: number
  message: string
}

export const getNormalMLStatus = () => apiFetch<MLModelStatus>('/intelligence/ml-status')
export const trainNormalModel  = () => apiFetch<MLTrainResult>('/intelligence/train', { method: 'POST' })

export const getSpecialMLStatus = () => apiFetch<MLModelStatus>('/special/ml-status')
export const trainSpecialModel  = () => apiFetch<MLTrainResult>('/special/ml/train', { method: 'POST' })
```

### Navigation + routing

- `frontend/src/components/NavBar.tsx` — add `ML Models` link
- `frontend/src/App.tsx` — add route `/ml-models → <MLModelsPage />`

---

## Files Changed / Created

| File | Action |
|------|--------|
| `backend/domains/intelligence/router.py` | ADD 2 endpoints: `GET /intelligence/ml-status`, `POST /intelligence/train` |
| `backend/domains/special_strategies/ml_scorer.py` | NEW — `SpecialMLScorer` with `train()`, `predict()`, module-level cache |
| `backend/domains/special_strategies/router.py` | ADD 2 endpoints + update `_enrich_with_performance()` |
| `frontend/src/api/ml.ts` | NEW — 4 API functions |
| `frontend/src/pages/MLModelsPage.tsx` | NEW — two-card ML management page |
| `frontend/src/components/NavBar.tsx` | ADD nav link |
| `frontend/src/App.tsx` | ADD route |

---

## Verification

1. `GET /api/v1/intelligence/ml-status` → `{ exists: false, last_trained: null, samples_available: N }`
2. `POST /api/v1/intelligence/train` with ≥50 samples → `{ status: "ok", samples: N }`; pkl file appears at `ml_models/signal_scorer.pkl`
3. `GET /api/v1/intelligence/top-opportunities` → `ml_probability` field populated (not null) on results
4. `POST /api/v1/special/ml/train` → pkl at `ml_models/special_signal_scorer.pkl`
5. `GET /api/v1/special/recommendations` → `ml_probability` field populated
6. UI: `/ml-models` page loads, both cards show status, Train buttons work end-to-end
