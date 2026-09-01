# Intraday Entry-Window Alerts + FII/DII Context Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fire immediate Telegram alerts when a pre-qualified BUY signal stock enters its entry price window (±2%) during trading hours, enriched with NSE FII/DII flow context.

**Architecture:** The existing `INTRADAY_SCAN` job (every 15 min) is extended with a second phase: fetch live 5-min prices from yfinance for BUY-signal stocks, check entry window, deduplicate via `intraday_alerts_sent` table, alert. A separate `FII_DII_FETCH` job at 4:35 PM fetches NSE participant-wise data and stores it for same-day alert enrichment.

**Tech Stack:** Python/FastAPI backend, SQLite/SQLAlchemy, yfinance, httpx, APScheduler, existing Telegram AlertService.

---

## File Map

| Action | File | Responsibility |
|---|---|---|
| Modify | `backend/main.py` | Add `intraday_alerts_sent` + `fii_dii_daily` table migrations |
| Create | `backend/domains/data/live_price_fetcher.py` | Bulk yfinance 5-min LTP fetch |
| Create | `backend/domains/data/fii_dii_fetcher.py` | NSE FII/DII fetch + upsert + `get_latest_fii_dii()` |
| Create | `backend/domains/alerts/entry_window.py` | Entry-window filter + dedup against DB |
| Modify | `backend/domains/alerts/telegram.py` | Add `send_entry_alert()` method |
| Modify | `backend/scheduler.py` | Extend `_intraday_scan()`, add `FII_DII_FETCH` job |
| Create | `backend/tests/test_live_price_fetcher.py` | Unit tests for live price fetcher |
| Create | `backend/tests/test_fii_dii_fetcher.py` | Unit tests for FII/DII parser |
| Create | `backend/tests/test_entry_window.py` | Unit tests for entry-window logic |

---

### Task 1: DB migrations

**Files:**
- Modify: `backend/main.py`

- [ ] **Step 1: Read main.py to find the last migration block**

Read `backend/main.py` and find the "Index pipeline tables" try block (the last `CREATE TABLE IF NOT EXISTS` block). You will insert after it.

- [ ] **Step 2: Add two new table migrations**

After the index pipeline tables block, add:

```python
    # Intraday alert dedup + FII/DII tables
    try:
        with engine.connect() as _conn:
            _conn.execute(text("""
                CREATE TABLE IF NOT EXISTS intraday_alerts_sent (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol      TEXT NOT NULL,
                    strategy_id INTEGER NOT NULL,
                    signal_date DATE NOT NULL,
                    alerted_at  DATETIME DEFAULT (datetime('now')),
                    UNIQUE(symbol, strategy_id, signal_date)
                )
            """))
            _conn.execute(text("""
                CREATE TABLE IF NOT EXISTS fii_dii_daily (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    date            DATE NOT NULL UNIQUE,
                    fii_net_equity  REAL,
                    dii_net_equity  REAL,
                    fii_buy         REAL,
                    fii_sell        REAL,
                    dii_buy         REAL,
                    dii_sell        REAL,
                    fetched_at      DATETIME DEFAULT (datetime('now'))
                )
            """))
            _conn.commit()
        logger.info("Intraday alert + FII/DII tables verified")
    except Exception as e:
        logger.warning("intraday/fii_dii table migration skipped: %s", e)
```

- [ ] **Step 3: Verify**

```bash
cd C:/DLP_Repos/MyRepo/StockV2/backend && python -c "
from database import engine
from sqlalchemy import inspect
tables = inspect(engine).get_table_names()
assert 'intraday_alerts_sent' in tables, f'missing intraday_alerts_sent, tables={tables}'
assert 'fii_dii_daily' in tables, f'missing fii_dii_daily, tables={tables}'
print('Tables OK')
"
```

- [ ] **Step 4: Commit**

```bash
git -C C:/DLP_Repos/MyRepo/StockV2 add backend/main.py
git -C C:/DLP_Repos/MyRepo/StockV2 commit -m "feat: add intraday_alerts_sent and fii_dii_daily DB migrations"
```

---

### Task 2: Live price fetcher

**Files:**
- Create: `backend/domains/data/live_price_fetcher.py`
- Create: `backend/tests/test_live_price_fetcher.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_live_price_fetcher.py`:

```python
"""Tests for live_price_fetcher."""
import pandas as pd
from unittest.mock import patch


def test_fetch_live_prices_empty_symbols():
    from domains.data.live_price_fetcher import fetch_live_prices
    assert fetch_live_prices([]) == {}


def test_fetch_live_prices_single_symbol():
    from domains.data.live_price_fetcher import fetch_live_prices
    mock_df = pd.DataFrame({"Close": [100.0, 101.0, 102.5]})
    with patch("domains.data.live_price_fetcher.yf.download", return_value=mock_df) as mock_dl:
        result = fetch_live_prices(["RELIANCE"])
    mock_dl.assert_called_once()
    assert result == {"RELIANCE": 102.5}


def test_fetch_live_prices_handles_download_exception():
    from domains.data.live_price_fetcher import fetch_live_prices
    with patch("domains.data.live_price_fetcher.yf.download", side_effect=Exception("network")):
        result = fetch_live_prices(["RELIANCE"])
    assert result == {}


def test_fetch_live_prices_handles_empty_dataframe():
    from domains.data.live_price_fetcher import fetch_live_prices
    with patch("domains.data.live_price_fetcher.yf.download", return_value=pd.DataFrame()):
        result = fetch_live_prices(["RELIANCE"])
    assert result == {}


def test_fetch_live_prices_multi_symbol():
    from domains.data.live_price_fetcher import fetch_live_prices
    # Multi-symbol returns MultiIndex DataFrame: columns = (yf_symbol, field)
    import pandas as pd
    arrays = [["RELIANCE.NS", "RELIANCE.NS", "SBIN.NS", "SBIN.NS"],
              ["Close", "Open", "Close", "Open"]]
    mi = pd.MultiIndex.from_arrays(arrays)
    mock_df = pd.DataFrame([[500.0, 495.0, 800.0, 795.0]], columns=mi)
    with patch("domains.data.live_price_fetcher.yf.download", return_value=mock_df):
        result = fetch_live_prices(["RELIANCE", "SBIN"])
    assert result["RELIANCE"] == 500.0
    assert result["SBIN"] == 800.0
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd C:/DLP_Repos/MyRepo/StockV2/backend && python -m pytest tests/test_live_price_fetcher.py -v 2>&1 | head -20
```
Expected: `ModuleNotFoundError` — file not created yet.

- [ ] **Step 3: Create live_price_fetcher.py**

Create `backend/domains/data/live_price_fetcher.py`:

```python
"""Fetches live intraday prices for a list of NSE symbols via yfinance."""
import logging
from typing import Optional

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)


def fetch_live_prices(symbols: list[str]) -> dict[str, float]:
    """
    Returns {symbol: latest_price} for each symbol using the most recent 5-min close.
    Symbols absent from the result had a fetch error — callers must handle missing keys.
    """
    if not symbols:
        return {}

    yf_symbols = [f"{s}.NS" for s in symbols]
    try:
        data = yf.download(
            yf_symbols if len(yf_symbols) > 1 else yf_symbols[0],
            period="1d",
            interval="5m",
            progress=False,
            auto_adjust=True,
            group_by="ticker",
        )
    except Exception:
        logger.exception("[live_price] yfinance download failed for %d symbols", len(symbols))
        return {}

    if data is None or (isinstance(data, pd.DataFrame) and data.empty):
        logger.warning("[live_price] empty response for symbols: %s", symbols)
        return {}

    result: dict[str, float] = {}

    if len(symbols) == 1:
        # Single symbol: flat columns (Close, Open, ...)
        try:
            closes = data["Close"].dropna()
            if not closes.empty:
                result[symbols[0]] = float(closes.iloc[-1])
        except (KeyError, IndexError):
            logger.warning("[live_price] no Close data for %s", symbols[0])
    else:
        # Multiple symbols: MultiIndex columns (yf_symbol, field)
        for sym, yf_sym in zip(symbols, yf_symbols):
            try:
                closes = data[yf_sym]["Close"].dropna()
                if not closes.empty:
                    result[sym] = float(closes.iloc[-1])
            except (KeyError, IndexError):
                logger.debug("[live_price] no data for %s", sym)

    logger.info("[live_price] fetched %d/%d symbols", len(result), len(symbols))
    return result
```

- [ ] **Step 4: Run tests — all should pass**

```bash
cd C:/DLP_Repos/MyRepo/StockV2/backend && python -m pytest tests/test_live_price_fetcher.py -v
```
Expected: 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git -C C:/DLP_Repos/MyRepo/StockV2 add backend/domains/data/live_price_fetcher.py backend/tests/test_live_price_fetcher.py
git -C C:/DLP_Repos/MyRepo/StockV2 commit -m "feat: add live_price_fetcher for intraday LTP via yfinance"
```

---

### Task 3: FII/DII fetcher

**Files:**
- Create: `backend/domains/data/fii_dii_fetcher.py`
- Create: `backend/tests/test_fii_dii_fetcher.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_fii_dii_fetcher.py`:

```python
"""Tests for fii_dii_fetcher parse logic."""


def test_parse_fii_dii_response_flat():
    from domains.data.fii_dii_fetcher import _parse_fii_dii_response
    rows = [
        {"category": "FII/FPI", "buyValue": "8420.10", "sellValue": "7179.60", "netValue": "1240.50", "date": "19-Aug-2026"},
        {"category": "DII",     "buyValue": "4210.30", "sellValue": "3530.10", "netValue":  "680.20", "date": "19-Aug-2026"},
        {"category": "PRO",     "buyValue":  "100.00", "sellValue":  "120.00", "netValue":  "-20.00", "date": "19-Aug-2026"},
    ]
    result = _parse_fii_dii_response(rows)
    assert result is not None
    assert result["fii_net_equity"] == 1240.50
    assert result["fii_buy"] == 8420.10
    assert result["fii_sell"] == 7179.60
    assert result["dii_net_equity"] == 680.20
    assert result["dii_buy"] == 4210.30
    assert result["dii_sell"] == 3530.10


def test_parse_fii_dii_response_clienttype_key():
    """NSE sometimes returns 'clientType' instead of 'category'."""
    from domains.data.fii_dii_fetcher import _parse_fii_dii_response
    rows = [
        {"clientType": "FII/FPI", "buyValue": "5000.00", "sellValue": "4000.00", "netValue": "1000.00"},
        {"clientType": "DII",     "buyValue": "2000.00", "sellValue": "1500.00", "netValue":  "500.00"},
    ]
    result = _parse_fii_dii_response(rows)
    assert result is not None
    assert result["fii_net_equity"] == 1000.00
    assert result["dii_net_equity"] == 500.00


def test_parse_fii_dii_response_no_relevant_rows():
    from domains.data.fii_dii_fetcher import _parse_fii_dii_response
    rows = [{"category": "CLIENT", "buyValue": "100.00", "sellValue": "90.00", "netValue": "10.00"}]
    result = _parse_fii_dii_response(rows)
    assert result is None


def test_parse_fii_dii_response_empty():
    from domains.data.fii_dii_fetcher import _parse_fii_dii_response
    assert _parse_fii_dii_response([]) is None


def test_parse_fii_dii_response_comma_values():
    """Values like '8,420.10' must be parsed correctly."""
    from domains.data.fii_dii_fetcher import _parse_fii_dii_response
    rows = [
        {"category": "FII/FPI", "buyValue": "8,420.10", "sellValue": "7,179.60", "netValue": "1,240.50"},
        {"category": "DII",     "buyValue": "4,210.30", "sellValue": "3,530.10", "netValue":   "680.20"},
    ]
    result = _parse_fii_dii_response(rows)
    assert result is not None
    assert abs(result["fii_net_equity"] - 1240.50) < 0.01
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd C:/DLP_Repos/MyRepo/StockV2/backend && python -m pytest tests/test_fii_dii_fetcher.py -v 2>&1 | head -20
```
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Create fii_dii_fetcher.py**

Create `backend/domains/data/fii_dii_fetcher.py`:

```python
"""NSE FII/DII participant-wise equity flow fetcher."""
import logging
from datetime import date
from typing import Optional

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_NSE_HOME = "https://www.nseindia.com"
_NSE_FII_DII_URL = "https://www.nseindia.com/api/fiidiiTradeReact"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}


def _parse_fii_dii_response(rows: list[dict]) -> Optional[dict]:
    """
    Parse the flat list returned by NSE fiidiiTradeReact.
    Returns dict with fii_*/dii_* keys or None if no relevant rows found.
    NSE uses either 'category' or 'clientType' as the participant key.
    """
    def _key(row: dict) -> str:
        return (row.get("category") or row.get("clientType") or "").upper()

    def _float(val) -> Optional[float]:
        try:
            return float(str(val).replace(",", ""))
        except (TypeError, ValueError):
            return None

    fii_row = next((r for r in rows if "FII" in _key(r)), None)
    dii_row = next((r for r in rows if _key(r) == "DII"), None)

    if not fii_row and not dii_row:
        return None

    return {
        "fii_buy":        _float(fii_row.get("buyValue"))  if fii_row else None,
        "fii_sell":       _float(fii_row.get("sellValue")) if fii_row else None,
        "fii_net_equity": _float(fii_row.get("netValue"))  if fii_row else None,
        "dii_buy":        _float(dii_row.get("buyValue"))  if dii_row else None,
        "dii_sell":       _float(dii_row.get("sellValue")) if dii_row else None,
        "dii_net_equity": _float(dii_row.get("netValue"))  if dii_row else None,
    }


def fetch_and_store_fii_dii(db: Session) -> None:
    """
    Fetch today's FII/DII participant data from NSE and upsert into fii_dii_daily.
    NSE requires a two-step HTTP flow: first GET the home page to get cookies,
    then GET the API endpoint with those cookies.
    Logs a warning and returns silently on any failure.
    """
    today = str(date.today())
    try:
        with httpx.Client(headers=_HEADERS, follow_redirects=True, timeout=15.0) as client:
            client.get(_NSE_HOME)  # establish session cookie
            r = client.get(_NSE_FII_DII_URL)
            r.raise_for_status()
            raw = r.json()
    except Exception:
        logger.exception("[fii_dii] NSE fetch failed — skipping")
        return

    # The API may return a list directly or wrap it under a key
    if isinstance(raw, dict):
        raw = raw.get("data", []) or []

    parsed = _parse_fii_dii_response(raw)
    if not parsed:
        logger.warning("[fii_dii] could not parse response — no FII/DII rows found")
        return

    try:
        db.execute(
            text("""
                INSERT INTO fii_dii_daily
                    (date, fii_net_equity, dii_net_equity, fii_buy, fii_sell, dii_buy, dii_sell)
                VALUES (:date, :fii_net, :dii_net, :fii_buy, :fii_sell, :dii_buy, :dii_sell)
                ON CONFLICT(date) DO UPDATE SET
                    fii_net_equity=excluded.fii_net_equity,
                    dii_net_equity=excluded.dii_net_equity,
                    fii_buy=excluded.fii_buy, fii_sell=excluded.fii_sell,
                    dii_buy=excluded.dii_buy, dii_sell=excluded.dii_sell,
                    fetched_at=datetime('now')
            """),
            {
                "date":      today,
                "fii_net":   parsed["fii_net_equity"],
                "dii_net":   parsed["dii_net_equity"],
                "fii_buy":   parsed["fii_buy"],
                "fii_sell":  parsed["fii_sell"],
                "dii_buy":   parsed["dii_buy"],
                "dii_sell":  parsed["dii_sell"],
            },
        )
        db.commit()
        logger.info("[fii_dii] stored: FII net=%.0f Cr  DII net=%.0f Cr",
                    parsed["fii_net_equity"] or 0, parsed["dii_net_equity"] or 0)
    except Exception:
        logger.exception("[fii_dii] DB upsert failed")


def get_latest_fii_dii(db: Session) -> Optional[dict]:
    """Return the most recent row from fii_dii_daily, or None if table is empty."""
    row = db.execute(
        text("SELECT * FROM fii_dii_daily ORDER BY date DESC LIMIT 1")
    ).mappings().fetchone()
    return dict(row) if row else None
```

- [ ] **Step 4: Run tests — all should pass**

```bash
cd C:/DLP_Repos/MyRepo/StockV2/backend && python -m pytest tests/test_fii_dii_fetcher.py -v
```
Expected: 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git -C C:/DLP_Repos/MyRepo/StockV2 add backend/domains/data/fii_dii_fetcher.py backend/tests/test_fii_dii_fetcher.py
git -C C:/DLP_Repos/MyRepo/StockV2 commit -m "feat: add fii_dii_fetcher with NSE API parser and get_latest_fii_dii"
```

---

### Task 4: Entry-window checker

**Files:**
- Create: `backend/domains/alerts/entry_window.py`
- Create: `backend/tests/test_entry_window.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_entry_window.py`:

```python
"""Tests for entry_window module."""


def test_is_in_entry_window_exact_match():
    from domains.alerts.entry_window import is_in_entry_window
    assert is_in_entry_window(current_price=100.0, entry_price=100.0) is True


def test_is_in_entry_window_within_2pct_above():
    from domains.alerts.entry_window import is_in_entry_window
    assert is_in_entry_window(current_price=101.9, entry_price=100.0) is True


def test_is_in_entry_window_within_2pct_below():
    from domains.alerts.entry_window import is_in_entry_window
    assert is_in_entry_window(current_price=98.1, entry_price=100.0) is True


def test_is_in_entry_window_outside_above():
    from domains.alerts.entry_window import is_in_entry_window
    assert is_in_entry_window(current_price=102.1, entry_price=100.0) is False


def test_is_in_entry_window_outside_below():
    from domains.alerts.entry_window import is_in_entry_window
    assert is_in_entry_window(current_price=97.9, entry_price=100.0) is False


def test_get_signals_in_entry_window_filters_non_buy():
    from unittest.mock import MagicMock
    from sqlalchemy import text
    from domains.alerts.entry_window import get_signals_in_entry_window

    db = MagicMock()
    db.execute.return_value.fetchone.return_value = None  # not already alerted

    signals = [
        {"symbol": "SBIN", "strategy_id": 1, "signal_type": "SELL",
         "price_at_signal": 820.0, "signal_date": "2026-08-19"},
    ]
    live_prices = {"SBIN": 821.0}
    result = get_signals_in_entry_window(db, signals, live_prices)
    assert result == []


def test_get_signals_in_entry_window_passes_valid_signal():
    from unittest.mock import MagicMock
    from domains.alerts.entry_window import get_signals_in_entry_window

    db = MagicMock()
    db.execute.return_value.fetchone.return_value = None  # not already alerted

    signals = [
        {"symbol": "SBIN", "strategy_id": 1, "signal_type": "BUY",
         "price_at_signal": 820.0, "signal_date": "2026-08-19"},
    ]
    live_prices = {"SBIN": 821.0}  # within 2%
    result = get_signals_in_entry_window(db, signals, live_prices)
    assert len(result) == 1
    assert result[0]["symbol"] == "SBIN"


def test_get_signals_in_entry_window_skips_already_alerted():
    from unittest.mock import MagicMock
    from domains.alerts.entry_window import get_signals_in_entry_window

    db = MagicMock()
    db.execute.return_value.fetchone.return_value = (1,)  # already alerted

    signals = [
        {"symbol": "SBIN", "strategy_id": 1, "signal_type": "BUY",
         "price_at_signal": 820.0, "signal_date": "2026-08-19"},
    ]
    live_prices = {"SBIN": 821.0}
    result = get_signals_in_entry_window(db, signals, live_prices)
    assert result == []


def test_get_signals_in_entry_window_skips_missing_live_price():
    from unittest.mock import MagicMock
    from domains.alerts.entry_window import get_signals_in_entry_window

    db = MagicMock()
    signals = [
        {"symbol": "SBIN", "strategy_id": 1, "signal_type": "BUY",
         "price_at_signal": 820.0, "signal_date": "2026-08-19"},
    ]
    live_prices = {}  # SBIN missing
    result = get_signals_in_entry_window(db, signals, live_prices)
    assert result == []
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd C:/DLP_Repos/MyRepo/StockV2/backend && python -m pytest tests/test_entry_window.py -v 2>&1 | head -20
```
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Create entry_window.py**

Create `backend/domains/alerts/entry_window.py`:

```python
"""Entry-window filtering and dedup for intraday BUY signal alerts."""
import logging
from datetime import date
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

ENTRY_WINDOW_PCT = 0.02  # ±2% of signal entry price


def is_in_entry_window(current_price: float, entry_price: float) -> bool:
    """Return True if current_price is within ENTRY_WINDOW_PCT of entry_price."""
    return abs(current_price - entry_price) / entry_price <= ENTRY_WINDOW_PCT


def get_signals_in_entry_window(
    db: Session,
    scan_results: list[dict],
    live_prices: dict[str, float],
) -> list[dict]:
    """
    From scan_results (output of StrategyService.get_today_signals()), return
    signals where:
      1. signal_type == 'BUY'
      2. symbol has a live price available
      3. current price is within ENTRY_WINDOW_PCT of price_at_signal
      4. (symbol, strategy_id, signal_date) has NOT already been alerted today
    """
    today = str(date.today())
    in_window: list[dict] = []

    for signal in scan_results:
        if signal.get("signal_type") != "BUY":
            continue

        sym = signal.get("symbol")
        entry_price = signal.get("price_at_signal")
        strategy_id = signal.get("strategy_id")
        signal_date = str(signal.get("signal_date", today))

        if not sym or not entry_price or sym not in live_prices:
            continue

        current_price = live_prices[sym]
        if not is_in_entry_window(current_price, float(entry_price)):
            continue

        # Dedup check
        already_sent = db.execute(
            text("""
                SELECT 1 FROM intraday_alerts_sent
                WHERE symbol = :sym AND strategy_id = :sid AND signal_date = :date
                LIMIT 1
            """),
            {"sym": sym, "sid": strategy_id, "date": signal_date},
        ).fetchone()

        if already_sent:
            logger.debug("[entry_window] %s/%s already alerted today — skip", sym, strategy_id)
            continue

        in_window.append(signal)

    return in_window
```

- [ ] **Step 4: Run tests — all should pass**

```bash
cd C:/DLP_Repos/MyRepo/StockV2/backend && python -m pytest tests/test_entry_window.py -v
```
Expected: 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git -C C:/DLP_Repos/MyRepo/StockV2 add backend/domains/alerts/entry_window.py backend/tests/test_entry_window.py
git -C C:/DLP_Repos/MyRepo/StockV2 commit -m "feat: add entry_window checker with ±2% filter and dedup"
```

---

### Task 5: Telegram entry alert

**Files:**
- Modify: `backend/domains/alerts/telegram.py`

- [ ] **Step 1: Read telegram.py**

Read `backend/domains/alerts/telegram.py` to understand the existing `AlertService` class and `send()` method signature. The new `send_entry_alert()` method uses the same `send()` call with HTML-formatted text.

- [ ] **Step 2: Add send_entry_alert() to AlertService**

At the end of the `AlertService` class (after `send_sell_alerts()`), add:

```python
    def send_entry_alert(
        self,
        signal: dict,
        current_price: float,
        fii_dii_row: Optional[dict] = None,
    ) -> bool:
        """Send an individual entry-window alert for a BUY signal."""
        sym = signal.get("symbol", "")
        strategy = signal.get("strategy_name", "")
        entry_price = float(signal.get("price_at_signal") or current_price)
        pct = (current_price - entry_price) / entry_price * 100

        win_rate = signal.get("historical_win_rate")
        win_str = f"{int(win_rate * 100)}%" if win_rate is not None else "N/A"

        score = signal.get("opportunity_score")
        grade = signal.get("opportunity_grade") or ""
        score_str = f"{score}/100 [{grade}]" if score is not None else "—"

        stop_loss = signal.get("suggested_stop_loss")
        target = signal.get("suggested_target")
        sl_str = f"₹{stop_loss:,.1f} ({(stop_loss - current_price)/current_price*100:.1f}%)" if stop_loss else "—"
        tgt_str = f"₹{target:,.1f} ({(target - current_price)/current_price*100:+.1f}%)" if target else "—"

        fii_dii_line = ""
        if fii_dii_row:
            fii_net = fii_dii_row.get("fii_net_equity") or 0
            dii_net = fii_dii_row.get("dii_net_equity") or 0
            flow_emoji = "🟢" if fii_net > 0 else "🔴"
            fii_dii_line = (
                f"\n<b>FII/DII:</b>   FII {fii_net:+,.0f} Cr | DII {dii_net:+,.0f} Cr {flow_emoji}"
            )

        text = (
            f"🚨 <b>Entry Window — {sym}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"\n<b>Signal:</b>     {strategy} ({win_str} win rate)"
            f"\n<b>Entry:</b>      ₹{current_price:,.1f}  (signal ₹{entry_price:,.1f}, {pct:+.1f}%)"
            f"\n<b>Target:</b>     {tgt_str}"
            f"\n<b>Stop Loss:</b>  {sl_str}"
            f"\n<b>Score:</b>      {score_str}"
            f"{fii_dii_line}"
        )
        return self.send(text)
```

Note: `Optional` is already imported in telegram.py. If not, add `from typing import Optional` to the top.

- [ ] **Step 3: Verify syntax**

```bash
cd C:/DLP_Repos/MyRepo/StockV2/backend && python -c "
import ast
with open('domains/alerts/telegram.py') as f:
    ast.parse(f.read())
print('Syntax OK')
"
```

- [ ] **Step 4: Quick functional test**

```bash
cd C:/DLP_Repos/MyRepo/StockV2/backend && python -c "
from domains.alerts.telegram import AlertService

signal = {
    'symbol': 'SBIN',
    'strategy_name': 'RSI Oversold Bounce',
    'price_at_signal': 820.0,
    'historical_win_rate': 0.63,
    'opportunity_score': 74,
    'opportunity_grade': 'A',
    'suggested_stop_loss': 779.0,
    'suggested_target': 900.0,
}
fii_dii = {'fii_net_equity': 1240.0, 'dii_net_equity': 680.0}

# Don't actually send — just verify it builds the message
import unittest.mock as mock
with mock.patch.object(AlertService, 'send', return_value=True) as m:
    AlertService().send_entry_alert(signal, 821.0, fii_dii)
    msg = m.call_args[0][0]
    assert 'SBIN' in msg
    assert '821' in msg
    assert 'FII/DII' in msg
    assert '1,240' in msg
print('send_entry_alert OK')
"
```
Expected: `send_entry_alert OK`.

- [ ] **Step 5: Commit**

```bash
git -C C:/DLP_Repos/MyRepo/StockV2 add backend/domains/alerts/telegram.py
git -C C:/DLP_Repos/MyRepo/StockV2 commit -m "feat: add send_entry_alert to AlertService"
```

---

### Task 6: Scheduler integration

**Files:**
- Modify: `backend/scheduler.py`

- [ ] **Step 1: Add FII_DII_FETCH to JobIds**

In `backend/scheduler.py`, add to the `JobIds` class:

```python
class JobIds:
    # ... existing entries ...
    FII_DII_FETCH = "fii_dii_fetch"
```

- [ ] **Step 2: Add _fii_dii_fetch() job function**

After the `_daily_index_update()` function (around line 366), add:

```python
def _fii_dii_fetch():
    """Fetch NSE FII/DII participant data after market close and store for alert enrichment."""
    from database import SessionLocal
    from domains.data.fii_dii_fetcher import fetch_and_store_fii_dii
    db = SessionLocal()
    try:
        fetch_and_store_fii_dii(db)
    except Exception:
        logger.exception("[fii_dii_fetch] failed")
    finally:
        db.close()
```

- [ ] **Step 3: Extend _intraday_scan() with entry-window phase**

Replace the current `_intraday_scan()` function body with:

```python
def _intraday_scan():
    from database import SessionLocal
    from domains.strategies.engine import StrategyEngine
    from domains.strategies.service import StrategyService
    from domains.data.nse_universe import NSE_SYMBOLS
    from domains.data.live_price_fetcher import fetch_live_prices
    from domains.data.fii_dii_fetcher import get_latest_fii_dii
    from domains.alerts.entry_window import get_signals_in_entry_window
    from domains.alerts.telegram import AlertService
    from sqlalchemy import text

    if not _is_market_hours():
        return
    db = SessionLocal()
    try:
        # Phase 1: run all strategies (stores signals to DB)
        engine = StrategyEngine(db)
        results = engine.scan_all(NSE_SYMBOLS, ist_today())
        logger.info("[scheduler] intraday_scan: %d signals", len(results))

        # Phase 2: exit monitor for open positions
        open_rows = db.execute(
            text("SELECT ph.symbol FROM portfolio_holdings ph WHERE ph.is_active=1")
        ).fetchall()
        open_symbols = [r[0] for r in open_rows]
        if open_symbols:
            placeholders = ",".join(f"'{s}'" for s in open_symbols)
            price_rows = db.execute(
                text(f"""
                    SELECT symbol, close FROM stock_prices_daily
                    WHERE (symbol, date) IN (
                        SELECT symbol, MAX(date) FROM stock_prices_daily
                        WHERE symbol IN ({placeholders})
                        GROUP BY symbol
                    )
                """)
            ).fetchall()
            current_prices = {r[0]: r[1] for r in price_rows}
            if current_prices:
                from domains.portfolio.exit_monitor import ExitMonitor
                exits = ExitMonitor(db).scan_exits(current_prices)
                if exits:
                    logger.info("[scheduler] intraday_scan: %d positions exited", len(exits))

        # Phase 3: entry-window alerts for pre-qualified BUY signals
        today_str = ist_today().strftime("%Y-%m-%d")
        signals = StrategyService(db).get_today_signals(signal_date=today_str)
        buy_signals = [s for s in signals if s.get("signal_type") == "BUY"]

        if buy_signals:
            symbols_with_signals = list({s["symbol"] for s in buy_signals})
            live_prices = fetch_live_prices(symbols_with_signals)

            if live_prices:
                fii_dii_row = get_latest_fii_dii(db)
                in_window = get_signals_in_entry_window(db, buy_signals, live_prices)
                alert_svc = AlertService()
                for signal in in_window:
                    sym = signal["symbol"]
                    alert_svc.send_entry_alert(signal, live_prices[sym], fii_dii_row)
                    db.execute(
                        text("""
                            INSERT OR IGNORE INTO intraday_alerts_sent
                                (symbol, strategy_id, signal_date)
                            VALUES (:sym, :sid, :date)
                        """),
                        {
                            "sym":  sym,
                            "sid":  signal["strategy_id"],
                            "date": str(signal.get("signal_date", today_str)),
                        },
                    )
                db.commit()
                if in_window:
                    logger.info("[scheduler] intraday_scan: %d entry-window alerts sent", len(in_window))
            else:
                logger.warning("[scheduler] intraday_scan: live price fetch returned no data")

    except Exception:
        logger.exception("[scheduler] intraday_scan failed")
    finally:
        db.close()
```

- [ ] **Step 4: Register FII_DII_FETCH job**

In `register_jobs()`, after the `DAILY_INDEX_UPDATE` job block, add:

```python
    # 4:35pm — fetch FII/DII participant flow data from NSE after market close
    scheduler.add_job(
        _fii_dii_fetch,
        CronTrigger(hour=16, minute=35, day_of_week="mon-fri"),
        id=JobIds.FII_DII_FETCH,
        replace_existing=True,
    )
```

- [ ] **Step 5: Verify scheduler syntax and job registration**

```bash
cd C:/DLP_Repos/MyRepo/StockV2/backend && python -c "
import ast
with open('scheduler.py') as f:
    ast.parse(f.read())
print('Syntax OK')

from scheduler import scheduler, register_jobs
register_jobs()
job_ids = [j.id for j in scheduler.get_jobs()]
assert 'fii_dii_fetch' in job_ids, f'fii_dii_fetch not found: {job_ids}'
assert 'intraday_scan' in job_ids
print('Jobs OK:', job_ids)
"
```

- [ ] **Step 6: Run all new tests together**

```bash
cd C:/DLP_Repos/MyRepo/StockV2/backend && python -m pytest tests/test_live_price_fetcher.py tests/test_fii_dii_fetcher.py tests/test_entry_window.py -v
```
Expected: all 18 tests PASS.

- [ ] **Step 7: Commit**

```bash
git -C C:/DLP_Repos/MyRepo/StockV2 add backend/scheduler.py
git -C C:/DLP_Repos/MyRepo/StockV2 commit -m "feat: add entry-window alerts and FII/DII fetch to scheduler"
```

---

## Self-Review Notes

- Spec section 1.1 (intraday_alerts_sent table) → Task 1 ✅
- Spec section 1.2 (live_price_fetcher) → Task 2 ✅
- Spec section 1.3 (entry_window checker) → Task 4 ✅
- Spec section 1.4 (send_entry_alert) → Task 5 ✅
- Spec section 1.5 (scheduler extension) → Task 6 ✅
- Spec section 2.1 (fii_dii_daily table) → Task 1 ✅
- Spec section 2.2 (fii_dii_fetcher) → Task 3 ✅
- Spec section 2.3 (FII_DII_FETCH job) → Task 6 ✅
- Error handling: live fetch failure → `fetch_live_prices` returns `{}` → `if live_prices:` guard skips alert phase ✅
- Error handling: NSE fetch failure → `fetch_and_store_fii_dii` logs + returns → `get_latest_fii_dii` returns None → `send_entry_alert` skips FII/DII line ✅
- Dedup: `INSERT OR IGNORE` + dedup check in `get_signals_in_entry_window` ✅
- Type consistency: `get_latest_fii_dii` returns `dict | None`, `send_entry_alert` accepts `Optional[dict]` ✅
- `_parse_fii_dii_response` handles both `category` and `clientType` keys ✅
- No placeholders or TBDs ✅
