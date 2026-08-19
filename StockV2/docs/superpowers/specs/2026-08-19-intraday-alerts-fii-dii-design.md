# Intraday Entry-Window Alerts + FII/DII Context

**Date:** 2026-08-19
**Status:** Approved

## Overview

Two additive features that make Telegram alerts actionable in real time:

1. **Intraday entry-window alerts** — every 15 min during trading hours, fetch live prices for pre-qualified BUY signal stocks, fire an immediate Telegram alert the moment a stock's current price is within ±2% of its signal entry level. Deduplicates so each (symbol, strategy, signal_date) alerts once per day.

2. **FII/DII context** — fetch NSE participant-wise flow data daily after market close, store it, and append a one-line FII/DII summary to every entry-window alert. Context only — does not affect scores.

Both features are additive. Existing fixed-time digest jobs are untouched.

---

## Feature 1: Intraday Entry-Window Alerts

### Architecture

The existing `INTRADAY_SCAN` scheduler job (every 15 min, 9 AM–3 PM IST, Mon–Fri) already runs all strategies on daily bars and produces BUY signals. We extend it with a second phase:

1. **Collect** active BUY signals from today's scan (symbol, strategy_id, entry_price, stop_loss, target, confidence, win_rate, score, grade)
2. **Fetch live LTP** only for those pre-qualified symbols (5–30 stocks, not all 353) via yfinance `fast_info`
3. **Entry window check**: `abs(current_price - entry_price) / entry_price <= 0.02`
4. **Dedup check**: query `intraday_alerts_sent` — if (symbol, strategy_id, signal_date) exists, skip
5. **Alert**: call `AlertService.send_entry_alert(signal, current_price, fii_dii_row)` → individual Telegram message
6. **Record**: insert into `intraday_alerts_sent`

### 1.1 New DB Table

Added in `main.py` lifespan migrations:

```sql
CREATE TABLE IF NOT EXISTS intraday_alerts_sent (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol      TEXT NOT NULL,
    strategy_id INTEGER NOT NULL,
    signal_date DATE NOT NULL,
    alerted_at  DATETIME DEFAULT (datetime('now')),
    UNIQUE(symbol, strategy_id, signal_date)
)
```

### 1.2 Live Price Fetcher

**New file:** `backend/domains/data/live_price_fetcher.py`

```python
def fetch_live_prices(symbols: list[str]) -> dict[str, float]:
    """
    Returns {symbol: current_price} for each symbol.
    Uses yfinance fast_info (single HTTP call per symbol).
    Returns empty dict entry (symbol absent) on failure — caller handles missing.
    """
```

Implementation: iterate symbols, call `yf.Ticker(f"{sym}.NS").fast_info["last_price"]`. Catches per-symbol exceptions and continues. Returns only successful lookups.

### 1.3 Entry-Window Checker

**New file:** `backend/domains/alerts/entry_window.py`

```python
ENTRY_WINDOW_PCT = 0.02  # ±2%

def get_signals_in_entry_window(
    db: Session,
    scan_results: list[dict],
    live_prices: dict[str, float],
) -> list[dict]:
    """
    Returns signals where:
    - current price is within ENTRY_WINDOW_PCT of entry price
    - (symbol, strategy_id, signal_date) not already in intraday_alerts_sent
    """
```

### 1.4 Telegram Alert Method

**`backend/domains/alerts/telegram.py`** — add `send_entry_alert()`:

```
🚨 Entry Window Open — {SYMBOL}

Signal:     {strategy_name} ({win_rate}% win rate)
Entry:      ₹{current_price:.1f} (signal ₹{entry_price:.1f}, {pct:+.1f}%)
Target:     ₹{target:.1f} ({target_upside:+.1f}%)
Stop Loss:  ₹{stop_loss:.1f} ({sl_pct:.1f}%)
Score:      {score}/100 [{grade}]
Regime:     {regime}

{fii_dii_line}
```

`fii_dii_line` = `"FII/DII (today): FII {fii_net:+,.0f} Cr | DII {dii_net:+,.0f} Cr {emoji}"` or `""` if no data.

### 1.5 Scheduler Change

**`backend/scheduler.py`** — extend `_intraday_scan()`:

After the existing scan logic, add the second phase:
```python
from domains.alerts.entry_window import get_signals_in_entry_window
from domains.data.live_price_fetcher import fetch_live_prices
from domains.alerts.telegram import AlertService

# Collect symbols with BUY signals
buy_signals = [r for r in scan_results if r.get("signal_type") == "BUY"]
if buy_signals:
    symbols = list({r["symbol"] for r in buy_signals})
    live_prices = fetch_live_prices(symbols)
    fii_dii_row = _get_latest_fii_dii(db)
    in_window = get_signals_in_entry_window(db, buy_signals, live_prices)
    for signal in in_window:
        AlertService().send_entry_alert(signal, live_prices[signal["symbol"]], fii_dii_row)
        db.execute(text("""
            INSERT OR IGNORE INTO intraday_alerts_sent (symbol, strategy_id, signal_date)
            VALUES (:sym, :sid, :date)
        """), {"sym": signal["symbol"], "sid": signal["strategy_id"], "date": signal["signal_date"]})
    db.commit()
```

`_get_latest_fii_dii(db)` is defined in `fii_dii_fetcher.py` — reads the latest row from `fii_dii_daily` (returns `dict | None`).

---

## Feature 2: FII/DII Context

### 2.1 New DB Table

```sql
CREATE TABLE IF NOT EXISTS fii_dii_daily (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    date            DATE NOT NULL UNIQUE,
    fii_net_equity  REAL,   -- ₹ Cr, positive = net buy
    dii_net_equity  REAL,
    fii_buy         REAL,
    fii_sell        REAL,
    dii_buy         REAL,
    dii_sell        REAL,
    fetched_at      DATETIME DEFAULT (datetime('now'))
)
```

### 2.2 FII/DII Fetcher

**New file:** `backend/domains/data/fii_dii_fetcher.py`

```python
def fetch_and_store_fii_dii(db: Session) -> None:
    """
    Fetches today's FII/DII participant data from NSE and upserts into fii_dii_daily.
    NSE endpoint: https://www.nseindia.com/api/fiidiiTradeReact
    Requires browser-like headers + session cookie to bypass NSE bot protection.
    """
```

NSE requires a two-step fetch:
1. GET `https://www.nseindia.com` to establish session cookie
2. GET `https://www.nseindia.com/api/fiidiiTradeReact` with that cookie + headers

Headers required:
```python
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}
```

The API returns a list of participant rows. Filter for `"FII/FPI"` and `"DII"` categories, sum `buyValue` and `sellValue` for equity segment. Net = buy - sell.

On HTTP failure or parse error: log warning, return without inserting (no crash).

### 2.3 Scheduler Job

**`backend/scheduler.py`** — add `FII_DII_FETCH` job:

```python
class JobIds:
    FII_DII_FETCH = "fii_dii_fetch"

def _fii_dii_fetch():
    """Fetch NSE FII/DII participant data after market close."""
    ...

# In register_jobs():
scheduler.add_job(
    _fii_dii_fetch,
    CronTrigger(hour=16, minute=35, day_of_week="mon-fri"),
    id=JobIds.FII_DII_FETCH,
    replace_existing=True,
)
```

Runs at 4:35 PM IST — after `DAILY_DATA_REFRESH` (3:45 PM) and `DAILY_EOD_UPDATE` (4:00 PM).

---

## File Map

| Action | File | Responsibility |
|---|---|---|
| Modify | `backend/main.py` | Add `intraday_alerts_sent` + `fii_dii_daily` migrations |
| Create | `backend/domains/data/live_price_fetcher.py` | Bulk yfinance LTP fetch |
| Create | `backend/domains/data/fii_dii_fetcher.py` | NSE FII/DII fetch + upsert + `get_latest_fii_dii()` |
| Create | `backend/domains/alerts/entry_window.py` | Entry-window filter + dedup logic |
| Modify | `backend/domains/alerts/telegram.py` | Add `send_entry_alert()` method |
| Modify | `backend/scheduler.py` | Extend `_intraday_scan()`, add `FII_DII_FETCH` job |

---

## Error Handling

- **yfinance live fetch fails for a symbol** → skip that symbol, alert the rest
- **All live prices fail** → log warning, skip entry-window phase for this cycle
- **NSE FII/DII endpoint fails** → log warning, entry-window alerts still fire without FII/DII line
- **Duplicate alert insert** → `INSERT OR IGNORE` silently skips
- **No BUY signals** → entry-window phase exits immediately, no network calls made

---

## Out of Scope

- Per-stock or per-sector FII/DII breakdown (not available free)
- Modifying the 5 fixed-time digest jobs
- Changing how signals are generated (daily bars only)
- Entry window threshold configuration via UI (hardcoded ±2%)
- Historical FII/DII backfill
