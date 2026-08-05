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
