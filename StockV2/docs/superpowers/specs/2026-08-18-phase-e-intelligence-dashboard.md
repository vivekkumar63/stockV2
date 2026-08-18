# Phase E: Intelligence Dashboard — Design Spec

**Goal:** Expose all Phase C/D intelligence features (opportunity scores, market regime, MTF alignment, ML probability, strategy ranking, false signal rates, correlations) directly inside the existing Dashboard page.

**Architecture:** One new backend endpoint batches opportunity scores for today's BUY signals. The frontend Dashboard gains three vertical sections: a regime banner, an enriched signals table, and a collapsible Strategy Intelligence panel. No new pages or routes are added.

**Tech Stack:** FastAPI (backend), React + TanStack Query v5 + Tailwind CSS (frontend)

---

## Backend Changes

### New endpoint: `GET /intelligence/top-opportunities`

**File:** `backend/domains/intelligence/router.py`

**Query params:**
- `limit: int = 20`

**Logic:**
1. Fetch today's BUY signals from `strategy_signals` (joined with `strategies` for name)
2. For each unique `(symbol, strategy_id)` pair, call `OpportunityScorer().full_score()` with all components: MTF, volume, S/R, ML probability, false signal rate
3. Return list sorted by `score` descending, capped at `limit`

**Response shape (per item):**
```json
{
  "signal_id": 4821,
  "symbol": "RELIANCE",
  "strategy_id": 3,
  "strategy_name": "SuperTrend",
  "signal_date": "2026-08-18",
  "confidence_score": 0.78,
  "price_at_signal": 1450.0,
  "stop_loss_price": 1409.4,
  "target_price": 1529.75,
  "stop_loss_pct": 2.8,
  "target_pct": 5.5,
  "holding_days": 15,
  "score": 91,
  "grade": "A",
  "regime": "BULL",
  "mtf_alignment": 0.82,
  "ml_probability": 0.72,
  "false_signal_rate": 0.18,
  "breakdown": {
    "historical_win_rate": 0.67,
    "strategy_confidence": 0.78,
    "regime_alignment": 1.0,
    "mtf_alignment": 0.82,
    "volume": 0.74,
    "sr_context": 0.61,
    "regime_strategy": 0.71,
    "ml_signal_probability": 0.72,
    "false_signal_rate": 0.18
  }
}
```

**Performance note:** Today's BUY signals are typically 20–50 stocks. MTF + volume + S/R computation per stock is ~50ms each; total latency ~1–3s for 20 stocks. Acceptable for a dashboard that refreshes every 3 minutes.

---

## Frontend Changes

**File:** `frontend/src/pages/DashboardPage.tsx` (primary), `frontend/src/api/intelligence.ts` (new API functions)

### Section 1: Market Regime Banner

- Pinned at top of page, above portfolio cards
- Calls `GET /market/regime` on mount (same 3-minute refetch interval as signals)
- Shows: regime label (colour-coded), confidence %, breadth %, ADX
- Colour map: STRONG_BULL → emerald, BULL → green, SIDEWAYS → amber, BEAR → red, STRONG_BEAR → rose, HIGH_VOLATILITY → purple

### Section 2: Top Opportunities Table

- Replaces/upgrades the existing `Today's BUY Signals` table
- Data source: `GET /intelligence/top-opportunities?limit=20`
- Default sort: `score` descending
- Columns:
  - `#` (rank)
  - `Symbol`
  - `Score` (badge: A/B/C/D, colour-coded)
  - `Signal` (BUY badge)
  - `Regime` (pill: BULL/BEAR/SIDEWAYS)
  - `MTF` (alignment % or `—` if unavailable)
  - `ML%` (probability % or `—` if no model)
  - `Entry` / `SL` / `Target`
  - `R:R`
  - `Strategy`
  - Enter button (existing behaviour)

- **Expanded row** (click to toggle):
  - Left panel: Score Breakdown — per-component label, mini progress bar, weight number; false signal rate one-liner below
  - Right panel: Signal Reasoning — existing conditions met/failed list, stop loss %, target %, R:R, hold days, ML probability

### Section 3: Strategy Intelligence Panel

- Collapsed by default; toggle via header click
- Data fetched lazily on first expand (three independent queries)
- Sub-panels:

**Strategy Ranking** (full width):
- Calls `GET /intelligence/strategy-ranking?regime=<current_regime>` — passes the regime string already loaded by the banner query; falls back to current regime if omitted
- Table: Rank, Strategy, Regime Win Rate, Overall Win Rate, Trade Count
- Header shows current regime

**False Signal Rates** (left half):
- Calls `GET /intelligence/false-signal-stats`
- Table: Strategy, False Rate (colour dot: green ≤30%, amber 31–50%, red >50%)
- Strategies with `< MIN_SIGNALS` outcomes show `—`

**High Correlation Pairs** (right half):
- Calls `GET /intelligence/strategy-correlations`
- Filtered to pairs with `correlation > 0.70`, sorted descending
- Columns: Strategy A, Strategy B, Correlation
- One-line note: "High correlation = fewer independent confirmations"

---

## Data Flow

```
DashboardPage mounts
  ├── GET /market/regime           → regime banner
  ├── GET /intelligence/top-opportunities → signals table
  └── GET /portfolio/summary       → portfolio cards (unchanged)

User expands Strategy Intelligence
  ├── GET /intelligence/strategy-ranking
  ├── GET /intelligence/false-signal-stats
  └── GET /intelligence/strategy-correlations

User clicks signal row
  └── No extra fetch — breakdown data already in top-opportunities response
```

---

## Error & Loading States

- Regime banner: skeleton pill while loading; hidden (not errored) if fetch fails
- Signals table: existing loading spinner; falls back to empty state with message if endpoint errors
- Strategy Intelligence: each sub-panel shows its own loading skeleton; errors shown inline per panel

---

## Testing

**Backend:**
- `test_top_opportunities_returns_sorted_list` — endpoint returns items sorted by score descending
- `test_top_opportunities_empty_when_no_signals` — returns `[]` when no BUY signals today
- `test_top_opportunities_limit_respected` — `?limit=5` returns at most 5 items

**Frontend (manual verification):**
- Regime banner shows correct label and colour for each regime
- Signals table sorted by score on load
- Expanded row shows all 8 score components
- Strategy Intelligence panel loads lazily (network tab: no fetch until panel opened)
- Correlation pairs filtered to > 0.70 only

---

## What Is NOT Changing

- Portfolio page (unchanged)
- Backtest page (unchanged)
- Scanner page (unchanged)
- Strategy Match / Leaderboard page (unchanged)
- Existing signal reasoning expand logic (reused in new expanded row)
- `GET /signals/today` endpoint (still exists; replaced in Dashboard by top-opportunities)
