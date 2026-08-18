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

    from domains.strategies.seed import seed_strategies
    db = SessionLocal()
    try:
        seed_strategies(db)
    finally:
        db.close()

    # Auto-bootstrap: if no price data exists, download 15 years in the background
    db3 = SessionLocal()
    try:
        has_prices = db3.execute(text("SELECT 1 FROM stock_prices_daily LIMIT 1")).scalar()
    finally:
        db3.close()
    if not has_prices:
        logger.info("[startup] No price data found — auto-bootstrap starting in background (~20-60 min)")
        threading.Thread(target=_run_bootstrap, daemon=True, name="auto-bootstrap").start()

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
