import logging
import threading
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Security, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security.api_key import APIKeyHeader
from sqlalchemy import text

from database import Base, engine, SessionLocal
from settings import settings
import models  # noqa

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(key: str = Security(API_KEY_HEADER)) -> str:
    if key != settings.api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
    return key


def _run_bootstrap() -> None:
    """Background thread: download 15 years of OHLCV for all NSE stocks (first-time setup)."""
    from scripts.bootstrap import BootstrapRunner
    db = SessionLocal()
    try:
        logger.info("[bootstrap] starting automatic historical data download")
        stats = BootstrapRunner(db=db).run(years=15)
        logger.info("[bootstrap] done — downloaded=%d skipped=%d failed=%d",
                    stats["downloaded"], stats["skipped"], stats["failed"])
    except Exception:
        logger.exception("[bootstrap] failed")
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables verified")

    # Phase F: safe migration — add dividend_yield to existing DBs
    with engine.connect() as _conn:
        try:
            _conn.execute(text("ALTER TABLE fundamentals ADD COLUMN dividend_yield REAL"))
            _conn.commit()
        except Exception:
            pass  # column already exists

    # Strategy Combination Engine tables
    try:
        with engine.connect() as _conn:
            _conn.execute(text("""
                CREATE TABLE IF NOT EXISTS strategy_combinations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    strategy_ids TEXT NOT NULL,
                    strategy_names TEXT NOT NULL,
                    size INTEGER NOT NULL,
                    search_method TEXT NOT NULL,
                    created_at DATETIME DEFAULT (datetime('now'))
                )
            """))
            _conn.execute(text("""
                CREATE UNIQUE INDEX IF NOT EXISTS uq_combination_ids
                ON strategy_combinations(strategy_ids)
            """))
            _conn.execute(text("""
                CREATE TABLE IF NOT EXISTS combination_run_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_at DATETIME NOT NULL,
                    completed_at DATETIME,
                    status TEXT NOT NULL DEFAULT 'running',
                    symbols_analyzed INTEGER,
                    candidates_selected INTEGER,
                    combinations_tested INTEGER,
                    top_combination_id INTEGER REFERENCES strategy_combinations(id),
                    error_message TEXT,
                    config_json TEXT
                )
            """))
            _conn.execute(text("""
                CREATE TABLE IF NOT EXISTS combination_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    combination_id INTEGER NOT NULL REFERENCES strategy_combinations(id),
                    run_id INTEGER NOT NULL REFERENCES combination_run_log(id),
                    train_cagr REAL, train_sharpe REAL, train_win_rate REAL,
                    train_max_drawdown REAL, train_profit_factor REAL,
                    train_total_trades INTEGER, train_sortino REAL,
                    val_cagr REAL, val_sharpe REAL, val_win_rate REAL,
                    val_max_drawdown REAL, val_total_trades INTEGER,
                    oos_cagr REAL, oos_sharpe REAL, oos_win_rate REAL,
                    oos_max_drawdown REAL, oos_profit_factor REAL,
                    oos_total_trades INTEGER, oos_sortino REAL, oos_median_return_pct REAL,
                    wf_consistency_score REAL, wf_avg_oos_cagr REAL,
                    vs_buy_and_hold_cagr REAL, vs_best_single_cagr REAL, vs_sma_crossover_cagr REAL,
                    reliability_score REAL, reliability_label TEXT, sensitivity_score REAL,
                    explanation_json TEXT,
                    computed_at DATETIME DEFAULT (datetime('now'))
                )
            """))
            _conn.execute(text("""
                CREATE TABLE IF NOT EXISTS combination_regime_perf (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    combination_id INTEGER NOT NULL REFERENCES strategy_combinations(id),
                    run_id INTEGER NOT NULL REFERENCES combination_run_log(id),
                    regime TEXT NOT NULL,
                    win_rate REAL, avg_pnl_pct REAL, trade_count INTEGER, cagr REAL
                )
            """))
            _conn.commit()
        logger.info("Strategy Combination Engine tables verified")
    except Exception as e:
        logger.warning("combination tables migration skipped: %s", e)

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

    from domains.strategies.seed import seed_strategies
    db = SessionLocal()
    try:
        seed_strategies(db)
    finally:
        db.close()

    # Auto-precompute: populate strategy_performance for any strategies missing it.
    # Runs in background so startup is not blocked. Unblocks combination analysis
    # and "Scan All Stocks" without requiring manual intervention after adding strategies.
    db_pc = SessionLocal()
    try:
        missing_ids = [
            r[0] for r in db_pc.execute(text("""
                SELECT id FROM strategies WHERE is_active = 1
                AND id NOT IN (SELECT DISTINCT strategy_id FROM strategy_performance)
            """)).fetchall()
        ]
    finally:
        db_pc.close()

    if missing_ids:
        logger.info(
            "[startup] %d strategies missing performance data — auto-precompute starting in background",
            len(missing_ids)
        )
        from domains.backtest.router import _run_precompute_bg
        threading.Thread(
            target=_run_precompute_bg, args=(missing_ids,),
            daemon=True, name="auto-precompute"
        ).start()

    # Auto-bootstrap: if no price data exists, download 15 years in the background
    db3 = SessionLocal()
    try:
        has_prices = db3.execute(text("SELECT 1 FROM stock_prices_daily LIMIT 1")).scalar()
    finally:
        db3.close()
    if not has_prices:
        logger.info("[startup] No price data found — auto-bootstrap starting in background (~20-60 min)")
        threading.Thread(target=_run_bootstrap, daemon=True, name="auto-bootstrap").start()

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

    from scheduler import scheduler, register_jobs
    register_jobs()
    scheduler.start()
    logger.info("APScheduler started")
    yield
    scheduler.shutdown(wait=False)
    logger.info("APScheduler stopped")


app = FastAPI(
    title="StockV2 API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["system"])
def health():
    return {"status": "ok", "version": "1.0.0"}


from domains.data.router import router as data_router  # noqa: E402

app.include_router(data_router, prefix="/api/v1", dependencies=[Depends(verify_api_key)])

from domains.strategies.router import router as strategies_router  # noqa: E402
app.include_router(strategies_router, prefix="/api/v1", dependencies=[Depends(verify_api_key)])

from domains.ai.router import router as ai_router  # noqa: E402
app.include_router(ai_router, prefix="/api/v1", dependencies=[Depends(verify_api_key)])

from domains.portfolio.router import router as portfolio_router  # noqa: E402
app.include_router(portfolio_router, prefix="/api/v1", dependencies=[Depends(verify_api_key)])

from domains.backtest.router import router as backtest_router  # noqa: E402
app.include_router(backtest_router, prefix="/api/v1", dependencies=[Depends(verify_api_key)])

from domains.market.router import router as market_router  # noqa: E402
app.include_router(market_router, prefix="/api/v1", dependencies=[Depends(verify_api_key)])

from domains.intelligence.router import router as intelligence_router  # noqa: E402
app.include_router(intelligence_router, prefix="/api/v1", dependencies=[Depends(verify_api_key)])

from domains.combinations.router import router as combinations_router  # noqa: E402
app.include_router(combinations_router, prefix="/api/v1", dependencies=[Depends(verify_api_key)])
