import logging
import threading
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from database import get_db, SessionLocal
from sqlalchemy import text
from domains.backtest.runner import BacktestRunner
from ist import ist_today
from domains.backtest.service import BacktestService

logger = logging.getLogger(__name__)
router = APIRouter(tags=["backtest"])

# ── Leaderboard background state ─────────────────────────────────────────────
_lb_lock = threading.Lock()
_lb_state: dict = {
    "is_computing": False,
    "pairs_done": 0,
    "error": None,
    "sl": 5.0,
    "tgt": 10.0,
}
_LEADERBOARD_FROM = date(2015, 1, 1)


def _parse_date(val) -> Optional[date]:
    """Parse a date value that may be a date object, 'YYYY-MM-DD', or 'YYYY-MM-DD HH:MM:SS'."""
    if val is None:
        return None
    if isinstance(val, date):
        return val
    return date.fromisoformat(str(val)[:10])


def _get_last_price_date(db) -> Optional[date]:
    row = db.execute(text("SELECT MAX(date) FROM stock_prices_daily")).scalar()
    return _parse_date(row)


def _run_leaderboard_bg(stop_loss_pct: float, target_pct: float) -> None:
    global _lb_state
    with _lb_lock:
        if _lb_state["is_computing"]:
            return
        _lb_state.update({"is_computing": True, "error": None,
                           "sl": stop_loss_pct, "tgt": target_pct})
    db = SessionLocal()
    try:
        to_date = _get_last_price_date(db) or ist_today()
        BacktestRunner(db).scan_all(
            from_date=_LEADERBOARD_FROM,
            to_date=to_date,
            stop_loss_pct=stop_loss_pct,
            target_pct=target_pct,
            limit=500,
        )
        logger.info("[leaderboard] compute done sl=%s tgt=%s to_date=%s", stop_loss_pct, target_pct, to_date)
    except Exception as e:
        _lb_state["error"] = str(e)
        logger.exception("[leaderboard] compute failed")
    finally:
        _lb_state["is_computing"] = False
        db.close()


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


@router.get("/backtest/scan/status")
def scan_precompute_status(db: Session = Depends(get_db)):
    """Returns how many strategies have been precomputed vs total."""
    total = db.execute(
        text("SELECT COUNT(*) FROM strategies WHERE is_active = 1")
    ).fetchone()[0]
    computed = db.execute(
        text("SELECT COUNT(DISTINCT strategy_id) FROM strategy_performance")
    ).fetchone()[0]
    return {"total": total, "computed": computed, "pending": total - computed, "ready": computed >= total}


@router.get("/backtest/scan/results")
def precomputed_scan_results(
    strategy_id: Optional[int] = Query(None),
    min_trades: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """Return permanently precomputed backtest results — instant, no recomputation."""
    q = """
        SELECT sp.symbol, sp.strategy_id, s.name AS strategy_name,
               sp.total_trades, sp.win_rate, sp.cagr, sp.sharpe_ratio,
               sp.max_drawdown, sp.profit_factor, sp.total_pnl
        FROM strategy_performance sp
        JOIN strategies s ON sp.strategy_id = s.id
        WHERE 1=1
    """
    params: dict = {}
    if strategy_id is not None:
        q += " AND sp.strategy_id = :sid"
        params["sid"] = strategy_id
    if min_trades > 0:
        q += " AND sp.total_trades >= :mt"
        params["mt"] = min_trades
    q += " ORDER BY sp.cagr DESC"
    rows = db.execute(text(q), params).fetchall()
    return [dict(r._mapping) for r in rows]


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


# ── Leaderboard ───────────────────────────────────────────────────────────────

@router.get("/backtest/leaderboard")
def get_leaderboard(
    stop_loss_pct: float = Query(5.0),
    target_pct: float = Query(10.0),
    min_trades: int = Query(3, ge=1),
    limit: int = Query(500, le=5000),
    symbol: Optional[str] = Query(None),
    strategy_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    """Top (stock, strategy) pairs by win rate for a fixed SL/target."""
    q = """
        SELECT src.symbol, src.strategy_id, s.name AS strategy_name,
               src.total_trades, src.win_rate, src.cagr, src.sharpe_ratio,
               src.max_drawdown, src.profit_factor, src.total_pnl
        FROM scan_result_cache src
        JOIN strategies s ON src.strategy_id = s.id
        WHERE src.stop_loss_pct = :sl AND src.target_pct = :tgt
          AND src.total_trades >= :mt
          AND src.from_date = :fd
    """
    params: dict = {
        "sl": stop_loss_pct, "tgt": target_pct,
        "mt": min_trades, "fd": str(_LEADERBOARD_FROM),
    }
    if symbol:
        q += " AND src.symbol = :sym"
        params["sym"] = symbol.upper()
    if strategy_id is not None:
        q += " AND src.strategy_id = :sid"
        params["sid"] = strategy_id
    q += " ORDER BY src.win_rate DESC NULLS LAST, src.cagr DESC NULLS LAST LIMIT :lim"
    params["lim"] = limit
    rows = db.execute(text(q), params).fetchall()
    return [dict(r._mapping) for r in rows]


@router.get("/backtest/leaderboard/status")
def leaderboard_status(
    stop_loss_pct: float = Query(5.0),
    target_pct: float = Query(10.0),
    db: Session = Depends(get_db),
):
    pairs_cached = db.execute(
        text("""
            SELECT COUNT(*) FROM scan_result_cache
            WHERE stop_loss_pct = :sl AND target_pct = :tgt AND from_date = :fd
        """),
        {"sl": stop_loss_pct, "tgt": target_pct, "fd": str(_LEADERBOARD_FROM)},
    ).scalar() or 0

    total_symbols = db.execute(
        text("""
            SELECT COUNT(DISTINCT symbol) FROM stock_prices_daily
            WHERE date >= :fd
        """),
        {"fd": str(_LEADERBOARD_FROM)},
    ).scalar() or 0

    total_strategies = db.execute(
        text("SELECT COUNT(*) FROM strategies WHERE is_active = 1")
    ).scalar() or 0

    total_expected = total_symbols * total_strategies

    last_price_date = _get_last_price_date(db)

    # determine the to_date used when the cache was last built
    cached_to_date_row = db.execute(
        text("""
            SELECT MAX(to_date) FROM scan_result_cache
            WHERE stop_loss_pct = :sl AND target_pct = :tgt AND from_date = :fd
        """),
        {"sl": stop_loss_pct, "tgt": target_pct, "fd": str(_LEADERBOARD_FROM)},
    ).scalar()
    cached_to_date = _parse_date(cached_to_date_row)
    is_current = (
        last_price_date is not None
        and cached_to_date is not None
        and cached_to_date >= last_price_date
    )

    return {
        "is_computing": _lb_state["is_computing"],
        "pairs_cached": pairs_cached,
        "total_expected": total_expected,
        "total_symbols": total_symbols,
        "total_strategies": total_strategies,
        "pct_done": round(pairs_cached / total_expected * 100, 1) if total_expected > 0 else 0,
        "error": _lb_state.get("error"),
        "is_current": is_current,
        "last_price_date": str(last_price_date) if last_price_date else None,
        "cached_to_date": str(cached_to_date) if cached_to_date else None,
        "params": {"stop_loss_pct": stop_loss_pct, "target_pct": target_pct,
                   "from_date": str(_LEADERBOARD_FROM)},
    }


@router.post("/backtest/leaderboard/compute")
def trigger_leaderboard_compute(
    stop_loss_pct: float = Query(5.0),
    target_pct: float = Query(10.0),
    force: bool = Query(False),
    db: Session = Depends(get_db),
):
    """Kick off background computation of win rates for all (stock, strategy) pairs."""
    if _lb_state["is_computing"]:
        return {"status": "already_running",
                "message": "Computation already in progress — check /leaderboard/status"}

    if not force:
        last_price_date = _get_last_price_date(db)
        if last_price_date:
            cached_to = db.execute(
                text("""
                    SELECT MAX(to_date) FROM scan_result_cache
                    WHERE stop_loss_pct = :sl AND target_pct = :tgt AND from_date = :fd
                """),
                {"sl": stop_loss_pct, "tgt": target_pct, "fd": str(_LEADERBOARD_FROM)},
            ).scalar()
            cached_date = _parse_date(cached_to)
            if cached_date is not None and cached_date >= last_price_date:
                    return {
                        "status": "up_to_date",
                        "message": f"Cache is already current as of {last_price_date}. Use force=true to recompute.",
                    }

    t = threading.Thread(
        target=_run_leaderboard_bg,
        args=(stop_loss_pct, target_pct),
        daemon=True,
    )
    t.start()
    return {
        "status": "started",
        "message": f"Computing leaderboard: SL={stop_loss_pct}% · Target={target_pct}% · from {_LEADERBOARD_FROM}",
    }
