# Demand & Supply Zone Detection — Design Spec

**Date:** 2026-09-03

---

## Goal

Detect and score demand/supply zones for every stock using multiple detection methods (price structure, moving averages, volume nodes, volatility, momentum, Fibonacci). Pre-compute zones nightly for all stocks. Allow on-demand refresh per stock or for all stocks. Provide optimal entry/exit prices for both long and short setups. Expose results on a dedicated Zones page and as a summary badge on the Opportunities page.

---

## Phase Decomposition

**Phase A (this spec):** Core detection engine, pre-computation pipeline, API, Zones page with stock-centric analysis panel + sortable ranking table. Opportunities badge. No chart overlay or backtesting.

**Phase B (future):** Interactive chart overlay showing zones as coloured bands, zone backtest (historical R:R analysis), VWAP zone detection.

---

## Backend Architecture

New domain: `backend/domains/zones/`

```
backend/domains/zones/
  __init__.py
  models.py          ← ZoneLevel, Zone, ZoneResult dataclasses
  detectors.py       ← All detector classes (price, MA, volume, volatility, momentum, fibonacci)
  clusterer.py       ← ZoneClusterer (merge + pad + deduplicate)
  scorer.py          ← ZoneScorer (0-100 score per zone)
  entry_engine.py    ← EntryEngine (long/short entry, SL, T1/T2/T3, R:R)
  engine.py          ← ZoneEngine (orchestrates all detectors → cluster → score → entry)
  precompute.py      ← ZonePrecomputer (batch pre-compute for all symbols)
  router.py          ← FastAPI router /zones/...
```

This domain has no dependency on `strategies/` or `backtest/`. It depends only on `data/` (prices + indicators).

---

## Detection Methodology

### Raw Level Sources

Seven detector classes, each returning a list of `ZoneLevel(price, zone_type, source_tag, strength_hint, timeframe)`:

| Detector | Method | Guard |
|---|---|---|
| `PriceStructureDetector` | Swing highs/lows (rolling window, default 10 bars). Demand = swing low, supply = swing high | Minimum 3 bars between consecutive levels |
| `MADetector` | EMA9, EMA21, EMA50, SMA200 current values. Demand = MA if price above and recently bounced. Supply = MA if price below and recently rejected | Bounce/rejection ≥2× in last 60 bars |
| `VolumeDetector` | High-volume price nodes (volume ≥ 1.5× 20-day avg). Demand = high-vol bar that was followed by up move; supply = high-vol bar followed by down move | Requires `IndicatorEngine` output |
| `VolatilityDetector` | Bollinger Bands lower band → demand zone; upper band → supply zone | Only emitted when price is within 1 ATR of the band |
| `MomentumDetector` | RSI oversold bounce zones (RSI < 35 then reversal) → demand. RSI overbought rejection (RSI > 65 then reversal) → supply | Level is the closing price at the reversal bar |
| `FibonacciDetector` | Fibonacci retracement levels (23.6%, 38.2%, 50%, 61.8%, 78.6%) from recent major swing. Demand = retracement level in an uptrend; supply = retracement in a downtrend | Only emitted if price reaction observed within 0.3 × ATR of the level |
| `VWAPDetector` | _(Phase B only)_ Session VWAP ± 1σ bands | Requires intraday data |

Each detector works on the computed indicator DataFrame from `IndicatorEngine.compute(df)`.

### Zone Clustering

`ZoneClusterer` takes the full list of raw levels (demand and supply separately) and:

1. Sort by price ascending.
2. Merge any two levels whose prices are within `0.5 × ATR` of each other into one zone.
3. The merged zone's `low = min_price − 0.1 × ATR`, `high = max_price + 0.1 × ATR`.
4. Collect all source tags from merged levels (used for scoring and attribution).
5. Return `Zone(low, high, zone_type, source_tags, touch_count, last_reaction_pct, freshness)`.

`freshness` = `"fresh"` if touch_count == 0 or 1, `"tested"` if 2–3, `"weakened"` if ≥4.

**Position tag rules** (assigned after clustering, based on current price `p` vs zones):
- `in_demand`: p is inside a demand zone (p ≥ zone.low and p ≤ zone.high)
- `in_supply`: p is inside a supply zone
- `near_demand`: p is above the nearest demand zone by ≤1.5 × ATR
- `near_supply`: p is below the nearest supply zone by ≤1.5 × ATR
- `breakout`: p has crossed above the highest supply zone (p > supply_zone.high + 0.2 × ATR), indicating a zone-break in progress — this is distinct from being "near supply"
- `neutral`: none of the above

### Zone Scoring (0–100)

`ZoneScorer` computes a score for each clustered zone from 6 components:

| Component | Max pts | Rationale |
|---|---|---|
| Confirmations (unique source tags) | 30 | More independent methods = stronger zone |
| Reaction quality (last_reaction_pct) | 20 | Larger bounce/rejection from zone = stronger |
| Volume at zone | 15 | High volume when zone was formed |
| Timeframe weight | 15 | Zone derived from weekly > daily > intraday levels |
| Recency | 10 | More recently formed zone scores higher |
| ATR proximity | 10 | Price closer to zone (within 2 ATR) scores higher |

**Correlated-indicator guard:** EMA9 and EMA21 count as 1 unique source (not 2) for the confirmations component. Similarly EMA50 and SMA200 within 1 ATR of each other count as 1.

### Entry Engine

`EntryEngine.compute_long(demand_zone, supply_zones, atr)`:
- **Ideal entry:** zone midpoint
- **Aggressive entry:** zone high (top of demand zone)
- **Conservative entry:** zone low − 0.2 × ATR
- **Stop loss:** zone low − 0.3 × ATR
- **T1:** nearest supply zone low (if within 5 ATR), else +2 ATR
- **T2:** next supply zone low (or +4 ATR fallback)
- **T3:** +6 ATR fallback (or third supply zone)
- **R:R:** (target − ideal_entry) / (ideal_entry − stop_loss) for each target

`EntryEngine.compute_short(supply_zone, demand_zones, atr)`:
- Mirror of above (short sells at supply zone, SL above zone high, targets at demand zones below)

**Setup confidence score:** Separate 0–100 value, distinct from zone strength. Factors: zone strength (40%), R:R (30%), trend alignment (20%), RSI position (10%). A "LONG SETUP — 86/100" means high confidence the long setup will work, not that the zone itself is 86/100 strong.

---

## Data Model

### `zone_analysis_results` Table

Pre-computed results stored as JSON + scalar summary fields for fast ranking queries.

```sql
CREATE TABLE IF NOT EXISTS zone_analysis_results (
    id                  SERIAL PRIMARY KEY,
    symbol              VARCHAR(20) NOT NULL,
    computed_date       DATE NOT NULL,
    best_demand_score   REAL,
    best_supply_score   REAL,
    long_setup_score    REAL,
    short_setup_score   REAL,
    price_at_compute    REAL,
    atr_at_compute      REAL,
    rvol_at_compute     REAL,
    position_tag        VARCHAR(20),   -- 'in_demand' | 'near_demand' | 'near_supply' | 'in_supply' | 'breakout' | 'neutral'
    best_long_rr        REAL,          -- best R:R from long setups (e.g. 3.2 for 1:3.2)
    best_short_rr       REAL,
    result_json         JSONB NOT NULL,  -- full ZoneResult serialized
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (symbol, computed_date)
);

CREATE INDEX IF NOT EXISTS idx_zones_date ON zone_analysis_results (computed_date);
CREATE INDEX IF NOT EXISTS idx_zones_long_score ON zone_analysis_results (computed_date, long_setup_score DESC);
CREATE INDEX IF NOT EXISTS idx_zones_demand_score ON zone_analysis_results (computed_date, best_demand_score DESC);
```

`result_json` schema:
```json
{
  "demand_zones": [
    {
      "low": 970.0, "high": 980.0, "score": 91, "freshness": "fresh",
      "touch_count": 1, "last_reaction_pct": 6.8,
      "source_tags": ["swing_low", "ema_50", "vol_node", "fib_61.8"]
    }
  ],
  "supply_zones": [...],
  "long_setup": {
    "score": 86, "ideal_entry": 974.0, "aggressive_entry": 980.0,
    "conservative_entry": 966.0, "stop_loss": 955.0,
    "t1": 1005.0, "t1_rr": 1.9, "t2": 1035.0, "t2_rr": 3.2,
    "t3": 1070.0, "t3_rr": 5.1,
    "explanation": "Price is 1.1 ATR above a strong demand zone..."
  },
  "short_setup": { ... },
  "market_structure": "bullish" | "bearish" | "sideways",
  "atr": 18.4, "rvol": 1.7
}
```

### On-Demand Refresh

When the user requests analysis for a specific symbol, `ZoneEngine.analyze(symbol, db)`:
1. Loads 500 bars of daily prices from `stock_prices_daily`.
2. Runs `IndicatorEngine.compute(df)`.
3. Runs all detectors → cluster → score → entry engine.
4. Upserts `zone_analysis_results` for `(symbol, today)`.
5. Returns the `ZoneResult`.

No separate cache table needed — the `zone_analysis_results` row is the cache. Re-running overwrites it via `ON CONFLICT (symbol, computed_date) DO UPDATE`.

### Pre-computation Batch

`ZonePrecomputer.run_all(db)` called:
- Nightly by the scheduler (after `daily_eod_update` completes and prices are fresh).
- On `POST /zones/recompute-all` (background task, returns job_id immediately).

Processes all symbols from `SELECT DISTINCT symbol FROM stock_prices_daily` in batches of 50 (to avoid memory spikes). Logs `[zone_precompute] done N/M symbols` every 50.

---

## API Endpoints

All under `/api/v1/zones/`:

| Method | Path | Purpose |
|---|---|---|
| GET | `/zones/analyze/{symbol}` | On-demand: run/refresh zone analysis for one symbol. Returns full ZoneResult JSON. |
| GET | `/zones/results/{symbol}` | Most recent stored result for a symbol (any date, no recompute). 404 if never computed. |
| GET | `/zones/rankings` | All stocks with pre-computed results for today, sorted by long_setup_score DESC. Supports query params: `sort_by` (long_score/short_score/demand_score/supply_score/rvol/atr), `filter` (in_demand/near_supply/breakout/long/short), `limit` (default 200). |
| POST | `/zones/recompute-all` | Enqueue background recompute of all symbols. Returns `{"status": "started", "symbol_count": N}`. |
| GET | `/zones/recompute-status` | Status of last background recompute. Returns `{"done": N, "total": M, "finished": bool, "started_at": "..."}`. |

The `GET /zones/rankings` response row shape:
```json
{
  "rank": 1,
  "symbol": "RELIANCE",
  "long_setup_score": 92,
  "short_setup_score": 45,
  "best_demand_score": 91,
  "best_supply_score": 83,
  "position_tag": "near_demand",
  "price": 1045.0,
  "atr": 18.4,
  "rvol": 1.7,
  "best_long_rr": 3.2,
  "best_short_rr": null,
  "computed_at": "2026-09-03T10:30:00"
}
```

---

## Opportunities Page Integration

`GET /intelligence/top-opportunities` response enriched with a `zone_summary` field per stock:

```json
{
  "zone_summary": {
    "position_tag": "near_demand",
    "best_demand_score": 91,
    "long_setup_score": 86
  }
}
```

This is added by joining `zone_analysis_results` (today's date) to the existing opportunities query. If no zones have been computed for the stock yet, `zone_summary` is `null`. The frontend renders a small badge (e.g. "⚡ Near Demand · 91") next to the stock row.

---

## Frontend Layout

**Page:** `frontend/src/pages/ZonesPage.tsx`  
**Route:** `/zones`  
**Nav link:** Added to NavBar between existing links

### Top Bar

```
[  Demand & Supply Zones  ] [ search input: RELIANCE ] [ Analyze ▶ ]   Last batch: 2h ago · 487 stocks   [ ⟳ Recompute All ]
```

### Stock Analysis Panel (shown after Analyze or clicking a table row)

Three-column layout below a market structure strip:

**Market structure strip:** Symbol · trend badge (BULLISH/BEARISH/SIDEWAYS) · Price · ATR · Volume · RVol · position badge (NEAR DEMAND / IN SUPPLY / etc.) · distance from nearest zone

**Column 1 — Demand Zones (green):** Each zone card shows: price range, score badge, freshness label, touch count, last reaction %, indicator tags (blue chips)

**Column 2 — Supply Zones (red):** Same card structure with red styling

**Column 3 — Setup Panel (blue):**
- Long setup section: score/100, ideal/aggressive/conservative entry, SL, T1/T2/T3 with R:R ratios, plain-English explanation paragraph, invalidation condition
- Short setup section (purple header, collapsed to summary by default)

### Rankings Table

Columns: # | Symbol ↕ | Score ↕ | Position | Setup | Demand ↕ | Supply ↕ | ATR ↕ | RVol ↕ | Computed

- Sortable by any ↕ column (click header to sort asc/desc)
- Filter chips: Long | Short | In Demand | Breakout | Near Supply
- Default sort: long_setup_score DESC
- Clicking a row expands an inline summary row (demand/supply ranges, long entry/SL/T1/RR) + "View full analysis ↑" link that loads the stock into the top analysis panel

### API Module

`frontend/src/api/zones.ts` exports:
- `analyzeZones(symbol)` → full ZoneResult
- `getZoneResult(symbol)` → latest stored result
- `getZoneRankings(params)` → rankings list
- `recomputeAll()` → starts background job
- `getRecomputeStatus()` → job status

---

## Scheduler Integration

In `backend/scheduler.py`, after `daily_eod_update()` completes (prices are fresh), call:

```python
from domains.zones.precompute import ZonePrecomputer
ZonePrecomputer().run_all(db)
```

The batch run is synchronous inside the scheduler task. Expected runtime: ~3–8 minutes for 500 symbols (10–15ms per symbol).

---

## Out of Scope (Phase A)

- Chart overlay with zone bands rendered on a price chart
- Zone backtesting (historical R:R statistics per zone type)
- VWAP-based zones (requires intraday data)
- Multi-timeframe composite zones (weekly + daily merged)
- Zone alerts via Telegram (can be added later, reusing `zones` domain output)
