import logging
import threading
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Security, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security.api_key import APIKeyHeader
from sqlalchemy import text

from database import Base, engine, SessionLocal, get_db
from settings import settings
import models  # noqa
from sqlalchemy.orm import Session

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

    # Phase G: add to_date to strategy_performance for incremental skip logic
    with engine.connect() as _conn:
        try:
            _conn.execute(text("ALTER TABLE strategy_performance ADD COLUMN to_date DATE"))
            _conn.commit()
        except Exception:
            pass  # column already exists

    # Phase H: add unique constraint on strategy_signals (symbol, strategy_id, signal_date)
    # Required for ON CONFLICT upsert in StrategyEngine._save_signal
    with engine.connect() as _conn:
        try:
            _conn.execute(text("""
                ALTER TABLE strategy_signals
                ADD CONSTRAINT uq_signal_sym_strat_date
                UNIQUE (symbol, strategy_id, signal_date)
            """))
            _conn.commit()
        except Exception:
            pass  # constraint already exists

    # Strategy Combination Engine tables
    try:
        with engine.connect() as _conn:
            _conn.execute(text("""
                CREATE TABLE IF NOT EXISTS strategy_combinations (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    strategy_ids TEXT NOT NULL,
                    strategy_names TEXT NOT NULL,
                    size INTEGER NOT NULL,
                    search_method TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            _conn.execute(text("""
                CREATE UNIQUE INDEX IF NOT EXISTS uq_combination_ids
                ON strategy_combinations(strategy_ids)
            """))
            _conn.execute(text("""
                CREATE TABLE IF NOT EXISTS combination_run_log (
                    id SERIAL PRIMARY KEY,
                    started_at TIMESTAMP NOT NULL,
                    completed_at TIMESTAMP,
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
                    id SERIAL PRIMARY KEY,
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
                    computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            _conn.execute(text("""
                CREATE TABLE IF NOT EXISTS combination_regime_perf (
                    id SERIAL PRIMARY KEY,
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
                    id         SERIAL PRIMARY KEY,
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
                    id          SERIAL PRIMARY KEY,
                    index_name  TEXT NOT NULL,
                    date        DATE NOT NULL,
                    close       REAL NOT NULL,
                    sma20       REAL,
                    sma50       REAL,
                    above_sma20 INTEGER NOT NULL DEFAULT 0,
                    above_sma50 INTEGER NOT NULL DEFAULT 0,
                    trend_label TEXT NOT NULL,
                    computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(index_name, date)
                )
            """))
            _conn.commit()
        logger.info("Index pipeline tables verified")
    except Exception as e:
        logger.warning("index table migration skipped: %s", e)

    # Intraday alert dedup + FII/DII tables
    try:
        with engine.connect() as _conn:
            _conn.execute(text("""
                CREATE TABLE IF NOT EXISTS intraday_alerts_sent (
                    id          SERIAL PRIMARY KEY,
                    symbol      TEXT NOT NULL,
                    strategy_id INTEGER NOT NULL,
                    signal_date DATE NOT NULL,
                    alerted_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(symbol, strategy_id, signal_date)
                )
            """))
            _conn.execute(text("""
                CREATE TABLE IF NOT EXISTS fii_dii_daily (
                    id              SERIAL PRIMARY KEY,
                    date            DATE NOT NULL UNIQUE,
                    fii_net_equity  REAL,
                    dii_net_equity  REAL,
                    fii_buy         REAL,
                    fii_sell        REAL,
                    dii_buy         REAL,
                    dii_sell        REAL,
                    fetched_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            _conn.commit()
        logger.info("Intraday alert + FII/DII tables verified")
    except Exception as e:
        logger.warning("intraday/fii_dii table migration skipped: %s", e)

    # Special Strategies tables
    try:
        with engine.connect() as _conn:
            _conn.execute(text("""
                CREATE TABLE IF NOT EXISTS special_strategy_performance (
                    id                   SERIAL PRIMARY KEY,
                    special_strategy_id  INTEGER NOT NULL,
                    symbol               VARCHAR(20) NOT NULL,
                    total_trades         INTEGER DEFAULT 0,
                    win_rate             REAL,
                    cagr                 REAL,
                    sharpe_ratio         REAL,
                    max_drawdown         REAL,
                    profit_factor        REAL,
                    total_pnl            REAL DEFAULT 0,
                    avg_pnl_pct          REAL,
                    to_date              DATE,
                    computed_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(special_strategy_id, symbol)
                )
            """))
            _conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_sp_perf_strategy ON special_strategy_performance (special_strategy_id)"
            ))
            _conn.execute(text("""
                CREATE TABLE IF NOT EXISTS special_strategies (
                    id          SERIAL PRIMARY KEY,
                    name        VARCHAR(100) UNIQUE NOT NULL,
                    description TEXT,
                    is_active   BOOLEAN DEFAULT true,
                    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            _conn.execute(text("""
                CREATE TABLE IF NOT EXISTS special_backtest_results (
                    id                   SERIAL PRIMARY KEY,
                    special_strategy_id  INTEGER NOT NULL,
                    symbol               VARCHAR(20) NOT NULL,
                    from_date            DATE NOT NULL,
                    to_date              DATE NOT NULL,
                    total_trades         INTEGER DEFAULT 0,
                    win_rate             REAL,
                    total_pnl            REAL DEFAULT 0,
                    avg_pnl_pct          REAL,
                    ran_at               TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            _conn.execute(text("""
                CREATE TABLE IF NOT EXISTS special_backtest_trades (
                    id                  SERIAL PRIMARY KEY,
                    backtest_result_id  INTEGER NOT NULL,
                    symbol              VARCHAR(20) NOT NULL,
                    entry_date          DATE,
                    entry_price         REAL,
                    exit_date           DATE,
                    exit_price          REAL,
                    quantity            INTEGER,
                    pnl                 REAL,
                    pnl_pct             REAL,
                    exit_reason         VARCHAR(30),
                    holding_days        INTEGER
                )
            """))
            _conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_sp_bt_results ON special_backtest_results (special_strategy_id, symbol)"
            ))
            _conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_sp_bt_trades ON special_backtest_trades (backtest_result_id)"
            ))
            # Precomputed trades per (strategy, symbol) — populated by precompute_all, served as cache
            _conn.execute(text("""
                CREATE TABLE IF NOT EXISTS special_strategy_trades (
                    id                  SERIAL PRIMARY KEY,
                    special_strategy_id INTEGER NOT NULL,
                    symbol              VARCHAR(20) NOT NULL,
                    entry_date          DATE,
                    entry_price         REAL,
                    exit_date           DATE,
                    exit_price          REAL,
                    quantity            INTEGER,
                    pnl                 REAL,
                    pnl_pct             REAL,
                    exit_reason         VARCHAR(30),
                    holding_days        INTEGER
                )
            """))
            _conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_sst_sid_sym ON special_strategy_trades (special_strategy_id, symbol)"
            ))
            _conn.commit()
        logger.info("Special Strategies tables verified")
    except Exception as e:
        logger.warning("special_strategies tables migration skipped: %s", e)

    # Sector rotation tables
    try:
        with engine.connect() as _conn:
            _conn.execute(text("""
                CREATE TABLE IF NOT EXISTS sector_breadth_daily (
                    id                  SERIAL PRIMARY KEY,
                    sector_name         VARCHAR(30) NOT NULL,
                    trade_date          DATE NOT NULL,
                    pct_above_sma50     REAL,
                    index_vs_sma20      REAL,
                    return_1m           REAL,
                    return_3m           REAL,
                    sector_health_score REAL,
                    rotation_direction  VARCHAR(20),
                    UNIQUE(sector_name, trade_date)
                )
            """))
            _conn.execute(text("""
                CREATE TABLE IF NOT EXISTS sector_signal_flow (
                    id                  SERIAL PRIMARY KEY,
                    sector_name         VARCHAR(30) NOT NULL,
                    week_start          DATE NOT NULL,
                    signal_count        INTEGER DEFAULT 0,
                    prev_signal_count   INTEGER DEFAULT 0,
                    avg_win_rate        REAL,
                    top_strategy        VARCHAR(100),
                    stocks_with_signals TEXT,
                    UNIQUE(sector_name, week_start)
                )
            """))
            _conn.commit()
        logger.info("Sector rotation tables verified")
    except Exception as e:
        logger.warning("sector rotation tables migration skipped: %s", e)

    # Indicator cache table — wide table storing IndicatorEngine output per (symbol, date)
    try:
        from domains.data.indicator_cache import IND_COLS as _IND_COLS
        _ind_col_defs = "\n    ".join(f"{c} REAL," for c in _IND_COLS)
        with engine.connect() as _conn:
            _conn.execute(text(f"""
                CREATE TABLE IF NOT EXISTS stock_indicators_daily (
                    id          SERIAL PRIMARY KEY,
                    symbol      TEXT NOT NULL,
                    date        DATE NOT NULL,
                    {_ind_col_defs}
                    computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(symbol, date)
                )
            """))
            _conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_sid_symbol_date ON stock_indicators_daily(symbol, date)"
            ))
            _conn.commit()
        logger.info("stock_indicators_daily table verified")
    except Exception as e:
        logger.warning("stock_indicators_daily migration skipped: %s", e)

    # Schema upgrade: add new indicator columns to existing stock_indicators_daily tables
    _new_indicator_cols = [
        "ema_7", "ema_14", "ema_22", "zlema_14",
        "psar", "psar_bull",
        "dmi_plus_14", "dmi_minus_14",
        "vortex_pos", "vortex_neg",
        "fisher_9",
        "donchian_high_20", "donchian_low_20", "donchian_mid_20",
        "stoch_rsi_k", "stoch_rsi_d",
        "cmf_20",
        "ichimoku_tenkan", "ichimoku_kijun", "ichimoku_span_a", "ichimoku_span_b",
        "ichimoku_cloud_a", "ichimoku_cloud_b",
        "chandelier_long",
        "ao", "alligator_jaw", "alligator_teeth", "alligator_lips",
        "rolling_high_200",
        # Strategy-specific precomputed indicators
        "sma_200",
        "hma_50", "ut_bot_stop",
        "squeeze_on", "squeeze_mom",
        "qqe_fast_rsi", "qqe_fast", "qqe_slow_rsi", "qqe_slow",
        "connors_rsi",
        "lorentzian_pred",
        "nw_yhat", "nw_upper", "nw_lower",
        "mc_wt1", "mc_wt2", "rsimfi_60",
    ]
    with engine.connect() as _conn:
        for _col in _new_indicator_cols:
            _conn.execute(text(f"ALTER TABLE stock_indicators_daily ADD COLUMN IF NOT EXISTS {_col} REAL"))
        _conn.commit()

    # Migrate volume columns to BIGINT — some stocks (e.g. PCJEWELLER) exceed INT4 max
    try:
        with engine.connect() as _conn:
            for _tbl in ("stock_prices_daily", "stock_prices_intraday"):
                _conn.execute(text(
                    f"ALTER TABLE {_tbl} ALTER COLUMN volume TYPE BIGINT"
                ))
            _conn.commit()
    except Exception as _e:
        logger.warning("[migration] volume BIGINT upgrade skipped: %s", _e)

    # Remove rows where close is NULL or NaN — yfinance sometimes returns partial bars
    # (e.g. for the current day when market hasn't closed) that pass old validate_row checks.
    # These rows cause non-finite price errors in the scanner and precompute.
    try:
        with engine.connect() as _conn:
            _d1 = _conn.execute(text(
                "DELETE FROM stock_prices_daily WHERE close IS NULL OR close = 'NaN'::float"
            )).rowcount
            # indicator cache stores NaN close as NULL — delete those rows so the cache
            # is rebuilt from the now-clean price data on next precompute startup.
            _d2 = _conn.execute(text(
                "DELETE FROM stock_indicators_daily WHERE close IS NULL"
            )).rowcount
            _conn.commit()
            if _d1 or _d2:
                logger.info("[migration] Removed %d bad price rows, %d bad indicator cache rows", _d1, _d2)
    except Exception as _e:
        logger.warning("[migration] NaN close cleanup skipped: %s", _e)

    # Cache invalidation: if lorentzian_pred is NULL for all rows, the cache was built
    # with the old schema — clear it so the startup precompute rebuilds all 91 columns.
    try:
        with engine.connect() as _conn:
            _has_new = _conn.execute(
                text("SELECT COUNT(*) FROM stock_indicators_daily WHERE lorentzian_pred IS NOT NULL")
            ).scalar()
            if _has_new == 0:
                _total = _conn.execute(text("SELECT COUNT(*) FROM stock_indicators_daily")).scalar()
                if _total > 0:
                    _conn.execute(text("DELETE FROM stock_indicators_daily"))
                    _conn.commit()
                    logger.info("[migration] Cleared %d stale indicator cache rows (schema upgrade — new columns added)", _total)
    except Exception as e:
        logger.warning("[migration] Indicator cache invalidation check failed: %s", e)

    from domains.strategies.seed import seed_strategies
    from domains.special_strategies.seed import seed_special_strategies
    db = SessionLocal()
    try:
        seed_strategies(db)
        seed_special_strategies(db)
    finally:
        db.close()

    # Auto-precompute: runs precompute_all_strategies() in background.
    # Incremental skip logic inside the method means this is a no-op if
    # everything is already current — safe to trigger on every startup.
    def _startup_precompute():
        from database import SessionLocal as _SL
        from domains.backtest.runner import BacktestRunner
        _db = _SL()
        try:
            BacktestRunner(_db).precompute_all_strategies()
        except Exception:
            logger.exception("[startup] precompute failed")
        finally:
            _db.close()

    threading.Thread(target=_startup_precompute, daemon=True, name="auto-precompute").start()
    logger.info("[startup] auto-precompute thread started")

    # Auto-bootstrap: download any NSE symbols not yet in stock_prices_daily (handles
    # both first-run and partial-bootstrap cases — BootstrapRunner skips existing symbols).
    from domains.data.nse_universe import NSE_SYMBOLS as _NSE_SYMS
    db3 = SessionLocal()
    try:
        existing_syms = {
            r[0] for r in db3.execute(text("SELECT DISTINCT symbol FROM stock_prices_daily")).fetchall()
        }
    finally:
        db3.close()
    missing_syms = [s for s in _NSE_SYMS if s not in existing_syms]
    if missing_syms:
        logger.info(
            "[startup] %d/%d symbols missing price data — auto-bootstrap starting in background",
            len(missing_syms), len(_NSE_SYMS),
        )
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


# ── Tables cleared by each reset scope ────────────────────────────────────────
_COMPUTED_TABLES = [
    "strategy_performance",
    "stock_indicators_daily",
    "scan_result_cache",
    "strategy_signals",
    "backtest_results",
    "backtest_trades",
    "walk_forward_results",
    "combination_run_log",
    "combination_results",
    "combination_regime_perf",
    "strategy_combinations",
    "intraday_alerts_sent",
    "index_trend",
    "fii_dii_daily",
]

_FULL_EXTRA_TABLES = [
    "stock_prices_daily",
    "stock_prices_intraday",
    "index_prices_daily",
    "fundamentals",
    "corporate_actions",
    "news",
    "stocks",
    "portfolio_holdings",
    "trades",
]


@app.post("/api/v1/admin/reset-db", tags=["admin"], dependencies=[Depends(verify_api_key)])
def reset_db(
    scope: str = "computed",
    db: Session = Depends(get_db),
):
    """Reset the database.

    scope=computed (default): clears all derived/computed data — indicators,
    strategy performance, scan cache, backtests, combinations. Keeps price data.
    Fast (~1 second).

    scope=full: wipes everything including price data and portfolio. Re-seeds
    strategies and triggers background bootstrap (re-download takes hours).
    """
    if scope not in ("computed", "full"):
        raise HTTPException(status_code=400, detail="scope must be 'computed' or 'full'")

    tables = _COMPUTED_TABLES if scope == "computed" else _COMPUTED_TABLES + _FULL_EXTRA_TABLES

    cleared = []
    for tbl in tables:
        try:
            db.execute(text(f"DELETE FROM {tbl}"))
            cleared.append(tbl)
        except Exception as e:
            logger.warning("[reset-db] skipping %s: %s", tbl, e)
    db.commit()
    logger.info("[reset-db] scope=%s — cleared %d tables: %s", scope, len(cleared), cleared)

    bootstrap_started = False
    if scope == "full":
        from domains.strategies.seed import seed_strategies
        seed_strategies(db)

        threading.Thread(target=_run_bootstrap, daemon=True, name="reset-bootstrap").start()

        def _reset_index_bootstrap():
            from domains.data.index_fetcher import fetch_and_store_index_prices, compute_index_trends
            db_bg = SessionLocal()
            try:
                fetch_and_store_index_prices(db_bg, days=365)
                compute_index_trends(db_bg)
                logger.info("[reset] index bootstrap complete")
            except Exception:
                logger.exception("[reset] index bootstrap failed")
            finally:
                db_bg.close()

        threading.Thread(target=_reset_index_bootstrap, daemon=True, name="reset-index").start()
        bootstrap_started = True

    return {
        "status": "ok",
        "scope": scope,
        "tables_cleared": len(cleared),
        "bootstrap_started": bootstrap_started,
        "message": (
            "Computed data cleared. You can now run Force Recompute to rebuild strategy performance."
            if scope == "computed"
            else "Full reset complete. Price data download started in background — this may take several hours."
        ),
    }


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

from domains.special_strategies.router import router as special_router  # noqa: E402
app.include_router(special_router, prefix="/api/v1", dependencies=[Depends(verify_api_key)])

from domains.sector_rotation.router import router as sector_router  # noqa: E402
app.include_router(sector_router, prefix="/api/v1", dependencies=[Depends(verify_api_key)])
