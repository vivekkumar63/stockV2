# ML Model Upgrade — Design Spec

**Date:** 2026-09-01

## Goal

Upgrade both ML scorers (normal strategies + special strategies) to produce well-calibrated win-probability scores that are actually trustworthy for trading decisions. Replace sparse temporal features with strategy-performance features. Switch from GBC to a calibrated Random Forest. Report evaluation metrics after training so the user knows how much to trust the model.

---

## Section 1 — Better Features

### Normal Strategies (`MLSignalScorer`)

Current features (5): `confidence_score`, `regime_code`, `strategy_id`, `month`, `day_of_week`

New features added (3):

| Feature | Source | Why |
|---------|--------|-----|
| `strategy_win_rate` | Window function over `signal_outcomes` partitioned by `strategy_id` | Overall historical hit rate of this strategy |
| `log_total_trades` | `log1p(COUNT(*) OVER PARTITION BY strategy_id)` | Log-scaled reliability proxy — more data = more trustworthy win rate |
| `strategy_recent_win_rate` | Window: last 20 signals before current, partitioned by strategy | Captures whether strategy is currently in a hot or cold streak |

SQL (PostgreSQL window functions, no new tables):
```sql
SELECT
    ss.confidence_score,
    mr.regime,
    ss.strategy_id,
    so.signal_date,
    so.is_profitable,
    AVG(so.is_profitable::float) OVER (PARTITION BY ss.strategy_id) AS strategy_win_rate,
    COUNT(*) OVER (PARTITION BY ss.strategy_id) AS strategy_total_trades,
    AVG(so.is_profitable::float) OVER (
        PARTITION BY ss.strategy_id
        ORDER BY so.signal_date
        ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING
    ) AS strategy_recent_win_rate
FROM signal_outcomes so
JOIN strategy_signals ss ON ss.id = so.signal_id
LEFT JOIN market_regime mr ON mr.date = so.signal_date
WHERE so.is_profitable IS NOT NULL
```

`strategy_recent_win_rate` is NULL for the first signal of each strategy — fill with `strategy_win_rate` as fallback.

---

### Special Strategies (`SpecialMLScorer`)

Current features (4): `strategy_id`, `entry_month`, `entry_dow`, `regime_code`

New features added (3), all from `special_strategy_performance` (already precomputed):

| Feature | Source | Why |
|---------|--------|-----|
| `strategy_avg_win_rate` | `AVG(win_rate)` per strategy_id | Best predictor of future profitability |
| `strategy_profit_factor` | `AVG(profit_factor)` per strategy_id | Sum of wins / sum of losses — quality of winning trades |
| `strategy_avg_pnl_pct` | `AVG(avg_pnl_pct)` per strategy_id | Average return per trade |

SQL:
```sql
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
    COALESCE(ss.avg_win_rate, 0.5)       AS strategy_avg_win_rate,
    COALESCE(ss.avg_profit_factor, 1.0)  AS strategy_profit_factor,
    COALESCE(ss.avg_pnl_pct_stat, 0.0)   AS strategy_avg_pnl_pct
FROM special_backtest_trades sbt
JOIN special_backtest_results sbr ON sbr.id = sbt.backtest_result_id
LEFT JOIN market_regime mr ON mr.date = sbt.entry_date
LEFT JOIN strategy_stats ss ON ss.special_strategy_id = sbr.special_strategy_id
WHERE sbt.entry_date IS NOT NULL AND sbt.pnl IS NOT NULL
```

---

## Section 2 — Better Model: Calibrated Random Forest

**Problem with current GBC:** Probabilities are overconfident. A GBC score of 0.8 may correspond to only ~0.55 actual win rate. For trading, uncalibrated probabilities are misleading.

**New model stack (same for both scorers):**

```python
from sklearn.ensemble import RandomForestClassifier
from sklearn.calibration import CalibratedClassifierCV

base = RandomForestClassifier(
    n_estimators=300,
    max_depth=8,
    min_samples_leaf=5,
    class_weight='balanced',   # handles imbalanced win/loss ratio
    random_state=42,
    n_jobs=-1,
)
# 80/20 stratified split: train base on 80%, calibrate on 20%
# CalibratedClassifierCV(cv='prefit', method='sigmoid') maps raw probabilities
# to empirical win rates on the held-out calibration set.
model = CalibratedClassifierCV(base, cv='prefit', method='sigmoid')
```

**Training procedure:**

1. `train_test_split(X, y, test_size=0.2, stratify=y, random_state=42)` — ensures both splits have same class balance
2. `base.fit(X_train, y_train)`
3. Compute evaluation metrics on `X_cal, y_cal` (see Section 3)
4. `model = CalibratedClassifierCV(base, cv='prefit', method='sigmoid'); model.fit(X_cal, y_cal)` — fits calibration layer
5. Pickle `model` (the calibrated wrapper) to `.pkl`
6. Write metrics to sidecar `.json`

After calibration: `model.predict_proba(X)[:, 1]` returns genuinely calibrated win probabilities. A score of 0.70 means ~70% of signals at that confidence level historically won.

---

## Section 3 — Evaluation Metrics

Computed on the 20% held-out calibration split before calibration fitting:

| Metric | Description | Good value |
|--------|-------------|------------|
| `auc_roc` | Area under ROC curve | > 0.60 meaningful, > 0.70 strong |
| `precision_at_60` | Win rate of signals where model predicts ≥ 0.60 | > 0.65 useful for trading |
| `high_conf_signals` | Count of signals in calibration set with prob ≥ 0.60 | Tells you how selective the model is |
| `class_balance` | Fraction of training samples that were profitable | Context for interpreting precision |

Metrics saved to JSON sidecar files:
- `ml_models/signal_scorer_metrics.json`
- `ml_models/special_signal_scorer_metrics.json`

Format:
```json
{
  "auc_roc": 0.68,
  "precision_at_60": 0.74,
  "high_conf_signals": 23,
  "class_balance": 0.42,
  "samples": 312,
  "trained_at": "2026-09-01T10:22:00"
}
```

---

## Section 4 — API Changes

### `train()` return type change

Both scorers' `train()` method now returns a `dict` instead of `int`:

```python
# Success
{"samples": 312, "auc_roc": 0.68, "precision_at_60": 0.74,
 "high_conf_signals": 23, "class_balance": 0.42}

# Skipped (insufficient data)
{"samples": 0}
```

### `GET /intelligence/ml-status` and `GET /special/ml-status`

Now include metrics if the sidecar JSON exists:

```json
{
  "exists": true,
  "last_trained": "2026-09-01T10:22:00",
  "samples_available": 312,
  "auc_roc": 0.68,
  "precision_at_60": 0.74,
  "high_conf_signals": 23,
  "class_balance": 0.42
}
```

### `POST /intelligence/train` and `POST /special/ml/train`

Now return full metrics in the response body (same fields as `train()` return + `status` + `message`).

---

## Section 5 — UI Changes

### `frontend/src/api/ml.ts`

```typescript
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
```

### `frontend/src/pages/MLModelsPage.tsx`

Model card gains a metrics section (shown when model is trained):

```
● Trained  |  Last trained: 01 Sep 2026 10:22

AUC-ROC:         0.68    (random = 0.50)
Precision @60%:  74%     (high-confidence win rate)
Class balance:   42%     profitable in training data

[ Train Model ]
```

---

## Files Changed

| File | Action |
|------|--------|
| `backend/domains/intelligence/ml_scorer.py` | REWRITE — new features, RF+calibration, metrics, JSON sidecar |
| `backend/domains/special_strategies/ml_scorer.py` | REWRITE — new features, RF+calibration, metrics, JSON sidecar |
| `backend/domains/intelligence/router.py` | MODIFY — ml-status reads sidecar, train returns metrics |
| `backend/domains/special_strategies/router.py` | MODIFY — same |
| `frontend/src/api/ml.ts` | MODIFY — add metric fields to interfaces |
| `frontend/src/pages/MLModelsPage.tsx` | MODIFY — show metrics section on cards |

---

## Verification

1. `POST /api/v1/intelligence/train` → response includes `auc_roc`, `precision_at_60`
2. `GET /api/v1/intelligence/ml-status` → same metrics reflected
3. Call `scorer.predict({"confidence_score": 0.8, "regime_code": 4, "strategy_id": 1, "month": 6, "day_of_week": 2, "strategy_win_rate": 0.6, "log_total_trades": 3.4, "strategy_recent_win_rate": 0.65})` → returns float in [0,1]
4. Two calls with identical inputs return identical output (model cached in-process)
5. UI: model card shows metrics row after training
