import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Security, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security.api_key import APIKeyHeader

from database import Base, engine
from settings import settings
import models  # noqa

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(key: str = Security(API_KEY_HEADER)) -> str:
    if key != settings.api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
    return key


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables verified")
    from domains.strategies.seed import seed_strategies
    from database import SessionLocal
    db = SessionLocal()
    try:
        seed_strategies(db)
    finally:
        db.close()
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
    allow_origins=["http://localhost:3000"],
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
