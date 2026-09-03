# Zones Phase B Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add three features on top of Phase A zone detection: (1) interactive candlestick chart with zone band overlays, (2) walk-forward zone backtesting with trade history, and (3) VWAP-derived zones from intraday 5-min data.

**Architecture:** Three independent backend subsystems (chart endpoint, backtester, VWAP detector) all extend the existing zones domain; the frontend adds a PriceChart component and a Backtest tab to the existing ZonesPage with a 2/3-1/3 layout when a chart is visible.

**Tech Stack:** Python/FastAPI backend, yfinance 5-min bars, TanStack Query v5, lightweight-charts v4 (TradingView canvas chart), Tailwind CSS, PostgreSQL

---

## File Map

| File | Action |
|------|--------|
| `backend/main.py` | MODIFY — 3 new tables |
| `backend/domains/zones/models.py` | MODIFY — add `source` field to Zone |
| `backend/domains/zones/engine.py` | MODIFY — add `"source"` to `zone_to_dict`, call VWAPZoneDetector |
| `backend/domains/zones/detectors.py` | MODIFY — add `VWAPZoneDetector` class |
| `backend/domains/zones/backtester.py` | NEW — `ZoneBacktester` + `ZoneTrade` |
| `backend/domains/zones/router.py` | MODIFY — 4 new endpoints (chart-data + 3 backtest) |
| `backend/domains/data/intraday_fetcher.py` | NEW — `IntradayFetcher` (yfinance 5-min) |
| `backend/scheduler.py` | MODIFY — intraday VWAP fetch job at 09:20 IST |
| `backend/tests/test_intraday_fetcher.py` | NEW |
| `backend/tests/test_vwap_detector.py` | NEW |
| `backend/tests/test_zone_backtester.py` | NEW |
| `frontend/src/api/zones.ts` | MODIFY — chart + backtest types + functions, fix tag_filter bug |
| `frontend/src/components/PriceChart.tsx` | NEW — lightweight-charts wrapper |
| `frontend/src/pages/ZonesPage.tsx` | MODIFY — 2/3-1/3 layout when chart visible, Backtest tab |

---

## Task 1: DB Tables + Zone `source` Field

**Files:**
- Modify: `backend/main.py` (after `zone_analysis_results` block, ~line 504)
- Modify: `backend/domains/zones/models.py`
- Modify: `backend/domains/zones/engine.py:96-102`

- [ ] **Step 1: Add `source` field to Zone dataclass**

In `backend/domains/zones/models.py`, change the `Zone` dataclass — add `source` after `strength_hint`:

```python
@dataclass
class Zone:
    """A clustered zone after merging nearby ZoneLevels."""
    low: float
    high: float
    zone_type: str           # "demand" | "supply"
    source_tags: list[str] = field(default_factory=list)
    touch_count: int = 0
    last_reaction_pct: float = 0.0
    freshness: str = "fresh" # "fresh" | "tested" | "weakened"
    score: int = 0           # filled by ZoneScorer
    volume_at_zone: float = 1.0
    bar_index: int = -1      # most recent bar_index among merged levels
    strength_hint: float = 0.5
    source: str = "daily"    # "daily" | "vwap"

    @property
    def midpoint(self) -> float:
        return (self.low + self.high) / 2.0
```

- [ ] **Step 2: Add `source` to `zone_to_dict`**

In `backend/domains/zones/engine.py`, update `zone_to_dict` at line 96:

```python
def zone_to_dict(z: Zone) -> dict:
    return {
        "low": z.low, "high": z.high, "score": z.score,
        "freshness": z.freshness, "touch_count": z.touch_count,
        "last_reaction_pct": z.last_reaction_pct,
        "source_tags": z.source_tags,
        "source": z.source,
    }
```

- [ ] **Step 3: Add 3 new DB tables to `main.py`**

Add after the `zone_analysis_results` block (after line 504 — the `logger.info("zone_analysis_results table verified")` line):

```python
    # Zone Phase B tables
    try:
        with engine.connect() as _conn:
            _conn.execute(text("""
                CREATE TABLE IF NOT EXISTS intraday_prices_5m (
                    id       SERIAL PRIMARY KEY,
                    symbol   VARCHAR(20) NOT NULL,
                    datetime TIMESTAMP NOT NULL,
                    open     REAL, high REAL, low REAL, close REAL, volume BIGINT,
                    UNIQUE (symbol, datetime)
                )
            """))
            _conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_intraday_sym_dt ON intraday_prices_5m (symbol, datetime DESC)"
            ))
            _conn.execute(text("""
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
                )
            """))
            _conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_zone_bt_results ON zone_backtest_results (symbol, ran_at DESC)"
            ))
            _conn.execute(text("""
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
                )
            """))
            _conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_zone_bt_trades ON zone_backtest_trades (result_id)"
            ))
            _conn.commit()
        logger.info("Zone Phase B tables verified")
    except Exception as e:
        logger.warning("zone phase B tables migration skipped: %s", e)
```

- [ ] **Step 4: Verify backend starts without errors**

```bash
cd backend && python -c "from main import app; print('OK')"
```

Expected: `OK` (no import errors)

- [ ] **Step 5: Run existing zone tests to confirm `source` field doesn't break anything**

```bash
cd backend && python -m pytest tests/test_zone_detectors.py tests/test_zone_clusterer.py tests/test_zone_scorer.py tests/test_zone_entry_engine.py -v
```

Expected: All 41 tests PASS (Zone dataclass change is additive with a default value)

- [ ] **Step 6: Commit**

```bash
git add backend/main.py backend/domains/zones/models.py backend/domains/zones/engine.py
git commit -m "feat: add Zone.source field + intraday/backtest tables for zones phase B"
```

---

## Task 2: IntradayFetcher

**Files:**
- Create: `backend/domains/data/intraday_fetcher.py`
- Create: `backend/tests/test_intraday_fetcher.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_intraday_fetcher.py`:

```python
import pandas as pd
import pytest
from unittest.mock import MagicMock, patch
from domains.data.intraday_fetcher import IntradayFetcher


def _make_yf_df(n_rows: int = 12) -> pd.DataFrame:
    """Minimal fake yfinance 5-min response: Datetime index + OHLCV columns."""
    import numpy as np
    from datetime import datetime, timedelta
    idx = pd.date_range(start="2024-01-02 09:30", periods=n_rows, freq="5min", tz="Asia/Kolkata")
    data = {
        "Open":   np.full(n_rows, 100.0),
        "High":   np.full(n_rows, 102.0),
        "Low":    np.full(n_rows, 98.0),
        "Close":  np.full(n_rows, 101.0),
        "Volume": np.full(n_rows, 50000),
    }
    return pd.DataFrame(data, index=idx)


def test_fetch_one_normalizes_columns():
    fetcher = IntradayFetcher()
    fake_df = _make_yf_df()

    with patch("domains.data.intraday_fetcher.yf.Ticker") as mock_ticker:
        mock_ticker.return_value.history.return_value = fake_df
        df = fetcher.fetch_one("RELIANCE")

    assert list(df.columns) == ["datetime", "open", "high", "low", "close", "volume"]
    assert len(df) == 12
    assert df["close"].iloc[0] == 101.0


def test_fetch_one_returns_empty_on_yf_error():
    fetcher = IntradayFetcher()
    with patch("domains.data.intraday_fetcher.yf.Ticker") as mock_ticker:
        mock_ticker.return_value.history.side_effect = Exception("network error")
        df = fetcher.fetch_one("BADSTOCK")
    assert df.empty


def test_fetch_and_store_upserts_rows():
    fetcher = IntradayFetcher()
    fake_df = _make_yf_df(n_rows=3)
    db = MagicMock()

    with patch.object(fetcher, "fetch_one", return_value=pd.DataFrame({
        "datetime": pd.date_range("2024-01-02 09:30", periods=3, freq="5min"),
        "open": [100.0, 100.0, 100.0],
        "high": [102.0, 102.0, 102.0],
        "low":  [98.0,  98.0,  98.0],
        "close":[101.0, 101.0, 101.0],
        "volume":[50000, 50000, 50000],
    })):
        fetcher.fetch_and_store(["RELIANCE"], db)

    assert db.execute.called
    assert db.commit.called
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && python -m pytest tests/test_intraday_fetcher.py -v
```

Expected: ImportError or ModuleNotFoundError (file doesn't exist yet)

- [ ] **Step 3: Implement `intraday_fetcher.py`**

Create `backend/domains/data/intraday_fetcher.py`:

```python
from __future__ import annotations
import logging
import pandas as pd
import yfinance as yf
from sqlalchemy import text
from sqlalchemy.orm import Session
from domains.data.nse_universe import get_yfinance_symbol

logger = logging.getLogger(__name__)


class IntradayFetcher:
    def fetch_one(self, symbol: str) -> pd.DataFrame:
        """Download last 5 days of 5-min bars for a symbol. Returns empty DF on failure."""
        try:
            ticker = yf.Ticker(get_yfinance_symbol(symbol))
            raw = ticker.history(period="5d", interval="5m", auto_adjust=True)
            if raw.empty:
                return pd.DataFrame()
            df = raw.copy()
            df.columns = [c.lower() for c in df.columns]
            df = df[["open", "high", "low", "close", "volume"]].copy()
            df.index.name = "datetime"
            df = df.reset_index()
            df["datetime"] = pd.to_datetime(df["datetime"])
            if df["datetime"].dt.tz is not None:
                df["datetime"] = df["datetime"].dt.tz_convert("Asia/Kolkata").dt.tz_localize(None)
            df = df.dropna(subset=["open", "high", "low", "close"])
            df = df[df["close"] > 0]
            return df[["datetime", "open", "high", "low", "close", "volume"]].reset_index(drop=True)
        except Exception as e:
            logger.warning("[IntradayFetcher] fetch failed for %s: %s", symbol, e)
            return pd.DataFrame()

    def fetch_and_store(self, symbols: list[str], db: Session) -> int:
        """Fetch 5-min bars for all symbols and upsert into intraday_prices_5m. Returns row count."""
        total = 0
        for symbol in symbols:
            df = self.fetch_one(symbol)
            if df.empty:
                continue
            try:
                for _, row in df.iterrows():
                    db.execute(text("""
                        INSERT INTO intraday_prices_5m (symbol, datetime, open, high, low, close, volume)
                        VALUES (:sym, :dt, :o, :h, :l, :c, :v)
                        ON CONFLICT (symbol, datetime) DO NOTHING
                    """), {
                        "sym": symbol,
                        "dt": row["datetime"],
                        "o": float(row["open"]),
                        "h": float(row["high"]),
                        "l": float(row["low"]),
                        "c": float(row["close"]),
                        "v": int(row["volume"]) if pd.notna(row["volume"]) else 0,
                    })
                db.commit()
                total += len(df)
                logger.debug("[IntradayFetcher] stored %d rows for %s", len(df), symbol)
            except Exception as e:
                db.rollback()
                logger.warning("[IntradayFetcher] DB write failed for %s: %s", symbol, e)
        return total
```

- [ ] **Step 4: Run tests**

```bash
cd backend && python -m pytest tests/test_intraday_fetcher.py -v
```

Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/domains/data/intraday_fetcher.py backend/tests/test_intraday_fetcher.py
git commit -m "feat: add IntradayFetcher for yfinance 5-min intraday bars"
```

---

## Task 3: VWAPZoneDetector + ZoneEngine Integration

**Files:**
- Modify: `backend/domains/zones/detectors.py` (append at end)
- Modify: `backend/domains/zones/engine.py` (lines 13-16, 146-147)
- Create: `backend/tests/test_vwap_detector.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_vwap_detector.py`:

```python
import pandas as pd
import numpy as np
import pytest
from unittest.mock import MagicMock
from datetime import datetime
from domains.zones.detectors import VWAPZoneDetector


def _make_intraday_rows(n: int = 12, price: float = 100.0, vwap_price: float = 100.0):
    """Returns MagicMock db.execute().fetchall() result with n 5-min bars.
    volume is constant, so VWAP == vwap_price (set by close values).
    """
    # VWAP = cumsum(typical_price * vol) / cumsum(vol); if all typicals == vwap_price, VWAP == vwap_price
    rows = []
    for i in range(n):
        # typical = (high + low + close) / 3; set all three to vwap_price for predictable VWAP
        h = vwap_price + 0.5
        l = vwap_price - 0.5
        c = vwap_price
        rows.append((datetime(2024, 1, 2, 9, 30 + i * 5), h, l, c, 10000))
    return rows


def test_vwap_demand_when_price_above_vwap():
    db = MagicMock()
    db.execute.return_value.fetchall.return_value = _make_intraday_rows(12, vwap_price=95.0)
    detector = VWAPZoneDetector()
    zones = detector.detect("RELIANCE", db, atr=5.0, current_price=100.0)
    assert len(zones) == 1
    assert zones[0].zone_type == "demand"
    assert zones[0].source == "vwap"
    assert "vwap" in zones[0].source_tags


def test_vwap_supply_when_price_below_vwap():
    db = MagicMock()
    db.execute.return_value.fetchall.return_value = _make_intraday_rows(12, vwap_price=105.0)
    detector = VWAPZoneDetector()
    zones = detector.detect("RELIANCE", db, atr=5.0, current_price=100.0)
    assert len(zones) == 1
    assert zones[0].zone_type == "supply"


def test_vwap_returns_empty_with_too_few_bars():
    db = MagicMock()
    db.execute.return_value.fetchall.return_value = _make_intraday_rows(3)
    detector = VWAPZoneDetector()
    zones = detector.detect("RELIANCE", db, atr=5.0, current_price=100.0)
    assert zones == []


def test_vwap_band_width_is_0_3_atr():
    db = MagicMock()
    db.execute.return_value.fetchall.return_value = _make_intraday_rows(12, vwap_price=100.0)
    detector = VWAPZoneDetector()
    atr = 10.0
    zones = detector.detect("RELIANCE", db, atr=atr, current_price=105.0)
    assert len(zones) == 1
    z = zones[0]
    expected_low  = 100.0 - 0.3 * atr  # 97.0
    expected_high = 100.0 + 0.3 * atr  # 103.0
    assert abs(z.low - expected_low) < 0.01
    assert abs(z.high - expected_high) < 0.01
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && python -m pytest tests/test_vwap_detector.py -v
```

Expected: ImportError (VWAPZoneDetector doesn't exist yet)

- [ ] **Step 3: Add VWAPZoneDetector to detectors.py**

Append at the end of `backend/domains/zones/detectors.py` (after the `FibonacciDetector` class):

```python
class VWAPZoneDetector:
    """Intraday VWAP from 5-min bars → one demand or supply zone at current VWAP level."""

    def detect(
        self,
        symbol: str,
        db,           # Session — typed loosely to avoid circular import in tests
        *,
        atr: float,
        current_price: float | None = None,
    ) -> list[Zone]:
        from sqlalchemy import text as _text
        from datetime import date as _date

        rows = db.execute(_text("""
            SELECT datetime, high, low, close, volume
            FROM intraday_prices_5m
            WHERE symbol = :s AND datetime::date = CURRENT_DATE
            ORDER BY datetime ASC
        """), {"s": symbol}).fetchall()

        if len(rows) < 6:
            return []

        highs   = [float(r[1]) for r in rows]
        lows    = [float(r[2]) for r in rows]
        closes  = [float(r[3]) for r in rows]
        volumes = [max(float(r[4]), 1.0) for r in rows]

        typical = [(h + l + c) / 3.0 for h, l, c in zip(highs, lows, closes)]
        cum_tv  = 0.0
        cum_v   = 0.0
        for tp, v in zip(typical, volumes):
            cum_tv += tp * v
            cum_v  += v
        vwap = cum_tv / cum_v

        band_low  = vwap - 0.3 * atr
        band_high = vwap + 0.3 * atr

        price = current_price if current_price is not None else closes[-1]
        zone_type = "demand" if price > vwap else "supply"

        return [Zone(
            low=band_low,
            high=band_high,
            zone_type=zone_type,
            source_tags=["vwap"],
            touch_count=0,
            last_reaction_pct=0.0,
            freshness="fresh",
            volume_at_zone=1.0,
            bar_index=len(rows) - 1,
            strength_hint=0.6,
            source="vwap",
        )]
```

Note: `Zone` is already imported at the top of `detectors.py` from `.models`. Add the import if it's missing:

At the top of `detectors.py`, the current imports are:
```python
from .models import ZoneLevel
```

Change to:
```python
from .models import Zone, ZoneLevel
```

- [ ] **Step 4: Run tests**

```bash
cd backend && python -m pytest tests/test_vwap_detector.py -v
```

Expected: All 4 tests PASS

- [ ] **Step 5: Integrate VWAPZoneDetector into ZoneEngine.analyze()**

In `backend/domains/zones/engine.py`, update the imports at the top (line 13–16):

```python
from .detectors import (
    FibonacciDetector, MADetector, MomentumDetector,
    PriceStructureDetector, VolatilityDetector, VolumeDetector,
    VWAPZoneDetector,
)
```

In `ZoneEngine.analyze()`, after `all_zones = ZoneClusterer().cluster(levels, atr)` (line 147), add:

```python
        # VWAP zones from intraday data (optional — skipped if data unavailable)
        try:
            vwap_zones = VWAPZoneDetector().detect(symbol, db, atr=atr, current_price=price)
            all_zones.extend(vwap_zones)
        except Exception:
            pass  # intraday data may be unavailable; never block daily analysis
```

- [ ] **Step 6: Run all zone tests**

```bash
cd backend && python -m pytest tests/test_zone_detectors.py tests/test_zone_clusterer.py tests/test_zone_scorer.py tests/test_zone_entry_engine.py tests/test_vwap_detector.py -v
```

Expected: All 45 tests PASS

- [ ] **Step 7: Commit**

```bash
git add backend/domains/zones/detectors.py backend/domains/zones/engine.py backend/tests/test_vwap_detector.py
git commit -m "feat: add VWAPZoneDetector + integrate into ZoneEngine"
```

---

## Task 4: Chart-Data Endpoint

**Files:**
- Modify: `backend/domains/zones/router.py`

- [ ] **Step 1: Add `get_chart_data` endpoint**

In `backend/domains/zones/router.py`, add this endpoint after the `get_stored_result` function (after line 75):

```python
@router.get("/zones/chart-data/{symbol}")
def get_chart_data(
    symbol: str,
    bars: int = Query(120, ge=20, le=500),
    db: Session = Depends(get_db),
):
    """OHLCV bars + zone bands from latest stored result for the chart overlay."""
    rows = db.execute(
        text("""
            SELECT date, open, high, low, close, volume FROM (
                SELECT date, open, high, low, close, volume
                FROM stock_prices_daily
                WHERE symbol = :s
                ORDER BY date DESC LIMIT :b
            ) sub ORDER BY date ASC
        """),
        {"s": symbol.upper(), "b": bars},
    ).fetchall()
    if not rows:
        raise HTTPException(status_code=404, detail=f"No price data for {symbol}")

    ohlcv = [
        {
            "date":   str(r[0]),
            "open":   float(r[1]),
            "high":   float(r[2]),
            "low":    float(r[3]),
            "close":  float(r[4]),
            "volume": int(r[5]) if r[5] is not None else 0,
        }
        for r in rows
    ]

    # Load latest zone result (optional — chart still renders without zones)
    zone_row = db.execute(
        text("SELECT result_json FROM zone_analysis_results WHERE symbol = :s ORDER BY computed_date DESC LIMIT 1"),
        {"s": symbol.upper()},
    ).fetchone()

    result: dict = {"ohlcv": ohlcv}
    if zone_row:
        rj = json.loads(zone_row[0])
        result["demand_bands"] = [
            {"low": z["low"], "high": z["high"], "strength": z.get("score", 0), "zone_type": "demand", "source": z.get("source", "daily")}
            for z in rj.get("demand_zones", [])
        ]
        result["supply_bands"] = [
            {"low": z["low"], "high": z["high"], "strength": z.get("score", 0), "zone_type": "supply", "source": z.get("source", "daily")}
            for z in rj.get("supply_zones", [])
        ]
        ls = rj.get("long_setup")
        ss = rj.get("short_setup")
        if ls:
            result["long_setup"]  = {"entry": ls["ideal_entry"], "stop_loss": ls["stop_loss"], "target": ls["t2"]}
        if ss:
            result["short_setup"] = {"entry": ss["ideal_entry"], "stop_loss": ss["stop_loss"], "target": ss["t2"]}

    return result
```

- [ ] **Step 2: Verify import of `json` is present**

`json` is already imported at line 5 of `router.py`. Confirm with:
```bash
grep "^import json" backend/domains/zones/router.py
```

Expected: `import json`

- [ ] **Step 3: Smoke-test the endpoint (requires running backend)**

```bash
curl -s -H "X-API-Key: $API_KEY" "http://localhost:8000/api/v1/zones/chart-data/RELIANCE?bars=30" | python -c "import sys,json; d=json.load(sys.stdin); print(len(d['ohlcv']), 'bars')"
```

Expected: `30 bars`

- [ ] **Step 4: Commit**

```bash
git add backend/domains/zones/router.py
git commit -m "feat: add GET /zones/chart-data/{symbol} endpoint for chart overlay"
```

---

## Task 5: ZoneBacktester

**Files:**
- Create: `backend/domains/zones/backtester.py`
- Create: `backend/tests/test_zone_backtester.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_zone_backtester.py`:

```python
import math
import numpy as np
import pandas as pd
import pytest
from datetime import date, timedelta
from domains.zones.backtester import ZoneBacktester, ZoneTrade
from domains.zones.models import Zone


def _make_zone(low: float, high: float, zone_type: str = "demand") -> Zone:
    return Zone(
        low=low, high=high, zone_type=zone_type,
        source_tags=["swing_low"], score=70,
        freshness="fresh", bar_index=100, strength_hint=0.6,
    )


def _make_df(n_rows: int = 40, close: float = 100.0) -> pd.DataFrame:
    """Synthetic price DataFrame with required columns for _simulate()."""
    start = date(2023, 1, 1)
    dates = [start + timedelta(days=i) for i in range(n_rows)]
    closes = np.full(n_rows, close)
    return pd.DataFrame({
        "date":         pd.to_datetime(dates),
        "open":         closes,
        "high":         closes + 2,
        "low":          closes - 2,
        "close":        closes,
        "volume":       np.full(n_rows, 1_000_000.0),
        "atr_14":       np.full(n_rows, 5.0),
        "volume_ratio": np.ones(n_rows),
        "ema_50":       closes,
    })


def _snapshot(demand_zones, supply_zones=None, atr=5.0):
    return (demand_zones, supply_zones or [], atr)


def test_entry_and_supply_exit():
    """Price enters demand zone on day 5, enters supply zone on day 10 → supply_zone exit."""
    bt = ZoneBacktester()
    closes = np.full(40, 110.0)
    closes[5] = 100.0   # day 5: price enters demand zone [98, 102]
    closes[10] = 200.0  # day 10: price enters supply zone [195, 205]

    start = date(2023, 1, 1)
    dates = pd.to_datetime([start + timedelta(days=i) for i in range(40)])
    df = pd.DataFrame({
        "date": dates, "open": closes, "high": closes + 2,
        "low": closes - 2, "close": closes,
        "volume": np.full(40, 1e6), "atr_14": np.full(40, 5.0),
        "volume_ratio": np.ones(40), "ema_50": closes,
    })

    demand = [_make_zone(98.0, 102.0, "demand")]
    supply = [_make_zone(195.0, 205.0, "supply")]
    # Month snapshot: Jan 2023
    snapshots = {(2023, 1): (demand, supply, 5.0)}

    from_d = date(2023, 1, 1)
    to_d = date(2023, 2, 9)
    trades = bt._simulate("TEST", df, from_d, to_d, snapshots)

    assert len(trades) == 1
    assert trades[0].exit_reason == "supply_zone"
    assert trades[0].symbol == "TEST"


def test_stop_loss_exit():
    """Price falls below zone.low - 0.5*ATR → stop_loss exit."""
    bt = ZoneBacktester()
    closes = np.full(40, 110.0)
    closes[5] = 100.0   # enter demand zone [98, 102]
    closes[8] = 94.0    # below 98 - 0.5*5 = 95.5 → stop loss

    start = date(2023, 1, 1)
    dates = pd.to_datetime([start + timedelta(days=i) for i in range(40)])
    df = pd.DataFrame({
        "date": dates, "open": closes, "high": closes + 2,
        "low": closes - 2, "close": closes,
        "volume": np.full(40, 1e6), "atr_14": np.full(40, 5.0),
        "volume_ratio": np.ones(40), "ema_50": closes,
    })

    demand = [_make_zone(98.0, 102.0, "demand")]
    snapshots = {(2023, 1): (demand, [], 5.0)}

    trades = bt._simulate("TEST", df, date(2023, 1, 1), date(2023, 2, 9), snapshots)
    assert len(trades) == 1
    assert trades[0].exit_reason == "stop_loss"


def test_max_hold_exit():
    """Position held 20 days without hitting other exits → max_hold."""
    bt = ZoneBacktester()
    closes = np.full(60, 110.0)
    closes[5] = 100.0   # enter demand zone [98, 102]
    # Never enters supply zone, never falls below stop

    start = date(2023, 1, 1)
    dates = pd.to_datetime([start + timedelta(days=i) for i in range(60)])
    df = pd.DataFrame({
        "date": dates, "open": closes, "high": closes + 2,
        "low": closes - 2, "close": closes,
        "volume": np.full(60, 1e6), "atr_14": np.full(60, 5.0),
        "volume_ratio": np.ones(60), "ema_50": closes,
    })

    demand = [_make_zone(98.0, 102.0, "demand")]
    snapshots = {(2023, 1): (demand, [], 5.0), (2023, 2): (demand, [], 5.0)}

    trades = bt._simulate("TEST", df, date(2023, 1, 1), date(2023, 3, 1), snapshots)
    assert any(t.exit_reason == "max_hold" for t in trades)


def test_no_entry_when_no_demand_zones():
    bt = ZoneBacktester()
    df = _make_df()
    snapshots = {(2023, 1): ([], [], 5.0)}
    trades = bt._simulate("TEST", df, date(2023, 1, 1), date(2023, 1, 31), snapshots)
    assert trades == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && python -m pytest tests/test_zone_backtester.py -v
```

Expected: ImportError

- [ ] **Step 3: Implement `backtester.py`**

Create `backend/domains/zones/backtester.py`:

```python
from __future__ import annotations
import logging
import math
from dataclasses import dataclass
from datetime import date
from typing import Optional

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from domains.data.indicators import IndicatorEngine
from .clusterer import ZoneClusterer
from .detectors import (
    FibonacciDetector, MADetector, MomentumDetector,
    PriceStructureDetector, VolatilityDetector, VolumeDetector,
)
from .models import Zone
from .scorer import ZoneScorer

logger = logging.getLogger(__name__)

_DETECTORS = [
    PriceStructureDetector(),
    MADetector(),
    VolumeDetector(),
    VolatilityDetector(),
    MomentumDetector(),
    FibonacciDetector(),
]


@dataclass
class ZoneTrade:
    symbol: str
    entry_date: date
    entry_price: float
    exit_date: date
    exit_price: float
    pnl_pct: float
    exit_reason: str   # "supply_zone" | "stop_loss" | "max_hold" | "end_of_period"
    hold_days: int


class ZoneBacktester:
    def run(self, symbol: str, from_date: date, to_date: date, db: Session) -> list[ZoneTrade]:
        """Load historical data from DB, build monthly zone snapshots, run simulation."""
        rows = db.execute(
            text("""
                SELECT date, open, high, low, close, volume FROM (
                    SELECT date, open, high, low, close, volume
                    FROM stock_prices_daily
                    WHERE symbol = :s
                    ORDER BY date DESC LIMIT 1000
                ) sub ORDER BY date ASC
            """),
            {"s": symbol},
        ).fetchall()
        if len(rows) < 30:
            return []

        df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"])
        for col in ("open", "high", "low", "close", "volume"):
            df[col] = df[col].astype(float)
        df_ind = IndicatorEngine.compute(df)
        df_ind["date"] = pd.to_datetime(df_ind["date"])

        snapshots = self._build_snapshots(df_ind, from_date, to_date)
        return self._simulate(symbol, df_ind, from_date, to_date, snapshots)

    def _build_snapshots(
        self,
        df_ind: pd.DataFrame,
        from_date: date,
        to_date: date,
    ) -> dict[tuple, tuple]:
        """Return {(year, month): (demand_zones, supply_zones, atr)} for each month in range."""
        snapshots: dict[tuple, tuple] = {}
        all_dates = sorted(df_ind["date"].dt.date.tolist())
        sim_dates = [d for d in all_dates if from_date <= d <= to_date]
        seen: set[tuple] = set()

        for d in sim_dates:
            mk = (d.year, d.month)
            if mk in seen:
                continue
            seen.add(mk)

            # Use only data strictly before the first day of this month
            mask = df_ind["date"].dt.date < d
            df_hist = df_ind[mask]
            if len(df_hist) < 30:
                continue

            atr = float(df_hist["atr_14"].iloc[-1]) if "atr_14" in df_hist.columns else 0.0
            if not math.isfinite(atr) or atr <= 0:
                atr = float(df_hist["close"].iloc[-1]) * 0.01
            price_now = float(df_hist["close"].iloc[-1])

            levels = []
            for det in _DETECTORS:
                try:
                    levels.extend(det.detect(df_hist))
                except Exception:
                    pass

            all_zones = ZoneClusterer().cluster(levels, atr)
            scorer = ZoneScorer()
            n = len(df_hist)
            demand = scorer.score_all(
                [z for z in all_zones if z.zone_type == "demand"],
                atr=atr, n_bars=n, price=price_now,
            )
            supply = scorer.score_all(
                [z for z in all_zones if z.zone_type == "supply"],
                atr=atr, n_bars=n, price=price_now,
            )
            snapshots[mk] = (demand, supply, atr)

        return snapshots

    def _simulate(
        self,
        symbol: str,
        df_ind: pd.DataFrame,
        from_date: date,
        to_date: date,
        zone_snapshots: dict[tuple, tuple],
    ) -> list[ZoneTrade]:
        """Pure simulation — testable without DB."""
        all_dates = sorted(df_ind["date"].dt.date.tolist())
        sim_dates = [d for d in all_dates if from_date <= d <= to_date]
        if not sim_dates:
            return []

        trades: list[ZoneTrade] = []
        position: Optional[dict] = None   # {entry_date, entry_price, entry_zone, atr}
        pending_sell: Optional[str] = None
        pending_buy_zone: Optional[Zone] = None

        cur_demand: list[Zone] = []
        cur_supply: list[Zone] = []
        cur_atr: float = 0.0

        for d in sim_dates:
            mk = (d.year, d.month)
            if mk in zone_snapshots:
                cur_demand, cur_supply, cur_atr = zone_snapshots[mk]

            row = df_ind[df_ind["date"].dt.date == d]
            if row.empty:
                continue
            open_ = float(row["open"].iloc[0])
            close = float(row["close"].iloc[0])

            # Execute deferred actions at today's open
            if pending_sell and position:
                pnl_pct = (open_ - position["entry_price"]) / position["entry_price"] * 100
                hold = (d - position["entry_date"]).days
                trades.append(ZoneTrade(
                    symbol=symbol,
                    entry_date=position["entry_date"],
                    entry_price=position["entry_price"],
                    exit_date=d,
                    exit_price=open_,
                    pnl_pct=round(pnl_pct, 2),
                    exit_reason=pending_sell,
                    hold_days=hold,
                ))
                position = None
                pending_sell = None

            if pending_buy_zone is not None and position is None:
                position = {
                    "entry_date":  d,
                    "entry_price": open_,
                    "entry_zone":  pending_buy_zone,
                    "atr":         cur_atr,
                }
                pending_buy_zone = None

            # Detect conditions at today's close
            if position:
                hold = (d - position["entry_date"]).days
                if any(z.low <= close <= z.high for z in cur_supply):
                    pending_sell = "supply_zone"
                elif close < position["entry_zone"].low - 0.5 * position["atr"]:
                    pending_sell = "stop_loss"
                elif hold >= 20:
                    pending_sell = "max_hold"
            elif pending_buy_zone is None:
                for z in cur_demand:
                    if z.low <= close <= z.high:
                        pending_buy_zone = z
                        break

        # Force-close open position at end of period
        if position:
            last_row = df_ind[df_ind["date"].dt.date == sim_dates[-1]]
            if not last_row.empty:
                exit_price = float(last_row["close"].iloc[0])
                pnl_pct = (exit_price - position["entry_price"]) / position["entry_price"] * 100
                trades.append(ZoneTrade(
                    symbol=symbol,
                    entry_date=position["entry_date"],
                    entry_price=position["entry_price"],
                    exit_date=sim_dates[-1],
                    exit_price=exit_price,
                    pnl_pct=round(pnl_pct, 2),
                    exit_reason="end_of_period",
                    hold_days=(sim_dates[-1] - position["entry_date"]).days,
                ))

        return trades
```

- [ ] **Step 4: Run tests**

```bash
cd backend && python -m pytest tests/test_zone_backtester.py -v
```

Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/domains/zones/backtester.py backend/tests/test_zone_backtester.py
git commit -m "feat: add ZoneBacktester with walk-forward zone simulation"
```

---

## Task 6: Backtest Endpoints + Scheduler Job

**Files:**
- Modify: `backend/domains/zones/router.py`
- Modify: `backend/scheduler.py`

- [ ] **Step 1: Add imports to router.py**

At the top of `backend/domains/zones/router.py`, the existing import block has `datetime`. Add the backtester import. Find the line `from .precompute import ZonePrecomputer, get_precompute_state` and add after it:

```python
from .backtester import ZoneBacktester
```

- [ ] **Step 2: Add 3 backtest endpoints to router.py**

Add after the `get_chart_data` function:

```python
@router.post("/zones/backtest/run")
def run_backtest(
    symbol: str,
    from_date: str,
    to_date: str,
    db: Session = Depends(get_db),
):
    """Run walk-forward zone backtest for a symbol and store results."""
    from datetime import date as _date
    try:
        fd = _date.fromisoformat(from_date)
        td = _date.fromisoformat(to_date)
    except ValueError:
        raise HTTPException(status_code=422, detail="from_date and to_date must be YYYY-MM-DD")

    sym = symbol.upper()
    trades = ZoneBacktester().run(sym, fd, td, db)

    total = len(trades)
    wins  = sum(1 for t in trades if t.pnl_pct > 0)
    win_rate     = round(wins / total * 100, 1) if total else None
    total_pnl    = round(sum(t.pnl_pct for t in trades), 2)
    avg_hold     = round(sum(t.hold_days for t in trades) / total, 1) if total else None

    row = db.execute(
        text("""
            INSERT INTO zone_backtest_results
                (symbol, from_date, to_date, total_trades, win_rate, total_pnl_pct, avg_hold_days)
            VALUES (:sym, :fd, :td, :tt, :wr, :tp, :ah)
            RETURNING id, ran_at
        """),
        {"sym": sym, "fd": fd, "td": td, "tt": total,
         "wr": win_rate, "tp": total_pnl, "ah": avg_hold},
    ).fetchone()
    result_id = row[0]
    ran_at    = str(row[1])

    for t in trades:
        db.execute(
            text("""
                INSERT INTO zone_backtest_trades
                    (result_id, entry_date, entry_price, exit_date, exit_price,
                     pnl_pct, exit_reason, hold_days)
                VALUES (:rid, :ed, :ep, :xd, :xp, :pp, :er, :hd)
            """),
            {"rid": result_id, "ed": t.entry_date, "ep": t.entry_price,
             "xd": t.exit_date, "xp": t.exit_price, "pp": t.pnl_pct,
             "er": t.exit_reason, "hd": t.hold_days},
        )
    db.commit()

    return {
        "id":            result_id,
        "symbol":        sym,
        "from_date":     str(fd),
        "to_date":       str(td),
        "total_trades":  total,
        "win_rate":      win_rate,
        "total_pnl_pct": total_pnl,
        "avg_hold_days": avg_hold,
        "ran_at":        ran_at,
    }


@router.get("/zones/backtest/results/{symbol}")
def get_backtest_results(symbol: str, db: Session = Depends(get_db)):
    """List past backtest runs for a symbol, newest first."""
    rows = db.execute(
        text("""
            SELECT id, symbol, from_date, to_date, total_trades, win_rate,
                   total_pnl_pct, avg_hold_days, ran_at
            FROM zone_backtest_results
            WHERE symbol = :s
            ORDER BY ran_at DESC
            LIMIT 20
        """),
        {"s": symbol.upper()},
    ).fetchall()
    return [
        {
            "id":            r[0], "symbol": r[1],
            "from_date":     str(r[2]), "to_date": str(r[3]),
            "total_trades":  r[4], "win_rate": r[5],
            "total_pnl_pct": r[6], "avg_hold_days": r[7],
            "ran_at":        str(r[8]),
        }
        for r in rows
    ]


@router.get("/zones/backtest/trades/{result_id}")
def get_backtest_trades(result_id: int, db: Session = Depends(get_db)):
    """Full trade list for a stored backtest result."""
    rows = db.execute(
        text("""
            SELECT id, entry_date, entry_price, exit_date, exit_price,
                   pnl_pct, exit_reason, hold_days
            FROM zone_backtest_trades
            WHERE result_id = :rid
            ORDER BY entry_date ASC
        """),
        {"rid": result_id},
    ).fetchall()
    return [
        {
            "id":           r[0],
            "entry_date":   str(r[1]), "entry_price":  r[2],
            "exit_date":    str(r[3]) if r[3] else None, "exit_price": r[4],
            "pnl_pct":      r[5], "exit_reason":  r[6], "hold_days":  r[7],
        }
        for r in rows
    ]
```

- [ ] **Step 3: Add intraday fetch job to scheduler.py**

In `backend/scheduler.py`, add to the `JobIds` class:

```python
    INTRADAY_VWAP_FETCH = "intraday_vwap_fetch"
```

Add the job function after the `_earnings_refresh` function (before `_sector_rotation_daily`):

```python
def _intraday_vwap_fetch():
    """Fetch 5-min intraday bars for all active symbols at 09:20 IST for VWAP zone computation."""
    from database import SessionLocal
    from sqlalchemy import text as _text
    from domains.data.intraday_fetcher import IntradayFetcher
    db = SessionLocal()
    try:
        rows = db.execute(_text(
            "SELECT DISTINCT symbol FROM stock_prices_daily WHERE date >= CURRENT_DATE - INTERVAL '10 days'"
        )).fetchall()
        symbols = [r[0] for r in rows]
        n = IntradayFetcher().fetch_and_store(symbols, db)
        logger.info("[intraday_vwap_fetch] stored %d 5-min rows for %d symbols", n, len(symbols))
    except Exception:
        logger.exception("[intraday_vwap_fetch] failed")
    finally:
        db.close()
```

In `register_jobs()`, add before the closing line:

```python
    # 9:20am — fetch intraday 5-min bars for VWAP zone computation (20 min after NSE open)
    scheduler.add_job(
        _intraday_vwap_fetch,
        CronTrigger(hour=9, minute=20, day_of_week="mon-fri", timezone=_IST),
        id=JobIds.INTRADAY_VWAP_FETCH,
        replace_existing=True,
    )
```

- [ ] **Step 4: Smoke-test the backtest endpoint (requires running backend)**

```bash
curl -s -X POST \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  "http://localhost:8000/api/v1/zones/backtest/run?symbol=RELIANCE&from_date=2023-01-01&to_date=2023-06-30"
```

Expected: JSON with `total_trades`, `win_rate`, `total_pnl_pct` fields

- [ ] **Step 5: Commit**

```bash
git add backend/domains/zones/router.py backend/scheduler.py
git commit -m "feat: add zone backtest endpoints + intraday VWAP scheduler job"
```

---

## Task 7: Frontend API Additions

**Files:**
- Modify: `frontend/src/api/zones.ts`

- [ ] **Step 1: Update zones.ts**

Replace the entire file with:

```typescript
import { apiFetch } from './client'

export interface ZoneCard {
  low: number
  high: number
  score: number
  freshness: 'fresh' | 'tested' | 'weakened'
  touch_count: number
  last_reaction_pct: number
  source_tags: string[]
  source: 'daily' | 'vwap'   // NEW
}

export interface ZoneSetup {
  score: number
  ideal_entry: number
  aggressive_entry: number
  conservative_entry: number
  stop_loss: number
  t1: number
  t1_rr: number
  t2: number
  t2_rr: number
  t3: number
  t3_rr: number
  explanation: string
  invalidation: string
}

export interface ZoneResult {
  symbol: string
  demand_zones: ZoneCard[]
  supply_zones: ZoneCard[]
  long_setup: ZoneSetup | null
  short_setup: ZoneSetup | null
  market_structure: 'bullish' | 'bearish' | 'sideways'
  atr: number
  rvol: number
  price: number
  position_tag: string
  computed_at?: string
  long_setup_score?: number
  short_setup_score?: number
}

export interface ZoneRankRow {
  rank: number
  symbol: string
  long_setup_score: number | null
  short_setup_score: number | null
  best_demand_score: number | null
  best_supply_score: number | null
  position_tag: string
  price: number
  atr: number
  rvol: number
  best_long_rr: number | null
  best_short_rr: number | null
  computed_at: string
}

export interface RecomputeStatus {
  done: number
  total: number
  finished: boolean
  is_running: boolean
  started_at: string | null
  error: string | null
}

// ── Chart overlay ─────────────────────────────────────────────────────────────

export interface OhlcvBar {
  date: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export interface ZoneBand {
  low: number
  high: number
  strength: number
  zone_type: 'demand' | 'supply'
  source: 'daily' | 'vwap'
}

export interface ChartSetupLines {
  entry: number
  stop_loss: number
  target: number
}

export interface ChartDataResponse {
  ohlcv: OhlcvBar[]
  demand_bands?: ZoneBand[]
  supply_bands?: ZoneBand[]
  long_setup?: ChartSetupLines
  short_setup?: ChartSetupLines
}

// ── Backtest ──────────────────────────────────────────────────────────────────

export interface BacktestResult {
  id: number
  symbol: string
  from_date: string
  to_date: string
  total_trades: number
  win_rate: number | null
  total_pnl_pct: number
  avg_hold_days: number | null
  ran_at: string
}

export interface BacktestTrade {
  id: number
  entry_date: string
  entry_price: number
  exit_date: string | null
  exit_price: number | null
  pnl_pct: number | null
  exit_reason: string
  hold_days: number | null
}

// ── API functions ─────────────────────────────────────────────────────────────

export const analyzeZones = (symbol: string) =>
  apiFetch<ZoneResult>(`/zones/analyze/${symbol.toUpperCase()}`)

export const getZoneResult = (symbol: string) =>
  apiFetch<ZoneResult>(`/zones/results/${symbol.toUpperCase()}`)

export const getZoneRankings = (params?: { sort_by?: string; tag_filter?: string; limit?: number }) => {
  const qs = new URLSearchParams()
  if (params?.sort_by)    qs.set('sort_by',    params.sort_by)
  if (params?.tag_filter) qs.set('tag_filter', params.tag_filter)  // fix: was 'filter' (shadowed backend param)
  if (params?.limit)      qs.set('limit',      String(params.limit))
  const q = qs.toString()
  return apiFetch<ZoneRankRow[]>(`/zones/rankings${q ? '?' + q : ''}`)
}

export const recomputeAll = () =>
  apiFetch<{ status: string; symbol_count: number }>('/zones/recompute-all', { method: 'POST' })

export const getRecomputeStatus = () =>
  apiFetch<RecomputeStatus>('/zones/recompute-status')

export const getChartData = (symbol: string, bars = 120) =>
  apiFetch<ChartDataResponse>(`/zones/chart-data/${symbol.toUpperCase()}?bars=${bars}`)

export const runBacktest = (params: { symbol: string; from_date: string; to_date: string }) =>
  apiFetch<BacktestResult>(
    `/zones/backtest/run?symbol=${params.symbol.toUpperCase()}&from_date=${params.from_date}&to_date=${params.to_date}`,
    { method: 'POST' },
  )

export const getBacktestResults = (symbol: string) =>
  apiFetch<BacktestResult[]>(`/zones/backtest/results/${symbol.toUpperCase()}`)

export const getBacktestTrades = (resultId: number) =>
  apiFetch<BacktestTrade[]>(`/zones/backtest/trades/${resultId}`)
```

**Note:** `getZoneRankings` also has its call-site in `ZonesPage.tsx` which passes `filter` — update that call to `tag_filter` in Task 9.

- [ ] **Step 2: TypeScript check**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -20
```

Expected: No errors from `zones.ts`

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/zones.ts
git commit -m "feat: add chart + backtest types to zones API module, fix tag_filter param name"
```

---

## Task 8: PriceChart Component

**Files:**
- Create: `frontend/src/components/PriceChart.tsx`

- [ ] **Step 1: Install lightweight-charts**

```bash
cd frontend && npm install lightweight-charts
```

Expected: package added to `node_modules`, `package.json` updated

- [ ] **Step 2: Create PriceChart.tsx**

Create `frontend/src/components/PriceChart.tsx`:

```tsx
import { useEffect, useRef } from 'react'
import {
  createChart,
  CrosshairMode,
  LineStyle,
  type IChartApi,
  type ISeriesApi,
  type CandlestickSeriesOptions,
} from 'lightweight-charts'
import type { ZoneBand, ChartSetupLines, OhlcvBar } from '../api/zones'

interface PriceChartProps {
  ohlcv: OhlcvBar[]
  demandBands?: ZoneBand[]
  supplyBands?: ZoneBand[]
  longSetup?: ChartSetupLines
  shortSetup?: ChartSetupLines
  height?: number
}

export function PriceChart({
  ohlcv,
  demandBands = [],
  supplyBands = [],
  longSetup,
  shortSetup,
  height = 400,
}: PriceChartProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef     = useRef<IChartApi | null>(null)

  useEffect(() => {
    if (!containerRef.current || ohlcv.length === 0) return

    const chart = createChart(containerRef.current, {
      width:  containerRef.current.clientWidth,
      height,
      layout: {
        background: { color: '#0f172a' },
        textColor:  '#94a3b8',
      },
      grid: {
        vertLines: { color: '#1e293b' },
        horzLines: { color: '#1e293b' },
      },
      crosshair: { mode: CrosshairMode.Normal },
      timeScale: { borderColor: '#334155', timeVisible: true },
      rightPriceScale: { borderColor: '#334155' },
    })
    chartRef.current = chart

    const candleSeries = chart.addCandlestickSeries({
      upColor:      '#22c55e',
      downColor:    '#ef4444',
      borderVisible: false,
      wickUpColor:   '#22c55e',
      wickDownColor: '#ef4444',
    })

    candleSeries.setData(
      ohlcv.map(d => ({
        time:  d.date as any,
        open:  d.open,
        high:  d.high,
        low:   d.low,
        close: d.close,
      }))
    )

    // Demand zone bands (green)
    for (const z of demandBands) {
      candleSeries.createPriceLine({
        price:             z.low,
        color:             'rgba(34, 197, 94, 0.4)',
        lineWidth:         1,
        lineStyle:         LineStyle.Solid,
        axisLabelVisible:  false,
      })
      candleSeries.createPriceLine({
        price:             z.high,
        color:             'rgba(34, 197, 94, 0.7)',
        lineWidth:         2,
        lineStyle:         LineStyle.Solid,
        axisLabelVisible:  true,
        title:             `D${z.strength}${z.source === 'vwap' ? ' VWAP' : ''}`,
      })
    }

    // Supply zone bands (red)
    for (const z of supplyBands) {
      candleSeries.createPriceLine({
        price:             z.low,
        color:             'rgba(239, 68, 68, 0.7)',
        lineWidth:         2,
        lineStyle:         LineStyle.Solid,
        axisLabelVisible:  true,
        title:             `S${z.strength}${z.source === 'vwap' ? ' VWAP' : ''}`,
      })
      candleSeries.createPriceLine({
        price:             z.high,
        color:             'rgba(239, 68, 68, 0.4)',
        lineWidth:         1,
        lineStyle:         LineStyle.Solid,
        axisLabelVisible:  false,
      })
    }

    // Setup lines
    if (longSetup) {
      candleSeries.createPriceLine({ price: longSetup.entry,    color: '#3b82f6', lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: 'Entry' })
      candleSeries.createPriceLine({ price: longSetup.stop_loss, color: '#ef4444', lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: 'SL' })
      candleSeries.createPriceLine({ price: longSetup.target,   color: '#22c55e', lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: 'T2' })
    }

    chart.timeScale().fitContent()

    // Resize observer
    const ro = new ResizeObserver(() => {
      if (containerRef.current) chart.applyOptions({ width: containerRef.current.clientWidth })
    })
    ro.observe(containerRef.current)

    return () => {
      ro.disconnect()
      chart.remove()
      chartRef.current = null
    }
  }, [ohlcv, demandBands, supplyBands, longSetup, shortSetup, height])

  return <div ref={containerRef} style={{ height }} />
}
```

- [ ] **Step 3: TypeScript check**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep PriceChart
```

Expected: No errors related to PriceChart.tsx

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/PriceChart.tsx frontend/package.json frontend/package-lock.json
git commit -m "feat: add PriceChart component (lightweight-charts candlestick + zone bands)"
```

---

## Task 9: ZonesPage Layout B + Backtest Tab

**Files:**
- Modify: `frontend/src/pages/ZonesPage.tsx`

This task replaces `ZonesPage.tsx` completely. The changes are:

1. Import `PriceChart`, new API functions, and new types
2. Add `useQuery` for `getChartData` when `activeSymbol` is set
3. Add `activeTab` state: `'rankings' | 'backtest'`
4. Change layout: when `analyzeQuery.data` is present, render 2/3 chart + 1/3 panel side-by-side
5. Add Backtest tab: symbol input + date pickers + Run button + results table + trades table
6. Fix `getZoneRankings` call to use `tag_filter` instead of `filter`

- [ ] **Step 1: Replace ZonesPage.tsx**

```tsx
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  analyzeZones, getZoneRankings, recomputeAll, getRecomputeStatus,
  getChartData, runBacktest, getBacktestResults, getBacktestTrades,
  type ZoneCard, type ZoneRankRow, type ZoneResult, type RecomputeStatus,
  type BacktestResult, type BacktestTrade,
} from '../api/zones'
import { PriceChart } from '../components/PriceChart'

// ── Helpers ──────────────────────────────────────────────────────────────────

const POSITION_BADGE: Record<string, { bg: string; text: string; label: string }> = {
  in_demand:   { bg: 'bg-green-100',  text: 'text-green-700',  label: '✦ IN DEMAND' },
  near_demand: { bg: 'bg-yellow-100', text: 'text-yellow-700', label: '⚡ NEAR DEMAND' },
  near_supply: { bg: 'bg-orange-100', text: 'text-orange-700', label: '⚠ NEAR SUPPLY' },
  in_supply:   { bg: 'bg-red-100',    text: 'text-red-700',    label: '✦ IN SUPPLY' },
  breakout:    { bg: 'bg-blue-100',   text: 'text-blue-700',   label: '🚀 BREAKOUT' },
  neutral:     { bg: 'bg-gray-100',   text: 'text-gray-600',   label: '− NEUTRAL' },
}

const TREND_BADGE: Record<string, { bg: string; text: string }> = {
  bullish:  { bg: 'bg-green-100',  text: 'text-green-700' },
  bearish:  { bg: 'bg-red-100',    text: 'text-red-700' },
  sideways: { bg: 'bg-gray-100',   text: 'text-gray-600' },
}

const FRESHNESS_STYLE: Record<string, string> = {
  fresh:    'text-green-600',
  tested:   'text-yellow-600',
  weakened: 'text-red-500',
}

const EXIT_BADGE: Record<string, string> = {
  supply_zone:   'bg-green-100 text-green-700',
  stop_loss:     'bg-red-100 text-red-700',
  max_hold:      'bg-yellow-100 text-yellow-700',
  end_of_period: 'bg-gray-100 text-gray-600',
}

function scoreColor(s: number | null): string {
  if (s == null) return 'text-gray-400'
  if (s >= 75) return 'text-green-600 font-bold'
  if (s >= 50) return 'text-yellow-600 font-semibold'
  return 'text-red-500'
}

function SourceTag({ tag }: { tag: string }) {
  const isVwap = tag === 'vwap'
  return (
    <span className={`inline-block px-1.5 py-0.5 rounded text-[10px] border mr-1 mb-0.5 ${
      isVwap ? 'bg-purple-50 text-purple-700 border-purple-100' : 'bg-blue-50 text-blue-700 border-blue-100'
    }`}>
      {tag}
    </span>
  )
}

// ── Zone Card ─────────────────────────────────────────────────────────────────

function ZoneCardUI({ zone, type }: { zone: ZoneCard; type: 'demand' | 'supply' }) {
  const borderColor = type === 'demand' ? 'border-l-green-500' : 'border-l-red-500'
  const priceColor  = type === 'demand' ? 'text-green-700' : 'text-red-700'
  const badgeBg     = type === 'demand' ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'
  return (
    <div className={`bg-white rounded-md border border-gray-100 border-l-4 ${borderColor} p-3 mb-2`}>
      <div className="flex items-center justify-between mb-1">
        <span className={`font-bold text-sm ${priceColor}`}>
          ₹{zone.low.toLocaleString('en-IN', { maximumFractionDigits: 0 })} –{' '}
          ₹{zone.high.toLocaleString('en-IN', { maximumFractionDigits: 0 })}
        </span>
        <div className="flex items-center gap-1">
          {zone.source === 'vwap' && (
            <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-full bg-purple-100 text-purple-700">VWAP</span>
          )}
          <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${badgeBg}`}>{zone.score}/100</span>
        </div>
      </div>
      <div className="text-xs text-gray-500 mb-1.5">
        <span className={FRESHNESS_STYLE[zone.freshness] || 'text-gray-500'}>
          {zone.freshness.charAt(0).toUpperCase() + zone.freshness.slice(1)}
        </span>
        {zone.touch_count > 0 && ` · ${zone.touch_count} touch${zone.touch_count > 1 ? 'es' : ''}`}
        {zone.last_reaction_pct > 0 && ` · Last ${zone.last_reaction_pct.toFixed(1)}%`}
      </div>
      <div className="flex flex-wrap">
        {zone.source_tags.map(t => <SourceTag key={t} tag={t} />)}
      </div>
    </div>
  )
}

// ── Analysis Panel ─────────────────────────────────────────────────────────────

function AnalysisPanel({ result }: { result: ZoneResult }) {
  const [showShort, setShowShort] = useState(false)
  const posTag   = POSITION_BADGE[result.position_tag] ?? POSITION_BADGE.neutral
  const trendTag = TREND_BADGE[result.market_structure] ?? TREND_BADGE.sideways

  return (
    <div className="h-full overflow-y-auto">
      {/* Market structure strip */}
      <div className="flex flex-wrap items-center gap-2 px-3 py-2 bg-gray-50 rounded-md mb-3 text-xs">
        <span className="font-bold text-sm">{result.symbol}</span>
        <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${trendTag.bg} ${trendTag.text}`}>
          {result.market_structure.toUpperCase()}
        </span>
        <span>₹{result.price.toLocaleString('en-IN', { maximumFractionDigits: 0 })}</span>
        <span>ATR {result.atr.toFixed(1)}</span>
        <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${posTag.bg} ${posTag.text}`}>
          {posTag.label}
        </span>
      </div>

      {/* Demand zones */}
      <div className="bg-green-50 border border-green-100 rounded-md p-3 mb-2">
        <div className="text-xs font-bold text-green-700 mb-2">⬇ DEMAND ({result.demand_zones.length})</div>
        {result.demand_zones.length === 0
          ? <div className="text-xs text-gray-400">None</div>
          : result.demand_zones.map(z => <ZoneCardUI key={`${z.low}-${z.high}`} zone={z} type="demand" />)
        }
      </div>

      {/* Supply zones */}
      <div className="bg-red-50 border border-red-100 rounded-md p-3 mb-2">
        <div className="text-xs font-bold text-red-700 mb-2">⬆ SUPPLY ({result.supply_zones.length})</div>
        {result.supply_zones.length === 0
          ? <div className="text-xs text-gray-400">None</div>
          : result.supply_zones.map(z => <ZoneCardUI key={`${z.low}-${z.high}`} zone={z} type="supply" />)
        }
      </div>

      {/* Setup panel */}
      <div className="bg-blue-50 border border-blue-100 rounded-md p-3">
        {result.long_setup ? (
          <>
            <div className="text-xs font-bold text-blue-700 mb-2">🎯 LONG — {result.long_setup.score}/100</div>
            <div className="grid grid-cols-2 gap-x-2 gap-y-1 text-xs mb-2">
              <span className="text-gray-500">Ideal Entry</span>
              <span className="font-semibold">₹{result.long_setup.ideal_entry.toLocaleString('en-IN', { maximumFractionDigits: 0 })}</span>
              <span className="text-red-500">Stop Loss</span>
              <span className="text-red-600 font-semibold">₹{result.long_setup.stop_loss.toLocaleString('en-IN', { maximumFractionDigits: 0 })}</span>
              <span className="text-green-600">Target 1</span>
              <span className="text-green-700 font-semibold">₹{result.long_setup.t1.toLocaleString('en-IN', { maximumFractionDigits: 0 })} · 1:{result.long_setup.t1_rr}</span>
              <span className="text-green-600">Target 2</span>
              <span className="text-green-700">₹{result.long_setup.t2.toLocaleString('en-IN', { maximumFractionDigits: 0 })} · 1:{result.long_setup.t2_rr}</span>
            </div>
            <div className="text-[10px] text-gray-600 bg-white border border-blue-100 rounded p-2 leading-relaxed mb-2">
              {result.long_setup.explanation}
            </div>
            <div className="text-[10px] text-red-600">{result.long_setup.invalidation}</div>
          </>
        ) : (
          <div className="text-xs text-gray-400">No long setup</div>
        )}
        {result.short_setup && (
          <div className="border-t border-blue-100 mt-2 pt-2">
            <button onClick={() => setShowShort(v => !v)} className="text-xs font-bold text-purple-700 w-full text-left">
              ⬇ SHORT — {result.short_setup.score}/100 {showShort ? '▲' : '▼'}
            </button>
            {showShort && (
              <div className="text-xs text-gray-700 mt-1">
                Entry ₹{result.short_setup.ideal_entry.toLocaleString('en-IN', { maximumFractionDigits: 0 })} ·{' '}
                SL ₹{result.short_setup.stop_loss.toLocaleString('en-IN', { maximumFractionDigits: 0 })} ·{' '}
                T1 ₹{result.short_setup.t1.toLocaleString('en-IN', { maximumFractionDigits: 0 })} · R:R 1:{result.short_setup.t1_rr}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

// ── Rank Row ──────────────────────────────────────────────────────────────────

function RankRow({
  row, onSelect, isSelected,
}: { row: ZoneRankRow; onSelect: (sym: string) => void; isSelected: boolean }) {
  const posStyle = POSITION_BADGE[row.position_tag] ?? POSITION_BADGE.neutral
  return (
    <div className={`border-b border-gray-100 cursor-pointer hover:bg-gray-50 ${isSelected ? 'bg-blue-50 border-l-2 border-l-blue-500' : ''}`}>
      <div
        className="grid gap-1 px-3 py-2 text-xs"
        style={{ gridTemplateColumns: '28px 80px 55px 100px 70px 55px 55px 50px 50px 70px' }}
        onClick={() => onSelect(row.symbol)}
      >
        <span className="text-gray-400">{row.rank}</span>
        <span className={`font-bold ${isSelected ? 'text-blue-600' : ''}`}>{row.symbol} {isSelected ? '▼' : '▶'}</span>
        <span className={scoreColor(row.long_setup_score)}>{row.long_setup_score ?? '—'}</span>
        <span className={`px-1.5 py-0.5 rounded-full text-[10px] font-medium ${posStyle.bg} ${posStyle.text}`}>{posStyle.label}</span>
        <span className={scoreColor(row.short_setup_score)}>{row.short_setup_score != null ? `S:${row.short_setup_score}` : '—'}</span>
        <span className={scoreColor(row.best_demand_score)}>{row.best_demand_score ?? '—'}</span>
        <span className={scoreColor(row.best_supply_score)}>{row.best_supply_score ?? '—'}</span>
        <span>{row.atr?.toFixed(1) ?? '—'}</span>
        <span className={row.rvol >= 1.5 ? 'text-green-600 font-medium' : ''}>{row.rvol?.toFixed(1) ?? '—'}×</span>
        <span className="text-gray-400">{row.computed_at ? new Date(row.computed_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '—'}</span>
      </div>
    </div>
  )
}

// ── Backtest Tab ──────────────────────────────────────────────────────────────

function BacktestTab() {
  const [btSymbol, setBtSymbol]   = useState('')
  const [fromDate, setFromDate]   = useState('2022-01-01')
  const [toDate, setToDate]       = useState(new Date().toISOString().slice(0, 10))
  const [selectedResult, setSelectedResult] = useState<BacktestResult | null>(null)
  const queryClient = useQueryClient()

  const btMutation = useMutation({
    mutationFn: runBacktest,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['zone-bt-results'] })
    },
  })

  const resultsQuery = useQuery({
    queryKey: ['zone-bt-results', btSymbol],
    queryFn:  () => getBacktestResults(btSymbol),
    enabled:  btSymbol.length > 0,
  })

  const tradesQuery = useQuery({
    queryKey: ['zone-bt-trades', selectedResult?.id],
    queryFn:  () => getBacktestTrades(selectedResult!.id),
    enabled:  !!selectedResult,
  })

  const handleRun = () => {
    if (!btSymbol.trim()) return
    btMutation.mutate({ symbol: btSymbol.trim().toUpperCase(), from_date: fromDate, to_date: toDate })
  }

  const result = btMutation.data

  return (
    <div>
      {/* Form */}
      <div className="flex items-center gap-3 bg-white rounded-lg border border-gray-200 px-4 py-3 mb-4 shadow-sm">
        <input
          className="border border-gray-300 rounded px-3 py-1.5 text-sm w-28 focus:outline-none focus:border-blue-400"
          placeholder="Symbol"
          value={btSymbol}
          onChange={e => setBtSymbol(e.target.value.toUpperCase())}
        />
        <input type="date" value={fromDate} onChange={e => setFromDate(e.target.value)}
          className="border border-gray-300 rounded px-2 py-1.5 text-sm focus:outline-none" />
        <span className="text-gray-400 text-sm">→</span>
        <input type="date" value={toDate} onChange={e => setToDate(e.target.value)}
          className="border border-gray-300 rounded px-2 py-1.5 text-sm focus:outline-none" />
        <button
          onClick={handleRun}
          disabled={btMutation.isPending || !btSymbol.trim()}
          className="px-4 py-1.5 bg-indigo-600 text-white text-sm rounded font-medium hover:bg-indigo-700 disabled:opacity-50"
        >
          {btMutation.isPending ? 'Simulating…' : 'Run Backtest'}
        </button>
      </div>

      {/* Latest result summary */}
      {result && (
        <div className="bg-white rounded-lg border border-gray-200 p-4 mb-4 shadow-sm">
          <div className="text-sm font-bold text-gray-700 mb-2">{result.symbol} · {result.from_date} → {result.to_date}</div>
          <div className="grid grid-cols-4 gap-4 text-center">
            <div><div className="text-2xl font-bold text-gray-800">{result.total_trades}</div><div className="text-xs text-gray-500">Trades</div></div>
            <div><div className={`text-2xl font-bold ${result.win_rate != null && result.win_rate >= 50 ? 'text-green-600' : 'text-red-600'}`}>{result.win_rate != null ? `${result.win_rate}%` : '—'}</div><div className="text-xs text-gray-500">Win Rate</div></div>
            <div><div className={`text-2xl font-bold ${result.total_pnl_pct >= 0 ? 'text-green-600' : 'text-red-600'}`}>{result.total_pnl_pct >= 0 ? '+' : ''}{result.total_pnl_pct.toFixed(1)}%</div><div className="text-xs text-gray-500">Total PnL</div></div>
            <div><div className="text-2xl font-bold text-gray-800">{result.avg_hold_days != null ? result.avg_hold_days.toFixed(1) : '—'}</div><div className="text-xs text-gray-500">Avg Days</div></div>
          </div>
        </div>
      )}

      {/* Past results + trade table */}
      {btSymbol && (
        <div className="bg-white rounded-lg border border-gray-200 shadow-sm">
          <div className="px-4 py-3 border-b border-gray-100 text-sm font-bold text-gray-700">
            Past Backtests — {btSymbol}
          </div>
          {resultsQuery.data?.map(r => (
            <div key={r.id}>
              <div
                className={`grid gap-2 px-4 py-2 text-xs cursor-pointer hover:bg-gray-50 border-b border-gray-100 ${selectedResult?.id === r.id ? 'bg-blue-50' : ''}`}
                style={{ gridTemplateColumns: '120px 80px 60px 80px 80px' }}
                onClick={() => setSelectedResult(selectedResult?.id === r.id ? null : r)}
              >
                <span>{r.from_date} → {r.to_date}</span>
                <span>{r.total_trades} trades</span>
                <span className={r.win_rate != null && r.win_rate >= 50 ? 'text-green-600 font-medium' : 'text-red-600'}>{r.win_rate != null ? `${r.win_rate}%` : '—'} WR</span>
                <span className={r.total_pnl_pct >= 0 ? 'text-green-600' : 'text-red-600'}>{r.total_pnl_pct >= 0 ? '+' : ''}{r.total_pnl_pct.toFixed(1)}%</span>
                <span className="text-gray-400">{new Date(r.ran_at).toLocaleDateString()}</span>
              </div>
              {selectedResult?.id === r.id && tradesQuery.data && (
                <div className="bg-blue-50 px-4 py-3 border-b border-blue-100">
                  <div className="grid gap-1 mb-1 text-[10px] font-bold text-gray-500" style={{ gridTemplateColumns: '90px 90px 75px 60px 70px 80px' }}>
                    <span>Entry</span><span>Exit</span><span>Prices</span><span>PnL%</span><span>Days</span><span>Reason</span>
                  </div>
                  {tradesQuery.data.map(t => (
                    <div key={t.id} className="grid gap-1 text-xs py-0.5" style={{ gridTemplateColumns: '90px 90px 75px 60px 70px 80px' }}>
                      <span>{t.entry_date}</span>
                      <span>{t.exit_date ?? '—'}</span>
                      <span>₹{t.entry_price?.toLocaleString('en-IN', { maximumFractionDigits: 0 })} → ₹{t.exit_price?.toLocaleString('en-IN', { maximumFractionDigits: 0 }) ?? '—'}</span>
                      <span className={t.pnl_pct != null && t.pnl_pct >= 0 ? 'text-green-600 font-medium' : 'text-red-600'}>{t.pnl_pct != null ? `${t.pnl_pct >= 0 ? '+' : ''}${t.pnl_pct.toFixed(1)}%` : '—'}</span>
                      <span>{t.hold_days ?? '—'}d</span>
                      <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${EXIT_BADGE[t.exit_reason] ?? 'bg-gray-100 text-gray-600'}`}>{t.exit_reason}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
          {resultsQuery.data?.length === 0 && (
            <div className="text-center py-8 text-gray-400 text-sm">No backtests run for {btSymbol} yet.</div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

type SortKey = 'long_score' | 'short_score' | 'demand_score' | 'supply_score' | 'rvol' | 'atr'
type FilterKey = '' | 'long' | 'short' | 'in_demand' | 'breakout' | 'near_supply'

const FILTERS: { key: FilterKey; label: string }[] = [
  { key: 'long',        label: 'Long' },
  { key: 'short',       label: 'Short' },
  { key: 'in_demand',   label: 'In Demand' },
  { key: 'breakout',    label: 'Breakout' },
  { key: 'near_supply', label: 'Near Supply' },
]

const SORTS: { key: SortKey; label: string }[] = [
  { key: 'long_score',   label: 'Long Score' },
  { key: 'short_score',  label: 'Short Score' },
  { key: 'demand_score', label: 'Demand' },
  { key: 'supply_score', label: 'Supply' },
  { key: 'rvol',         label: 'RVol' },
  { key: 'atr',          label: 'ATR' },
]

export function ZonesPage() {
  const [symbol, setSymbol]             = useState('')
  const [activeSymbol, setActiveSymbol] = useState<string | null>(null)
  const [sortBy, setSortBy]             = useState<SortKey>('long_score')
  const [filterBy, setFilterBy]         = useState<FilterKey>('')
  const [expandedSym, setExpandedSym]   = useState<string | null>(null)
  const [activeTab, setActiveTab]       = useState<'rankings' | 'backtest'>('rankings')

  const analyzeQuery = useQuery({
    queryKey: ['zone-analyze', activeSymbol],
    queryFn:  () => analyzeZones(activeSymbol!),
    enabled:  !!activeSymbol,
  })

  const chartQuery = useQuery({
    queryKey: ['zone-chart', activeSymbol],
    queryFn:  () => getChartData(activeSymbol!),
    enabled:  !!activeSymbol,
    staleTime: 60 * 1000,
  })

  const rankingsQuery = useQuery({
    queryKey: ['zone-rankings', sortBy, filterBy],
    queryFn:  () => getZoneRankings({ sort_by: sortBy, tag_filter: filterBy || undefined }),
    staleTime: 5 * 60 * 1000,
  })

  const statusQuery = useQuery({
    queryKey: ['zone-recompute-status'],
    queryFn:  getRecomputeStatus,
    refetchInterval: (query) =>
      (query.state.data as RecomputeStatus | undefined)?.is_running ? 3000 : false,
  })

  const recomputeMut = useMutation({ mutationFn: recomputeAll })

  const handleAnalyze = () => {
    const sym = symbol.trim().toUpperCase()
    if (sym) { setActiveSymbol(sym); setExpandedSym(sym) }
  }

  const handleRowClick = (sym: string) => {
    if (expandedSym === sym) {
      setExpandedSym(null)
    } else {
      setExpandedSym(sym)
      setActiveSymbol(sym)
    }
  }

  const status = statusQuery.data
  const lastBatch = status?.finished
    ? `Last batch: just now · ${status.total} stocks`
    : status?.is_running
      ? `Recomputing… ${status.done}/${status.total}`
      : status?.started_at
        ? `Last batch: ${new Date(status.started_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`
        : 'No batch run yet'

  const showChart = !!analyzeQuery.data && !!chartQuery.data

  return (
    <div>
      {/* Top bar */}
      <div className="flex items-center gap-3 bg-white rounded-lg border border-gray-200 px-4 py-3 mb-4 shadow-sm">
        <span className="font-bold text-base text-gray-800">Demand &amp; Supply Zones</span>
        {/* Tab buttons */}
        <div className="flex gap-1 ml-2">
          {(['rankings', 'backtest'] as const).map(tab => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-3 py-1 text-xs rounded font-medium ${
                activeTab === tab
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
              }`}
            >
              {tab.charAt(0).toUpperCase() + tab.slice(1)}
            </button>
          ))}
        </div>
        {activeTab === 'rankings' && (
          <>
            <input
              className="flex-1 ml-2 border border-gray-300 rounded px-3 py-1.5 text-sm focus:outline-none focus:border-blue-400"
              placeholder="Symbol… RELIANCE"
              value={symbol}
              onChange={e => setSymbol(e.target.value.toUpperCase())}
              onKeyDown={e => e.key === 'Enter' && handleAnalyze()}
            />
            <button
              onClick={handleAnalyze}
              disabled={analyzeQuery.isFetching}
              className="px-4 py-1.5 bg-green-600 text-white text-sm rounded font-medium hover:bg-green-700 disabled:opacity-50"
            >
              {analyzeQuery.isFetching ? 'Analyzing…' : 'Analyze'}
            </button>
            <span className="text-xs text-gray-400 whitespace-nowrap">{lastBatch}</span>
            <button
              onClick={() => recomputeMut.mutate()}
              disabled={status?.is_running || recomputeMut.isPending}
              className="px-3 py-1.5 bg-indigo-600 text-white text-xs rounded font-medium hover:bg-indigo-700 disabled:opacity-50 whitespace-nowrap"
            >
              ⟳ Recompute All
            </button>
          </>
        )}
      </div>

      {activeTab === 'backtest' && <BacktestTab />}

      {activeTab === 'rankings' && (
        <>
          {analyzeQuery.isError && (
            <div className="text-red-600 text-sm mb-4 bg-red-50 border border-red-200 rounded p-3">
              Failed to analyze {activeSymbol}: {(analyzeQuery.error as Error)?.message}
            </div>
          )}

          {/* Chart + Analysis panel (layout B: 2/3 + 1/3) */}
          {showChart && (
            <div className="grid gap-4 mb-4" style={{ gridTemplateColumns: '2fr 1fr' }}>
              <div className="bg-white rounded-lg border border-gray-200 overflow-hidden shadow-sm">
                <PriceChart
                  ohlcv={chartQuery.data!.ohlcv}
                  demandBands={chartQuery.data!.demand_bands}
                  supplyBands={chartQuery.data!.supply_bands}
                  longSetup={chartQuery.data!.long_setup}
                  height={420}
                />
              </div>
              <div className="bg-white rounded-lg border border-gray-200 p-3 shadow-sm">
                <AnalysisPanel result={analyzeQuery.data!} />
              </div>
            </div>
          )}

          {/* Rankings table */}
          <div className="bg-white rounded-lg border border-gray-200 shadow-sm">
            <div className="flex items-center gap-2 px-4 py-3 border-b border-gray-100">
              <span className="font-bold text-sm">All Stocks Ranking</span>
              <span className="text-xs text-gray-400">{rankingsQuery.data?.length ?? 0} stocks</span>
              <div className="ml-auto flex items-center gap-2">
                {FILTERS.map(f => (
                  <button
                    key={f.key}
                    onClick={() => setFilterBy(filterBy === f.key ? '' : f.key)}
                    className={`px-2.5 py-1 rounded-full text-xs font-medium border transition-colors ${
                      filterBy === f.key
                        ? 'bg-blue-600 text-white border-blue-600'
                        : 'bg-white text-gray-600 border-gray-300 hover:border-blue-400'
                    }`}
                  >
                    {f.label}
                  </button>
                ))}
                <select
                  value={sortBy}
                  onChange={e => setSortBy(e.target.value as SortKey)}
                  className="border border-gray-300 rounded text-xs px-2 py-1 ml-2 focus:outline-none"
                >
                  {SORTS.map(s => <option key={s.key} value={s.key}>{s.label}</option>)}
                </select>
              </div>
            </div>

            <div
              className="grid gap-1 px-3 py-2 bg-gray-50 text-xs font-bold text-gray-500 border-b border-gray-100"
              style={{ gridTemplateColumns: '28px 80px 55px 100px 70px 55px 55px 50px 50px 70px' }}
            >
              <span>#</span><span>Symbol</span><span>Score</span><span>Position</span>
              <span>Setup</span><span>Demand</span><span>Supply</span><span>ATR</span><span>RVol</span><span>Computed</span>
            </div>

            {rankingsQuery.isLoading && (
              <div className="text-center py-8 text-gray-400 text-sm">Loading rankings…</div>
            )}

            {rankingsQuery.data?.map(row => (
              <div key={row.symbol}>
                <RankRow row={row} onSelect={handleRowClick} isSelected={expandedSym === row.symbol} />
                {expandedSym === row.symbol && analyzeQuery.data?.symbol === row.symbol && (
                  <div className="bg-blue-50 px-4 py-2.5 text-xs text-gray-700 border-b border-blue-100">
                    <span className="font-semibold">Demand:</span>{' '}
                    {analyzeQuery.data.demand_zones.slice(0, 2).map(
                      z => `₹${z.low.toLocaleString('en-IN', { maximumFractionDigits: 0 })}–₹${z.high.toLocaleString('en-IN', { maximumFractionDigits: 0 })} (${z.score})`
                    ).join(' · ')}
                    {' '}|{' '}
                    <span className="font-semibold">Supply:</span>{' '}
                    {analyzeQuery.data.supply_zones.slice(0, 2).map(
                      z => `₹${z.low.toLocaleString('en-IN', { maximumFractionDigits: 0 })}–₹${z.high.toLocaleString('en-IN', { maximumFractionDigits: 0 })} (${z.score})`
                    ).join(' · ')}
                    {analyzeQuery.data.long_setup && (
                      <>{' '}|{' '}<span className="font-semibold">Long:</span>{' '}
                        Entry ₹{analyzeQuery.data.long_setup.ideal_entry.toLocaleString('en-IN', { maximumFractionDigits: 0 })} ·{' '}
                        SL ₹{analyzeQuery.data.long_setup.stop_loss.toLocaleString('en-IN', { maximumFractionDigits: 0 })} ·{' '}
                        T1 ₹{analyzeQuery.data.long_setup.t1.toLocaleString('en-IN', { maximumFractionDigits: 0 })} · R:R 1:{analyzeQuery.data.long_setup.t1_rr}
                      </>
                    )}
                    {' '}
                    <button
                      className={`underline ml-1 ${analyzeQuery.isFetching && activeSymbol === row.symbol ? 'text-gray-400 cursor-wait' : 'text-blue-600 hover:text-blue-800'}`}
                      onClick={() => {
                        setActiveSymbol(row.symbol)
                        if (analyzeQuery.data?.symbol === row.symbol) {
                          window.scrollTo({ top: 0, behavior: 'smooth' })
                        }
                      }}
                    >
                      {analyzeQuery.isFetching && activeSymbol === row.symbol ? 'Loading…' : 'View full analysis ↑'}
                    </button>
                  </div>
                )}
              </div>
            ))}

            {rankingsQuery.data?.length === 0 && !rankingsQuery.isLoading && (
              <div className="text-center py-8 text-gray-400 text-sm">
                No zone data for today. Click "Recompute All" to generate.
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}
```

- [ ] **Step 2: TypeScript check**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -30
```

Expected: Zero TypeScript errors

- [ ] **Step 3: Build check**

```bash
cd frontend && npm run build 2>&1 | tail -10
```

Expected: Build succeeds with no errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/ZonesPage.tsx
git commit -m "feat: zones page layout B (2/3 chart + 1/3 panel) + backtest tab"
```

---

## Self-Review Checklist

After completing all tasks, run the full verification:

**Backend:**
```bash
cd backend && python -m pytest tests/test_zone_detectors.py tests/test_zone_clusterer.py tests/test_zone_scorer.py tests/test_zone_entry_engine.py tests/test_intraday_fetcher.py tests/test_vwap_detector.py tests/test_zone_backtester.py -v
```
Expected: All tests pass.

**Frontend:**
```bash
cd frontend && npx tsc --noEmit && npm run build
```
Expected: Zero TS errors, clean build.

**Functional verification (requires running stack):**
1. `GET /api/v1/zones/chart-data/RELIANCE?bars=60` → JSON with `ohlcv` array and optionally `demand_bands`/`supply_bands`
2. `POST /api/v1/zones/backtest/run?symbol=RELIANCE&from_date=2023-01-01&to_date=2024-06-30` → JSON with `total_trades > 0`, exit reasons from `{supply_zone, stop_loss, max_hold, end_of_period}`
3. ZonesPage: analyze RELIANCE → 2/3 chart (candlesticks + zone band lines) + 1/3 panel visible
4. ZonesPage Backtest tab: symbol + dates + Run → summary + trade table with exit reason badges
5. After intraday data present: zone result for RELIANCE includes at least one zone with `"source": "vwap"`
