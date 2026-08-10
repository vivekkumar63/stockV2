from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from domains.portfolio.paper_trader import PaperTrader
from domains.portfolio.service import PortfolioService
from domains.portfolio.watchlist_service import WatchlistService

router = APIRouter(tags=["portfolio"])


class EnterBody(BaseModel):
    price: float


class ExitBody(BaseModel):
    price: float
    reason: str = "manual"


class WatchlistBody(BaseModel):
    reason: Optional[str] = None


@router.get("/portfolio/summary")
def portfolio_summary(db: Session = Depends(get_db)):
    return PortfolioService(db).get_portfolio_summary()


@router.get("/portfolio/holdings")
def portfolio_holdings(db: Session = Depends(get_db)):
    return PortfolioService(db).get_holdings()


@router.get("/portfolio/trades")
def portfolio_trades(
    symbol: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    return PortfolioService(db).get_trade_history(symbol=symbol, limit=limit)


@router.get("/portfolio/pnl")
def portfolio_pnl(db: Session = Depends(get_db)):
    return PortfolioService(db).get_closed_pnl()


@router.post("/portfolio/enter/{signal_id}")
def paper_enter(signal_id: int, body: EnterBody, db: Session = Depends(get_db)):
    trade = PaperTrader(db).enter(signal_id, body.price)
    if trade is None:
        raise HTTPException(
            status_code=400,
            detail="Entry rejected — check signal validity and position limits",
        )
    return trade


@router.post("/portfolio/exit/{symbol}")
def paper_exit(symbol: str, body: ExitBody, db: Session = Depends(get_db)):
    trade = PaperTrader(db).exit(symbol.upper(), body.price, body.reason)
    if trade is None:
        raise HTTPException(status_code=404, detail=f"No active position for {symbol}")
    return trade


@router.get("/watchlist")
def watchlist_list(db: Session = Depends(get_db)):
    return WatchlistService(db).get_all()


@router.post("/watchlist/{symbol}")
def watchlist_add(symbol: str, body: WatchlistBody, db: Session = Depends(get_db)):
    return WatchlistService(db).add(symbol.upper(), body.reason)


@router.delete("/watchlist/{symbol}")
def watchlist_remove(symbol: str, db: Session = Depends(get_db)):
    removed = WatchlistService(db).remove(symbol.upper())
    if not removed:
        raise HTTPException(status_code=404, detail=f"{symbol} not in watchlist")
    return {"removed": symbol.upper()}
