from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from domains.strategies.service import StrategyService
from domains.strategies.scanner import LiveScanner

router = APIRouter(tags=["strategies"])


class LiveScanRequest(BaseModel):
    strategy_id: Optional[int] = None
    signal_type: Optional[str] = None  # "BUY", "SELL", or None for both
    limit: int = 200


@router.get("/strategies")
def list_strategies(db: Session = Depends(get_db)):
    return StrategyService(db).get_all_strategies()


@router.get("/signals/today")
def signals_today(db: Session = Depends(get_db)):
    return StrategyService(db).get_today_signals()


@router.get("/signals/{signal_id}")
def get_signal(signal_id: int, db: Session = Depends(get_db)):
    signal = StrategyService(db).get_signal_by_id(signal_id)
    if not signal:
        raise HTTPException(status_code=404, detail=f"Signal {signal_id} not found")
    return signal


@router.post("/signals/scan")
def live_scan(body: LiveScanRequest, db: Session = Depends(get_db)):
    """Run strategies against all stocks in real-time and return active signals."""
    return LiveScanner(db).scan(
        strategy_id=body.strategy_id,
        signal_type=body.signal_type,
        limit=min(body.limit, 500),
    )


@router.get("/signals")
def list_signals(
    symbol: Optional[str] = Query(None),
    signal_type: Optional[str] = Query(None),
    from_date: Optional[date] = Query(None),
    limit: int = Query(100, le=1000),
    db: Session = Depends(get_db),
):
    return StrategyService(db).get_signals(
        symbol=symbol,
        signal_type=signal_type,
        from_date=str(from_date) if from_date else None,
        limit=limit,
    )
