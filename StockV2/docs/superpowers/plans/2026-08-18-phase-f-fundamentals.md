# Phase F: Fundamentals Pipeline + Fundamental Strategies — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Populate the `fundamentals` table via yfinance weekly and add 6 fundamental-based strategies (CANSLIM, Magic Formula, Graham Value, Growth Investing, Dividend Investing, FII/DII Accumulation) to the existing strategy engine.

**Architecture:** A new `FundamentalsService` fetches data via `yfinance` and stores it in the existing `fundamentals` DB table. `StrategyEngine.scan_all()` is updated to pass the fundamentals dict into each strategy's `generate_signal()` call. The 6 new strategy files are auto-discovered and auto-seeded like every other strategy in the codebase. No new frontend pages — new strategies appear automatically in the Scanner, Leaderboard, and Dashboard.

**Tech Stack:** Python, yfinance, SQLAlchemy (raw text queries), FastAPI, pytest.

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `backend/models.py` | Modify | Add `dividend_yield` column to `Fundamental` model |
| `backend/main.py` | Modify | Add startup migration for `dividend_yield` column |
| `backend/domains/data/fundamentals.py` | Create | `FundamentalsService` — yfinance fetch + DB upsert |
| `backend/domains/strategies/engine.py` | Modify | Pass `fundamentals` dict into every `generate_signal()` call |
| `backend/scheduler.py` | Modify | Replace `_weekly_fundamentals` placeholder with real implementation |
| `backend/domains/data/router.py` | Modify | Add `POST /data/fundamentals/refresh` and `GET /data/fundamentals/{symbol}` |
| `backend/domains/strategies/strategies/canslim.py` | Create | CANSLIM strategy |
| `backend/domains/strategies/strategies/magic_formula.py` | Create | Magic Formula strategy |
| `backend/domains/strategies/strategies/graham_value.py` | Create | Graham Number value strategy |
| `backend/domains/strategies/strategies/growth_investing.py` | Create | Growth Investing strategy |
| `backend/domains/strategies/strategies/dividend_investing.py` | Create | Dividend Investing strategy |
| `backend/domains/strategies/strategies/fii_dii_accumulation.py` | Create | FII/DII institutional accumulation proxy strategy |
| `backend/tests/test_fundamentals_service.py` | Create | Tests for `FundamentalsService` |
| `backend/tests/test_fundamental_strategies.py` | Create | Tests for all 6 fundamental strategies |

---

## Context for Implementers

### How strategies work in this codebase

1. Drop a `.py` file into `backend/domains/strategies/strategies/`
2. Define a class inheriting `BaseStrategy` with a unique `name` class attribute
3. `_discover_strategies()` in `engine.py` auto-imports it at startup
4. `seed_strategies()` in `seed.py` registers it in the `strategies` DB table
5. Every strategy's `generate_signal(df, fundamentals)` receives:
   - `df`: pandas DataFrame of recent OHLCV + all indicator columns (last 200 rows)
   - `fundamentals`: dict from `FundamentalsService.get_latest(symbol)` — can be `{}` if not yet fetched

### Key indicator columns in df (always present after `IndicatorEngine.compute()`)
`rsi_14`, `sma_20`, `sma_50`, `ema_9`, `ema_21`, `bb_upper`, `bb_lower`, `bb_middle`, `adx_14`, `atr_14`, `volume_sma_20`, `volume_ratio`, `macd`, `macd_signal`, `macd_hist`

### Fundamentals dict shape (after FundamentalsService implementation)
```python
{
    "pe_ratio": float | None,      # P/E ratio (e.g. 24.5)
    "pb_ratio": float | None,      # P/B ratio (e.g. 2.1)
    "eps": float | None,           # EPS TTM in INR (e.g. 95.3)
    "revenue": float | None,       # Revenue TTM in INR (e.g. 8.74e11)
    "net_profit": float | None,    # Net profit TTM in INR
    "debt_equity": float | None,   # D/E ratio as a decimal (e.g. 0.43)
    "roe": float | None,           # ROE as decimal (e.g. 0.118 = 11.8%)
    "dividend_yield": float | None, # Dividend yield as decimal (e.g. 0.008 = 0.8%)
    "data_as_of": str | None,      # Date string "YYYY-MM-DD"
}
```

### Test patterns
Tests use in-memory SQLite. See `tests/test_data_router.py` for the `client` fixture pattern and `tests/test_strategies.py` for the `_make_df()` helper pattern. Run tests from `backend/` directory: `cd backend && pytest tests/<test_file>.py -v`

---

## Task 1: Add `dividend_yield` to model + create FundamentalsService

**Files:**
- Modify: `backend/models.py` (line 82 — after `dii_holding`)
- Modify: `backend/main.py` (line 43 — after `create_all`)
- Create: `backend/domains/data/fundamentals.py`
- Create: `backend/tests/test_fundamentals_service.py`

- [ ] **Step 1: Write failing tests for FundamentalsService**

Create `backend/tests/test_fundamentals_service.py`:

```python
from unittest.mock import patch, MagicMock
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base
import models  # noqa
from domains.data.fundamentals import FundamentalsService


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _mock_ticker(pe=20.0, pb=2.0, eps=50.0, revenue=1e10, net_profit=1e9,
                 de=0.5, roe=0.15, div_yield=0.02):
    mock = MagicMock()
    mock.info = {
        "trailingPE": pe, "priceToBook": pb, "trailingEps": eps,
        "totalRevenue": revenue, "netIncomeToCommon": net_profit,
        "debtToEquity": de, "returnOnEquity": roe, "dividendYield": div_yield,
    }
    return mock


def test_refresh_one_stores_row(db):
    with patch("yfinance.Ticker", return_value=_mock_ticker()):
        result = FundamentalsService(db).refresh_one("RELIANCE")
    assert result is True
    row = db.execute(
        text("SELECT eps, roe, dividend_yield FROM fundamentals WHERE symbol='RELIANCE'")
    ).fetchone()
    assert row is not None
    assert row[0] == pytest.approx(50.0)
    assert row[1] == pytest.approx(0.15)
    assert row[2] == pytest.approx(0.02)


def test_refresh_one_returns_false_on_yfinance_error(db):
    with patch("yfinance.Ticker", side_effect=Exception("network error")):
        result = FundamentalsService(db).refresh_one("BADSTOCK")
    assert result is False


def test_get_latest_returns_populated_dict(db):
    db.execute(text("""
        INSERT INTO fundamentals
            (symbol, pe_ratio, pb_ratio, eps, revenue, net_profit,
             debt_equity, roe, dividend_yield, data_as_of, updated_at)
        VALUES ('TCS', 25.0, 10.0, 120.0, 2e11, 4e10, 0.05, 0.42, 0.012,
                '2026-08-01', datetime('now'))
    """))
    db.commit()
    f = FundamentalsService(db).get_latest("TCS")
    assert f["eps"] == pytest.approx(120.0)
    assert f["roe"] == pytest.approx(0.42)
    assert f["dividend_yield"] == pytest.approx(0.012)
    assert f["data_as_of"] == "2026-08-01"


def test_get_latest_returns_empty_dict_when_no_data(db):
    result = FundamentalsService(db).get_latest("UNKNOWN")
    assert result == {}


def test_refresh_one_overwrites_existing_row(db):
    with patch("yfinance.Ticker", return_value=_mock_ticker(eps=50.0)):
        FundamentalsService(db).refresh_one("INFY")
    with patch("yfinance.Ticker", return_value=_mock_ticker(eps=75.0)):
        FundamentalsService(db).refresh_one("INFY")
    count = db.execute(text("SELECT COUNT(*) FROM fundamentals WHERE symbol='INFY'")).scalar()
    assert count == 1
    row = db.execute(text("SELECT eps FROM fundamentals WHERE symbol='INFY'")).fetchone()
    assert row[0] == pytest.approx(75.0)
```

- [ ] **Step 2: Run tests to confirm they fail**

```
cd backend && pytest tests/test_fundamentals_service.py -v
```
Expected: `ModuleNotFoundError: No module named 'domains.data.fundamentals'`

- [ ] **Step 3: Add `dividend_yield` to `Fundamental` model**

In `backend/models.py`, add one line after the `dii_holding` column (currently line 80):

```python
    dii_holding: Mapped[Optional[float]] = mapped_column(Float)
    dividend_yield: Mapped[Optional[float]] = mapped_column(Float)   # add this line
    data_as_of: Mapped[Optional[date]] = mapped_column(Date)
```

- [ ] **Step 4: Add startup migration in `main.py`**

In `backend/main.py`, add these lines immediately after `Base.metadata.create_all(bind=engine)` (currently line 43):

```python
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables verified")

    # Phase F: safe migration — add dividend_yield column to existing DBs
    with engine.connect() as _conn:
        try:
            _conn.execute(text("ALTER TABLE fundamentals ADD COLUMN dividend_yield REAL"))
            _conn.commit()
        except Exception:
            pass  # column already exists
```

- [ ] **Step 5: Create `backend/domains/data/fundamentals.py`**

```python
import logging
import time
from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class FundamentalsService:
    def __init__(self, db: Session):
        self.db = db

    def get_latest(self, symbol: str) -> dict:
        row = self.db.execute(
            text("""
                SELECT pe_ratio, pb_ratio, eps, revenue, net_profit,
                       debt_equity, roe, dividend_yield, data_as_of
                FROM fundamentals
                WHERE symbol = :sym
                ORDER BY data_as_of DESC LIMIT 1
            """),
            {"sym": symbol},
        ).fetchone()
        if not row:
            return {}
        return {
            "pe_ratio":       row[0],
            "pb_ratio":       row[1],
            "eps":            row[2],
            "revenue":        row[3],
            "net_profit":     row[4],
            "debt_equity":    row[5],
            "roe":            row[6],
            "dividend_yield": row[7],
            "data_as_of":     str(row[8]) if row[8] else None,
        }

    def refresh_one(self, symbol: str) -> bool:
        try:
            import yfinance as yf
            ticker = yf.Ticker(symbol + ".NS")
            info = ticker.info or {}

            pe      = _safe_float(info.get("trailingPE"))
            pb      = _safe_float(info.get("priceToBook"))
            eps     = _safe_float(info.get("trailingEps"))
            revenue = _safe_float(info.get("totalRevenue"))
            profit  = _safe_float(info.get("netIncomeToCommon"))
            roe     = _safe_float(info.get("returnOnEquity"))
            div_yld = _safe_float(info.get("dividendYield"))

            # yfinance debtToEquity: returned as percentage (43.5 means 0.435 ratio)
            # Normalise to decimal ratio; values <= 2 are already in ratio form
            raw_de = info.get("debtToEquity")
            de = None
            if raw_de is not None:
                de = float(raw_de) / 100 if float(raw_de) > 2 else float(raw_de)

            self.db.execute(
                text("DELETE FROM fundamentals WHERE symbol = :sym"),
                {"sym": symbol},
            )
            self.db.execute(
                text("""
                    INSERT INTO fundamentals
                        (symbol, pe_ratio, pb_ratio, eps, revenue, net_profit,
                         debt_equity, roe, dividend_yield, data_as_of, updated_at)
                    VALUES (:sym, :pe, :pb, :eps, :rev, :np,
                            :de, :roe, :dy, :asof, datetime('now'))
                """),
                {
                    "sym": symbol, "pe": pe, "pb": pb, "eps": eps,
                    "rev": revenue, "np": profit, "de": de, "roe": roe,
                    "dy": div_yld, "asof": str(date.today()),
                },
            )
            self.db.commit()
            return True
        except Exception as e:
            logger.warning("[FundamentalsService] refresh_one %s: %s", symbol, e)
            return False

    def refresh_all(self, symbols: list[str]) -> dict:
        updated = skipped = 0
        for i, symbol in enumerate(symbols):
            if self.refresh_one(symbol):
                updated += 1
            else:
                skipped += 1
            if (i + 1) % 50 == 0:
                logger.info("[FundamentalsService] %d/%d done", i + 1, len(symbols))
            time.sleep(0.3)
        logger.info("[FundamentalsService] complete: updated=%d skipped=%d", updated, skipped)
        return {"updated": updated, "skipped": skipped}


def _safe_float(v) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None
```

- [ ] **Step 6: Run tests to confirm they pass**

```
cd backend && pytest tests/test_fundamentals_service.py -v
```
Expected: 5 PASSED

- [ ] **Step 7: Commit**

```bash
cd backend && git add domains/data/fundamentals.py models.py main.py tests/test_fundamentals_service.py
git commit -m "feat: FundamentalsService — yfinance fetch + fundamentals table upsert"
```

---

## Task 2: Wire fundamentals into StrategyEngine + scheduler + API endpoints

**Files:**
- Modify: `backend/domains/strategies/engine.py` (line 92)
- Modify: `backend/scheduler.py` (`_weekly_fundamentals` function, lines 237-238)
- Modify: `backend/domains/data/router.py` (add 2 new endpoints)

- [ ] **Step 1: Update `StrategyEngine.scan_all()` to pass fundamentals**

In `backend/domains/strategies/engine.py`, modify the `scan_all` method. Replace line 89-92:

```python
        df = IndicatorEngine.compute(df)
        symbol_signals: list[tuple[BaseStrategy, Signal]] = []
        for strategy in ALL_STRATEGIES:
            signal = strategy.generate_signal(df)
```

with:

```python
        df = IndicatorEngine.compute(df)
        from domains.data.fundamentals import FundamentalsService
        fundamentals = FundamentalsService(self.db).get_latest(symbol)
        symbol_signals: list[tuple[BaseStrategy, Signal]] = []
        for strategy in ALL_STRATEGIES:
            signal = strategy.generate_signal(df, fundamentals=fundamentals)
```

- [ ] **Step 2: Implement `_weekly_fundamentals` in `scheduler.py`**

Replace the two-line placeholder (currently lines 237-238):

```python
def _weekly_fundamentals():
    logger.info("[scheduler] weekly_fundamentals — placeholder (implemented in Plan 2)")
```

with:

```python
def _weekly_fundamentals():
    from database import SessionLocal
    from domains.data.fundamentals import FundamentalsService
    from domains.data.nse_universe import NSE_SYMBOLS
    db = SessionLocal()
    try:
        result = FundamentalsService(db).refresh_all(NSE_SYMBOLS)
        logger.info("[weekly_fundamentals] updated=%d skipped=%d",
                    result["updated"], result["skipped"])
    except Exception:
        logger.exception("[weekly_fundamentals] failed")
    finally:
        db.close()
```

- [ ] **Step 3: Add fundamentals endpoints to `backend/domains/data/router.py`**

Append to the end of the file:

```python
@router.post("/data/fundamentals/refresh")
def trigger_fundamentals_refresh(db: Session = Depends(get_db)):
    import threading
    from domains.data.fundamentals import FundamentalsService
    from domains.data.nse_universe import NSE_SYMBOLS

    def _run():
        from database import SessionLocal
        _db = SessionLocal()
        try:
            FundamentalsService(_db).refresh_all(NSE_SYMBOLS)
        except Exception:
            import logging
            logging.getLogger(__name__).exception("[fundamentals/refresh] failed")
        finally:
            _db.close()

    threading.Thread(target=_run, daemon=True).start()
    return {"status": "started", "symbols": len(NSE_SYMBOLS)}


@router.get("/data/fundamentals/{symbol}")
def get_fundamentals(symbol: str, db: Session = Depends(get_db)):
    from domains.data.fundamentals import FundamentalsService
    data = FundamentalsService(db).get_latest(symbol.upper())
    if not data:
        raise HTTPException(status_code=404, detail=f"No fundamentals data for {symbol}")
    return {"symbol": symbol.upper(), **data}
```

- [ ] **Step 4: Verify the engine change doesn't break existing strategy tests**

```
cd backend && pytest tests/test_strategy_engine.py tests/test_strategies.py -v
```
Expected: All existing tests PASS (existing strategies accept `fundamentals=None` and return `NONE` or handle gracefully).

- [ ] **Step 5: Commit**

```bash
cd backend && git add domains/strategies/engine.py scheduler.py domains/data/router.py
git commit -m "feat: wire FundamentalsService into StrategyEngine + scheduler + API endpoints"
```

---

## Task 3: CANSLIM Strategy

**Files:**
- Create: `backend/domains/strategies/strategies/canslim.py`
- Create: `backend/tests/test_fundamental_strategies.py` (initial file — more strategies added in later tasks)

CANSLIM criteria (using available data as proxies):
- **C**: EPS > 0 (currently profitable)
- **A**: ROE > 15% (sustained quality earnings)
- **N**: Price within 15% of 200-day rolling high (`df["high"].rolling(200, min_periods=100).max()`)
- **S**: Volume above `volume_sma_20` in the last bar (accumulation signal)
- **L**: `pe_ratio < 30` (not wildly overvalued — quality company)
- **M**: `close > sma_50` (stock uptrend)

Signal: BUY if ≥5 of 6 criteria met. Confidence = met_count / 6.

- [ ] **Step 1: Write failing test**

Create `backend/tests/test_fundamental_strategies.py`:

```python
import pandas as pd
import pytest


def _make_df(n=100, close=100.0, volume=1_500_000.0, vol_sma=1_000_000.0,
             rsi=55.0, sma_50=95.0):
    """Minimal DataFrame with indicator columns needed by fundamental strategies."""
    closes = [close] * n
    return pd.DataFrame({
        "open":         [close - 1] * n,
        "high":         [close + 2] * n,
        "low":          [close - 2] * n,
        "close":        closes,
        "volume":       [volume] * n,
        "rsi_14":       [rsi] * n,
        "sma_20":       [close] * n,
        "sma_50":       [sma_50] * n,
        "volume_sma_20":[vol_sma] * n,
        "volume_ratio": [volume / vol_sma] * n,
        "bb_upper":     [close + 10] * n,
        "bb_lower":     [close - 10] * n,
        "bb_middle":    [close] * n,
        "adx_14":       [25.0] * n,
        "atr_14":       [2.0] * n,
        "macd":         [0.5] * n,
        "macd_signal":  [0.4] * n,
        "macd_hist":    [0.1] * n,
    })


def _good_fundamentals():
    """Fundamentals dict that passes all criteria for all fundamental strategies."""
    return {
        "pe_ratio":       20.0,
        "pb_ratio":       2.0,
        "eps":            50.0,
        "revenue":        1e10,
        "net_profit":     1e9,
        "debt_equity":    0.4,
        "roe":            0.20,
        "dividend_yield": 0.025,
        "data_as_of":     "2026-08-01",
    }


# ── CANSLIM ──────────────────────────────────────────────────────────────────

def test_canslim_buy_when_all_criteria_met():
    from domains.strategies.strategies.canslim import CANSLIMStrategy
    df = _make_df(close=100.0, sma_50=95.0, volume=1_500_000.0, vol_sma=1_000_000.0)
    f = _good_fundamentals()  # eps>0, roe>0.15, pe<30
    signal = CANSLIMStrategy().generate_signal(df, f)
    assert signal.signal_type == "BUY"
    assert signal.confidence > 0.5


def test_canslim_none_when_fundamentals_empty():
    from domains.strategies.strategies.canslim import CANSLIMStrategy
    df = _make_df()
    signal = CANSLIMStrategy().generate_signal(df, {})
    assert signal.signal_type == "NONE"


def test_canslim_none_when_only_2_criteria_met():
    from domains.strategies.strategies.canslim import CANSLIMStrategy
    df = _make_df(close=100.0, sma_50=110.0)  # close < sma_50 (M fails)
    f = {**_good_fundamentals(), "eps": -5.0, "roe": 0.05}  # C, A also fail
    signal = CANSLIMStrategy().generate_signal(df, f)
    assert signal.signal_type == "NONE"
```

- [ ] **Step 2: Run test to confirm it fails**

```
cd backend && pytest tests/test_fundamental_strategies.py::test_canslim_buy_when_all_criteria_met -v
```
Expected: `ModuleNotFoundError` or `ImportError`

- [ ] **Step 3: Create `backend/domains/strategies/strategies/canslim.py`**

```python
import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class CANSLIMStrategy(BaseStrategy):
    name = "CANSLIM"
    description = (
        "William O'Neil's CANSLIM: quality growth companies near 52-week highs. "
        "Proxies: EPS>0 (C), ROE>15% (A), near 200-day high (N), volume spike (S), PE<30 (L), price>SMA50 (M)."
    )
    strategy_type = StrategyType.FUNDAMENTAL
    timeframe = Timeframe.DAILY
    min_holding_days = 20
    max_holding_days = 60
    weight = 0.05

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if not fundamentals:
            return Signal("NONE")

        eps = fundamentals.get("eps")
        roe = fundamentals.get("roe")
        pe  = fundamentals.get("pe_ratio")

        if df.empty or len(df) < 50:
            return Signal("NONE")

        last  = df.iloc[-1]
        close = float(last["close"])

        high_200 = df["high"].rolling(200, min_periods=100).max().iloc[-1]
        sma_50   = float(last.get("sma_50", float("nan")))
        vol      = float(last["volume"])
        vol_sma  = float(last.get("volume_sma_20", float("nan")))

        met = []
        missed = []

        # C: Current EPS > 0 (profitable)
        if eps is not None and eps > 0:
            met.append(f"C: EPS={eps:.1f} > 0")
        else:
            missed.append("C: EPS not positive")

        # A: ROE > 15% (quality earnings)
        if roe is not None and roe > 0.15:
            met.append(f"A: ROE={roe*100:.1f}% > 15%")
        else:
            missed.append("A: ROE <= 15%")

        # N: Price within 15% of 200-day high
        if not pd.isna(high_200) and close >= high_200 * 0.85:
            met.append(f"N: close {close:.1f} within 15% of 200-day high {high_200:.1f}")
        else:
            missed.append("N: price not near 200-day high")

        # S: Volume above 20-day average (accumulation)
        if not pd.isna(vol_sma) and vol > vol_sma:
            met.append(f"S: volume {vol:.0f} > vol_sma_20 {vol_sma:.0f}")
        else:
            missed.append("S: volume not above average")

        # L: PE < 30 (not wildly overvalued)
        if pe is not None and pe < 30:
            met.append(f"L: PE={pe:.1f} < 30")
        else:
            missed.append("L: PE >= 30 or unknown")

        # M: Price above SMA50 (uptrend)
        if not pd.isna(sma_50) and close > sma_50:
            met.append(f"M: close {close:.1f} > SMA50 {sma_50:.1f}")
        else:
            missed.append("M: price below SMA50")

        if len(met) >= 5:
            confidence = round(len(met) / 6, 4)
            return Signal(
                signal_type="BUY",
                confidence=confidence,
                risk_score=0.35,
                expected_upside_pct=20.0,
                stop_loss_pct=8.0,
                target_pct=20.0,
                holding_days=30,
                conditions_met=met,
                conditions_failed=missed,
            )
        return Signal("NONE", conditions_met=met, conditions_failed=missed)

    def get_required_indicators(self) -> list[str]:
        return ["sma_50", "volume_sma_20"]
```

- [ ] **Step 4: Run CANSLIM tests**

```
cd backend && pytest tests/test_fundamental_strategies.py -k "canslim" -v
```
Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
cd backend && git add domains/strategies/strategies/canslim.py tests/test_fundamental_strategies.py
git commit -m "feat: CANSLIM fundamental strategy"
```

---

## Task 4: Magic Formula Strategy

**Files:**
- Create: `backend/domains/strategies/strategies/magic_formula.py`
- Modify: `backend/tests/test_fundamental_strategies.py` (append tests)

Magic Formula uses absolute thresholds (no universe-wide ranking per signal):
- Earnings Yield = EPS / price > 6%
- ROE > 15%
- PE < 20
- D/E < 1.0

- [ ] **Step 1: Append Magic Formula tests to `test_fundamental_strategies.py`**

```python
# ── Magic Formula ─────────────────────────────────────────────────────────────

def test_magic_formula_buy_when_all_criteria_met():
    from domains.strategies.strategies.magic_formula import MagicFormulaStrategy
    df = _make_df(close=500.0)  # EPS=50, price=500 → earnings yield=10% > 6%
    f = {**_good_fundamentals(), "pe_ratio": 15.0}
    signal = MagicFormulaStrategy().generate_signal(df, f)
    assert signal.signal_type == "BUY"


def test_magic_formula_none_when_fundamentals_empty():
    from domains.strategies.strategies.magic_formula import MagicFormulaStrategy
    signal = MagicFormulaStrategy().generate_signal(_make_df(), {})
    assert signal.signal_type == "NONE"


def test_magic_formula_none_when_earnings_yield_too_low():
    from domains.strategies.strategies.magic_formula import MagicFormulaStrategy
    # EPS=50, close=2000 → earnings yield = 50/2000 = 2.5% < 6%
    df = _make_df(close=2000.0)
    f = {**_good_fundamentals(), "pe_ratio": 15.0}
    signal = MagicFormulaStrategy().generate_signal(df, f)
    assert signal.signal_type == "NONE"
```

- [ ] **Step 2: Run tests to confirm they fail**

```
cd backend && pytest tests/test_fundamental_strategies.py -k "magic_formula" -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Create `backend/domains/strategies/strategies/magic_formula.py`**

```python
import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class MagicFormulaStrategy(BaseStrategy):
    name = "Magic Formula"
    description = (
        "Greenblatt Magic Formula: high earnings yield + high return on capital. "
        "Earnings Yield = EPS/price > 6%, ROE > 15%, PE < 20, D/E < 1.0."
    )
    strategy_type = StrategyType.FUNDAMENTAL
    timeframe = Timeframe.DAILY
    min_holding_days = 30
    max_holding_days = 90
    weight = 0.05

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if not fundamentals:
            return Signal("NONE")

        eps = fundamentals.get("eps")
        roe = fundamentals.get("roe")
        pe  = fundamentals.get("pe_ratio")
        de  = fundamentals.get("debt_equity")

        if df.empty:
            return Signal("NONE")

        close = float(df["close"].iloc[-1])
        if close <= 0:
            return Signal("NONE")

        met    = []
        missed = []

        # Earnings Yield = EPS / price
        if eps is not None and eps / close > 0.06:
            met.append(f"Earnings yield {eps/close*100:.1f}% > 6%")
        else:
            missed.append("Earnings yield <= 6%")

        # Return on Capital proxy: ROE > 15%
        if roe is not None and roe > 0.15:
            met.append(f"ROE {roe*100:.1f}% > 15%")
        else:
            missed.append("ROE <= 15%")

        # Reasonable valuation
        if pe is not None and pe < 20:
            met.append(f"PE {pe:.1f} < 20")
        else:
            missed.append("PE >= 20 or unknown")

        # Low financial leverage
        if de is not None and de < 1.0:
            met.append(f"D/E {de:.2f} < 1.0")
        else:
            missed.append("D/E >= 1.0 or unknown")

        if len(met) == 4:
            return Signal(
                signal_type="BUY",
                confidence=0.75,
                risk_score=0.30,
                expected_upside_pct=25.0,
                stop_loss_pct=8.0,
                target_pct=25.0,
                holding_days=45,
                conditions_met=met,
                conditions_failed=missed,
            )
        return Signal("NONE", conditions_met=met, conditions_failed=missed)

    def get_required_indicators(self) -> list[str]:
        return []
```

- [ ] **Step 4: Run Magic Formula tests**

```
cd backend && pytest tests/test_fundamental_strategies.py -k "magic_formula" -v
```
Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
cd backend && git add domains/strategies/strategies/magic_formula.py tests/test_fundamental_strategies.py
git commit -m "feat: Magic Formula fundamental strategy"
```

---

## Task 5: Graham Value Strategy

**Files:**
- Create: `backend/domains/strategies/strategies/graham_value.py`
- Modify: `backend/tests/test_fundamental_strategies.py` (append tests)

Graham Number = √(22.5 × EPS × BookValue). BookValue = price / pb_ratio.
BUY if price < 1.3 × Graham Number AND PE < 15 AND PB < 1.5.

- [ ] **Step 1: Append Graham Value tests**

```python
# ── Graham Value ──────────────────────────────────────────────────────────────

def test_graham_value_buy_when_undervalued():
    from domains.strategies.strategies.graham_value import GrahamValueStrategy
    # EPS=50, PB=1.2, close=400
    # BookValue = 400/1.2 = 333.3
    # Graham = sqrt(22.5 * 50 * 333.3) = sqrt(374962) ≈ 612
    # 1.3 * 612 = 796 → close=400 < 796 ✓
    # PE = 400/50 = 8 < 15 ✓, PB = 1.2 < 1.5 ✓
    df = _make_df(close=400.0)
    f = {**_good_fundamentals(), "eps": 50.0, "pb_ratio": 1.2, "pe_ratio": 8.0}
    signal = GrahamValueStrategy().generate_signal(df, f)
    assert signal.signal_type == "BUY"


def test_graham_value_none_when_fundamentals_empty():
    from domains.strategies.strategies.graham_value import GrahamValueStrategy
    signal = GrahamValueStrategy().generate_signal(_make_df(), {})
    assert signal.signal_type == "NONE"


def test_graham_value_none_when_overvalued():
    from domains.strategies.strategies.graham_value import GrahamValueStrategy
    # High PE = 30, PB = 3 → PB > 1.5, fails criteria
    df = _make_df(close=1500.0)
    f = {**_good_fundamentals(), "eps": 50.0, "pb_ratio": 3.0, "pe_ratio": 30.0}
    signal = GrahamValueStrategy().generate_signal(df, f)
    assert signal.signal_type == "NONE"
```

- [ ] **Step 2: Run to confirm failure**

```
cd backend && pytest tests/test_fundamental_strategies.py -k "graham_value" -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Create `backend/domains/strategies/strategies/graham_value.py`**

```python
import math
import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class GrahamValueStrategy(BaseStrategy):
    name = "Graham Value"
    description = (
        "Benjamin Graham Number: buy when price < 1.3× Graham Number "
        "and PE < 15 and PB < 1.5. Graham Number = sqrt(22.5 × EPS × BookValue)."
    )
    strategy_type = StrategyType.FUNDAMENTAL
    timeframe = Timeframe.DAILY
    min_holding_days = 30
    max_holding_days = 180
    weight = 0.05

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if not fundamentals:
            return Signal("NONE")

        eps = fundamentals.get("eps")
        pb  = fundamentals.get("pb_ratio")
        pe  = fundamentals.get("pe_ratio")

        if df.empty:
            return Signal("NONE")

        close = float(df["close"].iloc[-1])
        if close <= 0:
            return Signal("NONE")

        met    = []
        missed = []

        # Compute Graham Number (requires eps > 0 and pb > 0)
        graham_num = None
        if eps is not None and pb is not None and eps > 0 and pb > 0:
            book_value = close / pb
            val = 22.5 * eps * book_value
            if val > 0:
                graham_num = math.sqrt(val)

        if graham_num and close < 1.3 * graham_num:
            met.append(f"Price {close:.0f} < 1.3× Graham {graham_num:.0f}")
        else:
            missed.append("Price not below Graham Number × 1.3")

        if pe is not None and pe < 15:
            met.append(f"PE {pe:.1f} < 15 (value zone)")
        else:
            missed.append("PE >= 15 or unknown")

        if pb is not None and pb < 1.5:
            met.append(f"PB {pb:.2f} < 1.5 (near book)")
        else:
            missed.append("PB >= 1.5 or unknown")

        if len(met) == 3:
            margin = (1.3 * graham_num - close) / (1.3 * graham_num) if graham_num else 0
            confidence = round(min(1.0, 0.60 + margin), 4)
            return Signal(
                signal_type="BUY",
                confidence=confidence,
                risk_score=0.25,
                expected_upside_pct=30.0,
                stop_loss_pct=7.0,
                target_pct=30.0,
                holding_days=60,
                conditions_met=met,
                conditions_failed=missed,
            )
        return Signal("NONE", conditions_met=met, conditions_failed=missed)

    def get_required_indicators(self) -> list[str]:
        return []
```

- [ ] **Step 4: Run Graham Value tests**

```
cd backend && pytest tests/test_fundamental_strategies.py -k "graham_value" -v
```
Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
cd backend && git add domains/strategies/strategies/graham_value.py tests/test_fundamental_strategies.py
git commit -m "feat: Graham Value fundamental strategy"
```

---

## Task 6: Growth Investing Strategy

**Files:**
- Create: `backend/domains/strategies/strategies/growth_investing.py`
- Modify: `backend/tests/test_fundamental_strategies.py` (append tests)

GARP (Growth at a Reasonable Price):
- ROE > 15%
- EPS > 0 (profitable)
- PE < 40 (reasonable for a growth stock)
- D/E < 1.0 (manageable debt)
- Net profit > 0 (positive earnings)

Signal: BUY if ≥4 of 5 criteria met. Confidence = met/5.

- [ ] **Step 1: Append Growth tests**

```python
# ── Growth Investing ──────────────────────────────────────────────────────────

def test_growth_buy_when_all_criteria_met():
    from domains.strategies.strategies.growth_investing import GrowthInvestingStrategy
    signal = GrowthInvestingStrategy().generate_signal(_make_df(), _good_fundamentals())
    assert signal.signal_type == "BUY"


def test_growth_none_when_fundamentals_empty():
    from domains.strategies.strategies.growth_investing import GrowthInvestingStrategy
    signal = GrowthInvestingStrategy().generate_signal(_make_df(), {})
    assert signal.signal_type == "NONE"


def test_growth_none_when_3_criteria_fail():
    from domains.strategies.strategies.growth_investing import GrowthInvestingStrategy
    # roe=0.05 (<15%), eps=-10 (<0), de=2.0 (>1.0) → 3 fail, only 2 pass
    f = {**_good_fundamentals(), "roe": 0.05, "eps": -10.0, "debt_equity": 2.0}
    signal = GrowthInvestingStrategy().generate_signal(_make_df(), f)
    assert signal.signal_type == "NONE"
```

- [ ] **Step 2: Run to confirm failure**

```
cd backend && pytest tests/test_fundamental_strategies.py -k "growth" -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Create `backend/domains/strategies/strategies/growth_investing.py`**

```python
import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class GrowthInvestingStrategy(BaseStrategy):
    name = "Growth Investing"
    description = (
        "GARP (Growth at a Reasonable Price): ROE>15%, EPS>0, PE<40, D/E<1.0, profit>0. "
        "Buy quality growth companies at reasonable valuations."
    )
    strategy_type = StrategyType.FUNDAMENTAL
    timeframe = Timeframe.DAILY
    min_holding_days = 20
    max_holding_days = 60
    weight = 0.05

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if not fundamentals:
            return Signal("NONE")

        roe    = fundamentals.get("roe")
        eps    = fundamentals.get("eps")
        pe     = fundamentals.get("pe_ratio")
        de     = fundamentals.get("debt_equity")
        profit = fundamentals.get("net_profit")

        met    = []
        missed = []

        if roe is not None and roe > 0.15:
            met.append(f"ROE {roe*100:.1f}% > 15%")
        else:
            missed.append("ROE <= 15% or unknown")

        if eps is not None and eps > 0:
            met.append(f"EPS {eps:.1f} > 0 (profitable)")
        else:
            missed.append("EPS <= 0 or unknown")

        if pe is not None and 0 < pe < 40:
            met.append(f"PE {pe:.1f} < 40 (reasonable)")
        else:
            missed.append("PE >= 40 or unknown")

        if de is not None and de < 1.0:
            met.append(f"D/E {de:.2f} < 1.0")
        else:
            missed.append("D/E >= 1.0 or unknown")

        if profit is not None and profit > 0:
            met.append(f"Net profit {profit:.0f} > 0")
        else:
            missed.append("Net profit <= 0 or unknown")

        if len(met) >= 4:
            confidence = round(len(met) / 5, 4)
            return Signal(
                signal_type="BUY",
                confidence=confidence,
                risk_score=0.35,
                expected_upside_pct=20.0,
                stop_loss_pct=8.0,
                target_pct=20.0,
                holding_days=30,
                conditions_met=met,
                conditions_failed=missed,
            )
        return Signal("NONE", conditions_met=met, conditions_failed=missed)

    def get_required_indicators(self) -> list[str]:
        return []
```

- [ ] **Step 4: Run Growth tests**

```
cd backend && pytest tests/test_fundamental_strategies.py -k "growth" -v
```
Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
cd backend && git add domains/strategies/strategies/growth_investing.py tests/test_fundamental_strategies.py
git commit -m "feat: Growth Investing (GARP) fundamental strategy"
```

---

## Task 7: Dividend Investing Strategy

**Files:**
- Create: `backend/domains/strategies/strategies/dividend_investing.py`
- Modify: `backend/tests/test_fundamental_strategies.py` (append tests)

Criteria:
- `dividend_yield > 0.02` (> 2%)
- EPS > 0 (dividend is covered by earnings)
- ROE > 12%
- D/E < 0.5 (conservative balance sheet for income investors)

Signal: BUY if all 4 criteria met.

- [ ] **Step 1: Append Dividend tests**

```python
# ── Dividend Investing ────────────────────────────────────────────────────────

def test_dividend_buy_when_all_criteria_met():
    from domains.strategies.strategies.dividend_investing import DividendInvestingStrategy
    # dividend_yield=0.025 (2.5%) > 2%, roe=0.20 > 12%, de=0.4 < 0.5, eps=50 > 0
    signal = DividendInvestingStrategy().generate_signal(_make_df(), _good_fundamentals())
    assert signal.signal_type == "BUY"


def test_dividend_none_when_fundamentals_empty():
    from domains.strategies.strategies.dividend_investing import DividendInvestingStrategy
    signal = DividendInvestingStrategy().generate_signal(_make_df(), {})
    assert signal.signal_type == "NONE"


def test_dividend_none_when_low_yield():
    from domains.strategies.strategies.dividend_investing import DividendInvestingStrategy
    f = {**_good_fundamentals(), "dividend_yield": 0.005}  # 0.5% < 2%
    signal = DividendInvestingStrategy().generate_signal(_make_df(), f)
    assert signal.signal_type == "NONE"


def test_dividend_none_when_high_debt():
    from domains.strategies.strategies.dividend_investing import DividendInvestingStrategy
    f = {**_good_fundamentals(), "debt_equity": 0.8}  # D/E > 0.5
    signal = DividendInvestingStrategy().generate_signal(_make_df(), f)
    assert signal.signal_type == "NONE"
```

- [ ] **Step 2: Run to confirm failure**

```
cd backend && pytest tests/test_fundamental_strategies.py -k "dividend" -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Create `backend/domains/strategies/strategies/dividend_investing.py`**

```python
import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class DividendInvestingStrategy(BaseStrategy):
    name = "Dividend Investing"
    description = (
        "High-quality dividend payers: yield > 2%, EPS > 0 (covered), ROE > 12%, D/E < 0.5."
    )
    strategy_type = StrategyType.FUNDAMENTAL
    timeframe = Timeframe.DAILY
    min_holding_days = 30
    max_holding_days = 365
    weight = 0.05

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if not fundamentals:
            return Signal("NONE")

        div_yield = fundamentals.get("dividend_yield")
        eps       = fundamentals.get("eps")
        roe       = fundamentals.get("roe")
        de        = fundamentals.get("debt_equity")

        met    = []
        missed = []

        if div_yield is not None and div_yield > 0.02:
            met.append(f"Dividend yield {div_yield*100:.1f}% > 2%")
        else:
            missed.append("Dividend yield <= 2% or unknown")

        if eps is not None and eps > 0:
            met.append(f"EPS {eps:.1f} > 0 (dividend covered)")
        else:
            missed.append("EPS <= 0 — dividend sustainability risk")

        if roe is not None and roe > 0.12:
            met.append(f"ROE {roe*100:.1f}% > 12%")
        else:
            missed.append("ROE <= 12% or unknown")

        if de is not None and de < 0.5:
            met.append(f"D/E {de:.2f} < 0.5 (conservative)")
        else:
            missed.append("D/E >= 0.5 or unknown")

        if len(met) == 4:
            confidence = round(0.60 + min(0.20, (div_yield - 0.02) * 10), 4) if div_yield else 0.60
            return Signal(
                signal_type="BUY",
                confidence=confidence,
                risk_score=0.20,
                expected_upside_pct=12.0,
                stop_loss_pct=6.0,
                target_pct=12.0,
                holding_days=90,
                conditions_met=met,
                conditions_failed=missed,
            )
        return Signal("NONE", conditions_met=met, conditions_failed=missed)

    def get_required_indicators(self) -> list[str]:
        return []
```

- [ ] **Step 4: Run Dividend tests**

```
cd backend && pytest tests/test_fundamental_strategies.py -k "dividend" -v
```
Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
cd backend && git add domains/strategies/strategies/dividend_investing.py tests/test_fundamental_strategies.py
git commit -m "feat: Dividend Investing fundamental strategy"
```

---

## Task 8: FII/DII Accumulation Strategy

**Files:**
- Create: `backend/domains/strategies/strategies/fii_dii_accumulation.py`
- Modify: `backend/tests/test_fundamental_strategies.py` (append tests)

Uses **technical proxies** for institutional accumulation (actual FII/DII % data is not available via yfinance for NSE stocks):
- Volume > 1.5× `volume_sma_20` for ≥3 of last 5 bars
- Close > `sma_50` for ≥3 of last 5 bars
- RSI between 40 and 70 (trending but not overbought)

Signal: BUY if all 3 conditions met. No fundamentals data required.

- [ ] **Step 1: Append FII/DII tests**

```python
# ── FII/DII Accumulation ──────────────────────────────────────────────────────

def test_fii_dii_buy_when_accumulation_pattern():
    from domains.strategies.strategies.fii_dii_accumulation import FIIDIIAccumulationStrategy
    # volume=1_500_000 > vol_sma=1_000_000 (ratio 1.5) for all 5 bars
    # close=100 > sma_50=95 for all bars, rsi=55 in 40-70
    df = _make_df(close=100.0, volume=1_600_000.0, vol_sma=1_000_000.0,
                  rsi=55.0, sma_50=95.0)
    signal = FIIDIIAccumulationStrategy().generate_signal(df)
    assert signal.signal_type == "BUY"


def test_fii_dii_none_when_low_volume():
    from domains.strategies.strategies.fii_dii_accumulation import FIIDIIAccumulationStrategy
    # volume = vol_sma (no accumulation)
    df = _make_df(close=100.0, volume=1_000_000.0, vol_sma=1_000_000.0, rsi=55.0, sma_50=95.0)
    signal = FIIDIIAccumulationStrategy().generate_signal(df)
    assert signal.signal_type == "NONE"


def test_fii_dii_none_when_rsi_overbought():
    from domains.strategies.strategies.fii_dii_accumulation import FIIDIIAccumulationStrategy
    df = _make_df(close=100.0, volume=1_600_000.0, vol_sma=1_000_000.0, rsi=80.0, sma_50=95.0)
    signal = FIIDIIAccumulationStrategy().generate_signal(df)
    assert signal.signal_type == "NONE"


def test_fii_dii_works_without_fundamentals():
    from domains.strategies.strategies.fii_dii_accumulation import FIIDIIAccumulationStrategy
    # Passing empty fundamentals (or None) should still work — this strategy is purely technical
    df = _make_df(close=100.0, volume=1_600_000.0, vol_sma=1_000_000.0, rsi=55.0, sma_50=95.0)
    signal = FIIDIIAccumulationStrategy().generate_signal(df, fundamentals=None)
    assert signal.signal_type == "BUY"
    signal2 = FIIDIIAccumulationStrategy().generate_signal(df, fundamentals={})
    assert signal2.signal_type == "BUY"
```

- [ ] **Step 2: Run to confirm failure**

```
cd backend && pytest tests/test_fundamental_strategies.py -k "fii_dii" -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Create `backend/domains/strategies/strategies/fii_dii_accumulation.py`**

```python
import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class FIIDIIAccumulationStrategy(BaseStrategy):
    name = "FII/DII Accumulation"
    description = (
        "Detects institutional accumulation via price/volume proxies: "
        "volume > 1.5× average for 3 of last 5 days, close > SMA50 for 3 of last 5 days, RSI 40-70."
    )
    strategy_type = StrategyType.FUNDAMENTAL
    timeframe = Timeframe.DAILY
    min_holding_days = 10
    max_holding_days = 30
    weight = 0.05

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if df.empty or len(df) < 10:
            return Signal("NONE")

        required = ["volume_sma_20", "sma_50", "rsi_14"]
        if not all(c in df.columns for c in required):
            return Signal("NONE")

        last5 = df.tail(5)
        last  = df.iloc[-1]
        rsi   = float(last["rsi_14"])

        if pd.isna(rsi):
            return Signal("NONE")

        # Condition 1: volume > 1.5× vol_sma for ≥3 of last 5 bars
        vol_high = (last5["volume"] > last5["volume_sma_20"] * 1.5).sum()

        # Condition 2: close > sma_50 for ≥3 of last 5 bars
        above_sma = (last5["close"] > last5["sma_50"]).sum()

        # Condition 3: RSI in accumulation range (not overbought/oversold)
        rsi_ok = 40 <= rsi <= 70

        met    = []
        missed = []

        if vol_high >= 3:
            met.append(f"High volume {vol_high}/5 bars (accumulation)")
        else:
            missed.append(f"Only {vol_high}/5 bars with high volume (need ≥3)")

        if above_sma >= 3:
            met.append(f"Above SMA50 {above_sma}/5 bars (uptrend)")
        else:
            missed.append(f"Only {above_sma}/5 bars above SMA50 (need ≥3)")

        if rsi_ok:
            met.append(f"RSI {rsi:.1f} in 40–70 (not overbought)")
        else:
            missed.append(f"RSI {rsi:.1f} outside 40–70")

        if len(met) == 3:
            return Signal(
                signal_type="BUY",
                confidence=0.65,
                risk_score=0.40,
                expected_upside_pct=15.0,
                stop_loss_pct=7.0,
                target_pct=15.0,
                holding_days=20,
                conditions_met=met,
                conditions_failed=missed,
            )
        return Signal("NONE", conditions_met=met, conditions_failed=missed)

    def get_required_indicators(self) -> list[str]:
        return ["volume_sma_20", "sma_50", "rsi_14"]
```

- [ ] **Step 4: Run FII/DII tests**

```
cd backend && pytest tests/test_fundamental_strategies.py -k "fii_dii" -v
```
Expected: 4 PASSED

- [ ] **Step 5: Run full fundamental strategy test suite**

```
cd backend && pytest tests/test_fundamental_strategies.py -v
```
Expected: All 17 tests PASS

- [ ] **Step 6: Run broader test suite to check for regressions**

```
cd backend && pytest tests/ -v --ignore=tests/test_bootstrap.py -q
```
Expected: All existing tests pass. Any failures should be investigated.

- [ ] **Step 7: Commit**

```bash
cd backend && git add domains/strategies/strategies/fii_dii_accumulation.py tests/test_fundamental_strategies.py
git commit -m "feat: FII/DII Accumulation strategy + complete fundamental strategy test suite"
```

---

## Post-Implementation: First Fundamentals Fetch

After deploying, trigger the first fundamentals fetch manually (takes ~5 min in background):

```bash
curl -X POST http://localhost:8000/api/v1/data/fundamentals/refresh \
  -H "X-API-Key: <your-key>"
# Returns: {"status": "started", "symbols": 237}

# Check if data landed (try after ~10 min):
curl http://localhost:8000/api/v1/data/fundamentals/RELIANCE \
  -H "X-API-Key: <your-key>"
# Returns the fundamentals row or 404 if still fetching
```

After the fetch completes, run the strategy scan to generate fundamental signals:

```bash
curl -X POST http://localhost:8000/api/v1/strategies/run-all \
  -H "X-API-Key: <your-key>"
```

New fundamental signals will appear in the Dashboard Top Opportunities and Scanner within minutes.
