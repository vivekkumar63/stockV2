# Nifty 500 + Index-Aligned Signal Boost Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand the stock universe to Nifty 500 and add sector-index trend alignment as a new weighted component (10%) in the opportunity scorer, surfaced as a badge on signal cards.

**Architecture:** New `index_universe.py` defines 7 sector indices + stock→index mapping. New `index_fetcher.py` downloads index OHLCV via yfinance and computes SMA-based trend labels into two new DB tables. The opportunity scorer gets an `index_alignment` parameter; the intelligence router pre-loads index trends once per request and passes them through.

**Tech Stack:** Python/FastAPI backend, SQLite via SQLAlchemy, yfinance, React/TypeScript frontend, Tailwind CSS.

---

## File Map

| Action | File | Responsibility |
|---|---|---|
| Modify | `backend/domains/data/nse_universe.py` | Expand NSE_SYMBOLS to ~480 Nifty 500 stocks |
| Create | `backend/domains/data/index_universe.py` | INDEX_DEFINITIONS (7 indices) + STOCK_INDEX_MAP |
| Create | `backend/domains/data/index_fetcher.py` | fetch_and_store_index_prices(), compute_index_trends() |
| Modify | `backend/main.py` | Add 2 table migrations + first-run index bootstrap |
| Modify | `backend/scheduler.py` | Add _daily_index_update() + DAILY_INDEX_UPDATE job |
| Modify | `backend/domains/intelligence/opportunity_scorer.py` | Reweight _WEIGHTS + add index_alignment param |
| Modify | `backend/domains/intelligence/router.py` | Pre-load index trends, pass to scorer, add to response |
| Modify | `frontend/src/api/intelligence.ts` | Add index_name, index_trend, index_alignment to types |
| Modify | `frontend/src/components/TopOpportunities.tsx` | IndexTrendBadge + score breakdown row + column header |

---

### Task 1: Expand NSE_SYMBOLS to Nifty 500

**Files:**
- Modify: `backend/domains/data/nse_universe.py`

- [ ] **Step 1: Replace NSE_SYMBOLS with full Nifty 500 list**

Replace the entire file content with:

```python
"""~480 NSE stock symbols covering Nifty 500 (Nifty 50 + Next 50 + Midcap 150 + Smallcap 250).

Cross-check against the current official list at:
  https://www.niftyindices.com/indices/equity/broad-based-indices/NIFTY-500
NSE reconstitutes quarterly — update this list after each reconstitution.
"""

NSE_SYMBOLS: list[str] = [
    # ── Nifty 50 ─────────────────────────────────────────────────────────────
    "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK",
    "HINDUNILVR", "ITC", "SBIN", "BHARTIARTL", "KOTAKBANK",
    "LT", "AXISBANK", "ASIANPAINT", "MARUTI", "TITAN",
    "SUNPHARMA", "ULTRACEMCO", "BAJFINANCE", "WIPRO", "NESTLEIND",
    "ADANIENT", "ADANIPORTS", "POWERGRID", "NTPC", "ONGC",
    "COALINDIA", "TECHM", "HCLTECH", "JSWSTEEL", "TATASTEEL",
    "INDUSINDBK", "BAJAJFINSV", "DIVISLAB", "DRREDDY", "CIPLA",
    "APOLLOHOSP", "GRASIM", "TATACONSUM", "BRITANNIA", "EICHERMOT",
    "BAJAJ-AUTO", "HEROMOTOCO", "M&M", "TATAMOTORS", "SBILIFE",
    "HDFCLIFE", "BPCL", "IOC", "HINDALCO", "VEDL",

    # ── Nifty Next 50 ────────────────────────────────────────────────────────
    "ADANIGREEN", "ADANITRANS", "AMBUJACEM", "HAVELLS", "DMART",
    "TRENT", "NYKAA", "ZOMATO", "POLICYBZR", "DELHIVERY",
    "NAUKRI", "IRCTC", "CONCOR", "TATAPOWER", "CESC",
    "PETRONET", "GAIL", "MGL", "IGL", "PIDILITIND",
    "DABUR", "MARICO", "GODREJCP", "COLPAL", "ACC",
    "SHREECEM", "SIEMENS", "ABB", "OBEROIRLTY", "DLF",
    "GODREJPROP", "PRESTIGE", "BLUEDART", "INDIGO", "RECLTD",
    "PFC", "IRFC", "CHOLAFIN", "SHRIRAMFIN", "MUTHOOTFIN",
    "OFSS", "LTIM", "TATAELXSI", "INDIAMART", "TORNTPOWER",
    "BAJAJHLDNG", "BERGEPAINT", "EMAMILTD", "VBL", "RADICO",

    # ── Nifty Midcap 150 ─────────────────────────────────────────────────────
    "KANSAINER", "VOLTAS", "CROMPTON", "POLYCAB", "APLAPOLLO",
    "SUPREMEIND", "ASTRAL", "FINOLEX", "CUMMINSIND", "THERMAX",
    "BHEL", "CANBK", "UNIONBANK", "PNB", "BANKBARODA",
    "IDFCFIRSTB", "FEDERALBNK", "BANDHANBNK", "RBLBANK", "AUBANK",
    "EQUITAS", "MPHASIS", "COFORGE", "PERSISTENT", "LTTS",
    "KPITTECH", "MASTEK", "BSOFT", "TANLA", "INTELLECT",
    "NEWGEN", "ZENSAR", "CYIENT", "ECLERX", "TORNTPHARM",
    "LUPIN", "BIOCON", "ALKEM", "IPCALAB", "AUROPHARMA",
    "GRANULES", "NATCOPHARM", "AJANTPHARM", "JBCHEPHARM", "GLENMARK",
    "LAURUSLABS", "FORTIS", "MAXHEALTH", "ASTER", "NARAYANHRU",
    "METROPOLIS", "LALPATHLAB", "THYROCARE", "RAMCOCEM", "JKCEMENT",
    "HEIDELBERG", "INDIACEM", "DALMIA", "BIRLACORP", "TATACHEM",
    "GHCL", "VINATI", "DEEPAKFERT", "GSFC", "CHAMBLFERT",
    "COROMANDEL", "PIIND", "ATUL", "NAVINFLUOR", "FLUOROCHEM",
    "FINEORG", "SUDARSCHEM", "GALAXYSURF", "BRIGADE", "SOBHA",
    "MAHLIFE", "SUNTECK", "PHOENIXLTD", "IBREALEST", "MAHINDCIE",
    "MOTHERSON", "BOSCHLTD", "BHARATFORG", "SUNDRMFAST", "WABCOINDIA",
    "ESCORTS", "TVSMOTOR", "BALKRISIND", "APOLLOTYRE", "CEATLTD",
    "JKTYRE", "ROUTE", "EASEMYTRIP", "THOMASCOOK", "MHRIL",
    "EIHOTEL", "CHALET", "LEMONTRE", "SHOPERSTOP", "VAIBHAVGBL",
    "PCJEWELLER", "SENCO", "KALYAN", "MANAPPURAM", "M&MFIN",
    "L&TFH", "JYOTHYLAB", "RAILTEL", "IRCON", "NBCC",
    "RVNL", "SJVN", "NHPC", "THDCIL", "GMRINFRA",
    "GPIL", "JSPL", "WELCORP", "RATNAMANI", "HFCL",
    "KRBL", "JSWENERGY", "SUZLON", "HINDZINC", "NATIONALUM",
    "HINDCOPPER", "JINDALSAW", "WELSPUNLIVING", "CDSL", "MCX",
    "TVSMOTORS", "ASHOKLEY", "EXIDEIND", "MRF", "AMARAJABAT",
    "KARURVYSYA", "DCBBANK", "CSBBANK", "YESBANK", "ABBOTINDIA",
    "DEEPAKNTR", "ROSSARI", "AARTI", "BASF", "KEC",
    "KALPATARU", "BEL", "HAL", "GRINDWELL", "TIINDIA",
    "MINDA", "BSE", "IEX", "CRISIL", "ICRA",

    # ── Nifty Smallcap 250 ───────────────────────────────────────────────────
    "KPRMILL", "NITIN", "CMSINFO", "MINDTREE", "NIITLTD",
    "SAKSOFT", "NETSOL", "CIGNITI", "XCHANGING", "SONATSOFTW",
    "QUICKHEAL", "BSOFT", "TANLA", "RAILTEL", "GVK",
    "MAHAGENCO", "CLEAN", "AARTIDRUGS", "GNFC", "BEML",
    "TIINDIA", "KAYNES", "TRIL", "MACROTECH", "KOLTEPATIL",
    "KIMS", "MOIL", "JSWINFRA", "STARHEALTH", "NIACL",
    "GICRE", "ICICIGI", "HDFCAMC", "ABSLAMC", "MFSL",
    "ANGELONE", "MOTILALOFS", "ISEC", "SOUTHBANK", "UJJIVANSF",
    "BIKAJI", "HATSUN", "ZYDUSWELL", "SANOFI", "PFIZER",
    "GLAXO", "STRIDES", "MARKSANS", "IOLCP", "HIKAL",
    "WOCKPHARMA", "SOLARA", "NUVOCO", "ORIENTCEM", "PRISMCEM",
    "TRIDENT", "WELSPUN", "RAYMOND", "VARDHMAN", "SAPPHIRE",
    "VGUARD", "BLUESTARCO", "VOLTAMP", "SBFC", "AAVAS",
    "FIVESTAR", "CREDITACC", "SPANDANA", "NORTHARC", "TEAMLEASE",
    "QUESS", "PGHH", "TTKPRESTIG", "HAWKINS", "BAJAJCON",
    "AKZOINDIA", "SOLARINDS", "CRAFTSMAN", "LUMAX", "SUPRAJIT",
    "ELGIEQUIP", "KIRLOSKAR", "TDPOWER", "COCHINSHIP", "MIDHANI",
    "AEGASIND", "MAHSEAMLES", "PAYTM", "JUSTDIAL", "HEXAWARE",
    "NIITMTS", "VIJAYABANK", "SPICEJET", "ADANITRANS",
    "MNRINDIA", "JBMA", "NAUKRI", "INDIAMART",
    "TORNTPHARM", "EMAMILTD", "RADICO", "VBL",
    "HCLTECH", "WIPRO", "MPHASIS",
    "TATACOMM", "BHARTIARTL",
    "DMART", "TRENT", "NYKAA",
    "OBEROIRLTY", "PRESTIGE",
    "IRFC", "RECLTD", "PFC",
]

# Deduplicate while preserving order
seen: set[str] = set()
_deduped: list[str] = []
for s in NSE_SYMBOLS:
    if s not in seen:
        seen.add(s)
        _deduped.append(s)
NSE_SYMBOLS = _deduped


def get_yfinance_symbol(symbol: str) -> str:
    """Convert bare NSE symbol to yfinance format (e.g. RELIANCE → RELIANCE.NS)."""
    return f"{symbol}.NS"
```

- [ ] **Step 2: Verify deduplication works and count is reasonable**

```bash
cd backend && python -c "
from domains.data.nse_universe import NSE_SYMBOLS
print(f'Total unique symbols: {len(NSE_SYMBOLS)}')
assert len(NSE_SYMBOLS) >= 400, f'Expected 400+, got {len(NSE_SYMBOLS)}'
assert len(NSE_SYMBOLS) == len(set(NSE_SYMBOLS)), 'Duplicates found'
print('OK')
"
```
Expected output: `Total unique symbols: <N>` followed by `OK`.

- [ ] **Step 3: Commit**

```bash
git add backend/domains/data/nse_universe.py
git commit -m "feat: expand NSE_SYMBOLS from 237 to Nifty 500 universe"
```

---

### Task 2: Index universe definition

**Files:**
- Create: `backend/domains/data/index_universe.py`

- [ ] **Step 1: Create index_universe.py**

```python
# backend/domains/data/index_universe.py
"""Sector index definitions and stock→index membership map."""

# yfinance symbols for each of the 7 NSE sector indices
INDEX_DEFINITIONS: dict[str, dict] = {
    "NIFTY BANK":   {"yf_symbol": "^NSEBANK",   "description": "Banking sector"},
    "NIFTY IT":     {"yf_symbol": "^CNXIT",     "description": "Information technology"},
    "NIFTY FMCG":   {"yf_symbol": "^CNXFMCG",   "description": "Fast-moving consumer goods"},
    "NIFTY AUTO":   {"yf_symbol": "^CNXAUTO",   "description": "Automobiles & components"},
    "NIFTY PHARMA": {"yf_symbol": "^CNXPHARMA", "description": "Pharmaceuticals"},
    "NIFTY METAL":  {"yf_symbol": "^CNXMETAL",  "description": "Metals & mining"},
    "NIFTY ENERGY": {"yf_symbol": "^CNXENERGY", "description": "Energy & utilities"},
}

# One primary parent index per stock.
# Stocks absent from this map receive a neutral alignment score (50/100).
STOCK_INDEX_MAP: dict[str, str] = {
    # ── NIFTY BANK ────────────────────────────────────────────────────────────
    "HDFCBANK": "NIFTY BANK",   "ICICIBANK": "NIFTY BANK",   "KOTAKBANK": "NIFTY BANK",
    "SBIN": "NIFTY BANK",       "AXISBANK": "NIFTY BANK",    "INDUSINDBK": "NIFTY BANK",
    "BANDHANBNK": "NIFTY BANK", "PNB": "NIFTY BANK",         "BANKBARODA": "NIFTY BANK",
    "FEDERALBNK": "NIFTY BANK", "IDFCFIRSTB": "NIFTY BANK",  "AUBANK": "NIFTY BANK",
    "CSBBANK": "NIFTY BANK",    "DCBBANK": "NIFTY BANK",     "RBLBANK": "NIFTY BANK",
    "YESBANK": "NIFTY BANK",    "KARURVYSYA": "NIFTY BANK",  "SOUTHBANK": "NIFTY BANK",
    "CANBK": "NIFTY BANK",      "UNIONBANK": "NIFTY BANK",   "EQUITAS": "NIFTY BANK",
    "UJJIVANSF": "NIFTY BANK",  "SBFC": "NIFTY BANK",        "VIJAYABANK": "NIFTY BANK",
    # ── NIFTY IT ──────────────────────────────────────────────────────────────
    "TCS": "NIFTY IT",          "INFY": "NIFTY IT",          "HCLTECH": "NIFTY IT",
    "WIPRO": "NIFTY IT",        "TECHM": "NIFTY IT",         "LTIM": "NIFTY IT",
    "MPHASIS": "NIFTY IT",      "COFORGE": "NIFTY IT",       "PERSISTENT": "NIFTY IT",
    "OFSS": "NIFTY IT",         "LTTS": "NIFTY IT",          "KPITTECH": "NIFTY IT",
    "TATAELXSI": "NIFTY IT",    "NIITLTD": "NIFTY IT",       "BSOFT": "NIFTY IT",
    "MASTEK": "NIFTY IT",       "HEXAWARE": "NIFTY IT",      "ZENSAR": "NIFTY IT",
    "CYIENT": "NIFTY IT",       "ECLERX": "NIFTY IT",        "TANLA": "NIFTY IT",
    "INTELLECT": "NIFTY IT",    "NEWGEN": "NIFTY IT",        "SAKSOFT": "NIFTY IT",
    "SONATSOFTW": "NIFTY IT",   "MINDTREE": "NIFTY IT",      "CIGNITI": "NIFTY IT",
    "QUICKHEAL": "NIFTY IT",    "NETSOL": "NIFTY IT",        "XCHANGING": "NIFTY IT",
    # ── NIFTY FMCG ────────────────────────────────────────────────────────────
    "HINDUNILVR": "NIFTY FMCG", "ITC": "NIFTY FMCG",        "NESTLEIND": "NIFTY FMCG",
    "BRITANNIA": "NIFTY FMCG",  "DABUR": "NIFTY FMCG",      "MARICO": "NIFTY FMCG",
    "GODREJCP": "NIFTY FMCG",   "TATACONSUM": "NIFTY FMCG",  "COLPAL": "NIFTY FMCG",
    "EMAMILTD": "NIFTY FMCG",   "RADICO": "NIFTY FMCG",     "VBL": "NIFTY FMCG",
    "JYOTHYLAB": "NIFTY FMCG",  "BIKAJI": "NIFTY FMCG",     "HATSUN": "NIFTY FMCG",
    "ZYDUSWELL": "NIFTY FMCG",  "BAJAJCON": "NIFTY FMCG",   "PGHH": "NIFTY FMCG",
    "TTKPRESTIG": "NIFTY FMCG", "HAWKINS": "NIFTY FMCG",
    # ── NIFTY AUTO ────────────────────────────────────────────────────────────
    "MARUTI": "NIFTY AUTO",     "TATAMOTORS": "NIFTY AUTO",  "M&M": "NIFTY AUTO",
    "BAJAJ-AUTO": "NIFTY AUTO", "EICHERMOT": "NIFTY AUTO",   "HEROMOTOCO": "NIFTY AUTO",
    "TVSMOTORS": "NIFTY AUTO",  "TVSMOTOR": "NIFTY AUTO",   "ASHOKLEY": "NIFTY AUTO",
    "BALKRISIND": "NIFTY AUTO", "MOTHERSON": "NIFTY AUTO",   "BOSCHLTD": "NIFTY AUTO",
    "EXIDEIND": "NIFTY AUTO",   "MRF": "NIFTY AUTO",         "APOLLOTYRE": "NIFTY AUTO",
    "CEATLTD": "NIFTY AUTO",    "AMARAJABAT": "NIFTY AUTO",  "JKTYRE": "NIFTY AUTO",
    "ESCORTS": "NIFTY AUTO",    "BHARATFORG": "NIFTY AUTO",  "SUNDRMFAST": "NIFTY AUTO",
    "WABCOINDIA": "NIFTY AUTO", "MAHINDCIE": "NIFTY AUTO",   "CRAFTSMAN": "NIFTY AUTO",
    "LUMAX": "NIFTY AUTO",      "SUPRAJIT": "NIFTY AUTO",    "MINDA": "NIFTY AUTO",
    "TIINDIA": "NIFTY AUTO",
    # ── NIFTY PHARMA ──────────────────────────────────────────────────────────
    "SUNPHARMA": "NIFTY PHARMA",  "DRREDDY": "NIFTY PHARMA",   "CIPLA": "NIFTY PHARMA",
    "DIVISLAB": "NIFTY PHARMA",   "BIOCON": "NIFTY PHARMA",    "AUROPHARMA": "NIFTY PHARMA",
    "LUPIN": "NIFTY PHARMA",      "ALKEM": "NIFTY PHARMA",     "TORNTPHARM": "NIFTY PHARMA",
    "ABBOTINDIA": "NIFTY PHARMA", "IPCALAB": "NIFTY PHARMA",   "AJANTPHARM": "NIFTY PHARMA",
    "LAURUSLABS": "NIFTY PHARMA", "GRANULES": "NIFTY PHARMA",  "GLENMARK": "NIFTY PHARMA",
    "NATCOPHARM": "NIFTY PHARMA", "JBCHEPHARM": "NIFTY PHARMA","SANOFI": "NIFTY PHARMA",
    "PFIZER": "NIFTY PHARMA",     "GLAXO": "NIFTY PHARMA",     "STRIDES": "NIFTY PHARMA",
    "MARKSANS": "NIFTY PHARMA",   "IOLCP": "NIFTY PHARMA",     "HIKAL": "NIFTY PHARMA",
    "WOCKPHARMA": "NIFTY PHARMA", "SOLARA": "NIFTY PHARMA",
    # ── NIFTY METAL ───────────────────────────────────────────────────────────
    "TATASTEEL": "NIFTY METAL",   "JSWSTEEL": "NIFTY METAL",   "HINDALCO": "NIFTY METAL",
    "VEDL": "NIFTY METAL",        "COALINDIA": "NIFTY METAL",  "NMDC": "NIFTY METAL",
    "SAIL": "NIFTY METAL",        "NATIONALUM": "NIFTY METAL", "WELSPUNLIVING": "NIFTY METAL",
    "RATNAMANI": "NIFTY METAL",   "JINDALSAW": "NIFTY METAL",  "APLAPOLLO": "NIFTY METAL",
    "HINDCOPPER": "NIFTY METAL",  "GPIL": "NIFTY METAL",       "JSPL": "NIFTY METAL",
    "WELCORP": "NIFTY METAL",     "HINDZINC": "NIFTY METAL",   "MOIL": "NIFTY METAL",
    "MAHSEAMLES": "NIFTY METAL",
    # ── NIFTY ENERGY ──────────────────────────────────────────────────────────
    "RELIANCE": "NIFTY ENERGY",   "ONGC": "NIFTY ENERGY",     "NTPC": "NIFTY ENERGY",
    "POWERGRID": "NIFTY ENERGY",  "BPCL": "NIFTY ENERGY",     "IOC": "NIFTY ENERGY",
    "GAIL": "NIFTY ENERGY",       "ADANIGREEN": "NIFTY ENERGY","TATAPOWER": "NIFTY ENERGY",
    "ADANIENT": "NIFTY ENERGY",   "CESC": "NIFTY ENERGY",     "TORNTPOWER": "NIFTY ENERGY",
    "IGL": "NIFTY ENERGY",        "MGL": "NIFTY ENERGY",      "PETRONET": "NIFTY ENERGY",
    "HINDPETRO": "NIFTY ENERGY",  "MRPL": "NIFTY ENERGY",     "JSWENERGY": "NIFTY ENERGY",
    "SUZLON": "NIFTY ENERGY",     "NHPC": "NIFTY ENERGY",     "SJVN": "NIFTY ENERGY",
    "ADANITRANS": "NIFTY ENERGY", "AEGASIND": "NIFTY ENERGY",
}
```

- [ ] **Step 2: Write and run a quick validation test**

```bash
cd backend && python -c "
from domains.data.index_universe import INDEX_DEFINITIONS, STOCK_INDEX_MAP

# All index names in STOCK_INDEX_MAP must be valid INDEX_DEFINITIONS keys
valid = set(INDEX_DEFINITIONS.keys())
for sym, idx in STOCK_INDEX_MAP.items():
    assert idx in valid, f'{sym} maps to unknown index {idx!r}'

print(f'INDEX_DEFINITIONS: {len(INDEX_DEFINITIONS)} indices')
print(f'STOCK_INDEX_MAP: {len(STOCK_INDEX_MAP)} stocks mapped')
print('OK')
"
```
Expected: `INDEX_DEFINITIONS: 7 indices` / `STOCK_INDEX_MAP: <N> stocks mapped` / `OK`.

- [ ] **Step 3: Commit**

```bash
git add backend/domains/data/index_universe.py
git commit -m "feat: add index_universe.py with 7 sector indices and stock mapping"
```

---

### Task 3: DB migrations for index tables

**Files:**
- Modify: `backend/main.py` (lifespan function)

- [ ] **Step 1: Add two table migrations inside the lifespan function**

In `backend/main.py`, inside the `lifespan` function after the combination engine table block, add:

```python
    # Index pipeline tables
    try:
        with engine.connect() as _conn:
            _conn.execute(text("""
                CREATE TABLE IF NOT EXISTS index_prices_daily (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    index_name TEXT NOT NULL,
                    date       DATE NOT NULL,
                    open       REAL,
                    high       REAL,
                    low        REAL,
                    close      REAL NOT NULL,
                    volume     REAL,
                    UNIQUE(index_name, date)
                )
            """))
            _conn.execute(text("""
                CREATE TABLE IF NOT EXISTS index_trend (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    index_name  TEXT NOT NULL,
                    date        DATE NOT NULL,
                    close       REAL NOT NULL,
                    sma20       REAL,
                    sma50       REAL,
                    above_sma20 INTEGER NOT NULL DEFAULT 0,
                    above_sma50 INTEGER NOT NULL DEFAULT 0,
                    trend_label TEXT NOT NULL,
                    computed_at DATETIME DEFAULT (datetime('now')),
                    UNIQUE(index_name, date)
                )
            """))
            _conn.commit()
        logger.info("Index pipeline tables verified")
    except Exception as e:
        logger.warning("index table migration skipped: %s", e)
```

- [ ] **Step 2: Verify tables are created on startup**

Start the server and check:
```bash
cd backend && python -c "
from database import engine
from sqlalchemy import text, inspect
insp = inspect(engine)
tables = insp.get_table_names()
assert 'index_prices_daily' in tables, 'index_prices_daily missing'
assert 'index_trend' in tables, 'index_trend missing'
print('Tables OK:', [t for t in tables if 'index' in t])
"
```

- [ ] **Step 3: Commit**

```bash
git add backend/main.py
git commit -m "feat: add index_prices_daily and index_trend DB migrations"
```

---

### Task 4: Index fetcher — compute_index_trends() (pure logic, testable)

**Files:**
- Create: `backend/domains/data/index_fetcher.py`
- Create: `backend/tests/test_index_fetcher.py` (or `backend/domains/data/test_index_fetcher.py`)

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_index_fetcher.py`:

```python
"""Tests for index_fetcher compute logic."""
import pytest
from unittest.mock import MagicMock
from sqlalchemy import text


def test_compute_trend_label_strong_bull():
    from domains.data.index_fetcher import _compute_trend_label
    assert _compute_trend_label(above_sma20=True, above_sma50=True) == "STRONG_BULL"


def test_compute_trend_label_bull():
    from domains.data.index_fetcher import _compute_trend_label
    assert _compute_trend_label(above_sma20=True, above_sma50=False) == "BULL"


def test_compute_trend_label_neutral():
    from domains.data.index_fetcher import _compute_trend_label
    assert _compute_trend_label(above_sma20=False, above_sma50=True) == "NEUTRAL"


def test_compute_trend_label_bear():
    from domains.data.index_fetcher import _compute_trend_label
    assert _compute_trend_label(above_sma20=False, above_sma50=False) == "BEAR"


def test_index_alignment_score_unmapped():
    from domains.data.index_fetcher import compute_index_alignment_score
    # Stock not in any index → neutral 50
    score = compute_index_alignment_score(index_trend_row=None)
    assert score == 50


def test_index_alignment_score_strong_bull():
    from domains.data.index_fetcher import compute_index_alignment_score
    row = {"above_sma20": 1, "above_sma50": 1, "trend_label": "STRONG_BULL"}
    assert compute_index_alignment_score(row) == 100


def test_index_alignment_score_bull():
    from domains.data.index_fetcher import compute_index_alignment_score
    row = {"above_sma20": 1, "above_sma50": 0, "trend_label": "BULL"}
    assert compute_index_alignment_score(row) == 70


def test_index_alignment_score_neutral():
    from domains.data.index_fetcher import compute_index_alignment_score
    row = {"above_sma20": 0, "above_sma50": 1, "trend_label": "NEUTRAL"}
    assert compute_index_alignment_score(row) == 40


def test_index_alignment_score_bear():
    from domains.data.index_fetcher import compute_index_alignment_score
    row = {"above_sma20": 0, "above_sma50": 0, "trend_label": "BEAR"}
    assert compute_index_alignment_score(row) == 15
```

- [ ] **Step 2: Run to confirm they fail**

```bash
cd backend && python -m pytest tests/test_index_fetcher.py -v 2>&1 | head -20
```
Expected: `ModuleNotFoundError` or `ImportError` — the file doesn't exist yet.

- [ ] **Step 3: Create index_fetcher.py with the pure functions**

Create `backend/domains/data/index_fetcher.py`:

```python
"""Index OHLCV fetcher and trend computer for the 7 NSE sector indices."""
import logging
from typing import Optional

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from domains.data.index_universe import INDEX_DEFINITIONS

logger = logging.getLogger(__name__)


# ── Pure helpers (no DB) ──────────────────────────────────────────────────────

def _compute_trend_label(above_sma20: bool, above_sma50: bool) -> str:
    if above_sma20 and above_sma50:
        return "STRONG_BULL"
    if above_sma20 and not above_sma50:
        return "BULL"
    if not above_sma20 and above_sma50:
        return "NEUTRAL"
    return "BEAR"


def compute_index_alignment_score(index_trend_row: Optional[dict]) -> int:
    """
    Returns a 0–100 raw score for the index alignment component.
    Pass None if the stock is not mapped to any sector index (returns 50 = neutral).
    """
    if index_trend_row is None:
        return 50
    above20 = bool(index_trend_row.get("above_sma20"))
    above50 = bool(index_trend_row.get("above_sma50"))
    if above20 and above50:
        return 100
    if above20 and not above50:
        return 70
    if not above20 and above50:
        return 40
    return 15


# ── DB-backed functions ────────────────────────────────────────────────────────

def compute_index_trends(db: Session) -> None:
    """
    Read index_prices_daily, compute SMA20/SMA50 for each index,
    and upsert today's trend row into index_trend.
    """
    from ist import ist_today
    today = ist_today()

    for index_name in INDEX_DEFINITIONS:
        rows = db.execute(
            text("""
                SELECT date, close FROM index_prices_daily
                WHERE index_name = :name
                ORDER BY date DESC
                LIMIT 60
            """),
            {"name": index_name},
        ).fetchall()

        if not rows:
            logger.warning("[index_trend] no price data for %s — skipping", index_name)
            continue

        closes = pd.Series(
            [r[1] for r in reversed(rows)],
            index=[r[0] for r in reversed(rows)],
            dtype=float,
        )
        latest_close = float(closes.iloc[-1])
        sma20 = float(closes.rolling(20).mean().iloc[-1]) if len(closes) >= 20 else None
        sma50 = float(closes.rolling(50).mean().iloc[-1]) if len(closes) >= 50 else None

        above_sma20 = int(latest_close > sma20) if sma20 is not None else 0
        above_sma50 = int(latest_close > sma50) if sma50 is not None else 0
        trend_label = _compute_trend_label(bool(above_sma20), bool(above_sma50))

        db.execute(
            text("""
                INSERT INTO index_trend
                    (index_name, date, close, sma20, sma50, above_sma20, above_sma50, trend_label)
                VALUES (:name, :date, :close, :sma20, :sma50, :a20, :a50, :label)
                ON CONFLICT(index_name, date) DO UPDATE SET
                    close=excluded.close, sma20=excluded.sma20, sma50=excluded.sma50,
                    above_sma20=excluded.above_sma20, above_sma50=excluded.above_sma50,
                    trend_label=excluded.trend_label, computed_at=datetime('now')
            """),
            {
                "name": index_name, "date": str(today),
                "close": latest_close, "sma20": sma20, "sma50": sma50,
                "a20": above_sma20, "a50": above_sma50, "label": trend_label,
            },
        )
        logger.info("[index_trend] %s: close=%.1f sma20=%s sma50=%s → %s",
                    index_name, latest_close,
                    f"{sma20:.1f}" if sma20 else "N/A",
                    f"{sma50:.1f}" if sma50 else "N/A",
                    trend_label)

    db.commit()


def fetch_and_store_index_prices(db: Session, days: int = 365) -> None:
    """
    Download the last `days` of daily OHLCV for all 7 sector indices via yfinance
    and upsert into index_prices_daily. Logs and continues on per-index failure.
    """
    import yfinance as yf
    import time as _time

    for index_name, meta in INDEX_DEFINITIONS.items():
        yf_symbol = meta["yf_symbol"]
        try:
            df = yf.download(
                yf_symbol,
                period=f"{days}d",
                interval="1d",
                progress=False,
                auto_adjust=True,
            )
            if df.empty:
                logger.warning("[index_fetch] %s (%s): empty response", index_name, yf_symbol)
                continue

            df = df.reset_index()
            df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
            df["date"] = pd.to_datetime(df["Date"]).dt.date

            for _, row in df.iterrows():
                db.execute(
                    text("""
                        INSERT INTO index_prices_daily
                            (index_name, date, open, high, low, close, volume)
                        VALUES (:name, :date, :open, :high, :low, :close, :volume)
                        ON CONFLICT(index_name, date) DO UPDATE SET
                            open=excluded.open, high=excluded.high, low=excluded.low,
                            close=excluded.close, volume=excluded.volume
                    """),
                    {
                        "name": index_name,
                        "date": str(row["date"]),
                        "open":   float(row.get("Open",   row.get("open",   0))) or None,
                        "high":   float(row.get("High",   row.get("high",   0))) or None,
                        "low":    float(row.get("Low",    row.get("low",    0))) or None,
                        "close":  float(row.get("Close",  row.get("close",  0))),
                        "volume": float(row.get("Volume", row.get("volume", 0))) or None,
                    },
                )
            db.commit()
            logger.info("[index_fetch] %s: %d rows upserted", index_name, len(df))
        except Exception:
            logger.exception("[index_fetch] %s (%s): failed", index_name, yf_symbol)
        _time.sleep(0.3)
```

- [ ] **Step 4: Run the tests — they should all pass**

```bash
cd backend && python -m pytest tests/test_index_fetcher.py -v
```
Expected: all 9 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/domains/data/index_fetcher.py backend/tests/test_index_fetcher.py
git commit -m "feat: add index_fetcher with compute_index_trends and alignment score"
```

---

### Task 5: Bootstrap first-run index history

**Files:**
- Modify: `backend/main.py` (lifespan function)

- [ ] **Step 1: Add first-run index bootstrap after the stock bootstrap block**

In `backend/main.py`, after the `if not has_prices:` block (around line 158), add:

```python
    # Auto-bootstrap index prices: if index_prices_daily is empty, download 1 year
    db_idx = SessionLocal()
    try:
        has_index_prices = db_idx.execute(
            text("SELECT 1 FROM index_prices_daily LIMIT 1")
        ).scalar()
    finally:
        db_idx.close()

    if not has_index_prices:
        logger.info("[startup] No index price data found — downloading 1 year of index history")
        def _bootstrap_indexes():
            from domains.data.index_fetcher import fetch_and_store_index_prices, compute_index_trends
            db_bg = SessionLocal()
            try:
                fetch_and_store_index_prices(db_bg, days=365)
                compute_index_trends(db_bg)
                logger.info("[startup] Index bootstrap complete")
            except Exception:
                logger.exception("[startup] Index bootstrap failed")
            finally:
                db_bg.close()
        threading.Thread(target=_bootstrap_indexes, daemon=True, name="index-bootstrap").start()
```

- [ ] **Step 2: Verify startup logs when index table is empty**

Restart the server (or clear the index_prices_daily table) and watch for:
```
[startup] No index price data found — downloading 1 year of index history
[index_fetch] NIFTY BANK: <N> rows upserted
...
[startup] Index bootstrap complete
```

- [ ] **Step 3: Commit**

```bash
git add backend/main.py
git commit -m "feat: auto-bootstrap index history on first run"
```

---

### Task 6: Add DAILY_INDEX_UPDATE scheduler job

**Files:**
- Modify: `backend/scheduler.py`

- [ ] **Step 1: Add the job function and registration**

In `backend/scheduler.py`, add `DAILY_INDEX_UPDATE` to `JobIds`:

```python
class JobIds:
    # ... existing entries ...
    DAILY_INDEX_UPDATE = "daily_index_update"
```

Add the job function after `_market_regime_compute()`:

```python
def _daily_index_update():
    """Fetch latest index OHLCV and recompute trend labels. Runs at 4:15 PM IST."""
    from database import SessionLocal
    from domains.data.index_fetcher import fetch_and_store_index_prices, compute_index_trends
    db = SessionLocal()
    try:
        fetch_and_store_index_prices(db, days=5)
        compute_index_trends(db)
        logger.info("[daily_index_update] complete")
    except Exception:
        logger.exception("[daily_index_update] failed")
    finally:
        db.close()
```

In `register_jobs()`, add after the market_regime_compute job:

```python
    # 4:20 PM — refresh index trends after EOD prices land
    scheduler.add_job(
        _daily_index_update,
        CronTrigger(hour=16, minute=20, day_of_week="mon-fri"),
        id=JobIds.DAILY_INDEX_UPDATE,
        replace_existing=True,
    )
```

- [ ] **Step 2: Verify job appears in scheduler**

```bash
cd backend && python -c "
from scheduler import scheduler, register_jobs
register_jobs()
job_ids = [j.id for j in scheduler.get_jobs()]
assert 'daily_index_update' in job_ids, f'Job not found. Jobs: {job_ids}'
print('Job registered OK')
"
```

- [ ] **Step 3: Commit**

```bash
git add backend/scheduler.py
git commit -m "feat: add DAILY_INDEX_UPDATE scheduler job at 4:20 PM IST"
```

---

### Task 7: Update opportunity scorer — reweight + new component

**Files:**
- Modify: `backend/domains/intelligence/opportunity_scorer.py`

- [ ] **Step 1: Write failing tests**

Add to `backend/tests/test_opportunity_scorer.py` (create if it doesn't exist):

```python
"""Tests for OpportunityScorer with index_alignment component."""


def test_weights_sum_to_100():
    from domains.intelligence.opportunity_scorer import _WEIGHTS
    assert sum(_WEIGHTS.values()) == 100, f"Weights sum to {sum(_WEIGHTS.values())}, expected 100"


def test_index_alignment_in_weights():
    from domains.intelligence.opportunity_scorer import _WEIGHTS
    assert "index_alignment" in _WEIGHTS
    assert _WEIGHTS["index_alignment"] == 10


def test_full_score_with_strong_bull_index_raises_score():
    from domains.intelligence.opportunity_scorer import OpportunityScorer
    scorer = OpportunityScorer()

    base = scorer.full_score(
        symbol="SBIN", strategy_id=1, confidence=0.6,
        historical_win_rate=0.55, regime="BULL",
        regime_strategy_win_rate=0.60,
        mtf_alignment=0.7, volume_score=0.8, sr_score=0.6,
        index_alignment_score=50,  # neutral
    )
    boosted = scorer.full_score(
        symbol="SBIN", strategy_id=1, confidence=0.6,
        historical_win_rate=0.55, regime="BULL",
        regime_strategy_win_rate=0.60,
        mtf_alignment=0.7, volume_score=0.8, sr_score=0.6,
        index_alignment_score=100,  # strong bull
    )
    assert boosted.score > base.score, (
        f"Expected boosted score ({boosted.score}) > base ({base.score})"
    )


def test_full_score_with_bear_index_lowers_score():
    from domains.intelligence.opportunity_scorer import OpportunityScorer
    scorer = OpportunityScorer()

    neutral = scorer.full_score(
        symbol="SBIN", strategy_id=1, confidence=0.6,
        historical_win_rate=0.55, regime="BULL",
        regime_strategy_win_rate=0.60,
        mtf_alignment=0.7, volume_score=0.8, sr_score=0.6,
        index_alignment_score=50,
    )
    penalised = scorer.full_score(
        symbol="SBIN", strategy_id=1, confidence=0.6,
        historical_win_rate=0.55, regime="BULL",
        regime_strategy_win_rate=0.60,
        mtf_alignment=0.7, volume_score=0.8, sr_score=0.6,
        index_alignment_score=15,  # bear
    )
    assert penalised.score < neutral.score


def test_full_score_none_index_alignment_is_neutral():
    from domains.intelligence.opportunity_scorer import OpportunityScorer
    scorer = OpportunityScorer()

    no_index = scorer.full_score(
        symbol="KRBL", strategy_id=2, confidence=0.6,
        historical_win_rate=0.55, regime="BULL",
        regime_strategy_win_rate=None,
        mtf_alignment=None, volume_score=None, sr_score=None,
        index_alignment_score=None,  # unmapped stock
    )
    neutral_index = scorer.full_score(
        symbol="KRBL", strategy_id=2, confidence=0.6,
        historical_win_rate=0.55, regime="BULL",
        regime_strategy_win_rate=None,
        mtf_alignment=None, volume_score=None, sr_score=None,
        index_alignment_score=50,  # explicit neutral
    )
    # Both should produce the same score since 50/100 = 0.5 is the neutral normalised value
    assert no_index.score == neutral_index.score
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd backend && python -m pytest tests/test_opportunity_scorer.py -v 2>&1 | head -30
```
Expected: failures on `test_weights_sum_to_100` (sum will be 100 without new key) and `test_index_alignment_in_weights`.

- [ ] **Step 3: Update opportunity_scorer.py**

In `backend/domains/intelligence/opportunity_scorer.py`:

Replace `_WEIGHTS` dict:

```python
_WEIGHTS: dict[str, int] = {
    "historical_win_rate":   20,   # was 22
    "strategy_confidence":   16,   # was 18
    "regime_alignment":      14,   # was 16
    "mtf_alignment":         13,   # was 14
    "volume":                 9,   # was 10
    "sr_context":             7,   # was 8
    "regime_strategy":        4,
    "ml_signal_probability":  7,   # was 8
    "index_alignment":       10,   # NEW — sector index SMA trend
    # ── total ──────────── 100
}
```

Add `index_alignment_score` parameter to `full_score()`:

```python
    def full_score(
        self,
        symbol: str,
        strategy_id: Optional[int],
        confidence: float,
        historical_win_rate: Optional[float],
        regime: str,
        regime_strategy_win_rate: Optional[float],
        mtf_alignment: Optional[float],
        volume_score: Optional[float],
        sr_score: Optional[float],
        false_signal_rate: Optional[float] = None,
        ml_probability: Optional[float] = None,
        index_alignment_score: Optional[int] = None,   # 0–100 raw; None = unmapped (treated as 50)
    ) -> OpportunityScore:
        # Normalise index_alignment_score: None → 50 (neutral) → 0.5
        idx_norm: Optional[float] = (index_alignment_score / 100.0) if index_alignment_score is not None else 0.5

        parts: dict[str, Optional[float]] = {
            "historical_win_rate": historical_win_rate,
            "strategy_confidence": min(1.0, max(0.0, confidence)),
            "regime_alignment":    _REGIME_BUY_SCORE.get(regime, 0.5),
            "regime_strategy":     regime_strategy_win_rate,
            "mtf_alignment":       mtf_alignment,
            "volume":              volume_score,
            "sr_context":          sr_score,
            "ml_signal_probability": ml_probability,
            "index_alignment":     idx_norm,
        }
        opp = self._compute(symbol, strategy_id, parts)

        if false_signal_rate is not None:
            rate = max(0.0, min(1.0, false_signal_rate))
            if rate >= 0.70:
                multiplier = 0.60
            elif rate >= 0.50:
                multiplier = 0.80
            else:
                multiplier = 1.0
            opp.score = round(opp.score * multiplier)
            opp.grade = _grade(opp.score)
            opp.breakdown["false_signal_rate"] = round(rate, 4)

        return opp
```

Also update the docstring at the top of the file:

```python
"""
Opportunity score (0–100) for a BUY signal.

Component weights:
  historical_win_rate   20  — backtest win rate for this (symbol, strategy) pair
  strategy_confidence   16  — confidence score from signal generation (0–1)
  regime_alignment      14  — how buy-friendly is the current market regime
  mtf_alignment         13  — multi-timeframe trend alignment score (0–1)
  volume                 9  — volume confirmation (normalised 0–1)
  sr_context             7  — proximity to support vs resistance (normalised 0–1)
  ml_signal_probability  7  — ML model probability that signal will be profitable
  regime_strategy        4  — strategy's historical win rate in the current regime
  index_alignment       10  — sector index SMA20/SMA50 trend (0–1 normalised from 0–100)
  ── total ──────────── 100

Quick mode (scanner): only win_rate, confidence, regime_alignment, regime_strategy
  (sum = 54; normalised to full scale when partial components are absent)

Full mode (on-demand endpoint): all 9 components.
"""
```

- [ ] **Step 4: Run the tests — all should pass**

```bash
cd backend && python -m pytest tests/test_opportunity_scorer.py -v
```
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/domains/intelligence/opportunity_scorer.py backend/tests/test_opportunity_scorer.py
git commit -m "feat: add index_alignment component to OpportunityScorer (10% weight)"
```

---

### Task 8: Update intelligence router

**Files:**
- Modify: `backend/domains/intelligence/router.py`

- [ ] **Step 1: Add index trend pre-load and pass-through in get_top_opportunities()**

In `router.py`, add the import at the top of the file:

```python
from domains.data.index_universe import STOCK_INDEX_MAP
from domains.data.index_fetcher import compute_index_alignment_score
```

In `get_top_opportunities()`, after the `false_rates = FalseSignalDetector().get_false_signal_rates(db)` line and before the per-symbol cache block, add:

```python
    # Pre-load latest index trends — one query for all 7 indices
    index_trend_rows = db.execute(
        text("""
            SELECT index_name, above_sma20, above_sma50, trend_label
            FROM index_trend
            WHERE date = (SELECT MAX(date) FROM index_trend)
        """)
    ).mappings().fetchall()
    index_trend_map: dict[str, dict] = {
        r["index_name"]: dict(r) for r in index_trend_rows
    }
```

In the scoring loop, after `sr_score = _compute_sr_score(sr_result) if sr_result is not None else None`, add:

```python
        # Index alignment
        parent_index = STOCK_INDEX_MAP.get(symbol)
        index_trend_row = index_trend_map.get(parent_index) if parent_index else None
        idx_alignment_raw = compute_index_alignment_score(index_trend_row)
```

Update the `opp_scorer.full_score(...)` call to include the new parameter:

```python
        opp = opp_scorer.full_score(
            symbol=symbol,
            strategy_id=strategy_id,
            confidence=confidence_score or 0.5,
            historical_win_rate=hist_wr,
            regime=regime,
            regime_strategy_win_rate=regime_wr,
            mtf_alignment=mtf_score,
            volume_score=vol_score,
            sr_score=sr_score,
            false_signal_rate=false_rate,
            ml_probability=ml_prob,
            index_alignment_score=idx_alignment_raw,
        )
```

Add `index_name` and `index_trend` to the results dict:

```python
        results.append({
            # ... all existing fields ...
            "index_name":   parent_index,
            "index_trend":  index_trend_row["trend_label"] if index_trend_row else None,
            "breakdown":    opp.breakdown,
        })
```

- [ ] **Step 2: Verify the endpoint returns the new fields**

With the server running:
```bash
curl -s -H "X-API-Key: <your-key>" http://localhost:8000/api/v1/intelligence/top-opportunities?limit=3 \
  | python -m json.tool | grep -E "index_name|index_trend"
```
Expected: lines like `"index_name": "NIFTY BANK"` and `"index_trend": "STRONG_BULL"` (or null if no signals today / no index data yet).

- [ ] **Step 3: Commit**

```bash
git add backend/domains/intelligence/router.py
git commit -m "feat: add index alignment to top-opportunities endpoint"
```

---

### Task 9: Update TypeScript types

**Files:**
- Modify: `frontend/src/api/intelligence.ts`

- [ ] **Step 1: Add new fields to interfaces**

In `OpportunityBreakdown`, add:

```typescript
export interface OpportunityBreakdown {
  historical_win_rate: number | null
  strategy_confidence: number | null
  regime_alignment: number | null
  regime_strategy: number | null
  mtf_alignment: number | null
  volume: number | null
  sr_context: number | null
  ml_signal_probability: number | null
  index_alignment: number | null      // NEW — 0–1 normalised
  false_signal_rate: number | null
}
```

In `TopOpportunity`, add:

```typescript
export interface TopOpportunity {
  // ... all existing fields ...
  index_name: string | null          // e.g. "NIFTY BANK" — null if stock not mapped
  index_trend: 'STRONG_BULL' | 'BULL' | 'NEUTRAL' | 'BEAR' | null
  breakdown: OpportunityBreakdown
}
```

- [ ] **Step 2: TypeScript compile check**

```bash
cd frontend && npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/intelligence.ts
git commit -m "feat: add index_name, index_trend, index_alignment to TypeScript types"
```

---

### Task 10: Update TopOpportunities frontend

**Files:**
- Modify: `frontend/src/components/TopOpportunities.tsx`

- [ ] **Step 1: Add IndexTrendBadge component and update SCORE_COMPONENTS**

At the top of `TopOpportunities.tsx`, after the existing `REGIME_SHORT` constant, add:

```typescript
const INDEX_TREND_STYLE: Record<string, { bg: string; text: string; arrow: string }> = {
  STRONG_BULL: { bg: 'bg-emerald-100', text: 'text-emerald-700', arrow: '↑↑' },
  BULL:        { bg: 'bg-green-50',    text: 'text-green-700',   arrow: '↑'  },
  NEUTRAL:     { bg: 'bg-gray-100',    text: 'text-gray-500',    arrow: '→'  },
  BEAR:        { bg: 'bg-red-50',      text: 'text-red-600',     arrow: '↓'  },
}

function IndexTrendBadge({ indexName, trend }: { indexName: string | null; trend: string | null }) {
  if (!indexName || !trend) return null
  const style = INDEX_TREND_STYLE[trend] ?? INDEX_TREND_STYLE.NEUTRAL
  const shortName = indexName.replace('NIFTY ', '')
  return (
    <span
      className={`inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-xs font-medium ${style.bg} ${style.text}`}
      title={`${indexName}: ${trend}`}
    >
      {shortName} {style.arrow}
    </span>
  )
}
```

Replace `SCORE_COMPONENTS` with the updated list (new `index_alignment` entry, updated weights):

```typescript
const SCORE_COMPONENTS: { key: ComponentKey; label: string; weight: number }[] = [
  { key: 'historical_win_rate',   label: 'Historical Win Rate',   weight: 20 },
  { key: 'strategy_confidence',   label: 'Strategy Confidence',   weight: 16 },
  { key: 'regime_alignment',      label: 'Regime Alignment',      weight: 14 },
  { key: 'mtf_alignment',         label: 'MTF Alignment',         weight: 13 },
  { key: 'index_alignment',       label: 'Index Alignment',       weight: 10 },
  { key: 'volume',                label: 'Volume',                weight:  9 },
  { key: 'sr_context',            label: 'S/R Context',           weight:  7 },
  { key: 'ml_signal_probability', label: 'ML Probability',        weight:  7 },
  { key: 'regime_strategy',       label: 'Regime-Strategy',       weight:  4 },
]
```

- [ ] **Step 2: Add IndexTrendBadge to the symbol cell in OpportunityRow**

In the `OpportunityRow` `<tr>`, find the symbol `<td>` cell:

```typescript
<td className="px-4 py-2 font-semibold">{opp.symbol}</td>
```

Replace with:

```typescript
<td className="px-4 py-2">
  <div className="flex items-center gap-1.5">
    <span className="font-semibold">{opp.symbol}</span>
    <IndexTrendBadge indexName={opp.index_name} trend={opp.index_trend} />
  </div>
</td>
```

- [ ] **Step 3: TypeScript compile check**

```bash
cd frontend && npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/TopOpportunities.tsx
git commit -m "feat: add IndexTrendBadge and updated score breakdown to opportunity cards"
```

---

## Self-Review Notes

- All 10 tasks produce working, independently testable changes
- The `compute_index_alignment_score` helper is imported by both the test suite (Task 4) and the router (Task 8) — name is consistent throughout
- `index_alignment_score=None` in the scorer maps to 0.5 normalised (neutral), matching `compute_index_alignment_score(None) == 50` → `50/100 = 0.5`
- TypeScript `OpportunityBreakdown.index_alignment` is `number | null` matching the Python scorer which may omit the key if value is None — the frontend handles null gracefully via `val != null` check in `ScoreBreakdown`
- The `ON CONFLICT ... DO UPDATE` syntax is SQLite-compatible (requires SQLite 3.24+, which ships with Python 3.8+)
- Weight sums: Task 7 test explicitly asserts `sum(_WEIGHTS.values()) == 100`
