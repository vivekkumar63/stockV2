# Sector Rotation Feature — Design Spec

**Date:** 2026-08-31  
**Status:** Approved

---

## Overview

Add sector rotation awareness to StockV2. The system pre-computes two sector health metrics daily — breadth/momentum and signal flow — surfaces them via a new `/sector-rotation` frontend page, and folds sector health into the existing `OpportunityScorer` predictions (replacing the weaker `index_alignment` component).

---

## 1. Data Model

### New tables

**`sector_breadth_daily`** — one row per (sector, date); computed once per trading day.

| Column | Type | Notes |
|--------|------|-------|
| id | SERIAL PK | |
| sector_name | VARCHAR(30) | "BANK", "IT", "AUTO", "PHARMA", "FMCG", "METAL", "ENERGY" |
| trade_date | DATE | |
| pct_above_sma50 | REAL | % of sector stocks trading above SMA50 |
| index_vs_sma20 | REAL | (sector index close / SMA20) - 1 |
| return_1m | REAL | 1-month return of sector index |
| return_3m | REAL | 3-month return |
| sector_health_score | REAL | 0–100 composite (breadth × 0.5 + momentum × 0.3 + trend × 0.2) |
| rotation_direction | VARCHAR(20) | "ROTATING_IN" / "NEUTRAL" / "ROTATING_OUT" |

Unique constraint: `(sector_name, trade_date)`.

**`sector_signal_flow`** — one row per (sector, week_start); computed weekly (or daily with week_start anchor).

| Column | Type | Notes |
|--------|------|-------|
| id | SERIAL PK | |
| sector_name | VARCHAR(30) | |
| week_start | DATE | Monday of the trading week |
| signal_count | INTEGER | Total BUY signals fired in the sector this week |
| prev_signal_count | INTEGER | Same metric for the previous week |
| avg_win_rate | REAL | Average historical win rate of signals fired |
| top_strategy | VARCHAR(100) | Name of strategy that fired most signals this week |
| stocks_with_signals | TEXT | Comma-separated list of symbols |

Unique constraint: `(sector_name, week_start)`.

### Sector-to-index mapping

Reuse `STOCK_INDEX_MAP` from `backend/domains/indices/index_universe.py` (already maps 150+ symbols → 7 sector indices). The 7 sectors: BANK, IT, AUTO, PHARMA, FMCG, METAL, ENERGY.

---

## 2. SectorRotationEngine

**New file:** `backend/domains/sector_rotation/engine.py`

```
SectorRotationEngine
  ├── compute_breadth(db, trade_date)        → writes sector_breadth_daily rows
  ├── compute_signal_flow(db, week_start)    → writes sector_signal_flow rows
  ├── get_market_phase(db) → str             → "EXPANSION" | "CONTRACTION" | "RECOVERY" | "SLOWDOWN"
  └── get_sector_summary(db) → list[dict]   → current breadth + signal flow merged
```

**Market phase logic** (based on latest breadth snapshot):

| Condition | Phase |
|-----------|-------|
| ≥3 sectors ROTATING_IN, avg breadth ≥60% | EXPANSION |
| ≥3 sectors ROTATING_OUT, avg breadth <40% | CONTRACTION |
| avg breadth 40–60%, positive momentum | RECOVERY |
| avg breadth 40–60%, negative momentum | SLOWDOWN |

**`sector_health_score` formula:**
```
breadth_score = pct_above_sma50 * 0.50
momentum_score = clamp(index_vs_sma20 * 10, -50, 50) * 0.30   # scaled from %
trend_score = clamp(return_1m * 5, -50, 50) * 0.20            # scaled from %
sector_health_score = clamp(50 + breadth_score + momentum_score + trend_score, 0, 100)
```

**`rotation_direction` thresholds:**
- `ROTATING_IN`: score ≥ 60
- `NEUTRAL`: 40 ≤ score < 60
- `ROTATING_OUT`: score < 40

---

## 3. OpportunityScorer Integration

**File:** `backend/domains/intelligence/opportunity_scorer.py`

Replace the existing `index_alignment` component (which queries `stock_index_daily` alignment) with a `sector_health` component that uses `sector_breadth_daily`.

Weight stays the same: **10%** of total score.

```python
# Old
index_alignment = self._compute_index_alignment(symbol, db)  # 0–1

# New
sector_health = self._compute_sector_health(symbol, db)      # 0–1

def _compute_sector_health(self, symbol: str, db) -> float:
    sector = SYMBOL_TO_SECTOR.get(symbol)              # reverse-lookup from STOCK_INDEX_MAP
    if not sector:
        return 0.5                                     # unknown sector → neutral
    row = db.execute(
        "SELECT sector_health_score FROM sector_breadth_daily "
        "WHERE sector_name = :s ORDER BY trade_date DESC LIMIT 1",
        {"s": sector}
    ).fetchone()
    if not row:
        return 0.5
    return row[0] / 100.0                             # normalize to 0–1
```

`SYMBOL_TO_SECTOR` is a pre-built reverse dict from `STOCK_INDEX_MAP`.

---

## 4. Scheduler Integration

**File:** `backend/scheduler.py`

Add one new daily job: runs after market close (18:00 IST), after the existing `precompute_all_strategies` job.

```python
@scheduler.scheduled_job('cron', hour=18, minute=10, timezone='Asia/Kolkata', id='sector_rotation_daily')
def sector_rotation_daily():
    from domains.sector_rotation.engine import SectorRotationEngine
    engine = SectorRotationEngine()
    with get_db() as db:
        today = date.today()
        engine.compute_breadth(db, today)
        engine.compute_signal_flow(db, _week_start(today))
```

---

## 5. API Endpoints

**New file:** `backend/domains/sector_rotation/router.py`  
Registered under `/api/v1/sector`.

| Method | Path | Response |
|--------|------|----------|
| GET | `/sector/summary` | Market phase + all 7 sectors (breadth + signal flow merged) |
| GET | `/sector/breadth` | Full history of `sector_breadth_daily` (optional `?days=30`) |
| GET | `/sector/signal-flow` | Full history of `sector_signal_flow` (optional `?weeks=8`) |
| POST | `/sector/recompute` | Trigger manual recompute for today (admin/debug) |

**`/sector/summary` response shape:**
```json
{
  "market_phase": "EXPANSION",
  "as_of": "2026-08-31",
  "sectors": [
    {
      "name": "BANK",
      "rotation_direction": "ROTATING_IN",
      "sector_health_score": 82.1,
      "pct_above_sma50": 82.0,
      "index_vs_sma20": 3.1,
      "return_1m": 8.2,
      "return_3m": 18.4,
      "signal_count_this_week": 18,
      "signal_count_prev_week": 10,
      "avg_win_rate": 0.64,
      "top_strategy": "EMA Cross",
      "stocks_with_signals": ["HDFCBANK", "ICICIBANK", "KOTAKBANK"]
    }
  ]
}
```

---

## 6. Frontend Page

**New file:** `frontend/src/pages/SectorRotationPage.tsx`

**Layout:** Option C (sidebar + expandable rows) with two tabs.

### Header
- Market phase badge (color-coded: green = Expansion, red = Contraction, amber = Slowdown/Recovery)
- "As of [date]" + Refresh button

### Tab 1 — Breadth & Momentum
- **Sidebar:** Market phase + rotation map (7 sectors, color-coded by `rotation_direction`)
- **Main area:** Expandable sector rows sorted by `sector_health_score` desc
  - Collapsed: sector name, score, 1M return, rotation direction badge
  - Expanded: 3 metric tiles (% above SMA50, index vs SMA20, 3M return) + breadth bar + top stocks list

### Tab 2 — Signal Flow
- **Sidebar:** Weekly signal summary (total BUY signals this week vs last week) + signal heat map per sector
- **Main area:** Expandable rows sorted by `signal_count_this_week` desc
  - Collapsed: sector name, signal count, vs-last-week delta, status badge (🔥 HEATING UP / 📈 RISING / ➡️ STABLE / 📉 COOLING)
  - Expanded: 4 metric tiles (this week, last week, avg win rate, top strategy) + stocks with signals list

### Navigation
- Add `<NavLink to="/sector-rotation">Sectors</NavLink>` to NavBar
- Add `<Route path="/sector-rotation" element={<SectorRotationPage />} />` to App.tsx

---

## 7. New Files Summary

| File | Purpose |
|------|---------|
| `backend/domains/sector_rotation/__init__.py` | Empty package marker |
| `backend/domains/sector_rotation/engine.py` | SectorRotationEngine |
| `backend/domains/sector_rotation/router.py` | 4 API endpoints |
| `frontend/src/pages/SectorRotationPage.tsx` | Two-tab sector rotation page |
| `frontend/src/api/sector.ts` | TypeScript API client |

**Modified files:**

| File | Change |
|------|--------|
| `backend/main.py` | Create 2 new tables, register sector router |
| `backend/scheduler.py` | Add `sector_rotation_daily` job |
| `backend/domains/intelligence/opportunity_scorer.py` | Replace `index_alignment` with `sector_health` |
| `frontend/src/components/NavBar.tsx` | Add "Sectors" nav link |
| `frontend/src/App.tsx` | Add `/sector-rotation` route |

---

## 8. Verification Checklist

1. Backend starts without error — 2 new tables created, sector router registered
2. `POST /api/v1/sector/recompute` → returns 200, rows appear in `sector_breadth_daily`
3. `GET /api/v1/sector/summary` → returns JSON with `market_phase` and 7 sector objects
4. OpportunityScorer: run a scan for a known BANK stock (e.g., HDFCBANK) and confirm `sector_health` component is non-null in debug output
5. Frontend: `/sector-rotation` loads, both tabs render, expandable rows work, rotation badges are color-coded correctly
