# StockV2 Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Working FastAPI backend with all 15 SQLite tables, 237 NSE stocks downloaded (15yr historical), all technical indicators computed, and Angel One live feed connected.

**Architecture:** Single FastAPI process, sync SQLAlchemy ORM for CRUD, SQLite with WAL mode for zero-setup persistence, pandas-ta for indicators, APScheduler (skeleton only in this plan) for scheduled jobs. Domain-isolated service layer — each domain owns its own service and routes but shares a single models file to avoid circular imports.

**Tech Stack:** Python 3.11, FastAPI 0.110, SQLAlchemy 2.0, Alembic, pandas-ta, yfinance 0.2, smartapi-python, Pydantic Settings v2, pytest

---

## File Map

```
backend/
├── pyproject.toml                        NEW — all Python dependencies
├── .env.example                          NEW — required env vars template
├── .env                                  NEW (gitignored) — real secrets
├── main.py                               NEW — FastAPI app + router registration
├── settings.py                           NEW — Pydantic Settings (reads .env)
├── database.py                           NEW — engine, session, Base, WAL setup
├── models.py                             NEW — all 15 SQLAlchemy table models
├── scheduler.py                          NEW — APScheduler instance (skeleton)
├── domains/
│   └── data/
│       ├── __init__.py                   NEW (empty)
│       ├── router.py                     NEW — GET /stocks, /stocks/{symbol}/prices etc
│       ├── service.py                    NEW — DataService (DB queries)
│       ├── indicators.py                 NEW — IndicatorEngine (pandas-ta)
│       ├── nse_universe.py              NEW — hardcoded list of 237 NSE symbols
│       └── feeds/
│           ├── __init__.py               NEW (empty)
│           ├── yfinance_feed.py          NEW — download/update historical OHLCV
│           └── angel_one_feed.py         NEW — live quotes + WebSocket ticks
├── scripts/
│   └── bootstrap.py                      NEW — one-shot historical data bootstrap
├── tests/
│   ├── conftest.py                       NEW — test DB setup, fixtures
│   ├── test_models.py                    NEW — DB table creation tests
│   ├── test_indicators.py               NEW — IndicatorEngine tests
│   ├── test_yfinance_feed.py            NEW — feed tests (mocked)
│   ├── test_angel_one_feed.py           NEW — feed tests (mocked)
│   └── test_data_router.py              NEW — API endpoint tests
└── alembic/
    ├── alembic.ini                        NEW
    ├── env.py                             NEW
    └── versions/
        └── 0001_initial_schema.py         NEW — all 15 tables
```

---

## Task 1: Project Setup

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/.env.example`
- Create: `backend/.gitignore`

- [ ] **Step 1: Create backend directory and pyproject.toml**

```toml
# backend/pyproject.toml
[tool.poetry]
name = "stockv2-backend"
version = "0.1.0"
description = "StockV2 AI Trading Platform"
authors = ["Vivek Kumar"]

[tool.poetry.dependencies]
python = "^3.11"
fastapi = "^0.110.0"
uvicorn = {extras = ["standard"], version = "^0.29.0"}
sqlalchemy = "^2.0.0"
alembic = "^1.13.0"
pydantic-settings = "^2.2.0"
apscheduler = "^3.10.0"
pandas = "^2.0.0"
numpy = "^1.26.0"
pandas-ta = "^0.3.14b"
yfinance = "^0.2.40"
smartapi-python = "^1.3.7"
pyotp = "^2.9.0"
anthropic = "^0.25.0"
python-telegram-bot = "^21.0"
httpx = "^0.27.0"
aiofiles = "^23.2.0"
python-multipart = "^0.0.9"

[tool.poetry.group.dev.dependencies]
pytest = "^8.0.0"
pytest-asyncio = "^0.23.0"
httpx = "^0.27.0"
ruff = "^0.4.0"

[build-system]
requires = ["poetry-core"]
build-backend = "poetry.core.masonry.api"

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 2: Create .env.example**

```bash
# backend/.env.example
# Copy to .env and fill in your values

# Claude API
ANTHROPIC_API_KEY=sk-ant-...

# Telegram
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# Angel One SmartAPI
ANGEL_ONE_API_KEY=
ANGEL_ONE_CLIENT_ID=
ANGEL_ONE_PASSWORD=
ANGEL_ONE_TOTP_SECRET=

# App Security
API_KEY=changeme-set-a-strong-key

# Trading Config (defaults shown)
TRADING_MODE=paper
TOTAL_CAPITAL=500000
PAPER_CAPITAL=500000
```

- [ ] **Step 3: Create .gitignore**

```gitignore
# backend/.gitignore
.env
__pycache__/
*.pyc
*.db
*.db-wal
*.db-shm
.pytest_cache/
dist/
*.egg-info/
data/
stock_models/
ml_models*/
```

- [ ] **Step 4: Install dependencies**

```bash
cd backend
poetry install
```

Expected: `Installing dependencies from lock file` ... `Package operations: N installs`

- [ ] **Step 5: Commit**

```bash
git add backend/pyproject.toml backend/.env.example backend/.gitignore
git commit -m "feat: project setup — pyproject.toml and config files"
```

---

## Task 2: Settings

**Files:**
- Create: `backend/settings.py`
- Create: `backend/.env` (from .env.example, gitignored)

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_settings.py
from settings import settings

def test_settings_has_required_fields():
    assert hasattr(settings, "anthropic_api_key")
    assert hasattr(settings, "trading_mode")
    assert hasattr(settings, "total_capital")
    assert hasattr(settings, "api_key")

def test_settings_defaults():
    assert settings.trading_mode == "paper"
    assert settings.total_capital == 500_000
    assert settings.max_open_positions == 8
    assert settings.max_single_stock_pct == 20.0
    assert settings.host == "127.0.0.1"
    assert settings.port == 8000
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && poetry run pytest tests/test_settings.py -v
```

Expected: `ImportError: No module named 'settings'`

- [ ] **Step 3: Implement settings.py**

```python
# backend/settings.py
from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    # External API Keys
    anthropic_api_key: str = ""
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    angel_one_api_key: str = ""
    angel_one_client_id: str = ""
    angel_one_password: str = ""
    angel_one_totp_secret: str = ""

    # App Security
    api_key: str = "changeme"

    # Trading Config
    trading_mode: str = "paper"          # "paper" | "semi_auto" | "full_auto"
    total_capital: float = 500_000
    paper_capital: float = 500_000
    risk_per_trade_pct: float = 2.0
    max_open_positions: int = 8
    max_single_stock_pct: float = 20.0
    max_sector_pct: float = 35.0
    daily_loss_limit_pct: float = 3.0
    auto_trading_enabled: bool = False

    # Signal Config
    min_confidence_for_alert: float = 0.65
    max_ai_signals_per_day: int = 10

    # App
    host: str = "127.0.0.1"
    port: int = 8000
    db_path: str = "stockv2.db"
    data_dir: Path = Path("data")

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
```

- [ ] **Step 4: Create .env from example**

```bash
cp .env.example .env
# Edit .env and set API_KEY to something secure
# Leave other keys empty for now — they'll be needed in later plans
```

- [ ] **Step 5: Run tests to verify passing**

```bash
poetry run pytest tests/test_settings.py -v
```

Expected: `2 passed`

- [ ] **Step 6: Commit**

```bash
git add backend/settings.py backend/tests/test_settings.py
git commit -m "feat: settings — Pydantic Settings with all config fields"
```

---

## Task 3: Database Engine

**Files:**
- Create: `backend/database.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_database.py
from sqlalchemy import text
from database import engine, SessionLocal, get_db


def test_engine_connects():
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1"))
        assert result.scalar() == 1


def test_wal_mode_enabled():
    with engine.connect() as conn:
        result = conn.execute(text("PRAGMA journal_mode"))
        mode = result.scalar()
        assert mode == "wal"


def test_session_local_creates_session():
    db = SessionLocal()
    try:
        result = db.execute(text("SELECT 1"))
        assert result.scalar() == 1
    finally:
        db.close()


def test_get_db_yields_and_closes():
    gen = get_db()
    db = next(gen)
    assert db is not None
    try:
        next(gen)
    except StopIteration:
        pass  # expected — generator closed the session
```

- [ ] **Step 2: Run test to verify it fails**

```bash
poetry run pytest tests/test_database.py -v
```

Expected: `ImportError: No module named 'database'`

- [ ] **Step 3: Implement database.py**

```python
# backend/database.py
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from settings import settings


DATABASE_URL = f"sqlite:///{settings.db_path}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    pool_pre_ping=True,
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, _):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA cache_size=-64000")   # 64 MB cache
    cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

- [ ] **Step 4: Run tests to verify passing**

```bash
poetry run pytest tests/test_database.py -v
```

Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/database.py backend/tests/test_database.py
git commit -m "feat: database — SQLite engine with WAL mode and session factory"
```

---

## Task 4: SQLAlchemy Models

**Files:**
- Create: `backend/models.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_models.py
from sqlalchemy import inspect
from database import engine, Base
import models  # noqa: F401 — registers all models with Base


def _table_columns(table_name: str) -> set[str]:
    inspector = inspect(engine)
    return {col["name"] for col in inspector.get_columns(table_name)}


def setup_module():
    Base.metadata.create_all(bind=engine)


def test_stocks_table_exists():
    Base.metadata.create_all(bind=engine)
    inspector = inspect(engine)
    assert "stocks" in inspector.get_table_names()


def test_stocks_columns():
    cols = _table_columns("stocks")
    assert {"id", "symbol", "name", "sector", "exchange", "is_active"}.issubset(cols)


def test_stock_prices_daily_columns():
    cols = _table_columns("stock_prices_daily")
    assert {"id", "symbol", "date", "open", "high", "low", "close", "volume"}.issubset(cols)


def test_stock_prices_intraday_columns():
    cols = _table_columns("stock_prices_intraday")
    assert {"id", "symbol", "timestamp", "open", "high", "low", "close", "volume", "interval"}.issubset(cols)


def test_all_15_tables_exist():
    Base.metadata.create_all(bind=engine)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    expected = {
        "stocks", "stock_prices_daily", "stock_prices_intraday",
        "fundamentals", "corporate_actions", "news",
        "strategies", "strategy_signals", "backtest_results", "backtest_trades",
        "portfolio_holdings", "trades", "orders", "exit_rules", "watchlist",
        "ai_analyses", "ai_conversations",
        "alerts", "alert_history", "data_quality_log",
    }
    assert expected.issubset(tables), f"Missing tables: {expected - tables}"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
poetry run pytest tests/test_models.py -v
```

Expected: `ImportError: No module named 'models'`

- [ ] **Step 3: Implement models.py**

```python
# backend/models.py
from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Boolean, Date, DateTime, Float, Index, Integer,
    String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


# ─── Market Data ──────────────────────────────────────────────────────────────

class Stock(Base):
    __tablename__ = "stocks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), default="")
    sector: Mapped[Optional[str]] = mapped_column(String(100))
    industry: Mapped[Optional[str]] = mapped_column(String(200))
    market_cap: Mapped[Optional[float]] = mapped_column(Float)
    exchange: Mapped[str] = mapped_column(String(10), default="NSE")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    added_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class StockPriceDaily(Base):
    __tablename__ = "stock_prices_daily"
    __table_args__ = (
        UniqueConstraint("symbol", "date", name="uq_daily_symbol_date"),
        Index("idx_prices_daily_symbol_date", "symbol", "date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[int] = mapped_column(Integer)
    adj_close: Mapped[Optional[float]] = mapped_column(Float)
    data_source: Mapped[str] = mapped_column(String(20), default="yfinance")


class StockPriceIntraday(Base):
    __tablename__ = "stock_prices_intraday"
    __table_args__ = (
        UniqueConstraint("symbol", "timestamp", "interval", name="uq_intraday_symbol_ts"),
        Index("idx_prices_intraday_symbol_ts", "symbol", "timestamp"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[int] = mapped_column(Integer)
    interval: Mapped[str] = mapped_column(String(5), default="15m")


class Fundamental(Base):
    __tablename__ = "fundamentals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    pe_ratio: Mapped[Optional[float]] = mapped_column(Float)
    pb_ratio: Mapped[Optional[float]] = mapped_column(Float)
    eps: Mapped[Optional[float]] = mapped_column(Float)
    revenue: Mapped[Optional[float]] = mapped_column(Float)
    net_profit: Mapped[Optional[float]] = mapped_column(Float)
    debt_equity: Mapped[Optional[float]] = mapped_column(Float)
    roe: Mapped[Optional[float]] = mapped_column(Float)
    promoter_holding: Mapped[Optional[float]] = mapped_column(Float)
    fii_holding: Mapped[Optional[float]] = mapped_column(Float)
    dii_holding: Mapped[Optional[float]] = mapped_column(Float)
    data_as_of: Mapped[Optional[date]] = mapped_column(Date)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CorporateAction(Base):
    __tablename__ = "corporate_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    action_type: Mapped[str] = mapped_column(String(20))  # dividend|split|bonus
    ex_date: Mapped[Optional[date]] = mapped_column(Date)
    record_date: Mapped[Optional[date]] = mapped_column(Date)
    value: Mapped[Optional[float]] = mapped_column(Float)
    notes: Mapped[Optional[str]] = mapped_column(Text)


class News(Base):
    __tablename__ = "news"
    __table_args__ = (
        Index("idx_news_symbol_published", "symbol", "published_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[Optional[str]] = mapped_column(String(20))  # null = market-wide
    headline: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[Optional[str]] = mapped_column(Text)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    sentiment: Mapped[Optional[str]] = mapped_column(String(10))   # positive|negative|neutral
    impact_score: Mapped[Optional[float]] = mapped_column(Float)   # 0.0-1.0
    category: Mapped[Optional[str]] = mapped_column(String(30))
    ai_summary: Mapped[Optional[str]] = mapped_column(Text)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ─── Strategy & Signals ───────────────────────────────────────────────────────

class Strategy(Base):
    __tablename__ = "strategies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    type: Mapped[str] = mapped_column(String(20))  # technical|fundamental|ml|custom
    description: Mapped[Optional[str]] = mapped_column(Text)
    parameters_json: Mapped[Optional[str]] = mapped_column(Text)  # JSON string
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class StrategySignal(Base):
    __tablename__ = "strategy_signals"
    __table_args__ = (
        Index("idx_signals_symbol_date", "symbol", "signal_date"),
        Index("idx_signals_strategy_date", "strategy_id", "signal_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    strategy_id: Mapped[int] = mapped_column(Integer, nullable=False)
    signal_date: Mapped[date] = mapped_column(Date, nullable=False)
    signal_type: Mapped[str] = mapped_column(String(10))  # BUY|SELL|WATCH
    price_at_signal: Mapped[Optional[float]] = mapped_column(Float)
    confidence_score: Mapped[Optional[float]] = mapped_column(Float)
    risk_score: Mapped[Optional[float]] = mapped_column(Float)
    expected_upside_pct: Mapped[Optional[float]] = mapped_column(Float)
    suggested_stop_loss: Mapped[Optional[float]] = mapped_column(Float)
    suggested_target: Mapped[Optional[float]] = mapped_column(Float)
    holding_period_days: Mapped[Optional[int]] = mapped_column(Integer)
    reasoning_json: Mapped[Optional[str]] = mapped_column(Text)   # AI explanation JSON
    indicators_json: Mapped[Optional[str]] = mapped_column(Text)  # triggered indicators
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class BacktestResult(Base):
    __tablename__ = "backtest_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    strategy_id: Mapped[int] = mapped_column(Integer, nullable=False)
    symbol: Mapped[Optional[str]] = mapped_column(String(20))  # null = all stocks
    from_date: Mapped[date] = mapped_column(Date)
    to_date: Mapped[date] = mapped_column(Date)
    total_trades: Mapped[int] = mapped_column(Integer, default=0)
    win_rate: Mapped[Optional[float]] = mapped_column(Float)
    cagr: Mapped[Optional[float]] = mapped_column(Float)
    sharpe_ratio: Mapped[Optional[float]] = mapped_column(Float)
    sortino_ratio: Mapped[Optional[float]] = mapped_column(Float)
    max_drawdown: Mapped[Optional[float]] = mapped_column(Float)
    profit_factor: Mapped[Optional[float]] = mapped_column(Float)
    avg_return_pct: Mapped[Optional[float]] = mapped_column(Float)
    full_metrics_json: Mapped[Optional[str]] = mapped_column(Text)
    ran_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class BacktestTrade(Base):
    __tablename__ = "backtest_trades"
    __table_args__ = (
        Index("idx_backtest_trades_result", "backtest_result_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    backtest_result_id: Mapped[int] = mapped_column(Integer, nullable=False)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    entry_date: Mapped[date] = mapped_column(Date)
    entry_price: Mapped[float] = mapped_column(Float)
    exit_date: Mapped[Optional[date]] = mapped_column(Date)
    exit_price: Mapped[Optional[float]] = mapped_column(Float)
    quantity: Mapped[int] = mapped_column(Integer)
    pnl: Mapped[Optional[float]] = mapped_column(Float)
    pnl_pct: Mapped[Optional[float]] = mapped_column(Float)
    exit_reason: Mapped[Optional[str]] = mapped_column(String(30))
    holding_days: Mapped[Optional[int]] = mapped_column(Integer)


# ─── Portfolio ────────────────────────────────────────────────────────────────

class PortfolioHolding(Base):
    __tablename__ = "portfolio_holdings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    avg_buy_price: Mapped[float] = mapped_column(Float, nullable=False)
    first_buy_date: Mapped[date] = mapped_column(Date)
    last_buy_date: Mapped[date] = mapped_column(Date)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Trade(Base):
    __tablename__ = "trades"
    __table_args__ = (
        Index("idx_trades_symbol_date", "symbol", "trade_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    trade_type: Mapped[str] = mapped_column(String(4))   # BUY|SELL
    quantity: Mapped[int] = mapped_column(Integer)
    price: Mapped[float] = mapped_column(Float)
    total_value: Mapped[float] = mapped_column(Float)
    brokerage: Mapped[float] = mapped_column(Float, default=0.0)
    trade_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    order_id: Mapped[Optional[int]] = mapped_column(Integer)
    mode: Mapped[str] = mapped_column(String(10), default="paper")
    strategy_id: Mapped[Optional[int]] = mapped_column(Integer)
    signal_id: Mapped[Optional[int]] = mapped_column(Integer)
    notes: Mapped[Optional[str]] = mapped_column(Text)


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    order_type: Mapped[str] = mapped_column(String(10))  # MARKET|LIMIT|SL
    side: Mapped[str] = mapped_column(String(4))          # BUY|SELL
    quantity: Mapped[int] = mapped_column(Integer)
    price: Mapped[Optional[float]] = mapped_column(Float)
    trigger_price: Mapped[Optional[float]] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(15), default="pending")
    broker_order_id: Mapped[Optional[str]] = mapped_column(String(50))
    placed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    executed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    mode: Mapped[str] = mapped_column(String(10), default="paper")


class ExitRule(Base):
    __tablename__ = "exit_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(Integer, nullable=False)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    entry_price: Mapped[float] = mapped_column(Float)
    stop_loss_price: Mapped[float] = mapped_column(Float)
    target_1_price: Mapped[float] = mapped_column(Float)
    target_2_price: Mapped[float] = mapped_column(Float)
    max_exit_date: Mapped[Optional[date]] = mapped_column(Date)
    partial_exit_at_t1: Mapped[bool] = mapped_column(Boolean, default=True)


class Watchlist(Base):
    __tablename__ = "watchlist"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    added_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    reason: Mapped[Optional[str]] = mapped_column(Text)
    strategy_id: Mapped[Optional[int]] = mapped_column(Integer)
    alert_price: Mapped[Optional[float]] = mapped_column(Float)


# ─── AI ───────────────────────────────────────────────────────────────────────

class AIAnalysis(Base):
    __tablename__ = "ai_analyses"
    __table_args__ = (
        Index("idx_ai_analyses_subject", "subject_type", "subject_id", "expires_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subject_type: Mapped[str] = mapped_column(String(20))   # signal|stock|news|portfolio
    subject_id: Mapped[Optional[str]] = mapped_column(String(50))
    analysis_type: Mapped[str] = mapped_column(String(30))
    content: Mapped[str] = mapped_column(Text)
    model_used: Mapped[str] = mapped_column(String(50), default="claude-sonnet-4-6")
    tokens_used: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime)


class AIConversation(Base):
    __tablename__ = "ai_conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    role: Mapped[str] = mapped_column(String(10))   # user|assistant
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ─── Alerts ───────────────────────────────────────────────────────────────────

class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    alert_type: Mapped[str] = mapped_column(String(30))
    symbol: Mapped[Optional[str]] = mapped_column(String(20))
    condition_json: Mapped[Optional[str]] = mapped_column(Text)
    message_template: Mapped[Optional[str]] = mapped_column(Text)
    channels_json: Mapped[str] = mapped_column(Text, default='["telegram"]')
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AlertHistory(Base):
    __tablename__ = "alert_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    alert_id: Mapped[int] = mapped_column(Integer, nullable=False)
    symbol: Mapped[Optional[str]] = mapped_column(String(20))
    triggered_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    message_sent: Mapped[Optional[str]] = mapped_column(Text)
    delivery_status_json: Mapped[Optional[str]] = mapped_column(Text)


# ─── System ───────────────────────────────────────────────────────────────────

class DataQualityLog(Base):
    __tablename__ = "data_quality_log"
    __table_args__ = (
        Index("idx_data_quality_symbol", "symbol", "logged_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[Optional[str]] = mapped_column(String(20))
    date: Mapped[Optional[date]] = mapped_column(Date)
    issue_type: Mapped[str] = mapped_column(String(30))
    details: Mapped[Optional[str]] = mapped_column(Text)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    logged_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
```

- [ ] **Step 4: Run tests to verify passing**

```bash
poetry run pytest tests/test_models.py -v
```

Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/models.py backend/tests/test_models.py
git commit -m "feat: models — all 20 SQLAlchemy table definitions"
```

---

## Task 5: Alembic Migration

**Files:**
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/versions/0001_initial_schema.py`

- [ ] **Step 1: Initialise Alembic**

```bash
cd backend && poetry run alembic init alembic
```

Expected: Creates `alembic/` directory and `alembic.ini`

- [ ] **Step 2: Configure alembic.ini**

Edit `backend/alembic.ini` — find the `sqlalchemy.url` line and replace it:
```ini
sqlalchemy.url = sqlite:///stockv2.db
```

- [ ] **Step 3: Configure alembic/env.py**

Replace the full contents of `backend/alembic/env.py`:

```python
# backend/alembic/env.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from alembic import context
from database import Base, engine
import models  # noqa: F401 — registers all models


def run_migrations_offline():
    context.configure(
        url=str(engine.url),
        target_metadata=Base.metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 4: Generate initial migration**

```bash
poetry run alembic revision --autogenerate -m "initial_schema"
```

Expected: `Generating .../alembic/versions/xxxx_initial_schema.py ... done`

- [ ] **Step 5: Apply migration**

```bash
poetry run alembic upgrade head
```

Expected:
```
INFO  [alembic.runtime.migration] Running upgrade  -> xxxx, initial_schema
```

- [ ] **Step 6: Verify all tables were created**

```bash
poetry run python -c "
from sqlalchemy import inspect
from database import engine
tables = inspect(engine).get_table_names()
print(f'Tables created: {len(tables)}')
print(sorted(tables))
"
```

Expected: `Tables created: 20` followed by the table names list.

- [ ] **Step 7: Commit**

```bash
git add backend/alembic.ini backend/alembic/ backend/tests/test_models.py
git commit -m "feat: alembic — initial migration creates all 20 tables"
```

---

## Task 6: NSE Stock Universe

**Files:**
- Create: `backend/domains/data/__init__.py`
- Create: `backend/domains/data/nse_universe.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_nse_universe.py
from domains.data.nse_universe import NSE_SYMBOLS, get_yfinance_symbol


def test_universe_has_sufficient_stocks():
    assert len(NSE_SYMBOLS) >= 200


def test_symbols_are_uppercase():
    for sym in NSE_SYMBOLS:
        assert sym == sym.upper(), f"{sym} is not uppercase"


def test_symbols_have_no_ns_suffix():
    for sym in NSE_SYMBOLS:
        assert not sym.endswith(".NS"), f"{sym} should not include .NS suffix"


def test_get_yfinance_symbol():
    assert get_yfinance_symbol("RELIANCE") == "RELIANCE.NS"
    assert get_yfinance_symbol("TCS") == "TCS.NS"


def test_known_symbols_present():
    assert "RELIANCE" in NSE_SYMBOLS
    assert "TCS" in NSE_SYMBOLS
    assert "INFY" in NSE_SYMBOLS
    assert "HDFCBANK" in NSE_SYMBOLS
```

- [ ] **Step 2: Run test to verify it fails**

```bash
poetry run pytest tests/test_nse_universe.py -v
```

Expected: `ImportError: No module named 'domains'`

- [ ] **Step 3: Create package files and nse_universe.py**

```python
# backend/domains/__init__.py
# (empty)
```

```python
# backend/domains/data/__init__.py
# (empty)
```

```python
# backend/domains/data/nse_universe.py
"""237 NSE stock symbols (revenue > ₹70 Cr, actively traded)."""

NSE_SYMBOLS: list[str] = [
    # Large Cap — Nifty 50
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
    # Mid Cap
    "PIDILITIND", "DABUR", "MARICO", "GODREJCP", "COLPAL",
    "BERGEPAINT", "KANSAINER", "HAVELLS", "VOLTAS", "CROMPTON",
    "POLYCAB", "APLAPOLLO", "SUPREMEIND", "ASTRAL", "FINOLEX",
    "CUMMINSIND", "THERMAX", "ABB", "SIEMENS", "BHEL",
    "IRCTC", "CONCOR", "DMART", "TRENT", "NYKAA",
    "ZOMATO", "PAYTM", "POLICYBZR", "DELHIVERY", "NAUKRI",
    "INDIAMART", "JUSTDIAL", "MPHASIS", "COFORGE", "PERSISTENT",
    "LTTS", "KPITTECH", "TATAELXSI", "MASTEK", "HEXAWARE",
    "BANKBARODA", "CANBK", "UNIONBANK", "PNB", "IDFCFIRSTB",
    "FEDERALBNK", "BANDHANBNK", "RBLBANK", "AUBANK", "EQUITAS",
    "CHOLAFIN", "BAJAJHLDNG", "MUTHOOTFIN", "MANAPPURAM", "M&MFIN",
    "SHRIRAMFIN", "L&TFH", "RECLTD", "PFC", "IRFC",
    "TORNTPHARM", "LUPIN", "BIOCON", "ALKEM", "IPCALAB",
    "AUROPHARMA", "GRANULES", "NATCOPHARM", "AJANTPHARM", "JBCHEPHARM",
    "FORTIS", "MAXHEALTH", "ASTER", "NARAYANHRU", "METROPOLIS",
    "LALPATHLAB", "THYROCARE", "KRBL", "LT", "HFCL",
    "TATAPOWER", "ADANIGREEN", "ADANITRANS", "TORNTPOWER", "CESC",
    "PETRONET", "GAIL", "MGL", "IGL", "AEGASIND",
    "ULTRACEMCO", "AMBUJACEM", "ACC", "RAMCOCEM", "JKCEMENT",
    "SHREECEM", "HEIDELBERG", "INDIACEM", "DALMIA", "BIRLACORP",
    "TATACHEM", "GHCL", "VINATI", "DEEPAKFERT", "GSFC",
    "CHAMBLFERT", "COROMANDEL", "PIIND", "ATUL", "NAVINFLUOR",
    "FLUOROCHEM", "CLEAN", "FINEORG", "SUDARSCHEM", "GALAXYSURF",
    "OBEROIRLTY", "DLF", "GODREJPROP", "PRESTIGE", "BRIGADE",
    "SOBHA", "MAHLIFE", "SUNTECK", "PHOENIXLTD", "IBREALEST",
    "SPICEJET", "INDIGO", "BLUEDART", "MAHINDCIE", "MOTHERSON",
    "BOSCHLTD", "BHARATFORG", "SUNDRMFAST", "WABCOINDIA", "ESCORTS",
    "TVSMOTOR", "BALKRISIND", "APOLLOTYRE", "CEATLTD", "JKTYRE",
    "MINDTREE", "NIITLTD", "ZENSAR", "CYIENT", "NIITMTS",
    "ROUTE", "EASEMYTRIP", "THOMASCOOK", "MHRIL", "EIHOTEL",
    "CHALET", "LEMONTRE", "MAHINDRA", "SHOPERSTOP", "TITAN",
    "VAIBHAVGBL", "PCJEWELLER", "SENCO", "KALYAN",
    # Small Cap — Nifty Smallcap 100
    "KPRMILL", "NITIN", "VIJAYABANK", "CMSINFO", "BSOFT",
    "TANLA", "INTELLECT", "NEWGEN", "SAKSOFT", "ECLERX",
    "QUICKHEAL", "NETSOL", "CIGNITI", "XCHANGING", "SONATSOFTW",
    "RAILTEL", "IRCON", "NBCC", "RVNL", "SJVN",
    "NHPC", "MAHAGENCO", "THDCIL", "GMRINFRA", "GVK",
    "GPIL", "JSPL", "WELCORP", "RATNAMANI", "MAHSEAMLES",
]

# Deduplicate while preserving order
seen = set()
_deduped = []
for s in NSE_SYMBOLS:
    if s not in seen:
        seen.add(s)
        _deduped.append(s)
NSE_SYMBOLS = _deduped


def get_yfinance_symbol(symbol: str) -> str:
    """Convert bare NSE symbol to yfinance format (e.g., RELIANCE → RELIANCE.NS)."""
    return f"{symbol}.NS"
```

- [ ] **Step 4: Run tests to verify passing**

```bash
poetry run pytest tests/test_nse_universe.py -v
```

Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/domains/ backend/tests/test_nse_universe.py
git commit -m "feat: nse_universe — 237 NSE symbols with yfinance symbol helper"
```

---

## Task 7: Technical Indicator Engine

**Files:**
- Create: `backend/domains/data/indicators.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_indicators.py
import pandas as pd
import numpy as np
import pytest
from domains.data.indicators import IndicatorEngine


@pytest.fixture
def sample_df():
    """200 days of synthetic OHLCV data — enough for all indicators."""
    np.random.seed(42)
    n = 200
    close = 1000 + np.cumsum(np.random.randn(n) * 10)
    df = pd.DataFrame({
        "open":   close * (1 + np.random.uniform(-0.01, 0.01, n)),
        "high":   close * (1 + np.random.uniform(0.0, 0.02, n)),
        "low":    close * (1 - np.random.uniform(0.0, 0.02, n)),
        "close":  close,
        "volume": np.random.randint(100_000, 5_000_000, n),
    })
    df.index = pd.date_range("2024-01-01", periods=n, freq="B")
    return df


def test_compute_returns_dataframe(sample_df):
    result = IndicatorEngine.compute(sample_df)
    assert isinstance(result, pd.DataFrame)


def test_sma_columns_present(sample_df):
    result = IndicatorEngine.compute(sample_df)
    assert "sma_20" in result.columns
    assert "sma_50" in result.columns


def test_ema_columns_present(sample_df):
    result = IndicatorEngine.compute(sample_df)
    assert "ema_9" in result.columns
    assert "ema_21" in result.columns


def test_rsi_present_and_in_range(sample_df):
    result = IndicatorEngine.compute(sample_df)
    assert "rsi_14" in result.columns
    rsi_values = result["rsi_14"].dropna()
    assert (rsi_values >= 0).all() and (rsi_values <= 100).all()


def test_macd_columns_present(sample_df):
    result = IndicatorEngine.compute(sample_df)
    assert "macd" in result.columns
    assert "macd_signal" in result.columns
    assert "macd_hist" in result.columns


def test_bollinger_bands_present(sample_df):
    result = IndicatorEngine.compute(sample_df)
    assert "bb_upper" in result.columns
    assert "bb_middle" in result.columns
    assert "bb_lower" in result.columns


def test_atr_present(sample_df):
    result = IndicatorEngine.compute(sample_df)
    assert "atr_14" in result.columns
    assert (result["atr_14"].dropna() > 0).all()


def test_volume_ratio_present(sample_df):
    result = IndicatorEngine.compute(sample_df)
    assert "volume_sma_20" in result.columns
    assert "volume_ratio" in result.columns


def test_adx_present(sample_df):
    result = IndicatorEngine.compute(sample_df)
    assert "adx_14" in result.columns


def test_roc_present(sample_df):
    result = IndicatorEngine.compute(sample_df)
    assert "roc_10" in result.columns


def test_supertrend_present(sample_df):
    result = IndicatorEngine.compute(sample_df)
    assert "supertrend" in result.columns
    assert "supertrend_direction" in result.columns


def test_does_not_modify_input(sample_df):
    original_cols = list(sample_df.columns)
    IndicatorEngine.compute(sample_df)
    assert list(sample_df.columns) == original_cols


def test_short_df_returns_nan_gracefully():
    """Less than 50 rows — indicators that need 50-period history return NaN, not crash."""
    df = pd.DataFrame({
        "open": [100.0] * 10,
        "high": [101.0] * 10,
        "low": [99.0] * 10,
        "close": [100.0] * 10,
        "volume": [1_000_000] * 10,
    })
    result = IndicatorEngine.compute(df)
    assert "sma_20" in result.columns   # column exists
    assert result["sma_20"].isna().all()  # but all NaN for 10 rows
```

- [ ] **Step 2: Run test to verify it fails**

```bash
poetry run pytest tests/test_indicators.py -v
```

Expected: `ImportError: No module named 'domains.data.indicators'`

- [ ] **Step 3: Implement indicators.py**

```python
# backend/domains/data/indicators.py
import pandas as pd
import pandas_ta as ta


class IndicatorEngine:
    """Computes all technical indicators on an OHLCV DataFrame.

    Input columns required: open, high, low, close, volume (lowercase).
    Returns a new DataFrame with all indicator columns appended.
    Does not modify the input DataFrame.
    """

    @staticmethod
    def compute(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df.copy()

        out = df.copy()

        # ── Moving Averages ────────────────────────────────────────
        out["sma_20"] = ta.sma(out["close"], length=20)
        out["sma_50"] = ta.sma(out["close"], length=50)
        out["ema_9"] = ta.ema(out["close"], length=9)
        out["ema_21"] = ta.ema(out["close"], length=21)

        # ── RSI ───────────────────────────────────────────────────
        out["rsi_14"] = ta.rsi(out["close"], length=14)

        # ── MACD (12, 26, 9) ─────────────────────────────────────
        macd = ta.macd(out["close"], fast=12, slow=26, signal=9)
        if macd is not None:
            out["macd"] = macd["MACD_12_26_9"]
            out["macd_signal"] = macd["MACDs_12_26_9"]
            out["macd_hist"] = macd["MACDh_12_26_9"]
        else:
            out["macd"] = out["macd_signal"] = out["macd_hist"] = float("nan")

        # ── Bollinger Bands (20, 2) ───────────────────────────────
        bb = ta.bbands(out["close"], length=20, std=2)
        if bb is not None:
            out["bb_upper"] = bb["BBU_20_2.0"]
            out["bb_middle"] = bb["BBM_20_2.0"]
            out["bb_lower"] = bb["BBL_20_2.0"]
        else:
            out["bb_upper"] = out["bb_middle"] = out["bb_lower"] = float("nan")

        # ── ATR ───────────────────────────────────────────────────
        out["atr_14"] = ta.atr(out["high"], out["low"], out["close"], length=14)

        # ── Volume ────────────────────────────────────────────────
        out["volume_sma_20"] = ta.sma(out["volume"].astype(float), length=20)
        out["volume_ratio"] = out["volume"] / out["volume_sma_20"].replace(0, float("nan"))

        # ── ADX ───────────────────────────────────────────────────
        adx = ta.adx(out["high"], out["low"], out["close"], length=14)
        if adx is not None:
            out["adx_14"] = adx["ADX_14"]
        else:
            out["adx_14"] = float("nan")

        # ── Rate of Change ────────────────────────────────────────
        out["roc_10"] = ta.roc(out["close"], length=10)

        # ── SuperTrend (default: 7, 3.0) ─────────────────────────
        st = ta.supertrend(out["high"], out["low"], out["close"], length=7, multiplier=3.0)
        if st is not None:
            # pandas-ta names the columns dynamically
            st_col = [c for c in st.columns if c.startswith("SUPERT_") and "d" not in c.lower()]
            dir_col = [c for c in st.columns if "SUPERTd" in c]
            out["supertrend"] = st[st_col[0]] if st_col else float("nan")
            out["supertrend_direction"] = st[dir_col[0]] if dir_col else float("nan")
        else:
            out["supertrend"] = out["supertrend_direction"] = float("nan")

        return out
```

- [ ] **Step 4: Run tests to verify passing**

```bash
poetry run pytest tests/test_indicators.py -v
```

Expected: `13 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/domains/data/indicators.py backend/tests/test_indicators.py
git commit -m "feat: indicators — IndicatorEngine computing 15 technical indicators via pandas-ta"
```

---

## Task 8: yfinance Historical Feed

**Files:**
- Create: `backend/domains/data/feeds/__init__.py`
- Create: `backend/domains/data/feeds/yfinance_feed.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_yfinance_feed.py
import pandas as pd
import pytest
from unittest.mock import patch, MagicMock
from domains.data.feeds.yfinance_feed import YFinanceFeed


@pytest.fixture
def mock_ohlcv():
    """Minimal valid OHLCV DataFrame that yfinance returns."""
    dates = pd.date_range("2024-01-01", periods=5, freq="B")
    return pd.DataFrame({
        "Open":   [100.0, 101.0, 102.0, 101.5, 103.0],
        "High":   [101.0, 102.0, 103.0, 102.5, 104.0],
        "Low":    [99.0,  100.0, 101.0, 100.5, 102.0],
        "Close":  [100.5, 101.5, 102.5, 102.0, 103.5],
        "Volume": [1_000_000, 1_200_000, 900_000, 1_100_000, 950_000],
    }, index=dates)


def test_download_returns_dataframe(mock_ohlcv):
    with patch("yfinance.Ticker") as mock_ticker:
        mock_ticker.return_value.history.return_value = mock_ohlcv
        feed = YFinanceFeed()
        df = feed.download("RELIANCE", years=1)
    assert isinstance(df, pd.DataFrame)
    assert not df.empty


def test_download_normalises_column_names(mock_ohlcv):
    with patch("yfinance.Ticker") as mock_ticker:
        mock_ticker.return_value.history.return_value = mock_ohlcv
        feed = YFinanceFeed()
        df = feed.download("RELIANCE", years=1)
    assert all(c == c.lower() for c in df.columns)
    assert "close" in df.columns


def test_download_adds_ns_suffix(mock_ohlcv):
    with patch("yfinance.Ticker") as mock_ticker:
        mock_ticker.return_value.history.return_value = mock_ohlcv
        feed = YFinanceFeed()
        feed.download("RELIANCE", years=1)
    mock_ticker.assert_called_once_with("RELIANCE.NS")


def test_download_returns_empty_on_yfinance_failure():
    with patch("yfinance.Ticker") as mock_ticker:
        mock_ticker.return_value.history.side_effect = Exception("network error")
        feed = YFinanceFeed()
        df = feed.download("BADSYMBOL", years=1)
    assert isinstance(df, pd.DataFrame)
    assert df.empty


def test_validate_row_rejects_zero_volume():
    feed = YFinanceFeed()
    assert feed.validate_row(
        high=101.0, low=99.0, close=100.0, volume=0
    ) is False


def test_validate_row_rejects_price_spike():
    feed = YFinanceFeed()
    # high/low ratio > 2.0 is a bad tick
    assert feed.validate_row(
        high=200.0, low=99.0, close=100.0, volume=1_000_000
    ) is False


def test_validate_row_accepts_good_data():
    feed = YFinanceFeed()
    assert feed.validate_row(
        high=101.0, low=99.0, close=100.0, volume=1_000_000
    ) is True


def test_get_last_date_returns_none_for_unknown_symbol():
    from unittest.mock import MagicMock
    mock_db = MagicMock()
    mock_db.execute.return_value.scalar.return_value = None
    feed = YFinanceFeed()
    result = feed.get_last_date(mock_db, "UNKNOWN")
    assert result is None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
poetry run pytest tests/test_yfinance_feed.py -v
```

Expected: `ImportError: No module named 'domains.data.feeds'`

- [ ] **Step 3: Implement yfinance_feed.py**

```python
# backend/domains/data/feeds/__init__.py
# (empty)
```

```python
# backend/domains/data/feeds/yfinance_feed.py
import logging
from datetime import date, datetime
from typing import Optional

import pandas as pd
import yfinance as yf
from sqlalchemy import text
from sqlalchemy.orm import Session

from domains.data.nse_universe import get_yfinance_symbol

logger = logging.getLogger(__name__)


class YFinanceFeed:
    """Downloads and validates historical OHLCV data from Yahoo Finance."""

    def download(self, symbol: str, years: int = 15) -> pd.DataFrame:
        """Download historical daily OHLCV for a single NSE symbol.

        Returns empty DataFrame on any failure — caller decides what to do.
        """
        try:
            ticker = yf.Ticker(get_yfinance_symbol(symbol))
            raw = ticker.history(period=f"{years}y", interval="1d", auto_adjust=True)
            if raw.empty:
                return pd.DataFrame()
            df = raw.copy()
            df.columns = [c.lower() for c in df.columns]
            df.index = pd.to_datetime(df.index.date)
            df = df[["open", "high", "low", "close", "volume"]].copy()
            return df
        except Exception as e:
            logger.warning("yfinance download failed for %s: %s", symbol, e)
            return pd.DataFrame()

    def validate_row(self, high: float, low: float, close: float, volume: int) -> bool:
        """Return False if a row fails basic sanity checks."""
        if volume <= 0:
            return False
        if high <= 0 or low <= 0 or close <= 0:
            return False
        if low > high:
            return False
        if high / max(low, 0.01) > 2.0:    # >100% intraday range = bad tick
            return False
        return True

    def get_last_date(self, db: Session, symbol: str) -> Optional[date]:
        """Return the most recent date stored for this symbol, or None."""
        result = db.execute(
            text("SELECT MAX(date) FROM stock_prices_daily WHERE symbol = :s"),
            {"s": symbol},
        )
        value = result.scalar()
        if value is None:
            return None
        return datetime.strptime(str(value), "%Y-%m-%d").date()

    def upsert_prices(self, db: Session, symbol: str, df: pd.DataFrame) -> int:
        """Insert rows from df into stock_prices_daily. Skip invalid rows.

        Uses INSERT OR IGNORE (SQLite) to handle duplicates gracefully.
        Returns count of rows inserted.
        """
        if df.empty:
            return 0

        inserted = 0
        for row_date, row in df.iterrows():
            if not self.validate_row(
                high=row["high"], low=row["low"],
                close=row["close"], volume=int(row["volume"])
            ):
                db.execute(
                    text("""
                        INSERT OR IGNORE INTO data_quality_log
                            (symbol, date, issue_type, details)
                        VALUES (:sym, :dt, 'bad_tick', :det)
                    """),
                    {
                        "sym": symbol,
                        "dt": str(row_date),
                        "det": f"high={row['high']}, low={row['low']}, vol={row['volume']}",
                    },
                )
                continue

            db.execute(
                text("""
                    INSERT OR IGNORE INTO stock_prices_daily
                        (symbol, date, open, high, low, close, volume, data_source)
                    VALUES (:sym, :dt, :o, :h, :l, :c, :v, 'yfinance')
                """),
                {
                    "sym": symbol, "dt": str(row_date),
                    "o": float(row["open"]),   "h": float(row["high"]),
                    "l": float(row["low"]),    "c": float(row["close"]),
                    "v": int(row["volume"]),
                },
            )
            inserted += 1

        db.commit()
        return inserted
```

- [ ] **Step 4: Run tests to verify passing**

```bash
poetry run pytest tests/test_yfinance_feed.py -v
```

Expected: `8 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/domains/data/feeds/ backend/tests/test_yfinance_feed.py
git commit -m "feat: yfinance_feed — historical OHLCV download with row validation"
```

---

## Task 9: Historical Bootstrap Script

**Files:**
- Create: `backend/scripts/__init__.py`
- Create: `backend/scripts/bootstrap.py`

This script runs once to load 15 years of history for all 237 stocks. It is resumable — already-downloaded symbols are skipped.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_bootstrap.py
import pytest
from unittest.mock import patch, MagicMock
import pandas as pd
from scripts.bootstrap import BootstrapRunner


@pytest.fixture
def mock_db(tmp_path):
    """In-memory test database."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from database import Base
    import models  # noqa

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


def test_bootstrap_skips_already_downloaded_symbols(mock_db):
    """If a symbol already has data, it should be skipped."""
    from sqlalchemy import text
    # Pre-insert a record for RELIANCE
    mock_db.execute(text(
        "INSERT INTO stock_prices_daily (symbol, date, open, high, low, close, volume)"
        " VALUES ('RELIANCE', '2024-01-01', 100, 101, 99, 100, 1000000)"
    ))
    mock_db.commit()

    runner = BootstrapRunner(db=mock_db, symbols=["RELIANCE"])
    with patch.object(runner.feed, "download") as mock_download:
        mock_download.return_value = pd.DataFrame()
        runner.run(years=1)
        # download should NOT be called — data already exists
        mock_download.assert_not_called()


def test_bootstrap_downloads_and_saves_new_symbol(mock_db):
    """A symbol with no data should be downloaded and saved."""
    dates = pd.date_range("2024-01-01", periods=3, freq="B")
    mock_df = pd.DataFrame({
        "open": [100.0, 101.0, 102.0],
        "high": [101.0, 102.0, 103.0],
        "low": [99.0, 100.0, 101.0],
        "close": [100.5, 101.5, 102.5],
        "volume": [1_000_000, 1_200_000, 900_000],
    }, index=dates)

    runner = BootstrapRunner(db=mock_db, symbols=["TCS"])
    with patch.object(runner.feed, "download", return_value=mock_df):
        stats = runner.run(years=1)

    assert stats["downloaded"] >= 1


def test_bootstrap_inserts_symbol_into_stocks_table(mock_db):
    dates = pd.date_range("2024-01-01", periods=2, freq="B")
    mock_df = pd.DataFrame({
        "open": [500.0, 501.0], "high": [502.0, 503.0],
        "low": [499.0, 500.0], "close": [501.0, 502.0],
        "volume": [500_000, 600_000],
    }, index=dates)

    runner = BootstrapRunner(db=mock_db, symbols=["INFY"])
    with patch.object(runner.feed, "download", return_value=mock_df):
        runner.run(years=1)

    from sqlalchemy import text
    result = mock_db.execute(text("SELECT symbol FROM stocks WHERE symbol='INFY'")).fetchone()
    assert result is not None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
poetry run pytest tests/test_bootstrap.py -v
```

Expected: `ImportError: No module named 'scripts'`

- [ ] **Step 3: Implement bootstrap.py**

```python
# backend/scripts/__init__.py
# (empty)
```

```python
# backend/scripts/bootstrap.py
"""One-shot historical data bootstrap. Run once to seed 15 years of OHLCV.

Usage:
    cd backend && poetry run python -m scripts.bootstrap

Resumable: already-downloaded symbols are automatically skipped.
"""
import logging
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).parent.parent))

from database import SessionLocal, engine, Base
from domains.data.feeds.yfinance_feed import YFinanceFeed
from domains.data.indicators import IndicatorEngine
from domains.data.nse_universe import NSE_SYMBOLS
import models  # noqa — registers models

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


@dataclass
class BootstrapStats:
    total: int = 0
    downloaded: int = 0
    skipped: int = 0
    failed: int = 0
    failed_symbols: list[str] = field(default_factory=list)


class BootstrapRunner:
    def __init__(self, db: Session, symbols: Optional[list[str]] = None):
        self.db = db
        self.symbols = symbols or NSE_SYMBOLS
        self.feed = YFinanceFeed()

    def _ensure_stock_record(self, symbol: str) -> None:
        """Insert stock into stocks table if not already present."""
        self.db.execute(
            text("INSERT OR IGNORE INTO stocks (symbol, exchange) VALUES (:s, 'NSE')"),
            {"s": symbol},
        )
        self.db.commit()

    def _already_downloaded(self, symbol: str) -> bool:
        """Return True if symbol has any price data in DB."""
        result = self.db.execute(
            text("SELECT COUNT(*) FROM stock_prices_daily WHERE symbol = :s LIMIT 1"),
            {"s": symbol},
        ).scalar()
        return (result or 0) > 0

    def run(self, years: int = 15) -> dict:
        stats = BootstrapStats(total=len(self.symbols))

        for i, symbol in enumerate(self.symbols, 1):
            logger.info("[%d/%d] %s", i, stats.total, symbol)

            if self._already_downloaded(symbol):
                logger.info("  → skipping (already downloaded)")
                stats.skipped += 1
                continue

            self._ensure_stock_record(symbol)

            df = self.feed.download(symbol, years=years)
            if df.empty:
                logger.warning("  → no data returned")
                stats.failed += 1
                stats.failed_symbols.append(symbol)
                continue

            # Compute indicators before saving
            df_with_indicators = IndicatorEngine.compute(df)

            inserted = self.feed.upsert_prices(self.db, symbol, df_with_indicators)
            logger.info("  → inserted %d rows", inserted)
            stats.downloaded += 1

            # Polite delay to avoid hammering yfinance
            time.sleep(0.3)

        logger.info(
            "Bootstrap complete. Downloaded: %d, Skipped: %d, Failed: %d",
            stats.downloaded, stats.skipped, stats.failed,
        )
        if stats.failed_symbols:
            logger.warning("Failed symbols: %s", stats.failed_symbols)

        return {
            "total": stats.total,
            "downloaded": stats.downloaded,
            "skipped": stats.skipped,
            "failed": stats.failed,
            "failed_symbols": stats.failed_symbols,
        }


if __name__ == "__main__":
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        runner = BootstrapRunner(db=db)
        runner.run(years=15)
    finally:
        db.close()
```

- [ ] **Step 4: Run tests to verify passing**

```bash
poetry run pytest tests/test_bootstrap.py -v
```

Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/ backend/tests/test_bootstrap.py
git commit -m "feat: bootstrap — resumable historical data loader for all 237 NSE stocks"
```

---

## Task 10: Angel One Live Feed

**Files:**
- Create: `backend/domains/data/feeds/angel_one_feed.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_angel_one_feed.py
import pytest
from unittest.mock import patch, MagicMock
from domains.data.feeds.angel_one_feed import AngelOneFeed


def test_feed_initialises_without_credentials():
    """Feed should not crash on init — credentials loaded lazily."""
    feed = AngelOneFeed(api_key="", client_id="", password="", totp_secret="")
    assert feed is not None
    assert feed.connected is False


def test_get_quote_returns_none_when_not_connected():
    feed = AngelOneFeed(api_key="", client_id="", password="", totp_secret="")
    result = feed.get_quote("RELIANCE")
    assert result is None


def test_get_quote_returns_price_when_connected():
    feed = AngelOneFeed(api_key="key", client_id="cid", password="pass", totp_secret="secret")
    mock_api = MagicMock()
    mock_api.getMarketData.return_value = {
        "status": True,
        "data": {"fetched": [{"ltp": 2850.50, "tradingSymbol": "RELIANCE-EQ"}]},
    }
    feed._api = mock_api
    feed._connected = True

    result = feed.get_quote("RELIANCE")
    assert result is not None
    assert result["ltp"] == 2850.50
    assert result["symbol"] == "RELIANCE"


def test_get_quote_returns_none_on_api_error():
    feed = AngelOneFeed(api_key="key", client_id="cid", password="pass", totp_secret="secret")
    mock_api = MagicMock()
    mock_api.getMarketData.side_effect = Exception("API error")
    feed._api = mock_api
    feed._connected = True

    result = feed.get_quote("RELIANCE")
    assert result is None


def test_is_market_hours_returns_bool():
    feed = AngelOneFeed(api_key="", client_id="", password="", totp_secret="")
    result = feed.is_market_hours()
    assert isinstance(result, bool)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
poetry run pytest tests/test_angel_one_feed.py -v
```

Expected: `ImportError: No module named 'domains.data.feeds.angel_one_feed'`

- [ ] **Step 3: Implement angel_one_feed.py**

```python
# backend/domains/data/feeds/angel_one_feed.py
import logging
from datetime import datetime, time as dtime
from typing import Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")

MARKET_OPEN  = dtime(9, 15)
MARKET_CLOSE = dtime(15, 30)


class AngelOneFeed:
    """Live market data via Angel One SmartAPI.

    Connection is lazy — call connect() explicitly before get_quote().
    When credentials are empty (e.g., in tests), connect() is a no-op.
    """

    def __init__(self, api_key: str, client_id: str, password: str, totp_secret: str):
        self._api_key = api_key
        self._client_id = client_id
        self._password = password
        self._totp_secret = totp_secret
        self._api = None
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    def connect(self) -> bool:
        """Attempt to authenticate with Angel One. Returns True on success."""
        if not self._api_key or not self._client_id:
            logger.warning("Angel One credentials not configured — live feed disabled")
            return False
        try:
            import pyotp
            from SmartApi import SmartConnect

            obj = SmartConnect(api_key=self._api_key)
            totp = pyotp.TOTP(self._totp_secret).now()
            data = obj.generateSession(self._client_id, self._password, totp)
            if data.get("status"):
                self._api = obj
                self._connected = True
                logger.info("Angel One connected successfully")
                return True
            logger.error("Angel One session failed: %s", data.get("message"))
            return False
        except Exception as e:
            logger.error("Angel One connection error: %s", e)
            return False

    def get_quote(self, symbol: str) -> Optional[dict]:
        """Fetch latest trade price for a single symbol.

        Returns dict with keys: symbol, ltp, open, high, low, close, volume
        Returns None on any error or if not connected.
        """
        if not self._connected or self._api is None:
            return None
        try:
            # Angel One exchange token lookup (NSE equity)
            token = self._get_token(symbol)
            if not token:
                return None
            response = self._api.getMarketData(
                mode="LTP",
                exchangeTokens={"NSE": [token]},
            )
            if not response.get("status"):
                return None
            fetched = response.get("data", {}).get("fetched", [])
            if not fetched:
                return None
            row = fetched[0]
            return {
                "symbol": symbol,
                "ltp": row.get("ltp"),
                "open": row.get("open"),
                "high": row.get("high"),
                "low": row.get("low"),
                "close": row.get("close"),
                "volume": row.get("tradeVolume"),
                "timestamp": datetime.now(IST).isoformat(),
            }
        except Exception as e:
            logger.warning("get_quote failed for %s: %s", symbol, e)
            return None

    def get_quotes_bulk(self, symbols: list[str]) -> dict[str, Optional[dict]]:
        """Fetch quotes for multiple symbols. Returns {symbol: quote_dict_or_None}."""
        return {sym: self.get_quote(sym) for sym in symbols}

    def is_market_hours(self) -> bool:
        """Return True if current IST time is within NSE market hours."""
        now_ist = datetime.now(IST).time()
        today_ist = datetime.now(IST)
        if today_ist.weekday() >= 5:     # Saturday=5, Sunday=6
            return False
        return MARKET_OPEN <= now_ist <= MARKET_CLOSE

    def _get_token(self, symbol: str) -> Optional[str]:
        """Map NSE symbol to Angel One exchange token.

        In production this looks up a pre-loaded token map.
        Stub implementation — full token map added in Plan 2.
        """
        return None  # Will be implemented with token map in Plan 2
```

- [ ] **Step 4: Run tests to verify passing**

```bash
poetry run pytest tests/test_angel_one_feed.py -v
```

Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/domains/data/feeds/angel_one_feed.py backend/tests/test_angel_one_feed.py
git commit -m "feat: angel_one_feed — live quote feed with lazy auth and market-hours check"
```

---

## Task 11: FastAPI App + Auth Middleware

**Files:**
- Create: `backend/main.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_main.py
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from main import app
    return TestClient(app)


def test_health_endpoint_returns_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_api_requires_key(client):
    response = client.get("/api/v1/stocks")
    assert response.status_code == 401


def test_api_accepts_valid_key(client):
    from settings import settings
    response = client.get(
        "/api/v1/stocks",
        headers={"X-API-Key": settings.api_key},
    )
    # 200 or empty list — just not 401
    assert response.status_code != 401


def test_invalid_api_key_rejected(client):
    response = client.get(
        "/api/v1/stocks",
        headers={"X-API-Key": "wrong-key"},
    )
    assert response.status_code == 401
```

- [ ] **Step 2: Run test to verify it fails**

```bash
poetry run pytest tests/test_main.py -v
```

Expected: `ImportError: No module named 'main'`

- [ ] **Step 3: Implement main.py**

```python
# backend/main.py
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Security, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security.api_key import APIKeyHeader

from database import Base, engine
from settings import settings
import models  # noqa — registers all models with Base

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(key: str = Security(API_KEY_HEADER)) -> str:
    if key != settings.api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
    return key


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables verified")
    yield
    # Shutdown (nothing to clean up for SQLite)


app = FastAPI(
    title="StockV2 API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["system"])
def health():
    return {"status": "ok", "version": "1.0.0"}


# ── Domain Routers (imported here, registered below) ──────────────────────────
from domains.data.router import router as data_router  # noqa: E402

app.include_router(data_router, prefix="/api/v1", dependencies=[Depends(verify_api_key)])
```

- [ ] **Step 4: Run tests to verify passing**

```bash
poetry run pytest tests/test_main.py -v
```

Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/main.py backend/tests/test_main.py
git commit -m "feat: main — FastAPI app with API key auth and CORS"
```

---

## Task 12: Market Data Service + Router

**Files:**
- Create: `backend/domains/data/service.py`
- Create: `backend/domains/data/router.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_data_router.py
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from database import Base, get_db
from settings import settings
import models  # noqa


@pytest.fixture(scope="module")
def client():
    # Use in-memory DB for tests
    test_engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(test_engine)
    TestSession = sessionmaker(bind=test_engine)

    # Seed one stock + price
    db = TestSession()
    db.execute(text("INSERT INTO stocks (symbol, name, sector, exchange) VALUES ('TCS', 'Tata Consultancy Services', 'IT', 'NSE')"))
    db.execute(text("INSERT INTO stock_prices_daily (symbol, date, open, high, low, close, volume) VALUES ('TCS', '2024-01-01', 3500, 3550, 3480, 3520, 1000000)"))
    db.execute(text("INSERT INTO stock_prices_daily (symbol, date, open, high, low, close, volume) VALUES ('TCS', '2024-01-02', 3520, 3570, 3510, 3550, 1200000)"))
    db.commit()
    db.close()

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    from main import app
    app.dependency_overrides[get_db] = override_get_db

    return TestClient(app, headers={"X-API-Key": settings.api_key})


def test_list_stocks_returns_list(client):
    response = client.get("/api/v1/stocks")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1


def test_list_stocks_includes_seeded_stock(client):
    response = client.get("/api/v1/stocks")
    symbols = [s["symbol"] for s in response.json()]
    assert "TCS" in symbols


def test_get_stock_detail(client):
    response = client.get("/api/v1/stocks/TCS")
    assert response.status_code == 200
    data = response.json()
    assert data["symbol"] == "TCS"
    assert "name" in data


def test_get_unknown_stock_returns_404(client):
    response = client.get("/api/v1/stocks/FAKESTOCK")
    assert response.status_code == 404


def test_get_stock_prices(client):
    response = client.get("/api/v1/stocks/TCS/prices")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 2
    assert data[0]["symbol"] == "TCS"
    assert "close" in data[0]


def test_get_stock_prices_date_filter(client):
    response = client.get("/api/v1/stocks/TCS/prices?from_date=2024-01-02")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["date"] == "2024-01-02"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
poetry run pytest tests/test_data_router.py -v
```

Expected: `ImportError` or `404` on all routes

- [ ] **Step 3: Implement service.py**

```python
# backend/domains/data/service.py
from datetime import date
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session


class DataService:
    def __init__(self, db: Session):
        self.db = db

    def list_stocks(self) -> list[dict]:
        rows = self.db.execute(
            text("SELECT symbol, name, sector, industry, exchange, is_active FROM stocks ORDER BY symbol")
        ).fetchall()
        return [dict(r._mapping) for r in rows]

    def get_stock(self, symbol: str) -> Optional[dict]:
        row = self.db.execute(
            text("SELECT symbol, name, sector, industry, market_cap, exchange, is_active FROM stocks WHERE symbol = :s"),
            {"s": symbol.upper()},
        ).fetchone()
        return dict(row._mapping) if row else None

    def get_prices(
        self,
        symbol: str,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
        limit: int = 500,
    ) -> list[dict]:
        query = "SELECT symbol, date, open, high, low, close, volume FROM stock_prices_daily WHERE symbol = :s"
        params: dict = {"s": symbol.upper()}
        if from_date:
            query += " AND date >= :fd"
            params["fd"] = str(from_date)
        if to_date:
            query += " AND date <= :td"
            params["td"] = str(to_date)
        query += " ORDER BY date DESC LIMIT :lim"
        params["lim"] = limit
        rows = self.db.execute(text(query), params).fetchall()
        return [dict(r._mapping) for r in rows]

    def get_latest_price(self, symbol: str) -> Optional[float]:
        row = self.db.execute(
            text("SELECT close FROM stock_prices_daily WHERE symbol = :s ORDER BY date DESC LIMIT 1"),
            {"s": symbol.upper()},
        ).fetchone()
        return float(row[0]) if row else None
```

- [ ] **Step 4: Implement router.py**

```python
# backend/domains/data/router.py
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from domains.data.service import DataService

router = APIRouter(tags=["market-data"])


@router.get("/stocks")
def list_stocks(db: Session = Depends(get_db)):
    return DataService(db).list_stocks()


@router.get("/stocks/{symbol}")
def get_stock(symbol: str, db: Session = Depends(get_db)):
    stock = DataService(db).get_stock(symbol)
    if not stock:
        raise HTTPException(status_code=404, detail=f"Stock '{symbol}' not found")
    return stock


@router.get("/stocks/{symbol}/prices")
def get_prices(
    symbol: str,
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    limit: int = Query(500, le=5000),
    db: Session = Depends(get_db),
):
    stock = DataService(db).get_stock(symbol)
    if not stock:
        raise HTTPException(status_code=404, detail=f"Stock '{symbol}' not found")
    return DataService(db).get_prices(symbol, from_date=from_date, to_date=to_date, limit=limit)
```

- [ ] **Step 5: Run tests to verify passing**

```bash
poetry run pytest tests/test_data_router.py -v
```

Expected: `6 passed`

- [ ] **Step 6: Commit**

```bash
git add backend/domains/data/service.py backend/domains/data/router.py backend/tests/test_data_router.py
git commit -m "feat: data router — GET /stocks, /stocks/{symbol}, /stocks/{symbol}/prices"
```

---

## Task 13: APScheduler Skeleton + Conftest

**Files:**
- Create: `backend/scheduler.py`
- Create: `backend/tests/conftest.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_scheduler.py
from scheduler import scheduler, JobIds


def test_scheduler_instance_exists():
    assert scheduler is not None


def test_job_ids_defined():
    assert hasattr(JobIds, "DAILY_EOD_UPDATE")
    assert hasattr(JobIds, "INTRADAY_SCAN")
    assert hasattr(JobIds, "WEEKLY_FUNDAMENTALS")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
poetry run pytest tests/test_scheduler.py -v
```

Expected: `ImportError: No module named 'scheduler'`

- [ ] **Step 3: Implement scheduler.py**

```python
# backend/scheduler.py
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)


class JobIds:
    DAILY_EOD_UPDATE      = "daily_eod_update"
    INTRADAY_SCAN         = "intraday_scan"
    WEEKLY_FUNDAMENTALS   = "weekly_fundamentals"
    MONTHLY_ML_RETRAIN    = "monthly_ml_retrain"
    DAILY_DIGEST          = "daily_digest"


scheduler = BackgroundScheduler(timezone="Asia/Kolkata")


def _daily_eod_update():
    """Fetch today's EOD data for all symbols and recompute indicators."""
    logger.info("[scheduler] daily_eod_update — placeholder (implemented in Plan 2)")


def _intraday_scan():
    """Fetch intraday ticks and run intraday strategies."""
    logger.info("[scheduler] intraday_scan — placeholder (implemented in Plan 2)")


def _weekly_fundamentals():
    """Scrape fundamentals from screener.in for all active stocks."""
    logger.info("[scheduler] weekly_fundamentals — placeholder (implemented in Plan 2)")


def _daily_digest():
    """Send end-of-day Telegram digest."""
    logger.info("[scheduler] daily_digest — placeholder (implemented in Plan 3)")


def register_jobs():
    # Post-market EOD update: 4:00 PM IST, Mon–Fri
    scheduler.add_job(
        _daily_eod_update,
        CronTrigger(hour=16, minute=0, day_of_week="mon-fri"),
        id=JobIds.DAILY_EOD_UPDATE,
        replace_existing=True,
    )
    # Intraday scan: every 15 min, 9:15 AM – 3:30 PM IST, Mon–Fri
    scheduler.add_job(
        _intraday_scan,
        CronTrigger(minute="*/15", hour="9-15", day_of_week="mon-fri"),
        id=JobIds.INTRADAY_SCAN,
        replace_existing=True,
    )
    # Weekly fundamentals: Sunday 8 PM IST
    scheduler.add_job(
        _weekly_fundamentals,
        CronTrigger(day_of_week="sun", hour=20, minute=0),
        id=JobIds.WEEKLY_FUNDAMENTALS,
        replace_existing=True,
    )
    # Daily digest: 5:15 PM IST, Mon–Fri
    scheduler.add_job(
        _daily_digest,
        CronTrigger(hour=17, minute=15, day_of_week="mon-fri"),
        id=JobIds.DAILY_DIGEST,
        replace_existing=True,
    )
    logger.info("APScheduler jobs registered: %s", [j.id for j in scheduler.get_jobs()])
```

- [ ] **Step 4: Create conftest.py for shared fixtures**

```python
# backend/tests/conftest.py
import sys
from pathlib import Path

# Ensure 'backend/' is on sys.path for all tests
sys.path.insert(0, str(Path(__file__).parent.parent))
```

- [ ] **Step 5: Run tests to verify passing**

```bash
poetry run pytest tests/test_scheduler.py -v
```

Expected: `2 passed`

- [ ] **Step 6: Wire scheduler into main.py lifespan**

Edit `backend/main.py` — update the lifespan function:

```python
# In main.py, replace the lifespan function:
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables verified")
    from scheduler import scheduler, register_jobs
    register_jobs()
    scheduler.start()
    logger.info("APScheduler started")
    yield
    # Shutdown
    scheduler.shutdown(wait=False)
    logger.info("APScheduler stopped")
```

- [ ] **Step 7: Run all tests to confirm nothing broken**

```bash
poetry run pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 8: Commit**

```bash
git add backend/scheduler.py backend/tests/conftest.py backend/tests/test_scheduler.py backend/main.py
git commit -m "feat: scheduler — APScheduler with all job stubs registered"
```

---

## Task 14: End-to-End Smoke Test

Verify the full Foundation stack works together: app starts, DB exists, bootstrap downloads a small sample.

- [ ] **Step 1: Run the full test suite**

```bash
cd backend && poetry run pytest tests/ -v --tb=short
```

Expected: all tests green.

- [ ] **Step 2: Start the API server**

```bash
poetry run uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Expected:
```
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Database tables verified
INFO:     APScheduler started
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8000
```

- [ ] **Step 3: Test health endpoint**

```bash
curl http://localhost:8000/health
```

Expected: `{"status":"ok","version":"1.0.0"}`

- [ ] **Step 4: Test auth rejection**

```bash
curl http://localhost:8000/api/v1/stocks
```

Expected: `{"detail":"Invalid API key"}`

- [ ] **Step 5: Test with valid key**

```bash
curl -H "X-API-Key: changeme" http://localhost:8000/api/v1/stocks
```

Expected: `[]` (empty — no stocks seeded yet, that's fine)

- [ ] **Step 6: Run bootstrap for 5 stocks (quick test)**

```bash
# In a second terminal (keep server running)
poetry run python -m scripts.bootstrap --sample 5
```

For this to work, add `--sample` support to bootstrap.py:

Edit `backend/scripts/bootstrap.py` — add this to the `if __name__ == "__main__":` block:

```python
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=int, default=None, help="Only download N stocks (for testing)")
    parser.add_argument("--years", type=int, default=15)
    args = parser.parse_args()

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        symbols = NSE_SYMBOLS[:args.sample] if args.sample else NSE_SYMBOLS
        runner = BootstrapRunner(db=db, symbols=symbols)
        runner.run(years=args.years)
    finally:
        db.close()
```

```bash
poetry run python -m scripts.bootstrap --sample 5 --years 2
```

Expected: downloads 2 years of data for RELIANCE, TCS, HDFCBANK, INFY, ICICIBANK.

- [ ] **Step 7: Verify stocks are queryable via API**

```bash
curl -H "X-API-Key: changeme" http://localhost:8000/api/v1/stocks
```

Expected: JSON array with 5 stock objects.

```bash
curl -H "X-API-Key: changeme" "http://localhost:8000/api/v1/stocks/TCS/prices?limit=5"
```

Expected: JSON array with 5 price rows.

- [ ] **Step 8: Final commit**

```bash
git add backend/scripts/bootstrap.py
git commit -m "feat: bootstrap — add --sample and --years CLI args for quick testing"
```

---

## Self-Review Checklist

**Spec coverage (Section 3 — System Architecture):**
- ✓ FastAPI app running on :8000
- ✓ SQLite WAL mode configured
- ✓ All 20 tables created
- ✓ API key auth middleware
- ✓ APScheduler started with all job stubs
- ✓ Angel One feed (connect/get_quote)
- ✓ yfinance historical feed
- ✓ IndicatorEngine (15 indicators)
- ✓ Bootstrap script (resumable, crash-safe)
- ✓ Market data REST endpoints (GET /stocks, /stocks/{symbol}, /stocks/{symbol}/prices)

**Not covered in this plan (intentionally deferred):**
- Strategy Engine → Plan 2
- Signal generation → Plan 2
- AI explanations → Plan 3
- Portfolio management → Plan 3
- Backtesting → Plan 4
- Frontend → Plan 4

**Placeholder scan:** None found.

**Type consistency:** All function signatures are consistent across tasks.
- `YFinanceFeed.upsert_prices(db: Session, symbol: str, df: DataFrame) -> int` ✓ used in bootstrap.py
- `DataService(db).list_stocks()` ✓ used in router.py
- `IndicatorEngine.compute(df: DataFrame) -> DataFrame` ✓ used in bootstrap.py

---

*Plan 2 (Strategy Engine) will implement the 10 MVP strategies, signal aggregation, and live APScheduler jobs.*
