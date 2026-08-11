from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator
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
    stop_loss_pct: Optional[float] = None
    target_pct: Optional[float] = None

    @model_validator(mode="after")
    def check_date_range(self):
        if self.from_date >= self.to_date:
            raise ValueError("from_date must be before to_date")
        return self


@router.post("/backtest/run")
def run_backtest(body: BacktestRunRequest, db: Session = Depends(get_db)):
    result = BacktestRunner(db).run(
        symbol=body.symbol,
        from_date=body.from_date,
        to_date=body.to_date,
        strategy_id=body.strategy_id,
        initial_capital=body.initial_capital,
        stop_loss_pct=body.stop_loss_pct,
        target_pct=body.target_pct,
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


class ScanRequest(BaseModel):
    from_date: date
    to_date: date
    strategy_ids: Optional[list[int]] = None
    initial_capital: float = 500_000.0
    limit: int = Field(default=200, le=500)
    stop_loss_pct: Optional[float] = None
    target_pct: Optional[float] = None

    @model_validator(mode="after")
    def check_date_range(self):
        if self.from_date >= self.to_date:
            raise ValueError("from_date must be before to_date")
        return self


@router.post("/backtest/scan")
def scan_backtest(body: ScanRequest, db: Session = Depends(get_db)):
    results = BacktestRunner(db).scan_all(
        from_date=body.from_date,
        to_date=body.to_date,
        strategy_ids=body.strategy_ids,
        initial_capital=body.initial_capital,
        limit=body.limit,
        stop_loss_pct=body.stop_loss_pct,
        target_pct=body.target_pct,
    )
    return results


@router.get("/backtest/results")
def list_results(
    symbol: Optional[str] = None,
    limit: int = Query(20, le=200),
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
def get_result_trades(
    result_id: int,
    limit: int = Query(100, le=1000),
    db: Session = Depends(get_db),
):
    svc = BacktestService(db)
    if not svc.get_result(result_id):
        raise HTTPException(status_code=404, detail="Backtest result not found")
    return svc.get_trades(result_id, limit=limit)
