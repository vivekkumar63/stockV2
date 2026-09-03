from __future__ import annotations
import datetime
import json
import logging
import threading
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from database import get_db, SessionLocal
from .engine import ZoneEngine, zone_to_dict, setup_to_dict
from .precompute import ZonePrecomputer, get_precompute_state
from .backtester import ZoneBacktester

router = APIRouter(tags=["zones"])
logger = logging.getLogger(__name__)

_recompute_lock = threading.Lock()


def _serialize_result(r) -> dict:
    return {
        "symbol":           r.symbol,
        "demand_zones":     [zone_to_dict(z) for z in r.demand_zones],
        "supply_zones":     [zone_to_dict(z) for z in r.supply_zones],
        "long_setup":       setup_to_dict(r.long_setup),
        "short_setup":      setup_to_dict(r.short_setup),
        "market_structure": r.market_structure,
        "atr":              r.atr,
        "rvol":             r.rvol,
        "price":            r.price,
        "position_tag":     r.position_tag,
    }


@router.get("/zones/analyze/{symbol}")
def analyze_symbol(symbol: str, db: Session = Depends(get_db)):
    """Run (or refresh) zone analysis for one symbol. Stores result and returns it."""
    result = ZoneEngine().analyze(symbol.upper(), db)
    if result is None:
        raise HTTPException(status_code=404, detail=f"No price data for {symbol}")
    return _serialize_result(result)


@router.get("/zones/results/{symbol}")
def get_stored_result(symbol: str, db: Session = Depends(get_db)):
    """Return the most recent stored result for a symbol (no recompute)."""
    row = db.execute(
        text("""
            SELECT result_json, computed_date, price_at_compute, atr_at_compute,
                   rvol_at_compute, position_tag, long_setup_score, short_setup_score,
                   best_demand_score, best_supply_score, created_at
            FROM zone_analysis_results
            WHERE symbol = :s
            ORDER BY computed_date DESC
            LIMIT 1
        """),
        {"s": symbol.upper()},
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"No stored zones for {symbol}")
    result = json.loads(row[0])
    result["symbol"]           = symbol.upper()
    result["computed_date"]    = str(row[1])
    result["price"]            = row[2]
    result["atr"]              = row[3]
    result["rvol"]             = row[4]
    result["position_tag"]     = row[5]
    result["long_setup_score"] = row[6]
    result["short_setup_score"]= row[7]
    result["best_demand_score"]= row[8]
    result["best_supply_score"]= row[9]
    result["computed_at"]      = str(row[10])
    return result


_SORT_MAP = {
    "long_score":    "long_setup_score",
    "short_score":   "short_setup_score",
    "demand_score":  "best_demand_score",
    "supply_score":  "best_supply_score",
    "rvol":          "rvol_at_compute",
    "atr":           "atr_at_compute",
    "dist_long":     "ABS(price_at_compute - long_entry_price) / NULLIF(price_at_compute, 0) * 100",
    "dist_short":    "ABS(price_at_compute - short_entry_price) / NULLIF(price_at_compute, 0) * 100",
    "near_52w_high": "pct_from_52w_high DESC NULLS LAST, long_setup_score",
    "near_52w_low":  "pct_from_52w_low ASC NULLS LAST, long_setup_score",
}

_FILTER_TAGS = {"in_demand", "near_supply", "breakout", "in_supply", "near_demand"}


@router.get("/zones/rankings")
def get_rankings(
    sort_by: str    = Query("long_score"),
    tag_filter: str = Query(None),
    limit: int      = Query(200, ge=1, le=500),
    db: Session     = Depends(get_db),
):
    """All stocks with today's pre-computed results, sorted and optionally filtered."""
    col = _SORT_MAP.get(sort_by, "long_setup_score")
    today = date.today()

    where = "computed_date = :dt"
    params: dict = {"dt": str(today), "lim": limit}

    if tag_filter == "long":
        where += " AND long_setup_score >= 50"
    elif tag_filter == "short":
        where += " AND short_setup_score >= 50"
    elif tag_filter == "near_52w_high":
        where += " AND pct_from_52w_high >= -5"
    elif tag_filter == "near_52w_low":
        where += " AND pct_from_52w_low <= 5"
    elif tag_filter in _FILTER_TAGS:
        where += " AND position_tag = :pt"
        params["pt"] = tag_filter

    rows = db.execute(
        text(f"""
            SELECT symbol, long_setup_score, short_setup_score,
                   best_demand_score, best_supply_score, position_tag,
                   price_at_compute, atr_at_compute, rvol_at_compute,
                   best_long_rr, best_short_rr, created_at,
                   pct_from_52w_high, pct_from_52w_low,
                   long_entry_price, short_entry_price,
                   ROW_NUMBER() OVER (ORDER BY {col} NULLS LAST) AS rank
            FROM zone_analysis_results
            WHERE {where}
            ORDER BY {col} NULLS LAST
            LIMIT :lim
        """),
        params,
    ).fetchall()

    def _dist(price, entry):
        if price and entry and price > 0:
            return round((price - entry) / price * 100, 1)
        return None

    return [
        {
            "rank":              int(r[16]),
            "symbol":            r[0],
            "long_setup_score":  r[1],
            "short_setup_score": r[2],
            "best_demand_score": r[3],
            "best_supply_score": r[4],
            "position_tag":      r[5],
            "price":             r[6],
            "atr":               r[7],
            "rvol":              r[8],
            "best_long_rr":      r[9],
            "best_short_rr":     r[10],
            "computed_at":       str(r[11]),
            "pct_from_52w_high": r[12],
            "pct_from_52w_low":  r[13],
            "dist_to_long":      _dist(r[6], r[14]),
            "dist_to_short":     _dist(r[6], r[15]),
        }
        for r in rows
    ]


def _run_recompute_bg() -> None:
    state = get_precompute_state()
    db = SessionLocal()
    try:
        ZonePrecomputer().run_all(db)
    except Exception as e:
        logger.exception("[zones/recompute-all] failed")
        state["error"] = str(e)
    finally:
        db.close()


@router.post("/zones/recompute-all")
def recompute_all(db: Session = Depends(get_db)):
    """Start background recompute of zones for all symbols."""
    state = get_precompute_state()
    if state.get("is_running"):
        return {"status": "already_running",
                "done": state["done"], "total": state["total"]}

    sym_count = db.execute(
        text("SELECT COUNT(DISTINCT symbol) FROM stock_prices_daily WHERE date >= CURRENT_DATE - INTERVAL '10 days'")
    ).scalar() or 0

    threading.Thread(target=_run_recompute_bg, daemon=True, name="zone-recompute").start()
    return {"status": "started", "symbol_count": sym_count}


@router.get("/zones/recompute-status")
def recompute_status():
    state = get_precompute_state()
    return {
        "done":       state.get("done", 0),
        "total":      state.get("total", 0),
        "finished":   state.get("finished", False),
        "is_running": state.get("is_running", False),
        "started_at": state.get("started_at"),
        "error":      state.get("error"),
    }


@router.get("/zones/chart-data/{symbol}")
def get_chart_data(
    symbol: str,
    bars: int = Query(120, ge=20, le=500),
    db: Session = Depends(get_db),
):
    """OHLCV bars + zone bands from latest stored result for the chart overlay."""
    rows = db.execute(
        text("""
            SELECT date, open, high, low, close, volume FROM (
                SELECT date, open, high, low, close, volume
                FROM stock_prices_daily
                WHERE symbol = :s
                ORDER BY date DESC LIMIT :b
            ) sub ORDER BY date ASC
        """),
        {"s": symbol.upper(), "b": bars},
    ).fetchall()
    if not rows:
        raise HTTPException(status_code=404, detail=f"No price data for {symbol}")

    ohlcv = [
        {
            "date":   str(r[0]),
            "open":   float(r[1]),
            "high":   float(r[2]),
            "low":    float(r[3]),
            "close":  float(r[4]),
            "volume": int(r[5]) if r[5] is not None else 0,
        }
        for r in rows
    ]

    # Load latest zone result (optional — chart still renders without zones)
    zone_row = db.execute(
        text("SELECT result_json FROM zone_analysis_results WHERE symbol = :s ORDER BY computed_date DESC LIMIT 1"),
        {"s": symbol.upper()},
    ).fetchone()

    result: dict = {"ohlcv": ohlcv}
    if zone_row:
        raw = zone_row[0]
        rj = raw if isinstance(raw, dict) else json.loads(raw)
        result["demand_bands"] = [
            {"low": z["low"], "high": z["high"], "strength": z.get("score", 0), "zone_type": "demand", "source": z.get("source", "daily")}
            for z in rj.get("demand_zones", [])
        ]
        result["supply_bands"] = [
            {"low": z["low"], "high": z["high"], "strength": z.get("score", 0), "zone_type": "supply", "source": z.get("source", "daily")}
            for z in rj.get("supply_zones", [])
        ]
        ls = rj.get("long_setup")
        ss = rj.get("short_setup")
        if ls and ls.get("ideal_entry") is not None:
            result["long_setup"]  = {"entry": ls["ideal_entry"], "stop_loss": ls["stop_loss"], "target": ls.get("t2")}
        if ss and ss.get("ideal_entry") is not None:
            result["short_setup"] = {"entry": ss["ideal_entry"], "stop_loss": ss["stop_loss"], "target": ss.get("t2")}

    return result


@router.post("/zones/backtest/run")
def run_backtest(
    symbol: str,
    from_date: str,
    to_date: str,
    db: Session = Depends(get_db),
):
    """Run walk-forward zone backtest for a symbol and store results."""
    from datetime import date as _date
    try:
        fd = _date.fromisoformat(from_date)
        td = _date.fromisoformat(to_date)
    except ValueError:
        raise HTTPException(status_code=422, detail="from_date and to_date must be YYYY-MM-DD")

    sym = symbol.upper()
    trades = ZoneBacktester().run(sym, fd, td, db)

    total = len(trades)
    wins  = sum(1 for t in trades if t.pnl_pct > 0)
    win_rate     = round(wins / total * 100, 1) if total else None
    total_pnl    = round(sum(t.pnl_pct for t in trades), 2)
    avg_hold     = round(sum(t.hold_days for t in trades) / total, 1) if total else None

    try:
        row = db.execute(
            text("""
                INSERT INTO zone_backtest_results
                    (symbol, from_date, to_date, total_trades, win_rate, total_pnl_pct, avg_hold_days)
                VALUES (:sym, :fd, :td, :tt, :wr, :tp, :ah)
                RETURNING id, ran_at
            """),
            {"sym": sym, "fd": fd, "td": td, "tt": total,
             "wr": win_rate, "tp": total_pnl, "ah": avg_hold},
        ).fetchone()
        result_id = row[0]
        ran_at    = str(row[1])

        if trades:
            db.execute(
                text("""
                    INSERT INTO zone_backtest_trades
                        (result_id, entry_date, entry_price, exit_date, exit_price,
                         pnl_pct, exit_reason, hold_days)
                    VALUES (:rid, :ed, :ep, :xd, :xp, :pp, :er, :hd)
                """),
                [{"rid": result_id, "ed": t.entry_date, "ep": t.entry_price,
                  "xd": t.exit_date, "xp": t.exit_price, "pp": t.pnl_pct,
                  "er": t.exit_reason, "hd": t.hold_days}
                 for t in trades],
            )
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("[run_backtest] DB write failed for %s", sym)
        raise HTTPException(status_code=500, detail="Failed to persist backtest results")

    return {
        "id":            result_id,
        "symbol":        sym,
        "from_date":     str(fd),
        "to_date":       str(td),
        "total_trades":  total,
        "win_rate":      win_rate,
        "total_pnl_pct": total_pnl,
        "avg_hold_days": avg_hold,
        "ran_at":        ran_at,
    }


@router.get("/zones/backtest/results/{symbol}")
def get_backtest_results(symbol: str, db: Session = Depends(get_db)):
    """List past backtest runs for a symbol, newest first."""
    rows = db.execute(
        text("""
            SELECT id, symbol, from_date, to_date, total_trades, win_rate,
                   total_pnl_pct, avg_hold_days, ran_at
            FROM zone_backtest_results
            WHERE symbol = :s
            ORDER BY ran_at DESC
            LIMIT 20
        """),
        {"s": symbol.upper()},
    ).fetchall()
    return [
        {
            "id":            r[0], "symbol": r[1],
            "from_date":     str(r[2]), "to_date": str(r[3]),
            "total_trades":  r[4], "win_rate": r[5],
            "total_pnl_pct": r[6], "avg_hold_days": r[7],
            "ran_at":        str(r[8]),
        }
        for r in rows
    ]


@router.get("/zones/backtest/trades/{result_id}")
def get_backtest_trades(result_id: int, db: Session = Depends(get_db)):
    """Full trade list for a stored backtest result."""
    rows = db.execute(
        text("""
            SELECT id, entry_date, entry_price, exit_date, exit_price,
                   pnl_pct, exit_reason, hold_days
            FROM zone_backtest_trades
            WHERE result_id = :rid
            ORDER BY entry_date ASC
        """),
        {"rid": result_id},
    ).fetchall()
    return [
        {
            "id":           r[0],
            "entry_date":   str(r[1]), "entry_price":  r[2],
            "exit_date":    str(r[3]) if r[3] else None, "exit_price": r[4],
            "pnl_pct":      r[5], "exit_reason":  r[6], "hold_days":  r[7],
        }
        for r in rows
    ]
