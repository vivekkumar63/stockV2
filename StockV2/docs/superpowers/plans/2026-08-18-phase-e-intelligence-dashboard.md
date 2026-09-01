# Phase E: Intelligence Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose all Phase C/D intelligence features inside the existing Dashboard — market regime banner, enriched signals table ranked by opportunity score with MTF/ML columns, score breakdown on expand, and a collapsible Strategy Intelligence panel (strategy ranking, false signal rates, correlations).

**Architecture:** One new backend endpoint (`GET /intelligence/top-opportunities`) fetches today's BUY signals and computes full opportunity scores. Three new frontend components (`RegimeBanner`, `TopOpportunities`, `StrategyIntelligence`) replace/augment the existing Dashboard page sections. Strategy Intelligence data is lazy-loaded on first expand.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy (backend); React 18, TanStack Query v5, Tailwind CSS (frontend)

---

## File Map

```
backend/
├── domains/intelligence/router.py       MODIFY — add GET /intelligence/top-opportunities
└── tests/test_top_opportunities.py      CREATE — 3 endpoint tests

frontend/src/
├── api/intelligence.ts                  CREATE — types + fetch functions
├── components/RegimeBanner.tsx          CREATE — compact regime badge widget
├── components/TopOpportunities.tsx      CREATE — enriched table + score breakdown
├── components/StrategyIntelligence.tsx  CREATE — collapsible 3-panel intelligence section
└── pages/DashboardPage.tsx              MODIFY — wire up new components, replace old signals section
```

---

### Task 1: Backend — `GET /intelligence/top-opportunities` endpoint

**Files:**
- Modify: `backend/domains/intelligence/router.py`

**Context:**
The existing router already imports all required engines. The endpoint fetches today's BUY signals from `strategy_signals`, computes full opportunity scores per signal (using `OpportunityScorer.full_score()` with all 8 components), and returns sorted by score descending.

Existing imports already present in `router.py`:
```python
from domains.intelligence.false_signal_detector import FalseSignalDetector
from domains.intelligence.ml_scorer import MLSignalScorer, regime_to_code
from domains.intelligence.opportunity_scorer import OpportunityScorer
from domains.intelligence.regime_performance import RegimePerformanceEngine
from domains.market.multi_timeframe import MultiTimeframeEngine
from domains.market.regime import MarketRegimeEngine
from domains.market.support_resistance import SupportResistanceEngine
```

Helper functions `_compute_volume_score(db, symbol)` and `_compute_sr_score(sr)` already exist in `router.py`.

- [ ] **Step 1: Add the new endpoint to `backend/domains/intelligence/router.py`**

Add this block after the existing `get_opportunity_score` endpoint (around line 136, before the `# ── Regime backfill trigger` comment):

```python
# ── Top opportunities (bulk scored today's BUY signals) ──────────────────────

@router.get("/intelligence/top-opportunities")
def get_top_opportunities(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """
    Today's BUY signals enriched with full opportunity scores, sorted by score descending.
    Computes MTF alignment, volume, S/R, ML probability, and false signal rate for each.
    """
    from ist import ist_today
    today = ist_today()

    rows = db.execute(
        text("""
            SELECT ss.id, ss.symbol, ss.strategy_id, s.name AS strategy_name,
                   ss.signal_date, ss.confidence_score, ss.price_at_signal,
                   ss.stop_loss_pct, ss.target_pct, ss.holding_days,
                   ss.reasoning_json
            FROM strategy_signals ss
            JOIN strategies s ON s.id = ss.strategy_id
            WHERE ss.signal_date = :today AND ss.signal_type = 'BUY'
            ORDER BY ss.confidence_score DESC
        """),
        {"today": str(today)},
    ).fetchall()

    if not rows:
        return []

    # Get regime once — reused for all signals
    regime_result = MarketRegimeEngine().get_or_compute(db)
    regime = regime_result.regime

    # Bulk-fetch historical win rates
    symbols = list({r[1] for r in rows})
    strategy_ids = list({r[2] for r in rows})
    hist_wr_map: dict[tuple, Optional[float]] = {}
    if symbols and strategy_ids:
        from sqlalchemy import bindparam
        hist_rows = db.execute(
            text("""
                SELECT symbol, strategy_id, win_rate FROM scan_result_cache
                WHERE symbol IN :syms AND strategy_id IN :sids
                  AND stop_loss_pct = 5.0 AND target_pct = 10.0
                  AND from_date = '2015-01-01'
            """).bindparams(
                bindparam("syms", expanding=True),
                bindparam("sids", expanding=True),
            ),
            {"syms": symbols, "sids": strategy_ids},
        ).fetchall()
        for hr in hist_rows:
            hist_wr_map[(hr[0], hr[1])] = float(hr[2]) if hr[2] is not None else None

    # Regime-strategy performance
    regime_perf = RegimePerformanceEngine().get_for_regime(db, regime)

    # False signal rates — bulk dict {strategy_id: rate}
    false_rates = FalseSignalDetector().get_false_signal_rates(db)

    results = []
    for r in rows:
        (signal_id, symbol, strategy_id, strategy_name,
         signal_date, confidence_score, price_at_signal,
         stop_loss_pct, target_pct, holding_days, reasoning_json) = r

        sl_pct = stop_loss_pct or 7.0
        tgt_pct = target_pct or 15.0
        stop_loss_price = round(price_at_signal * (1 - sl_pct / 100), 2)
        target_price    = round(price_at_signal * (1 + tgt_pct / 100), 2)
        rr = round(
            (target_price - price_at_signal) / (price_at_signal - stop_loss_price), 2
        ) if price_at_signal > stop_loss_price else None

        hist_wr    = hist_wr_map.get((symbol, strategy_id))
        regime_wr  = regime_perf[strategy_id].win_rate if strategy_id in regime_perf else None
        false_rate = false_rates.get(strategy_id)

        mtf_result = MultiTimeframeEngine().compute(db, symbol)
        mtf_score  = mtf_result.alignment_score if mtf_result.daily else None

        vol_score = _compute_volume_score(db, symbol)

        sr_result = SupportResistanceEngine().compute(db, symbol)
        sr_score  = _compute_sr_score(sr_result)

        ml_prob = MLSignalScorer().predict({
            "confidence_score": confidence_score or 0.5,
            "regime_code":      regime_to_code(regime),
            "strategy_id":      strategy_id,
            "month":            today.month,
            "day_of_week":      today.weekday(),
        })

        opp = OpportunityScorer().full_score(
            symbol=symbol,
            strategy_id=strategy_id,
            confidence=confidence_score or 0.5,
            historical_win_rate=hist_wr,
            regime=regime,
            regime_strategy_win_rate=regime_wr,
            mtf_alignment=mtf_score,
            volume_score=vol_score,
            sr_score=sr_score,
            false_signal_rate=false_rate,
            ml_probability=ml_prob,
        )

        results.append({
            "signal_id":        signal_id,
            "symbol":           symbol,
            "strategy_id":      strategy_id,
            "strategy_name":    strategy_name,
            "signal_date":      str(signal_date)[:10],
            "confidence_score": confidence_score,
            "price_at_signal":  price_at_signal,
            "stop_loss_price":  stop_loss_price,
            "target_price":     target_price,
            "stop_loss_pct":    stop_loss_pct,
            "target_pct":       target_pct,
            "holding_days":     holding_days,
            "rr":               rr,
            "reasoning_json":   reasoning_json,
            "score":            opp.score,
            "grade":            opp.grade,
            "regime":           regime,
            "mtf_alignment":    mtf_score,
            "ml_probability":   ml_prob,
            "false_signal_rate": false_rate,
            "breakdown":        opp.breakdown,
        })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:limit]
```

- [ ] **Step 2: Verify backend starts without import errors**

```bash
cd backend && python -c "from domains.intelligence.router import router; print('OK')"
```
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/domains/intelligence/router.py
git commit -m "feat: GET /intelligence/top-opportunities bulk opportunity scorer"
```

---

### Task 2: Backend — Tests for top-opportunities endpoint

**Files:**
- Create: `backend/tests/test_top_opportunities.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_top_opportunities.py`:

```python
"""Tests for GET /intelligence/top-opportunities endpoint."""
import sys, os
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database import Base, get_db
from settings import settings
import models  # noqa — registers all ORM models


@pytest.fixture(scope="module")
def client():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    db = Session()
    today = date.today().isoformat()

    # Insert two strategies
    db.execute(text("""
        INSERT INTO strategies (id, name, type, is_active, created_at)
        VALUES (1, 'StratA', 'technical', 1, CURRENT_TIMESTAMP),
               (2, 'StratB', 'technical', 1, CURRENT_TIMESTAMP)
    """))

    # Insert three BUY signals for today — two unique symbols
    db.execute(text("""
        INSERT INTO strategy_signals
            (symbol, strategy_id, signal_date, signal_type,
             confidence_score, price_at_signal, stop_loss_pct, target_pct,
             holding_days, created_at)
        VALUES
            ('RELIANCE', 1, :today, 'BUY', 0.80, 2400.0, 5.0, 10.0, 15, CURRENT_TIMESTAMP),
            ('TCS',      2, :today, 'BUY', 0.60, 3500.0, 5.0, 10.0, 15, CURRENT_TIMESTAMP),
            ('INFY',     1, :today, 'BUY', 0.70, 1800.0, 5.0, 10.0, 15, CURRENT_TIMESTAMP)
    """), {"today": today})
    db.commit()
    db.close()

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    from main import app
    app.dependency_overrides[get_db] = override
    return TestClient(app, headers={"X-API-Key": settings.api_key})


def test_top_opportunities_returns_list(client):
    r = client.get("/api/v1/intelligence/top-opportunities")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    assert len(body) > 0


def test_top_opportunities_sorted_by_score_descending(client):
    r = client.get("/api/v1/intelligence/top-opportunities")
    assert r.status_code == 200
    body = r.json()
    scores = [item["score"] for item in body]
    assert scores == sorted(scores, reverse=True), "results must be sorted by score descending"


def test_top_opportunities_limit_respected(client):
    r = client.get("/api/v1/intelligence/top-opportunities?limit=2")
    assert r.status_code == 200
    body = r.json()
    assert len(body) <= 2


def test_top_opportunities_empty_when_no_signals():
    """Returns [] when there are no BUY signals today."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    from main import app
    app.dependency_overrides[get_db] = override
    c = TestClient(app, headers={"X-API-Key": settings.api_key})
    r = c.get("/api/v1/intelligence/top-opportunities")
    assert r.status_code == 200
    assert r.json() == []


def test_top_opportunities_response_shape(client):
    """Each item has the required fields."""
    r = client.get("/api/v1/intelligence/top-opportunities?limit=1")
    assert r.status_code == 200
    item = r.json()[0]
    for field in ("signal_id", "symbol", "strategy_id", "strategy_name",
                  "score", "grade", "regime", "breakdown",
                  "stop_loss_price", "target_price"):
        assert field in item, f"missing field: {field}"
    assert isinstance(item["breakdown"], dict)
```

- [ ] **Step 2: Run tests to verify they fail (endpoint not yet fully wired — just check they run)**

```bash
cd backend && python -m pytest tests/test_top_opportunities.py -v 2>&1 | tail -20
```
Expected: some tests may pass (empty list test), others may fail due to missing data — that's OK at this stage.

- [ ] **Step 3: Run full test suite to confirm no regressions**

```bash
cd backend && python -m pytest tests/ -v --tb=short 2>&1 | tail -10
```
Expected: all previously passing tests still pass; new tests pass too.

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_top_opportunities.py
git commit -m "test: top-opportunities endpoint tests"
```

---

### Task 3: Frontend — `intelligence.ts` API module

**Files:**
- Create: `frontend/src/api/intelligence.ts`

The `apiFetch` helper is in `frontend/src/api/client.ts`. All other API modules follow the same pattern: define TypeScript interfaces, export fetch functions using `apiFetch`.

- [ ] **Step 1: Create `frontend/src/api/intelligence.ts`**

```typescript
import { apiFetch } from './client'

export interface MarketRegime {
  regime: string
  confidence: number
  pct_above_sma50: number
  pct_above_sma200: number
  advance_decline_ratio: number
  avg_atr_ratio: number
  stocks_counted: number
  as_of_date: string
}

export interface OpportunityBreakdown {
  historical_win_rate: number | null
  strategy_confidence: number | null
  regime_alignment: number | null
  regime_strategy: number | null
  mtf_alignment: number | null
  volume: number | null
  sr_context: number | null
  ml_signal_probability: number | null
  false_signal_rate: number | null
}

export interface TopOpportunity {
  signal_id: number
  symbol: string
  strategy_id: number
  strategy_name: string
  signal_date: string
  confidence_score: number | null
  price_at_signal: number
  stop_loss_price: number
  target_price: number
  stop_loss_pct: number | null
  target_pct: number | null
  holding_days: number | null
  rr: number | null
  reasoning_json: string | null
  score: number
  grade: string
  regime: string
  mtf_alignment: number | null
  ml_probability: number | null
  false_signal_rate: number | null
  breakdown: OpportunityBreakdown
}

export interface StrategyRank {
  rank: number
  strategy_id: number
  strategy_name: string
  regime_win_rate: number | null
  overall_win_rate: number | null
  regime_trades: number
}

export interface FalseSignalStat {
  strategy_id: number
  strategy_name: string
  total_evaluated: number
  win_rate: number | null
  false_signal_rate: number | null
  avg_pnl_pct: number | null
}

export interface CorrelationPair {
  strategy_id_a: number
  strategy_name_a: string
  strategy_id_b: number
  strategy_name_b: string
  correlation: number
  shared_signals: number
}

export const getMarketRegime = () =>
  apiFetch<MarketRegime>('/market/regime')

export const getTopOpportunities = (limit = 20) =>
  apiFetch<TopOpportunity[]>(`/intelligence/top-opportunities?limit=${limit}`)

export const getStrategyRanking = (regime?: string) => {
  const qs = regime ? `?regime=${encodeURIComponent(regime)}` : ''
  return apiFetch<StrategyRank[]>(`/intelligence/strategy-ranking${qs}`)
}

export const getFalseSignalStats = () =>
  apiFetch<FalseSignalStat[]>('/intelligence/false-signal-stats')

export const getStrategyCorrelations = () =>
  apiFetch<CorrelationPair[]>('/intelligence/strategy-correlations')
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -20
```
Expected: no errors relating to `intelligence.ts`

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/intelligence.ts
git commit -m "feat: intelligence API module with types and fetch functions"
```

---

### Task 4: Frontend — `RegimeBanner.tsx` component

**Files:**
- Create: `frontend/src/components/RegimeBanner.tsx`

- [ ] **Step 1: Create `frontend/src/components/RegimeBanner.tsx`**

```tsx
import type { MarketRegime } from '../api/intelligence'

const REGIME_CONFIG: Record<string, { label: string; color: string }> = {
  STRONG_BULL:     { label: 'Strong Bull',    color: 'bg-emerald-100 text-emerald-800 border-emerald-300' },
  BULL:            { label: 'Bull Trend',      color: 'bg-green-100 text-green-800 border-green-300' },
  SIDEWAYS:        { label: 'Sideways',        color: 'bg-amber-100 text-amber-800 border-amber-300' },
  BEAR:            { label: 'Bear Trend',      color: 'bg-red-100 text-red-800 border-red-300' },
  STRONG_BEAR:     { label: 'Strong Bear',     color: 'bg-rose-100 text-rose-800 border-rose-300' },
  HIGH_VOLATILITY: { label: 'High Volatility', color: 'bg-purple-100 text-purple-800 border-purple-300' },
}

export function RegimeBanner({ regime }: { regime: MarketRegime }) {
  const cfg = REGIME_CONFIG[regime.regime] ?? {
    label: regime.regime,
    color: 'bg-gray-100 text-gray-800 border-gray-300',
  }
  return (
    <div className={`flex flex-wrap items-center gap-4 px-4 py-2 rounded-lg border text-sm font-medium ${cfg.color}`}>
      <span className="font-bold uppercase tracking-wide">{cfg.label}</span>
      <span>Confidence: {Math.round(regime.confidence * 100)}%</span>
      <span>Breadth (SMA50): {Math.round(regime.pct_above_sma50 * 100)}%</span>
      <span>A/D Ratio: {regime.advance_decline_ratio.toFixed(2)}</span>
      <span className="text-xs opacity-70">as of {regime.as_of_date}</span>
    </div>
  )
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -20
```
Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/RegimeBanner.tsx
git commit -m "feat: RegimeBanner component with regime colour coding"
```

---

### Task 5: Frontend — `TopOpportunities.tsx` component

**Files:**
- Create: `frontend/src/components/TopOpportunities.tsx`

This is the largest component. It renders the enriched signals table and the score breakdown expand panel.

The `inr` formatter is in `frontend/src/utils/format.ts` and is already used in `DashboardPage.tsx`.
The `enterPosition` function is in `frontend/src/api/portfolio.ts`.

- [ ] **Step 1: Create `frontend/src/components/TopOpportunities.tsx`**

```tsx
import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { enterPosition } from '../api/portfolio'
import type { TopOpportunity, OpportunityBreakdown } from '../api/intelligence'
import { inr } from '../utils/format'

const REGIME_PILL: Record<string, string> = {
  STRONG_BULL:     'bg-emerald-100 text-emerald-700',
  BULL:            'bg-green-100 text-green-700',
  SIDEWAYS:        'bg-amber-100 text-amber-700',
  BEAR:            'bg-red-100 text-red-700',
  STRONG_BEAR:     'bg-rose-100 text-rose-700',
  HIGH_VOLATILITY: 'bg-purple-100 text-purple-700',
}

const REGIME_SHORT: Record<string, string> = {
  STRONG_BULL: 'S.Bull', BULL: 'Bull', SIDEWAYS: 'Side',
  BEAR: 'Bear', STRONG_BEAR: 'S.Bear', HIGH_VOLATILITY: 'Hi.Vol',
}

type ComponentKey = keyof OpportunityBreakdown

const SCORE_COMPONENTS: { key: ComponentKey; label: string; weight: number }[] = [
  { key: 'historical_win_rate',   label: 'Historical Win Rate',   weight: 22 },
  { key: 'strategy_confidence',   label: 'Strategy Confidence',   weight: 18 },
  { key: 'regime_alignment',      label: 'Regime Alignment',      weight: 16 },
  { key: 'mtf_alignment',         label: 'MTF Alignment',         weight: 14 },
  { key: 'volume',                label: 'Volume',                weight: 10 },
  { key: 'sr_context',            label: 'S/R Context',           weight:  8 },
  { key: 'ml_signal_probability', label: 'ML Probability',        weight:  8 },
  { key: 'regime_strategy',       label: 'Regime-Strategy',       weight:  4 },
]

function parseConditions(json: string | null): { met: string[]; failed: string[] } {
  if (!json) return { met: [], failed: [] }
  try {
    const p = JSON.parse(json)
    return { met: p.conditions_met ?? [], failed: p.conditions_failed ?? [] }
  } catch {
    return { met: [], failed: [] }
  }
}

function GradeBadge({ score, grade }: { score: number; grade: string }) {
  const color =
    score >= 80 ? 'bg-emerald-100 text-emerald-700' :
    score >= 65 ? 'bg-green-100 text-green-700' :
    score >= 50 ? 'bg-yellow-100 text-yellow-700' :
    score >= 35 ? 'bg-orange-100 text-orange-700' :
    'bg-red-100 text-red-600'
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-semibold ${color}`}
          title={`Opportunity score: ${score}/100 (grade ${grade})`}>
      {score} {grade}
    </span>
  )
}

function ScoreBreakdown({ opp }: { opp: TopOpportunity }) {
  const bd = opp.breakdown
  return (
    <div className="space-y-1.5">
      {SCORE_COMPONENTS.map(({ key, label, weight }) => {
        const val = bd[key] as number | null
        const pct = val != null ? Math.round(val * 100) : null
        return (
          <div key={key} className="flex items-center gap-2 text-xs">
            <span className="w-36 text-gray-600 text-right shrink-0">{label}</span>
            <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
              {pct != null && (
                <div className="h-full bg-blue-400 rounded-full" style={{ width: `${pct}%` }} />
              )}
            </div>
            <span className="w-10 text-gray-400 text-right">{pct != null ? `${pct}%` : '—'}</span>
            <span className="w-4 text-gray-300 text-right text-xs">{weight}</span>
          </div>
        )
      })}
      {opp.false_signal_rate != null && (
        <p className="text-xs mt-1 text-gray-500">
          False Signal Rate: {Math.round(opp.false_signal_rate * 100)}%
          {opp.false_signal_rate <= 0.30 ? ' ✓' : opp.false_signal_rate <= 0.50 ? ' ⚠' : ' ✗'}
        </p>
      )}
    </div>
  )
}

function OpportunityRow({
  opp, rank, entering, onEnter,
}: {
  opp: TopOpportunity; rank: number; entering: boolean; onEnter: () => void
}) {
  const [expanded, setExpanded] = useState(false)
  const { met, failed } = parseConditions(opp.reasoning_json)
  const regClass = REGIME_PILL[opp.regime] ?? 'bg-gray-100 text-gray-600'
  const regShort = REGIME_SHORT[opp.regime] ?? opp.regime

  return (
    <>
      <tr className="hover:bg-gray-50">
        <td className="px-2 py-2 text-center text-xs text-gray-400">{rank}</td>
        <td className="px-2 py-2 text-center">
          <button
            onClick={() => setExpanded(v => !v)}
            aria-label={expanded ? 'Collapse' : 'Expand'}
            className="text-gray-400 hover:text-gray-600 text-xs font-bold w-5 h-5 flex items-center justify-center rounded border border-gray-200 hover:border-gray-400"
          >
            {expanded ? '−' : '+'}
          </button>
        </td>
        <td className="px-4 py-2 font-semibold">{opp.symbol}</td>
        <td className="px-4 py-2"><GradeBadge score={opp.score} grade={opp.grade} /></td>
        <td className="px-4 py-2">
          <span className={`px-2 py-0.5 rounded text-xs font-medium ${regClass}`}>{regShort}</span>
        </td>
        <td className="px-4 py-2 text-xs text-gray-500">
          {opp.mtf_alignment != null ? `${Math.round(opp.mtf_alignment * 100)}%` : '—'}
        </td>
        <td className="px-4 py-2 text-xs text-gray-500">
          {opp.ml_probability != null ? `${Math.round(opp.ml_probability * 100)}%` : '—'}
        </td>
        <td className="px-4 py-2">{inr(opp.price_at_signal)}</td>
        <td className="px-4 py-2 text-red-600">{inr(opp.stop_loss_price)}</td>
        <td className="px-4 py-2 text-green-600">{inr(opp.target_price)}</td>
        <td className="px-4 py-2 text-gray-500 text-xs">
          {opp.rr != null ? `1:${opp.rr.toFixed(1)}` : '—'}
        </td>
        <td className="px-4 py-2 text-gray-500 text-xs max-w-[140px] truncate" title={opp.strategy_name}>
          {opp.strategy_name}
        </td>
        <td className="px-4 py-2">
          <button
            onClick={onEnter}
            disabled={entering}
            aria-label={`Enter position for ${opp.symbol}`}
            className="px-3 py-1 bg-blue-600 text-white text-xs rounded hover:bg-blue-700 disabled:opacity-50"
          >
            Enter
          </button>
        </td>
      </tr>
      {expanded && (
        <tr className="bg-blue-50">
          <td colSpan={13} className="px-6 py-4">
            <div className="grid grid-cols-2 gap-6 text-xs">
              <div>
                <p className="font-semibold text-gray-700 mb-2">
                  Score Breakdown — {opp.score}/100 ({opp.grade})
                </p>
                <ScoreBreakdown opp={opp} />
              </div>
              <div>
                <p className="font-semibold text-gray-700 mb-2">
                  Why {opp.symbol}? — {opp.strategy_name}
                </p>
                {met.length > 0 && (
                  <ul className="space-y-0.5 mb-1">
                    {met.map((c, i) => (
                      <li key={i} className="flex items-start gap-1.5 text-green-700">
                        <span className="mt-0.5">✓</span><span>{c}</span>
                      </li>
                    ))}
                  </ul>
                )}
                {failed.length > 0 && (
                  <ul className="space-y-0.5">
                    {failed.map((c, i) => (
                      <li key={i} className="flex items-start gap-1.5 text-gray-400">
                        <span className="mt-0.5">✗</span><span>{c}</span>
                      </li>
                    ))}
                  </ul>
                )}
                <div className="mt-2 space-y-0.5 text-gray-500">
                  <p>SL: {inr(opp.stop_loss_price)} ({opp.stop_loss_pct?.toFixed(1)}%)</p>
                  <p>Target: {inr(opp.target_price)} (+{opp.target_pct?.toFixed(1)}%)</p>
                  {opp.rr != null && <p>R:R 1:{opp.rr.toFixed(1)}</p>}
                  {opp.holding_days != null && <p>Hold: ~{opp.holding_days}d</p>}
                  {opp.ml_probability != null && (
                    <p>ML Probability: {Math.round(opp.ml_probability * 100)}%</p>
                  )}
                </div>
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  )
}

export function TopOpportunities({
  opportunities,
  isLoading,
  isError,
}: {
  opportunities: TopOpportunity[]
  isLoading: boolean
  isError: boolean
}) {
  const queryClient = useQueryClient()
  const enterMut = useMutation({
    mutationFn: ({ signalId, price }: { signalId: number; price: number }) =>
      enterPosition(signalId, price),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['portfolio'] }),
  })

  if (isLoading) return <p className="text-gray-400">Loading…</p>
  if (isError)   return <p className="text-red-600 text-sm">Failed to load opportunities.</p>
  if (opportunities.length === 0) return (
    <p className="text-gray-500 py-4">
      No BUY signals yet — scans run at 9:15, 10:30, 12:00, 14:00, 15:15 IST on trading days.
    </p>
  )

  return (
    <>
      <div className="overflow-x-auto rounded-lg border border-gray-200">
        <table className="w-full text-sm">
          <thead className="bg-gray-100 text-gray-600 text-left">
            <tr>
              <th className="px-2 py-2 text-center text-xs">#</th>
              <th className="px-2 py-2 w-6" />
              <th className="px-4 py-2">Symbol</th>
              <th className="px-4 py-2">Score</th>
              <th className="px-4 py-2">Regime</th>
              <th className="px-4 py-2">MTF</th>
              <th className="px-4 py-2">ML%</th>
              <th className="px-4 py-2">Entry</th>
              <th className="px-4 py-2">Stop Loss</th>
              <th className="px-4 py-2">Target</th>
              <th className="px-4 py-2">R:R</th>
              <th className="px-4 py-2">Strategy</th>
              <th className="px-4 py-2" />
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-100">
            {opportunities.map((opp, i) => (
              <OpportunityRow
                key={opp.signal_id}
                opp={opp}
                rank={i + 1}
                entering={enterMut.isPending && enterMut.variables?.signalId === opp.signal_id}
                onEnter={() => enterMut.mutate({ signalId: opp.signal_id, price: opp.price_at_signal })}
              />
            ))}
          </tbody>
        </table>
      </div>
      {enterMut.isError && (
        <p className="text-red-600 text-sm mt-2">
          Failed to enter position: {String(enterMut.error)}
        </p>
      )}
    </>
  )
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -30
```
Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/TopOpportunities.tsx
git commit -m "feat: TopOpportunities component with score breakdown expand"
```

---

### Task 6: Frontend — `StrategyIntelligence.tsx` component

**Files:**
- Create: `frontend/src/components/StrategyIntelligence.tsx`

Data is lazy-loaded on first expand (`enabled: open`). Three independent `useQuery` calls, one per sub-panel. Correlations filtered to pairs with `correlation > 0.70`.

- [ ] **Step 1: Create `frontend/src/components/StrategyIntelligence.tsx`**

```tsx
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  getFalseSignalStats,
  getStrategyCorrelations,
  getStrategyRanking,
} from '../api/intelligence'

export function StrategyIntelligence({ regime }: { regime: string | undefined }) {
  const [open, setOpen] = useState(false)

  const { data: ranking = [], isLoading: rankLoading } = useQuery({
    queryKey: ['intelligence', 'strategy-ranking', regime],
    queryFn:  () => getStrategyRanking(regime),
    enabled:  open,
  })

  const { data: falseStats = [], isLoading: falseLoading } = useQuery({
    queryKey: ['intelligence', 'false-signal-stats'],
    queryFn:  getFalseSignalStats,
    enabled:  open,
  })

  const { data: correlations = [], isLoading: corrLoading } = useQuery({
    queryKey: ['intelligence', 'correlations'],
    queryFn:  getStrategyCorrelations,
    enabled:  open,
  })

  const highCorr = correlations
    .filter(p => p.correlation > 0.70)
    .sort((a, b) => b.correlation - a.correlation)

  const regimeLabel = regime?.replace(/_/g, ' ') ?? 'Current Regime'

  return (
    <section>
      <button
        onClick={() => setOpen(v => !v)}
        className="flex items-center gap-2 text-sm font-semibold text-gray-600 hover:text-gray-800 mb-3"
      >
        <span className="text-gray-400 text-xs">{open ? '▼' : '▶'}</span>
        Strategy Intelligence
        {regime && (
          <span className="text-xs font-normal text-gray-400">— {regimeLabel}</span>
        )}
      </button>

      {open && (
        <div className="space-y-5">

          {/* Strategy Ranking */}
          <div>
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
              Strategy Ranking — {regimeLabel}
            </h3>
            {rankLoading ? (
              <p className="text-gray-400 text-sm">Loading…</p>
            ) : ranking.length === 0 ? (
              <p className="text-gray-400 text-sm">
                No regime performance data yet. Run the regime backfill to populate.
              </p>
            ) : (
              <div className="overflow-x-auto rounded-lg border border-gray-200">
                <table className="w-full text-xs">
                  <thead className="bg-gray-50 text-gray-500 text-left">
                    <tr>
                      <th className="px-3 py-2 text-center">Rank</th>
                      <th className="px-3 py-2">Strategy</th>
                      <th className="px-3 py-2 text-right">Regime Win%</th>
                      <th className="px-3 py-2 text-right">Overall Win%</th>
                      <th className="px-3 py-2 text-right">Trades</th>
                    </tr>
                  </thead>
                  <tbody className="bg-white divide-y divide-gray-100">
                    {ranking.map(r => (
                      <tr key={r.strategy_id} className="hover:bg-gray-50">
                        <td className="px-3 py-1.5 text-center text-gray-400">#{r.rank}</td>
                        <td className="px-3 py-1.5">{r.strategy_name}</td>
                        <td className="px-3 py-1.5 text-right">
                          {r.regime_win_rate != null ? (
                            <span className={
                              r.regime_win_rate >= 0.6  ? 'text-green-600 font-medium' :
                              r.regime_win_rate >= 0.4  ? 'text-yellow-600' :
                              'text-red-500'
                            }>
                              {Math.round(r.regime_win_rate * 100)}%
                            </span>
                          ) : '—'}
                        </td>
                        <td className="px-3 py-1.5 text-right text-gray-500">
                          {r.overall_win_rate != null
                            ? `${Math.round(r.overall_win_rate * 100)}%`
                            : '—'}
                        </td>
                        <td className="px-3 py-1.5 text-right text-gray-400">{r.regime_trades}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* False Signal Rates + Correlations side by side */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">

            {/* False Signal Rates */}
            <div>
              <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
                False Signal Rates
              </h3>
              {falseLoading ? (
                <p className="text-gray-400 text-sm">Loading…</p>
              ) : falseStats.length === 0 ? (
                <p className="text-gray-400 text-sm">
                  No outcome data yet — needs 15d+ of signal history.
                </p>
              ) : (
                <div className="overflow-x-auto rounded-lg border border-gray-200">
                  <table className="w-full text-xs">
                    <thead className="bg-gray-50 text-gray-500 text-left">
                      <tr>
                        <th className="px-3 py-2">Strategy</th>
                        <th className="px-3 py-2 text-right">False Rate</th>
                        <th className="px-3 py-2 text-right">Signals</th>
                      </tr>
                    </thead>
                    <tbody className="bg-white divide-y divide-gray-100">
                      {falseStats.map(s => (
                        <tr key={s.strategy_id} className="hover:bg-gray-50">
                          <td className="px-3 py-1.5 truncate max-w-[160px]" title={s.strategy_name}>
                            {s.strategy_name}
                          </td>
                          <td className="px-3 py-1.5 text-right">
                            {s.false_signal_rate != null ? (
                              <span className={`font-medium ${
                                s.false_signal_rate <= 0.30 ? 'text-green-600' :
                                s.false_signal_rate <= 0.50 ? 'text-amber-600' :
                                'text-red-600'
                              }`}>
                                {Math.round(s.false_signal_rate * 100)}%
                              </span>
                            ) : (
                              <span className="text-gray-300">—</span>
                            )}
                          </td>
                          <td className="px-3 py-1.5 text-right text-gray-400">
                            {s.total_evaluated}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            {/* High Correlation Pairs */}
            <div>
              <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
                High Correlation Pairs
              </h3>
              <p className="text-xs text-gray-400 mb-2">
                High correlation = fewer independent confirmations
              </p>
              {corrLoading ? (
                <p className="text-gray-400 text-sm">Loading…</p>
              ) : highCorr.length === 0 ? (
                <p className="text-gray-400 text-sm">
                  No high-correlation pairs (threshold: 0.70). Run correlation compute first.
                </p>
              ) : (
                <div className="overflow-x-auto rounded-lg border border-gray-200">
                  <table className="w-full text-xs">
                    <thead className="bg-gray-50 text-gray-500 text-left">
                      <tr>
                        <th className="px-3 py-2">Strategy A</th>
                        <th className="px-3 py-2">Strategy B</th>
                        <th className="px-3 py-2 text-right">Corr</th>
                      </tr>
                    </thead>
                    <tbody className="bg-white divide-y divide-gray-100">
                      {highCorr.map((p, i) => (
                        <tr key={i} className="hover:bg-gray-50">
                          <td className="px-3 py-1.5 truncate max-w-[120px]" title={p.strategy_name_a}>
                            {p.strategy_name_a}
                          </td>
                          <td className="px-3 py-1.5 truncate max-w-[120px]" title={p.strategy_name_b}>
                            {p.strategy_name_b}
                          </td>
                          <td className="px-3 py-1.5 text-right font-medium text-amber-600">
                            {p.correlation.toFixed(2)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

          </div>
        </div>
      )}
    </section>
  )
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -20
```
Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/StrategyIntelligence.tsx
git commit -m "feat: StrategyIntelligence collapsible panel with lazy loading"
```

---

### Task 7: Frontend — Update `DashboardPage.tsx`

**Files:**
- Modify: `frontend/src/pages/DashboardPage.tsx`

Replace the entire file. The old `getTodaySignals` query and the `SignalRow`, `OpportunityBadge`, `ConfidenceBadge`, `parseConditions` helpers move into `TopOpportunities.tsx` (already done). The new Dashboard orchestrates the three sections.

- [ ] **Step 1: Replace `frontend/src/pages/DashboardPage.tsx`**

```tsx
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { getPortfolioSummary } from '../api/portfolio'
import { getMarketRegime, getTopOpportunities } from '../api/intelligence'
import { RegimeBanner } from '../components/RegimeBanner'
import { TopOpportunities } from '../components/TopOpportunities'
import { StrategyIntelligence } from '../components/StrategyIntelligence'
import { inr } from '../utils/format'

const POLL_MS = 3 * 60 * 1000

export function DashboardPage() {
  const queryClient = useQueryClient()

  const { data: summary, isLoading: loadingSummary, isError: summaryError } = useQuery({
    queryKey: ['portfolio', 'summary'],
    queryFn: getPortfolioSummary,
  })

  const { data: regime, isLoading: regimeLoading } = useQuery({
    queryKey: ['market', 'regime'],
    queryFn: getMarketRegime,
    refetchInterval: POLL_MS,
    refetchIntervalInBackground: false,
  })

  const {
    data: opportunities = [],
    isLoading: oppsLoading,
    isError: oppsError,
    isFetching: oppsFetching,
    dataUpdatedAt,
  } = useQuery({
    queryKey: ['intelligence', 'top-opportunities'],
    queryFn: () => getTopOpportunities(20),
    refetchInterval: POLL_MS,
    refetchIntervalInBackground: false,
  })

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-800">Dashboard</h1>

      {/* Regime banner */}
      {!regimeLoading && regime && <RegimeBanner regime={regime} />}

      {/* Portfolio summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {loadingSummary ? (
          <p className="col-span-4 text-gray-400">Loading…</p>
        ) : summaryError ? (
          <p className="col-span-4 text-red-600 text-sm">Failed to load portfolio summary.</p>
        ) : summary ? (
          <>
            <Card label="Paper Capital"  value={inr(summary.paper_capital)} />
            <Card label="Invested"       value={inr(summary.total_invested)} />
            <Card label="Available"      value={inr(summary.cash_available)} />
            <Card label="Positions"      value={`${summary.open_positions} / ${summary.max_positions}`} />
          </>
        ) : null}
      </div>

      {/* Top Opportunities */}
      <section>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-semibold text-gray-700">Top Opportunities</h2>
          <div className="flex items-center gap-2">
            {dataUpdatedAt > 0 && (
              <span className="text-xs text-gray-400">
                updated {new Date(dataUpdatedAt).toLocaleTimeString('en-IN', {
                  hour: '2-digit', minute: '2-digit',
                })}
              </span>
            )}
            <button
              onClick={() =>
                queryClient.invalidateQueries({ queryKey: ['intelligence', 'top-opportunities'] })
              }
              disabled={oppsFetching}
              className="text-xs px-2 py-1 rounded border border-gray-300 text-gray-500 hover:text-gray-700 hover:border-gray-400 disabled:opacity-40"
              title="Refresh opportunities"
            >
              {oppsFetching ? '↻ …' : '↻ Refresh'}
            </button>
          </div>
        </div>
        <TopOpportunities
          opportunities={opportunities}
          isLoading={oppsLoading}
          isError={oppsError}
        />
      </section>

      {/* Strategy Intelligence (collapsed by default) */}
      <StrategyIntelligence regime={regime?.regime} />
    </div>
  )
}

function Card({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-white border border-gray-200 rounded-lg p-4 shadow-sm">
      <p className="text-xs text-gray-500 mb-1">{label}</p>
      <p className="text-xl font-bold text-gray-800">{value}</p>
    </div>
  )
}
```

- [ ] **Step 2: Verify TypeScript compiles with no errors**

```bash
cd frontend && npx tsc --noEmit 2>&1
```
Expected: no output (zero errors)

- [ ] **Step 3: Run the dev server and manually verify the dashboard**

```bash
cd frontend && npm run dev
```

Open `http://localhost:5173` and verify:
- [ ] Regime banner appears at top (correct colour for current regime)
- [ ] Top Opportunities table loads, sorted by score descending
- [ ] Each row shows Score badge, Regime pill, MTF%, ML% columns
- [ ] Clicking `+` expands to show Score Breakdown (8 bars) and Signal Reasoning
- [ ] `Enter` button on a row triggers position entry
- [ ] `▶ Strategy Intelligence` toggle expands the panel
- [ ] On first expand, three sub-panels load: Strategy Ranking, False Signal Rates, Correlations
- [ ] Correlations filtered to pairs with correlation > 0.70

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/DashboardPage.tsx
git commit -m "feat: Phase E intelligence dashboard — regime banner, top opportunities, strategy intelligence"
```

---

### Task 8: Full test suite verification

**Files:** no changes

- [ ] **Step 1: Run backend test suite**

```bash
cd backend && python -m pytest tests/ -v --tb=short 2>&1 | tail -15
```
Expected: all 275+ tests pass, 0 failures

- [ ] **Step 2: Run frontend TypeScript check**

```bash
cd frontend && npx tsc --noEmit 2>&1
```
Expected: no output

- [ ] **Step 3: Run frontend build (catches any remaining errors)**

```bash
cd frontend && npm run build 2>&1 | tail -10
```
Expected: `✓ built in` with no errors

- [ ] **Step 4: Commit if anything was fixed during verification**

Only commit if fixes were needed. Otherwise proceed.
