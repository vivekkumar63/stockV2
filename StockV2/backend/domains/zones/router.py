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
from .breakout_scanner import BreakoutScanner
from .breakout_backtester import BreakoutBacktester
from .breakout_ml import BreakoutMLScorer as BreakoutML
from .ml_scorer import MLZoneScorer, _build_reason
from domains.data.nse_universe import NSE_SYMBOLS

router = APIRouter(tags=["zones"])
logger = logging.getLogger(__name__)

_recompute_lock = threading.Lock()

# ── All-stocks backtest state ─────────────────────────────────────────────────
_bt_all_lock    = threading.Lock()
_bt_all_state: dict = {"running": False, "done": 0, "total": 0, "errors": 0, "finished": False}

# ── Breakout-candidates backtest state ────────────────────────────────────────
_bt_breakout_lock  = threading.Lock()
_bt_breakout_state: dict = {"running": False, "done": 0, "total": 0, "errors": 0, "finished": False}


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
        "candle_signal":    r.candle_signal,
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
    result.setdefault("candle_signal", "NONE")  # populated for newly analyzed results
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
    min_rr: float   = Query(None, ge=0.5, le=10.0),
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

    if min_rr is not None:
        where += " AND (best_long_rr >= :min_rr OR best_short_rr >= :min_rr)"
        params["min_rr"] = min_rr

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
            "ml_confidence":     MLZoneScorer.predict({
                "long_setup_score": r[1], "short_setup_score": r[2],
                "best_demand_score": r[3], "best_supply_score": r[4],
                "best_long_rr": r[9], "best_short_rr": r[10],
                "rvol_at_compute": r[8], "position_tag": r[5],
                "pct_from_52w_low": r[13], "pct_from_52w_high": r[12],
            }),
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


# ── All-stocks backtest ───────────────────────────────────────────────────────

@router.get("/zones/backtest/symbols")
def get_backtest_symbols():
    """Return the full NSE universe symbol list for the combo box."""
    return {"symbols": NSE_SYMBOLS}


def _run_bt_all_bg(from_date: date, to_date: date) -> None:
    global _bt_all_state
    symbols = list(NSE_SYMBOLS)
    with _bt_all_lock:
        _bt_all_state = {"running": True, "done": 0, "total": len(symbols),
                         "errors": 0, "finished": False}

    backtester = ZoneBacktester()
    for sym in symbols:
        db = SessionLocal()
        try:
            trades = backtester.run(sym, from_date, to_date, db)
            total = len(trades)
            wins  = sum(1 for t in trades if t.pnl_pct > 0)
            win_rate  = round(wins / total * 100, 1) if total else None
            total_pnl = round(sum(t.pnl_pct for t in trades), 2)
            avg_hold  = round(sum(t.hold_days for t in trades) / total, 1) if total else None

            db.execute(
                text("""
                    INSERT INTO zone_backtest_results
                        (symbol, from_date, to_date, total_trades, win_rate, total_pnl_pct, avg_hold_days)
                    VALUES (:sym, :fd, :td, :tt, :wr, :tp, :ah)
                """),
                {"sym": sym, "fd": from_date, "td": to_date, "tt": total,
                 "wr": win_rate, "tp": total_pnl, "ah": avg_hold},
            )
            if trades:
                result_id = db.execute(
                    text("SELECT id FROM zone_backtest_results WHERE symbol=:s AND from_date=:fd AND to_date=:td ORDER BY ran_at DESC LIMIT 1"),
                    {"s": sym, "fd": from_date, "td": to_date},
                ).scalar()
                if result_id:
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
            logger.exception("[bt-all] failed for %s", sym)
            with _bt_all_lock:
                _bt_all_state["errors"] += 1
        finally:
            db.close()
        with _bt_all_lock:
            _bt_all_state["done"] += 1

    with _bt_all_lock:
        _bt_all_state["running"]  = False
        _bt_all_state["finished"] = True
    logger.info("[bt-all] complete: %d/%d symbols, %d errors",
                _bt_all_state["done"], _bt_all_state["total"], _bt_all_state["errors"])


@router.post("/zones/backtest/run-all")
def run_backtest_all(from_date: str, to_date: str):
    """Start a background backtest run for all NSE symbols."""
    global _bt_all_state
    with _bt_all_lock:
        if _bt_all_state.get("running"):
            return {"status": "already_running", **_bt_all_state}
    try:
        fd = date.fromisoformat(from_date)
        td = date.fromisoformat(to_date)
    except ValueError:
        raise HTTPException(status_code=422, detail="Dates must be YYYY-MM-DD")

    threading.Thread(
        target=_run_bt_all_bg, args=(fd, td), daemon=True, name="zone-bt-all"
    ).start()
    return {"status": "started", "symbol_count": len(NSE_SYMBOLS)}


@router.get("/zones/backtest/run-all/status")
def get_backtest_all_status():
    with _bt_all_lock:
        return dict(_bt_all_state)


@router.get("/zones/backtest/all-results")
def get_all_backtest_results(db: Session = Depends(get_db)):
    """Return the most recent backtest result per symbol, sorted by total_pnl_pct desc."""
    rows = db.execute(text("""
        SELECT DISTINCT ON (symbol)
            id, symbol, from_date, to_date, total_trades, win_rate, total_pnl_pct, avg_hold_days, ran_at
        FROM zone_backtest_results
        ORDER BY symbol, ran_at DESC
    """)).fetchall()
    results = [
        {
            "id":            r[0], "symbol": r[1],
            "from_date":     str(r[2]), "to_date": str(r[3]),
            "total_trades":  r[4], "win_rate": r[5],
            "total_pnl_pct": r[6], "avg_hold_days": r[7],
            "ran_at":        str(r[8]),
        }
        for r in rows
    ]
    results.sort(key=lambda x: x["total_pnl_pct"] or 0, reverse=True)
    return results


# ── Breakout scanner ──────────────────────────────────────────────────────────

@router.get("/zones/breakout/scan")
def scan_breakouts(db: Session = Depends(get_db)):
    """Scan today's precomputed zone data for breakout signals with conviction scoring."""
    return BreakoutScanner().scan(db)


# ── Breakout signal backtesting ───────────────────────────────────────────────

def _store_breakout_backtest(db: Session, symbol: str, from_date: date,
                              to_date: date, trades) -> int:
    total    = len(trades)
    wins     = sum(1 for t in trades if t.pnl_pct > 0)
    win_rate = round(wins / total * 100, 1) if total else None
    total_pnl = round(sum(t.pnl_pct for t in trades), 2)
    avg_pnl   = round(total_pnl / total, 2) if total else None

    db.execute(text("""
        INSERT INTO breakout_backtest_results
            (symbol, from_date, to_date, total_trades, win_rate, total_pnl, avg_pnl_pct)
        VALUES (:sym, :fd, :td, :tt, :wr, :tp, :ap)
    """), {"sym": symbol, "fd": from_date, "td": to_date, "tt": total,
           "wr": win_rate, "tp": total_pnl, "ap": avg_pnl})

    rid = db.execute(
        text("SELECT id FROM breakout_backtest_results WHERE symbol=:s AND from_date=:fd AND to_date=:td ORDER BY ran_at DESC LIMIT 1"),
        {"s": symbol, "fd": from_date, "td": to_date},
    ).scalar()

    if rid and trades:
        db.execute(text("""
            INSERT INTO breakout_backtest_trades
                (result_id, entry_date, entry_price, resistance, exit_date, exit_price,
                 pnl_pct, exit_reason, hold_days,
                 volume_ratio, rsi, body_ratio, range_atr_ratio,
                 conviction_score, breakout_pct, ema50_slope_pct)
            VALUES (:rid, :ed, :ep, :res, :xd, :xp, :pp, :er, :hd,
                    :vr, :rsi, :br, :rar, :cs, :bpct, :slope)
        """), [{
            "rid": rid, "ed": t.entry_date, "ep": t.entry_price,
            "res": t.resistance, "xd": t.exit_date, "xp": t.exit_price,
            "pp": t.pnl_pct, "er": t.exit_reason, "hd": t.hold_days,
            "vr": t.volume_ratio, "rsi": t.rsi, "br": t.body_ratio,
            "rar": t.range_atr_ratio, "cs": t.conviction_score,
            "bpct": t.breakout_pct, "slope": t.ema50_slope_pct,
        } for t in trades])
    db.commit()
    return rid or 0


def _run_bt_breakout_bg(symbols: list[str], from_date: date, to_date: date) -> None:
    global _bt_breakout_state
    with _bt_breakout_lock:
        _bt_breakout_state = {
            "running": True, "done": 0, "total": len(symbols),
            "errors": 0, "finished": False,
        }

    backtester = BreakoutBacktester()
    for sym in symbols:
        db = SessionLocal()
        try:
            trades = backtester.run(sym, from_date, to_date, db)
            _store_breakout_backtest(db, sym, from_date, to_date, trades)
        except Exception:
            db.rollback()
            logger.exception("[bt-breakout] failed for %s", sym)
            with _bt_breakout_lock:
                _bt_breakout_state["errors"] += 1
        finally:
            db.close()
        with _bt_breakout_lock:
            _bt_breakout_state["done"] += 1

    with _bt_breakout_lock:
        _bt_breakout_state["running"]  = False
        _bt_breakout_state["finished"] = True
    logger.info("[bt-breakout] complete: %d/%d", _bt_breakout_state["done"], _bt_breakout_state["total"])


@router.post("/zones/breakout/backtest")
def run_breakout_backtest_single(symbol: str, from_date: str, to_date: str,
                                  db: Session = Depends(get_db)):
    """Backtest the breakout signal strategy for a single symbol."""
    try:
        fd = date.fromisoformat(from_date)
        td = date.fromisoformat(to_date)
    except ValueError:
        raise HTTPException(status_code=422, detail="Dates must be YYYY-MM-DD")

    sym = symbol.upper().strip()
    trades = BreakoutBacktester().run(sym, fd, td, db)
    rid = _store_breakout_backtest(db, sym, fd, td, trades)

    total    = len(trades)
    wins     = sum(1 for t in trades if t.pnl_pct > 0)
    win_rate = round(wins / total * 100, 1) if total else None
    return {
        "result_id":   rid,
        "symbol":      sym,
        "total_trades": total,
        "win_rate":    win_rate,
        "total_pnl":   round(sum(t.pnl_pct for t in trades), 2),
        "avg_pnl_pct": round(sum(t.pnl_pct for t in trades) / total, 2) if total else None,
        "trades": [{
            "entry_date":   str(t.entry_date),
            "entry_price":  t.entry_price,
            "resistance":   t.resistance,
            "exit_date":    str(t.exit_date),
            "exit_price":   t.exit_price,
            "pnl_pct":      t.pnl_pct,
            "exit_reason":  t.exit_reason,
            "hold_days":    t.hold_days,
            "conviction":   t.conviction_score,
            "volume_ratio": t.volume_ratio,
            "rsi":          t.rsi,
        } for t in trades],
    }


@router.post("/zones/breakout/backtest-all")
def run_breakout_backtest_all(from_date: str, to_date: str):
    """Backtest the breakout signal strategy across all NSE stocks."""
    global _bt_breakout_state
    with _bt_breakout_lock:
        if _bt_breakout_state.get("running"):
            return {"status": "already_running", **_bt_breakout_state}
    try:
        fd = date.fromisoformat(from_date)
        td = date.fromisoformat(to_date)
    except ValueError:
        raise HTTPException(status_code=422, detail="Dates must be YYYY-MM-DD")

    symbols = list(NSE_SYMBOLS)
    threading.Thread(
        target=_run_bt_breakout_bg, args=(symbols, fd, td), daemon=True, name="zone-bt-breakout"
    ).start()
    return {"status": "started", "total": len(symbols)}


@router.get("/zones/breakout/backtest-all/status")
def get_breakout_backtest_status():
    with _bt_breakout_lock:
        return dict(_bt_breakout_state)


@router.get("/zones/breakout/backtest-results")
def get_breakout_backtest_results(db: Session = Depends(get_db)):
    """Latest breakout backtest result per symbol, sorted by total_pnl desc."""
    rows = db.execute(text("""
        SELECT DISTINCT ON (symbol)
            id, symbol, from_date, to_date, total_trades, win_rate, total_pnl, avg_pnl_pct, ran_at
        FROM breakout_backtest_results
        ORDER BY symbol, ran_at DESC
    """)).fetchall()

    results = [{
        "id": r[0], "symbol": r[1],
        "from_date": str(r[2]), "to_date": str(r[3]),
        "total_trades": r[4], "win_rate": r[5],
        "total_pnl": r[6], "avg_pnl_pct": r[7],
        "ran_at": str(r[8]),
    } for r in rows]
    results.sort(key=lambda x: x["total_pnl"] or 0, reverse=True)
    return results


@router.get("/zones/breakout/backtest-results/{result_id}/trades")
def get_breakout_backtest_trades(result_id: int, db: Session = Depends(get_db)):
    rows = db.execute(text("""
        SELECT entry_date, entry_price, resistance, exit_date, exit_price,
               pnl_pct, exit_reason, hold_days, volume_ratio, rsi, conviction_score
        FROM breakout_backtest_trades
        WHERE result_id = :rid
        ORDER BY entry_date
    """), {"rid": result_id}).fetchall()
    return [{
        "entry_date": str(r[0]), "entry_price": r[1], "resistance": r[2],
        "exit_date": str(r[3]) if r[3] else None, "exit_price": r[4],
        "pnl_pct": r[5], "exit_reason": r[6], "hold_days": r[7],
        "volume_ratio": r[8], "rsi": r[9], "conviction_score": r[10],
    } for r in rows]


# ── Breakout ML ───────────────────────────────────────────────────────────────

@router.post("/zones/breakout/ml/train")
def train_breakout_ml(db: Session = Depends(get_db)):
    """Train the breakout ML model on stored breakout_backtest_trades."""
    return BreakoutML.train(db)


@router.get("/zones/breakout/ml/status")
def get_breakout_ml_status():
    from .breakout_ml import MODEL_PATH
    return {
        "model_exists": BreakoutML.model_exists(),
        "model_path":   str(MODEL_PATH),
        "using_ml":     BreakoutML.model_exists(),
        "note":         "Rule-based fallback active" if not BreakoutML.model_exists()
                        else "ML model active",
    }


# ── ML Zone Scorer ────────────────────────────────────────────────────────────

@router.post("/zones/ml/train")
def train_ml_model(db: Session = Depends(get_db)):
    """Train (or retrain) the ML zone quality model on stored backtest outcomes."""
    return MLZoneScorer.train(db)


@router.get("/zones/ml/status")
def get_ml_status():
    """Return whether a trained model exists and its path."""
    from .ml_scorer import MODEL_PATH
    return {
        "model_exists": MLZoneScorer.model_exists(),
        "model_path":   str(MODEL_PATH),
        "using_ml":     MLZoneScorer.model_exists(),
        "note":         "Rule-based fallback active" if not MLZoneScorer.model_exists()
                        else "ML model active",
    }


# ── Recommendations ───────────────────────────────────────────────────────────

@router.get("/zones/recommendations")
def get_recommendations(
    limit: int    = Query(20, ge=5, le=50),
    setup_type: str = Query("long"),
    db: Session   = Depends(get_db),
):
    """Top zone setups ranked by composite score (ML confidence × zone quality × R:R × volume)."""
    today = str(date.today())

    if setup_type == "short":
        score_filter = "short_setup_score >= 50"
        score_col    = "short_setup_score"
    else:
        score_filter = "long_setup_score >= 50"
        score_col    = "long_setup_score"

    rows = db.execute(text(f"""
        SELECT symbol, long_setup_score, short_setup_score, best_demand_score,
               best_supply_score, best_long_rr, best_short_rr, rvol_at_compute,
               position_tag, pct_from_52w_low, pct_from_52w_high,
               price_at_compute, atr_at_compute, result_json
        FROM zone_analysis_results
        WHERE computed_date = :dt AND {score_filter}
        ORDER BY {score_col} DESC NULLS LAST
        LIMIT 200
    """), {"dt": today}).fetchall()

    out = []
    for r in rows:
        row_dict = {
            "long_setup_score":  r[1], "short_setup_score": r[2],
            "best_demand_score": r[3], "best_supply_score": r[4],
            "best_long_rr": r[5], "best_short_rr": r[6],
            "rvol_at_compute": r[7], "position_tag": r[8],
            "pct_from_52w_low": r[9], "pct_from_52w_high": r[10],
        }
        ml_conf = MLZoneScorer.predict(row_dict)

        rj = r[13] if isinstance(r[13], dict) else json.loads(r[13] or "{}")
        ls = (r[1] or 0) / 100.0
        rr = min((r[5] or 0), 5) / 5.0
        rv = min((r[7] or 1.0), 3.0) / 3.0
        # Weighted composite: ML 40%, zone setup 30%, R:R 20%, volume 10%
        composite = round((0.40 * ml_conf + 0.30 * ls + 0.20 * rr + 0.10 * rv) * 100, 1)

        out.append({
            "symbol":            r[0],
            "composite_score":   composite,
            "ml_confidence":     round(ml_conf * 100, 1),
            "long_setup_score":  r[1],
            "short_setup_score": r[2],
            "best_long_rr":      r[5],
            "best_short_rr":     r[6],
            "rvol":              r[7],
            "position_tag":      r[8],
            "price":             r[11],
            "atr":               r[12],
            "pct_from_52w_high": r[10],
            "pct_from_52w_low":  r[9],
            "long_setup":        rj.get("long_setup"),
            "short_setup":       rj.get("short_setup"),
            "demand_zones":      rj.get("demand_zones", [])[:2],
            "supply_zones":      rj.get("supply_zones", [])[:2],
            "market_structure":  rj.get("market_structure", "sideways"),
            "candle_signal":     rj.get("candle_signal", "NONE"),
            "reason":            _build_reason(row_dict, ml_conf, rj),
        })

    out.sort(key=lambda x: x["composite_score"], reverse=True)
    return out[:limit]
