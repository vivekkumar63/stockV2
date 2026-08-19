# Nifty 500 Expansion + Index-Aligned Signal Boost

**Date:** 2026-08-19
**Status:** Approved

## Overview

Two related features:

1. **Nifty 500 expansion** — grow the stock universe from the current 237 hardcoded symbols to the full Nifty 500 (~500 symbols across four tiers).
2. **Index-aligned signal boost** — detect whether a stock's parent sector index (e.g., BANK NIFTY for SBIN) is bullish at signal time, surface this context on the signal card, and factor it into the opportunity score as a new weighted component.

---

## Feature 1: Nifty 500 Stock Universe

### What changes

Single file change: `backend/domains/data/nse_universe.py`

Replace the current `NSE_SYMBOLS` list (237 entries) with the full Nifty 500 constituent list organised into four tiers:

| Tier | Count | Index |
|---|---|---|
| Large Cap | 50 | Nifty 50 |
| Large-Mid Cap | 50 | Nifty Next 50 |
| Mid Cap | 150 | Nifty Midcap 150 |
| Small Cap | 250 | Nifty Smallcap 250 |

Total: ~500 symbols (exact count subject to deduplication).

### Downstream impact

Everything that consumes `NSE_SYMBOLS` picks up the new list automatically:
- `scripts/bootstrap.py` — downloads OHLCV history for new symbols on next run
- `domains/strategies/scanner.py` — scans all `NSE_SYMBOLS`
- `domains/strategies/engine.py` — `scan_all()` iterates `NSE_SYMBOLS`
- `POST /backtest/precompute` — auto-precompute job added in the previous commit picks up new symbols on server restart

### One-time cost

Bootstrap downloads ~15 years of OHLCV for ~263 new symbols. Runs in background, resumable. No user action required beyond server restart.

### No other code changes needed

The `get_yfinance_symbol()` helper in `nse_universe.py` already handles the `.NS` suffix conversion generically.

---

## Feature 2: Index-Aligned Signal Boost

### Architecture: Dedicated index pipeline (Approach A)

Separate `index_prices_daily` table for index OHLCV. A daily job keeps it fresh. The opportunity scorer reads the pre-loaded latest trend at score time — no per-signal yfinance calls.

---

### 2.1 Index Universe Definition

**New file:** `backend/domains/data/index_universe.py`

Two dicts:

```python
INDEX_DEFINITIONS = {
    "NIFTY BANK":   {"yf_symbol": "^NSEBANK",   "description": "Banking sector"},
    "NIFTY IT":     {"yf_symbol": "^CNXIT",     "description": "Information technology"},
    "NIFTY FMCG":   {"yf_symbol": "^CNXFMCG",   "description": "Fast-moving consumer goods"},
    "NIFTY AUTO":   {"yf_symbol": "^CNXAUTO",   "description": "Automobiles & auto components"},
    "NIFTY PHARMA": {"yf_symbol": "^CNXPHARMA", "description": "Pharmaceuticals"},
    "NIFTY METAL":  {"yf_symbol": "^CNXMETAL",  "description": "Metals & mining"},
    "NIFTY ENERGY": {"yf_symbol": "^CNXENERGY", "description": "Energy & utilities"},
}

# One primary index per stock. Stocks not in this map → index_alignment score = 50 (neutral).
STOCK_INDEX_MAP: dict[str, str] = {
    # NIFTY BANK
    "HDFCBANK": "NIFTY BANK", "ICICIBANK": "NIFTY BANK", "KOTAKBANK": "NIFTY BANK",
    "SBIN": "NIFTY BANK", "AXISBANK": "NIFTY BANK", "INDUSINDBK": "NIFTY BANK",
    "BANDHANBNK": "NIFTY BANK", "PNB": "NIFTY BANK", "BANKBARODA": "NIFTY BANK",
    "FEDERALBNK": "NIFTY BANK", "IDFCFIRSTB": "NIFTY BANK", "AUBANK": "NIFTY BANK",
    "CSBBANK": "NIFTY BANK", "DCBBANK": "NIFTY BANK", "RBLBANK": "NIFTY BANK",
    "YESBANK": "NIFTY BANK", "KARURVYSYA": "NIFTY BANK", "SOUTHBANK": "NIFTY BANK",
    # NIFTY IT
    "TCS": "NIFTY IT", "INFY": "NIFTY IT", "HCLTECH": "NIFTY IT",
    "WIPRO": "NIFTY IT", "TECHM": "NIFTY IT", "LTIM": "NIFTY IT",
    "MPHASIS": "NIFTY IT", "COFORGE": "NIFTY IT", "PERSISTENT": "NIFTY IT",
    "OFSS": "NIFTY IT", "LTTS": "NIFTY IT", "KPIT": "NIFTY IT",
    "TATAELXSI": "NIFTY IT", "NIITTECH": "NIFTY IT", "BSOFT": "NIFTY IT",
    # NIFTY FMCG
    "HINDUNILVR": "NIFTY FMCG", "ITC": "NIFTY FMCG", "NESTLEIND": "NIFTY FMCG",
    "BRITANNIA": "NIFTY FMCG", "DABUR": "NIFTY FMCG", "MARICO": "NIFTY FMCG",
    "GODREJCP": "NIFTY FMCG", "TATACONSUM": "NIFTY FMCG", "COLPAL": "NIFTY FMCG",
    "EMAMILTD": "NIFTY FMCG", "RADICO": "NIFTY FMCG", "VBL": "NIFTY FMCG",
    "JYOTHYLAB": "NIFTY FMCG", "BIKAJI": "NIFTY FMCG", "PATANJALI": "NIFTY FMCG",
    # NIFTY AUTO
    "MARUTI": "NIFTY AUTO", "TATAMOTORS": "NIFTY AUTO", "M&M": "NIFTY AUTO",
    "BAJAJ-AUTO": "NIFTY AUTO", "EICHERMOT": "NIFTY AUTO", "HEROMOTOCO": "NIFTY AUTO",
    "TVSMOTORS": "NIFTY AUTO", "TVSMOTOR": "NIFTY AUTO", "ASHOKLEY": "NIFTY AUTO",
    "BALKRISIND": "NIFTY AUTO", "MOTHERSON": "NIFTY AUTO", "BOSCHLTD": "NIFTY AUTO",
    "EXIDEIND": "NIFTY AUTO", "MRF": "NIFTY AUTO", "APOLLOTYRE": "NIFTY AUTO",
    "AMARAJABAT": "NIFTY AUTO", "CEATLTD": "NIFTY AUTO",
    # NIFTY PHARMA
    "SUNPHARMA": "NIFTY PHARMA", "DRREDDY": "NIFTY PHARMA", "CIPLA": "NIFTY PHARMA",
    "DIVISLAB": "NIFTY PHARMA", "BIOCON": "NIFTY PHARMA", "AUROPHARMA": "NIFTY PHARMA",
    "LUPIN": "NIFTY PHARMA", "ALKEM": "NIFTY PHARMA", "TORNTPHARM": "NIFTY PHARMA",
    "ABBOTINDIA": "NIFTY PHARMA", "IPCALAB": "NIFTY PHARMA", "AJANTPHARM": "NIFTY PHARMA",
    "LAURUSLABS": "NIFTY PHARMA", "GRANULES": "NIFTY PHARMA", "GLENMARK": "NIFTY PHARMA",
    "NATCOPHARM": "NIFTY PHARMA", "JBCHEPHARM": "NIFTY PHARMA",
    # NIFTY METAL
    "TATASTEEL": "NIFTY METAL", "JSWSTEEL": "NIFTY METAL", "HINDALCO": "NIFTY METAL",
    "VEDL": "NIFTY METAL", "COALINDIA": "NIFTY METAL", "NMDC": "NIFTY METAL",
    "SAIL": "NIFTY METAL", "NATIONALUM": "NIFTY METAL", "WELSPUNLIVING": "NIFTY METAL",
    "RATNAMANI": "NIFTY METAL", "JINDALSAW": "NIFTY METAL", "APL": "NIFTY METAL",
    "APLAPOLLO": "NIFTY METAL", "HINDCOPPER": "NIFTY METAL",
    # NIFTY ENERGY
    "RELIANCE": "NIFTY ENERGY", "ONGC": "NIFTY ENERGY", "NTPC": "NIFTY ENERGY",
    "POWERGRID": "NIFTY ENERGY", "BPCL": "NIFTY ENERGY", "IOC": "NIFTY ENERGY",
    "GAIL": "NIFTY ENERGY", "ADANIGREEN": "NIFTY ENERGY", "TATAPOWER": "NIFTY ENERGY",
    "ADANIENT": "NIFTY ENERGY", "CESC": "NIFTY ENERGY", "TORNTPOWER": "NIFTY ENERGY",
    "IGL": "NIFTY ENERGY", "MGL": "NIFTY ENERGY", "PETRONET": "NIFTY ENERGY",
    "HINDPETRO": "NIFTY ENERGY", "MRPL": "NIFTY ENERGY",
}
```

---

### 2.2 Database Schema

Two new tables added in `main.py` lifespan migrations:

```sql
CREATE TABLE IF NOT EXISTS index_prices_daily (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    index_name TEXT NOT NULL,
    date      DATE NOT NULL,
    open      REAL,
    high      REAL,
    low       REAL,
    close     REAL NOT NULL,
    volume    REAL,
    UNIQUE(index_name, date)
);

CREATE TABLE IF NOT EXISTS index_trend (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    index_name  TEXT NOT NULL,
    date        DATE NOT NULL,
    close       REAL NOT NULL,
    sma20       REAL,
    sma50       REAL,
    above_sma20 INTEGER NOT NULL DEFAULT 0,   -- 1 = true
    above_sma50 INTEGER NOT NULL DEFAULT 0,   -- 1 = true
    trend_label TEXT NOT NULL,                -- STRONG_BULL | BULL | NEUTRAL | BEAR
    computed_at DATETIME DEFAULT (datetime('now')),
    UNIQUE(index_name, date)
);
```

---

### 2.3 Index Fetcher

**New file:** `backend/domains/data/index_fetcher.py`

Two functions:

**`fetch_and_store_index_prices(db, days=365)`**
- For each entry in `INDEX_DEFINITIONS`, download last `days` of daily OHLCV via `yfinance.download(yf_symbol, period=f"{days}d")`
- Upsert rows into `index_prices_daily` using `INSERT OR REPLACE`
- Logs success/failure per index; continues on failure

**`compute_index_trends(db)`**
- For each index: load last 60 rows from `index_prices_daily` (enough for SMA50)
- Compute SMA20 and SMA50 on the close series
- Determine `above_sma20`, `above_sma50`
- Assign `trend_label`:
  - `above_sma20=1, above_sma50=1` → `STRONG_BULL`
  - `above_sma20=1, above_sma50=0` → `BULL`
  - `above_sma20=0, above_sma50=1` → `NEUTRAL`
  - `above_sma20=0, above_sma50=0` → `BEAR`
- Upsert today's row into `index_trend`

---

### 2.4 Scheduler

**`backend/scheduler.py`** gets one new job:

```python
# Daily index price update — 4:15 PM IST, after market close
scheduler.add_job(
    _run_daily_index_update,
    CronTrigger(hour=16, minute=15, timezone="Asia/Kolkata"),
    id="DAILY_INDEX_UPDATE",
)
```

`_run_daily_index_update` is defined in `scheduler.py` (same pattern as existing scheduled jobs). It opens a `SessionLocal()`, calls `fetch_and_store_index_prices(db, days=5)` then `compute_index_trends(db)`, then closes the session.

**Bootstrap** (`scripts/bootstrap.py` or `main.py` lifespan): on first run (when `index_prices_daily` is empty), calls `fetch_and_store_index_prices(db, days=365)` then `compute_index_trends(db)`.

---

### 2.5 Opportunity Scorer

**`backend/domains/intelligence/opportunity_scorer.py`**

**Reweighted components:**

| Component | Old | New |
|---|---|---|
| Historical Win Rate | 22% | 20% |
| Strategy Confidence | 18% | 16% |
| Regime Alignment | 16% | 14% |
| MTF Alignment | 14% | 13% |
| Volume | 10% | 9% |
| S/R Context | 8% | 7% |
| ML Probability | 8% | 7% |
| Regime-Strategy | 4% | 4% |
| **Index Alignment** | — | **10%** |
| **Total** | 100% | **100%** |

**Index alignment raw score (0–100):**

| Index state | Score |
|---|---|
| Stock not in `STOCK_INDEX_MAP` | 50 (neutral) |
| Below SMA20 and SMA50 | 15 |
| Below SMA20, above SMA50 | 40 |
| Above SMA20 only | 70 |
| Above SMA20 and SMA50 | 100 |

**Scorer receives** a pre-built `index_trend_map: dict[str, dict]` (index_name → trend row) from the router, avoiding per-signal DB calls.

---

### 2.6 Router Changes

**`backend/domains/intelligence/router.py`** — `get_top_opportunities()`:

Before the scoring loop, add one bulk query:
```python
index_trends = {
    r["index_name"]: r
    for r in db.execute(text("""
        SELECT index_name, above_sma20, above_sma50, trend_label
        FROM index_trend
        WHERE date = (SELECT MAX(date) FROM index_trend)
    """)).mappings()
}
```

Pass `index_trend_map=index_trends` to the scorer. Each scored opportunity gets two new fields populated: `index_name` and `index_trend`.

---

### 2.7 API Response

`TopOpportunity` response schema gains two fields:

```python
index_name: Optional[str]    # e.g. "NIFTY BANK" — None if stock not mapped
index_trend: Optional[str]   # "STRONG_BULL" | "BULL" | "NEUTRAL" | "BEAR" | None
```

The existing `breakdown` dict gains:
```python
"index_alignment": {"score": 100, "weight": 0.10, "contribution": 10.0}
```

---

### 2.8 Frontend

**`frontend/src/api/intelligence.ts`**

Add to `TopOpportunity` interface:
```typescript
index_name: string | null
index_trend: 'STRONG_BULL' | 'BULL' | 'NEUTRAL' | 'BEAR' | null
```

**`frontend/src/components/TopOpportunities.tsx`**

Add `IndexTrendBadge` component inline next to each symbol name:

| trend_label | Display | Style |
|---|---|---|
| STRONG_BULL | `BANK NIFTY ↑↑` | Green solid pill |
| BULL | `BANK NIFTY ↑` | Green outline pill |
| NEUTRAL | `BANK NIFTY →` | Gray pill |
| BEAR | `BANK NIFTY ↓` | Red outline pill |
| null | *(nothing)* | — |

Score breakdown panel gets one new row:
```
Index Alignment   ████████░░  80/100   ×10%  → +8.0 pts
```

No new pages. No new API endpoints beyond what's already described.

---

## Implementation Sequence

1. Expand `NSE_SYMBOLS` in `nse_universe.py` to Nifty 500
2. Create `index_universe.py` with `INDEX_DEFINITIONS` and `STOCK_INDEX_MAP`
3. Add DB table migrations in `main.py` lifespan
4. Create `index_fetcher.py` with `fetch_and_store_index_prices` and `compute_index_trends`
5. Add bootstrap call for index history (first-run guard)
6. Add `DAILY_INDEX_UPDATE` scheduler job
7. Update `opportunity_scorer.py` — reweight + new component
8. Update `router.py` — pre-load index trends, pass to scorer, add fields to response
9. Update `intelligence.ts` TypeScript interface
10. Update `TopOpportunities.tsx` — badge + breakdown row

---

## Out of Scope

- Nifty 500 list auto-refresh from NSE (quarterly rebalances handled manually)
- Multiple indices per stock (one primary index only)
- NIFTY MIDCAP 150 / SMALLCAP 250 as parent indices for mid/small cap stocks
- Index-level strategy signals (the index trend is SMA-based only)
