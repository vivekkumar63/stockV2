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
