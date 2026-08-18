# Phase F: Fundamentals Pipeline + Fundamental Strategies — Design Spec

**Goal:** Populate the `fundamentals` table via yfinance and add 6 fundamental-based trading strategies (CANSLIM, Magic Formula, Graham Value, Growth, Dividend, FII/DII Accumulation) that plug into the existing strategy engine.

**Architecture:** One new `FundamentalsService` fetches data via yfinance weekly. Six new `BaseStrategy` subclasses read from the `fundamentals` dict already passed to `generate_signal()`. No new pages — new strategies auto-appear in Scanner, Leaderboard, and Dashboard via existing `ALL_STRATEGIES` wiring.

**Tech Stack:** Python + yfinance + SQLAlchemy (backend), FastAPI (new refresh endpoint), existing React frontend (no changes needed for strategy exposure).

---

## Backend Changes

### 1. FundamentalsService

**File:** `backend/domains/data/fundamentals.py`

Fetches and upserts fundamental data for all NSE stocks using `yfinance`.

**Fields fetched per symbol** via `yf.Ticker(symbol + ".NS").info`:

| Field | yfinance key | DB column |
|---|---|---|
| P/E ratio | `trailingPE` | `pe_ratio` |
| P/B ratio | `priceToBook` | `pb_ratio` |
| EPS (TTM) | `trailingEps` | `eps` |
| Revenue (TTM) | `totalRevenue` | `revenue` |
| Net profit | `netIncomeToCommon` | `net_profit` |
| Debt/Equity | `debtToEquity` | `debt_equity` |
| ROE | `returnOnEquity` | `roe` |
| Market cap | `marketCap` | `market_cap` |
| As-of date | fetched at | `data_as_of` |

Quarterly revenue and EPS growth are computed from `yf.Ticker(...).quarterly_financials` if available.

**Interface:**

```python
class FundamentalsService:
    def __init__(self, db: Session): ...

    def refresh_all(self, symbols: list[str]) -> dict:
        """Fetch and upsert fundamentals for every symbol. Returns {updated, skipped, errors}."""

    def refresh_one(self, symbol: str) -> bool:
        """Fetch and upsert one symbol. Returns True on success."""

    def get_latest(self, symbol: str) -> dict:
        """Return latest fundamentals row as dict. Returns {} if no data."""
```

**Implementation notes:**
- Use `try/except` per symbol — one bad symbol must not abort the whole run
- `INSERT OR REPLACE INTO fundamentals` on `(symbol, date)` unique key
- `data_as_of` = today's date (IST)
- No rate-limit delay needed (yfinance handles internally, but add 0.3s sleep per symbol as courtesy)
- Log progress every 50 symbols

---

### 2. APScheduler Job

**File:** `backend/scheduler.py` (modify existing)

Add a weekly job:

```python
scheduler.add_job(
    _refresh_fundamentals,
    CronTrigger(day_of_week="sun", hour=20, minute=0, timezone="Asia/Kolkata"),
    id="refresh_fundamentals",
    replace_existing=True,
)
```

`_refresh_fundamentals()` opens a DB session, fetches the symbol list from `nse_universe.py`, instantiates `FundamentalsService`, and calls `refresh_all()`.

---

### 3. New API Endpoints

**File:** `backend/domains/data/router.py` (modify existing)

#### `POST /data/fundamentals/refresh`
Triggers a background refresh of all fundamentals. Returns immediately.

```json
{ "status": "started", "symbols": 237 }
```

Runs `FundamentalsService.refresh_all()` in a `threading.Thread(daemon=True)`.

#### `GET /data/fundamentals/{symbol}`
Returns the latest row from the `fundamentals` table for a symbol.

**Response:**
```json
{
  "symbol": "RELIANCE",
  "pe_ratio": 24.5,
  "pb_ratio": 2.1,
  "eps": 95.3,
  "revenue": 874000000000,
  "net_profit": 64640000000,
  "debt_equity": 0.43,
  "roe": 0.118,
  "market_cap": 1650000000000,
  "data_as_of": "2026-08-18"
}
```

Returns `404` if no data exists for the symbol.

---

### 4. Strategy Engine — Fundamentals Integration

**File:** `backend/domains/strategies/engine.py` (modify existing)

The `StrategyEngine` already passes a `fundamentals` dict to `generate_signal()`. Verify the dict is populated from the `fundamentals` table (or empty dict `{}` if not fetched). Each strategy must handle `{}` gracefully by returning `NONE`.

If the existing engine does not pass fundamentals, add a lookup:

```python
fundamentals = FundamentalsService(self.db).get_latest(symbol)
signal = strategy.generate_signal(df, fundamentals)
```

---

### 5. Six Fundamental Strategies

All files in `backend/domains/strategies/strategies/`.

#### 5a. CANSLIM (`canslim.py`)

Implements William O'Neil's CANSLIM framework using available data:

- **C** — Current quarterly EPS growth > 25% YoY
- **A** — Annual EPS growth > 25% over past 3 years
- **N** — Price within 10% of 52-week high
- **S** — Volume above 20-day average (institutional accumulation proxy)
- **L** — ROE > 15% (leader quality proxy)
- **M** — Price above 200-day SMA (market uptrend proxy)

**Signal:** BUY if ≥ 5 of 6 criteria met. Confidence = criteria_met / 6.

**Data requirement:** `eps` and `roe` from fundamentals; price/volume from `df`. Returns `NONE` if fundamentals dict is empty.

#### 5b. Magic Formula (`magic_formula.py`)

Greenblatt's Magic Formula: rank stocks by earnings yield and return on capital.

**This strategy is stock-universe-aware.** At signal generation time it cannot rank across all stocks, so it uses absolute thresholds instead of universe ranking:

- Earnings Yield = EPS / price > 6% (proxy for EBIT/EV)
- ROE > 15% (proxy for return on capital)
- PE ratio < 20
- D/E < 1.0

**Signal:** BUY if all 4 conditions met. Confidence = 0.75 (fixed — no universe ranking available per-signal).

**Data requirement:** `eps`, `roe`, `pe_ratio`, `debt_equity`.

#### 5c. Graham Value (`graham_value.py`)

Based on Benjamin Graham's value investing criteria.

- Graham Number = √(22.5 × EPS × Book Value per share)
- Book Value per share estimated as: price / pb_ratio
- BUY if: price < 1.3 × Graham Number AND PE < 15 AND PB < 1.5

**Signal:** BUY when all 3 met. Confidence = 1 − (price / graham_number − 1) clamped to [0.4, 1.0].

**Data requirement:** `eps`, `pe_ratio`, `pb_ratio`.

#### 5d. Growth Investing (`growth_investing.py`)

GARP (Growth at a Reasonable Price) criteria:

- Revenue growth (TTM vs prior year) > 20%
- EPS growth (TTM vs prior year) > 20%
- ROE > 15%
- D/E < 1.0
- PE < 40 (not wildly overvalued)

**Signal:** BUY if ≥ 4 of 5 criteria met. Confidence = criteria_met / 5.

**Data requirement:** `revenue`, `eps`, `roe`, `debt_equity`, `pe_ratio`.

Revenue/EPS growth is computed as `(ttm - prev) / abs(prev)` if both quarterly financials available; if prior-year data is unavailable, that criterion counts as **not met** (conservative).

#### 5e. Dividend Investing (`dividend_investing.py`)

Targets high-quality dividend payers:

- Dividend yield > 2% (`yf.Ticker().info["dividendYield"]`)
- Payout sustainable: `(dividend per share / EPS) < 0.8`
- ROE > 12%
- D/E < 0.5

**Signal:** BUY if all 4 met. Confidence = 0.7 (fixed).

**Data requirement:** `eps`, `roe`, `debt_equity` from fundamentals; `dividendYield` fetched fresh via yfinance in `FundamentalsService.refresh_one()` and stored as an extra field.

`fundamentals` dict gains one extra field: `dividend_yield: float | None`.

#### 5f. FII/DII Accumulation (`fii_dii_accumulation.py`)

Detects institutional buying using volume and price patterns as proxies (since FII/DII % data is not available via yfinance):

- Volume > 1.5× 20-day average for 3 of last 5 days (accumulation proxy)
- Price closed above 50-day SMA for 3 of last 5 days
- RSI between 40 and 70 (not overbought/oversold)
- No fundamentals data required (purely technical, triggered by institutional-accumulation price/volume patterns)

**Signal:** BUY if all 3 conditions met. Confidence = 0.65 (fixed).

**Note on naming:** Named `fii_dii_accumulation` to match the spec intent, but uses technical signals as FII/DII proxy since actual % data isn't available via yfinance.

---

### 6. Strategy Seeding

**File:** `backend/domains/strategies/seed.py` (modify existing)

Add entries for all 6 new strategies with `type = "fundamental"`. They are seeded at startup alongside existing strategies.

---

## Testing

**File:** `backend/tests/test_fundamentals_service.py`

- `test_refresh_one_stores_row` — mock `yf.Ticker`, verify row inserted to `fundamentals`
- `test_get_latest_returns_dict` — insert row, call `get_latest()`, verify fields match
- `test_get_latest_empty_when_no_data` — verify returns `{}` not error

**File:** `backend/tests/test_fundamental_strategies.py`

For each of the 6 strategies:
- `test_<strategy>_buy_signal` — pass a row meeting all criteria → assert `signal_type == "BUY"`
- `test_<strategy>_no_signal_missing_fundamentals` — pass empty `fundamentals={}` → assert `signal_type == "NONE"`
- `test_<strategy>_no_signal_criteria_not_met` — pass row failing criteria → assert `signal_type == "NONE"`

---

## What Is NOT Changing

- No new frontend pages
- No changes to `IndicatorEngine` (fundamentals are separate from technical indicators)
- No Screener.in scraping
- No NSE corporate actions feed (deferred)
- The `FII/DII Net Buying` strategy from the original spec spec is implemented as `fii_dii_accumulation` using technical proxies — actual FII/DII % tracking deferred to Phase G/H
