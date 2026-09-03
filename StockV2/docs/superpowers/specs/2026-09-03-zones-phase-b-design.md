# Demand & Supply Zones Phase B — Chart Overlay, Zone Backtesting, VWAP Zones

## Overview

Phase B extends the Zone Detection Engine (Phase A) with three independent subsystems:

1. **Chart Overlay** — interactive candlestick chart with zone bands and entry/SL/target lines, displayed in a 2/3–1/3 layout alongside the analysis panel
2. **Zone Backtesting** — walk-forward simulation of demand-zone entries against historical price data, with trade-level results stored and displayed in a new Backtest tab
3. **VWAP Zones** — intraday VWAP computed from 5-min bars, integrated into ZoneEngine as an additional zone source

All three subsystems extend the existing ZonesPage; no new pages are added.

---

## Subsystem 1 — Chart Overlay

### Backend

**New endpoint:** `GET /api/v1/zones/chart-data/{symbol}?bars=120`

Located in `backend/domains/zones/router.py`.

Reads `stock_prices_daily` for the last `bars` trading days and the latest `zone_analysis_results.result_json` for the symbol. Returns a combined payload — no new DB table.

Response schema:
```json
{
  "ohlcv": [
    { "date": "2024-01-02", "open": 2900.0, "high": 2950.0, "low": 2880.0, "close": 2940.0, "volume": 1200000 }
  ],
  "demand_bands": [
    { "low": 2800.0, "high": 2840.0, "strength": 85, "zone_type": "demand" }
  ],
  "supply_bands": [
    { "low": 3050.0, "high": 3090.0, "strength": 72, "zone_type": "supply" }
  ],
  "long_setup":  { "entry": 2840.0, "stop_loss": 2790.0, "target": 2960.0 },
  "short_setup": { "entry": 3060.0, "stop_loss": 3100.0, "target": 2930.0 }
}
```

If no zone result exists for the symbol, `demand_bands`, `supply_bands`, `long_setup`, and `short_setup` are omitted (chart still renders OHLCV).

### Frontend

**New dependency:** `lightweight-charts` (TradingView, ~45 KB, canvas-based, no WebSocket required).

**New file:** `frontend/src/components/PriceChart.tsx`

- Mounts a `lightweight-charts` chart in a `useEffect` / `useRef` container
- `CandlestickSeries` for OHLCV data
- Demand zone bands: green `PriceLine` pairs at `low` and `high` with `#16a34a` color, 20% opacity fill (achieved via two horizontal lines with label on the upper line)
- Supply zone bands: red `PriceLine` pairs at `low` and `high` with `#dc2626` color
- Entry line: dashed blue `PriceLine`; stop-loss: dashed red; target: dashed green
- Props: `{ ohlcv, demandBands, supplyBands, longSetup?, shortSetup?, height?: number }`
- Chart resizes on container resize via `ResizeObserver`

**ZonesPage layout change:**

When `AnalysisPanel` is visible (a symbol has been analyzed), the layout switches to a CSS grid:
```
[ PriceChart — 2/3 width ] [ ZoneCard + SetupCard panel — 1/3 width ]
```
No chart is rendered until the user clicks "Analyze" for a symbol.

**API addition:** `getChartData(symbol: string, bars?: number)` added to `frontend/src/api/zones.ts`.

---

## Subsystem 2 — Zone Backtesting

### Walk-Forward Simulation

`ZoneBacktester` in `backend/domains/zones/backtester.py` runs a month-by-month walk-forward simulation:

For each calendar month `M` in `[from_date, to_date]`:
1. Recompute zones using only price history available on the first trading day of `M` (no look-ahead)
2. Simulate entries/exits through the month using those zones

**Entry rule:** Close inside `[zone.low, zone.high]` of any demand zone on day `D` → buy at open of day `D+1`.

**Exit rules** (first condition hit):
1. Close inside any supply zone → sell at open of next day; `exit_reason = "supply_zone"`
2. Close below `zone.low - 0.5 × ATR` → sell at open of next day; `exit_reason = "stop_loss"`
3. 20 consecutive trading days held → sell at open of day 21; `exit_reason = "max_hold"`

Only one open position per symbol at a time. Position sizing is not modelled — trade results are expressed as percentage PnL only.

### DB Tables

Added to `backend/main.py` alongside existing CREATE TABLE blocks:

```sql
CREATE TABLE IF NOT EXISTS zone_backtest_results (
    id            SERIAL PRIMARY KEY,
    symbol        VARCHAR(20) NOT NULL,
    from_date     DATE NOT NULL,
    to_date       DATE NOT NULL,
    total_trades  INTEGER DEFAULT 0,
    win_rate      REAL,
    total_pnl_pct REAL DEFAULT 0,
    avg_hold_days REAL,
    ran_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS zone_backtest_trades (
    id           SERIAL PRIMARY KEY,
    result_id    INTEGER NOT NULL,
    entry_date   DATE,
    entry_price  REAL,
    exit_date    DATE,
    exit_price   REAL,
    pnl_pct      REAL,
    exit_reason  VARCHAR(30),
    hold_days    INTEGER
);

CREATE INDEX IF NOT EXISTS idx_zone_bt_results ON zone_backtest_results (symbol, ran_at DESC);
CREATE INDEX IF NOT EXISTS idx_zone_bt_trades ON zone_backtest_trades (result_id);
```

### Endpoints

Added to `backend/domains/zones/router.py`:

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/zones/backtest/run` | Body: `{symbol, from_date, to_date}` — runs walk-forward, stores result + trades, returns summary |
| GET | `/zones/backtest/results/{symbol}` | List past backtest runs for a symbol (newest first) |
| GET | `/zones/backtest/trades/{result_id}` | Full trade list for a stored result |

### Frontend

New "Backtest" tab in ZonesPage (alongside existing Rankings tab):

- Symbol input + date range pickers (`from_date`, `to_date`) + "Run" button
- While running: spinner / "Simulating…" label
- After completion: summary row — total trades | win rate | avg PnL% | avg hold days
- Past runs dropdown (auto-populated from `getBacktestResults(symbol)`) — selecting a past run loads its trade table
- Trade table: entry date → exit date | PnL% | exit reason badge (color-coded: green for supply_zone exit, amber for max_hold, red for stop_loss)

**API additions** to `frontend/src/api/zones.ts`:
```typescript
export interface BacktestResult { id: number; symbol: string; from_date: string; to_date: string; total_trades: number; win_rate: number | null; total_pnl_pct: number; avg_hold_days: number | null; ran_at: string }
export interface BacktestTrade { id: number; entry_date: string; entry_price: number; exit_date: string | null; exit_price: number | null; pnl_pct: number | null; exit_reason: string; hold_days: number | null }

export const runBacktest = (body: { symbol: string; from_date: string; to_date: string }) => apiFetch<BacktestResult>('/zones/backtest/run', { method: 'POST', body: JSON.stringify(body) })
export const getBacktestResults = (symbol: string) => apiFetch<BacktestResult[]>(`/zones/backtest/results/${symbol}`)
export const getBacktestTrades = (resultId: number) => apiFetch<BacktestTrade[]>(`/zones/backtest/trades/${resultId}`)
```

---

## Subsystem 3 — VWAP Zones

### Intraday Data Fetcher

**New file:** `backend/domains/data/intraday_fetcher.py`

```python
class IntradayFetcher:
    def fetch_and_store(self, symbols: list[str], db: Session) -> None: ...
    def fetch_one(self, symbol: str) -> pd.DataFrame: ...
```

`fetch_one()` calls `yfinance.download(symbol + ".NS", interval="5m", period="5d")` and normalizes column names to lowercase (`open`, `high`, `low`, `close`, `volume`) with a `datetime` column (UTC→IST converted).

`fetch_and_store()` iterates symbols, calls `fetch_one()`, and upserts rows to `intraday_prices_5m`.

### DB Table

```sql
CREATE TABLE IF NOT EXISTS intraday_prices_5m (
    id       SERIAL PRIMARY KEY,
    symbol   VARCHAR(20) NOT NULL,
    datetime TIMESTAMP NOT NULL,
    open     REAL, high REAL, low REAL, close REAL, volume BIGINT,
    UNIQUE (symbol, datetime)
);
CREATE INDEX IF NOT EXISTS idx_intraday_sym_dt ON intraday_prices_5m (symbol, datetime DESC);
```

### VWAP Zone Detector

New class `VWAPZoneDetector` added to `backend/domains/zones/detectors.py`:

```python
class VWAPZoneDetector:
    def detect(self, symbol: str, db: Session, atr: float) -> list[Zone]: ...
```

Logic:
1. Load today's 5-min bars from `intraday_prices_5m` for the symbol
2. If fewer than 6 bars (< 30 min of data): return empty list
3. Compute VWAP: `cumsum((high + low + close) / 3 × volume) / cumsum(volume)`
4. Current VWAP = last bar's running VWAP
5. Band: `[vwap - 0.3 × atr, vwap + 0.3 × atr]`
6. Determine zone type:
   - Current price > VWAP → VWAP acts as support → `zone_type = "demand"`
   - Current price ≤ VWAP → VWAP acts as resistance → `zone_type = "supply"`
7. Return one `Zone(zone_type=..., low=band_low, high=band_high, source="vwap", strength=60)`

### Zone Dataclass Change

`Zone` in `backend/domains/zones/detectors.py` gains a `source: str = "daily"` field. Existing detectors produce zones with `source="daily"` by default; `VWAPZoneDetector` produces zones with `source="vwap"`.

`zone_to_dict()` in `engine.py` manually lists fields, so it must also be updated to include `"source": z.source` alongside the existing keys.

### Integration into ZoneEngine

In `ZoneEngine.analyze()` in `backend/domains/zones/engine.py`, after existing zone detection:

```python
try:
    from .detectors import VWAPZoneDetector
    vwap_zones = VWAPZoneDetector().detect(symbol, db, atr=atr)
    all_zones.extend(vwap_zones)
except Exception:
    pass  # intraday data unavailable; don't block daily analysis
```

### Scheduler Job

New job added to `backend/scheduler.py`: runs at **09:20 IST** (20 min after NSE open, giving enough bars for a stable VWAP).

```python
def _fetch_intraday(db: Session) -> None:
    symbols = [r[0] for r in db.execute(
        text("SELECT DISTINCT symbol FROM stock_prices_daily WHERE date >= CURRENT_DATE - INTERVAL '10 days'")
    ).fetchall()]
    IntradayFetcher().fetch_and_store(symbols, db)
```

Wrapped in the same `try/except/finally` pattern as existing scheduler jobs.

---

## Files Created / Modified

| File | Action |
|------|--------|
| `backend/domains/zones/router.py` | MODIFY — add chart-data endpoint + 3 backtest endpoints |
| `backend/domains/zones/backtester.py` | NEW — ZoneBacktester walk-forward simulation |
| `backend/domains/zones/detectors.py` | MODIFY — add `source` field to Zone, add VWAPZoneDetector |
| `backend/domains/zones/engine.py` | MODIFY — call VWAPZoneDetector, add `"source": z.source` to `zone_to_dict` |
| `backend/domains/data/intraday_fetcher.py` | NEW — IntradayFetcher (yfinance 5-min) |
| `backend/main.py` | MODIFY — add 3 new tables (intraday_prices_5m, zone_backtest_results, zone_backtest_trades) |
| `backend/scheduler.py` | MODIFY — add 09:20 intraday fetch job |
| `frontend/src/api/zones.ts` | MODIFY — add getChartData, runBacktest, getBacktestResults, getBacktestTrades |
| `frontend/src/components/PriceChart.tsx` | NEW — lightweight-charts candlestick + zone bands |
| `frontend/src/pages/ZonesPage.tsx` | MODIFY — layout B (2/3 chart / 1/3 panel), Backtest tab |

---

## Verification

1. `GET /api/v1/zones/chart-data/RELIANCE?bars=60` returns `ohlcv` array with 60 rows and `demand_bands` / `supply_bands` from the latest zone result
2. ZonesPage: after clicking "Analyze", chart appears on the left with colored horizontal band overlays at each zone's price levels
3. `POST /api/v1/zones/backtest/run` with `{"symbol":"RELIANCE","from_date":"2023-01-01","to_date":"2024-12-31"}` returns a result with `total_trades > 0` and `exit_reason` values in `{supply_zone, stop_loss, max_hold}`
4. ZonesPage Backtest tab: entering RELIANCE + date range + Run populates the summary row and trade table
5. `intraday_prices_5m` table populates after the scheduler's 09:20 job runs (or calling `IntradayFetcher().fetch_and_store()` manually)
6. After intraday data is present, `ZoneEngine.analyze("RELIANCE", db)` returns at least one zone with `source="vwap"`
