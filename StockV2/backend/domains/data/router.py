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


@router.get("/data/fundamentals")
def list_all_fundamentals(db: Session = Depends(get_db)):
    """Latest fundamentals snapshot for every symbol that has data."""
    from sqlalchemy import text
    rows = db.execute(text("""
        SELECT DISTINCT ON (symbol)
            symbol, pe_ratio, pb_ratio, eps, revenue, net_profit,
            debt_equity, roe, dividend_yield, data_as_of
        FROM fundamentals
        ORDER BY symbol, data_as_of DESC
    """)).fetchall()
    return [
        {
            "symbol":        r[0],
            "pe_ratio":      r[1],
            "pb_ratio":      r[2],
            "eps":           r[3],
            "revenue":       r[4],
            "net_profit":    r[5],
            "debt_equity":   r[6],
            "roe":           r[7],
            "dividend_yield": r[8],
            "data_as_of":    str(r[9]) if r[9] else None,
        }
        for r in rows
    ]


@router.get("/data/fundamentals/count")
def get_fundamentals_count(db: Session = Depends(get_db)):
    from sqlalchemy import text
    count = db.execute(text("SELECT COUNT(*) FROM fundamentals")).scalar() or 0
    return {"count": int(count)}


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


@router.get("/data/fundamentals/{symbol}/history")
def get_fundamentals_history(symbol: str, db: Session = Depends(get_db)):
    """All historical snapshots for a single symbol, newest first."""
    from sqlalchemy import text
    rows = db.execute(text("""
        SELECT pe_ratio, pb_ratio, eps, revenue, net_profit,
               debt_equity, roe, dividend_yield, data_as_of
        FROM fundamentals
        WHERE symbol = :sym
        ORDER BY data_as_of DESC
    """), {"sym": symbol.upper()}).fetchall()
    if not rows:
        raise HTTPException(status_code=404, detail=f"No fundamentals data for {symbol}")
    return [
        {
            "pe_ratio":      r[0],
            "pb_ratio":      r[1],
            "eps":           r[2],
            "revenue":       r[3],
            "net_profit":    r[4],
            "debt_equity":   r[5],
            "roe":           r[6],
            "dividend_yield": r[7],
            "data_as_of":    str(r[8]) if r[8] else None,
        }
        for r in rows
    ]


@router.get("/data/fundamentals/{symbol}")
def get_fundamentals(symbol: str, db: Session = Depends(get_db)):
    from domains.data.fundamentals import FundamentalsService
    data = FundamentalsService(db).get_latest(symbol.upper())
    if not data:
        raise HTTPException(status_code=404, detail=f"No fundamentals data for {symbol}")
    return {"symbol": symbol.upper(), **data}
