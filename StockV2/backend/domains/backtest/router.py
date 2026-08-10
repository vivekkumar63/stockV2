from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from domains.backtest.runner import BacktestRunner
from domains.backtest.service import BacktestService

router = APIRouter(tags=["backtest"])


class BacktestRunRequest(BaseModel):
    symbol: str
    from_date: date
    to_date: date
    strategy_id: Optional[int] = None
    initial_capital: float = 500_000.0


@router.post("/backtest/run")
def run_backtest(body: BacktestRunRequest, db: Session = Depends(get_db)):
    result = BacktestRunner(db).run(
        symbol=body.symbol,
        from_date=body.from_date,
        to_date=body.to_date,
        strategy_id=body.strategy_id,
        initial_capital=body.initial_capital,
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/backtest/results")
def list_results(
    symbol: Optional[str] = None,
    limit: int = 20,
    db: Session = Depends(get_db),
):
    return BacktestService(db).get_results(symbol=symbol, limit=limit)


@router.get("/backtest/results/{result_id}")
def get_result(result_id: int, db: Session = Depends(get_db)):
    result = BacktestService(db).get_result(result_id)
    if not result:
        raise HTTPException(status_code=404, detail="Backtest result not found")
    return result


@router.get("/backtest/results/{result_id}/trades")
def get_result_trades(result_id: int, db: Session = Depends(get_db)):
    return BacktestService(db).get_trades(result_id)
