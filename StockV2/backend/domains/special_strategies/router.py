import json
import logging
import os
import threading
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from database import get_db, SessionLocal
from domains.special_strategies import ALL_SPECIAL_STRATEGIES
from domains.special_strategies.ml_scorer import (
    SpecialMLScorer, special_regime_to_code,
    MODEL_PATH as SPECIAL_ML_MODEL_PATH,
    METRICS_PATH as SPECIAL_ML_METRICS_PATH,
    MIN_TRAINING_SAMPLES as SPECIAL_ML_MIN_SAMPLES,
)
from domains.special_strategies.scanner import SpecialScanner
from domains.special_strategies.simulator import SpecialSimulator

router = APIRouter(tags=["special_strategies"])
logger = logging.getLogger(__name__)

# ── Precompute state ──────────────────────────────────────────────────────────
_precompute_state: dict = {
    "is_running": False,
    "done": 0,
    "total": 0,
    "phase": "idle",
    "message": "Not started",
    "error": None,
}
_precompute_lock = threading.Lock()


# ── Request / Response models ─────────────────────────────────────────────────

class SpecialScanRequest(BaseModel):
    strategy_id: Optional[int] = None


class SpecialBacktestRequest(BaseModel):
    symbol: str
    from_date: date
    to_date: date
    special_strategy_id: int
    initial_capital: float = 500_000.0


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_prices(db: Session, symbol: str):
    import pandas as pd
    rows = db.execute(
        text("""
            SELECT date, open, high, low, close, volume
            FROM stock_prices_daily
            WHERE symbol = :s
            ORDER BY date ASC
        """),
        {"s": symbol},
    ).fetchall()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"])
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = df[col].astype(float)
    return df


def _id_map(db: Session) -> dict[str, int]:
    rows = db.execute(text("SELECT name, id FROM special_strategies")).fetchall()
    return {r[0]: r[1] for r in rows}


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/special/strategies")
def list_special_strategies(db: Session = Depends(get_db)):
    rows = db.execute(
        text("SELECT id, name, description, is_active FROM special_strategies ORDER BY name")
    ).fetchall()
    return [{"id": r[0], "name": r[1], "description": r[2], "is_active": r[3]} for r in rows]


@router.post("/special/scan")
def special_scan(req: SpecialScanRequest, db: Session = Depends(get_db)):
    scanner = SpecialScanner(db)
    return scanner.scan(strategy_id=req.strategy_id)


@router.post("/special/backtest/run")
def special_backtest_run(req: SpecialBacktestRequest, db: Session = Depends(get_db)):
    id_to_name = {v: k for k, v in _id_map(db).items()}
    strat_name = id_to_name.get(req.special_strategy_id)
    if not strat_name:
        raise HTTPException(status_code=404, detail="Special strategy not found")

    strategy = next((s for s in ALL_SPECIAL_STRATEGIES if s.name == strat_name), None)
    if strategy is None:
        raise HTTPException(status_code=404, detail="Special strategy implementation not found")

    prices_df = _load_prices(db, req.symbol)
    if prices_df.empty:
        raise HTTPException(status_code=404, detail=f"No price data for {req.symbol}")

    simulator = SpecialSimulator()
    trades = simulator.run(
        symbol=req.symbol,
        prices_df=prices_df,
        from_date=req.from_date,
        to_date=req.to_date,
        strategy=strategy,
        initial_capital=req.initial_capital,
    )

    # Compute metrics
    total_trades = len(trades)
    wins = [t for t in trades if t.pnl > 0]
    win_rate = round(len(wins) / total_trades * 100, 2) if total_trades else None
    total_pnl = round(sum(t.pnl for t in trades), 2)
    avg_pnl_pct = round(sum(t.pnl_pct for t in trades) / total_trades, 2) if total_trades else None

    # Persist result
    result_row = db.execute(
        text("""
            INSERT INTO special_backtest_results
                (special_strategy_id, symbol, from_date, to_date, total_trades, win_rate, total_pnl, avg_pnl_pct)
            VALUES (:sid, :sym, :fd, :td, :tt, :wr, :pnl, :apct)
            RETURNING id
        """),
        {
            "sid": req.special_strategy_id,
            "sym": req.symbol,
            "fd": req.from_date,
            "td": req.to_date,
            "tt": total_trades,
            "wr": win_rate,
            "pnl": total_pnl,
            "apct": avg_pnl_pct,
        },
    ).fetchone()
    result_id = result_row[0]

    # Persist trades
    for t in trades:
        db.execute(
            text("""
                INSERT INTO special_backtest_trades
                    (backtest_result_id, symbol, entry_date, entry_price, exit_date, exit_price,
                     quantity, pnl, pnl_pct, exit_reason, holding_days)
                VALUES (:rid, :sym, :ed, :ep, :xd, :xp, :qty, :pnl, :pct, :reason, :hd)
            """),
            {
                "rid": result_id,
                "sym": t.symbol,
                "ed": t.entry_date,
                "ep": t.entry_price,
                "xd": t.exit_date,
                "xp": t.exit_price,
                "qty": t.quantity,
                "pnl": t.pnl,
                "pct": t.pnl_pct,
                "reason": t.exit_reason,
                "hd": t.holding_days,
            },
        )
    db.commit()

    logger.info("[special_backtest] %s/%s: %d trades, win_rate=%.1f%%", req.symbol, strat_name, total_trades, win_rate or 0)
    return {
        "id": result_id,
        "special_strategy_id": req.special_strategy_id,
        "symbol": req.symbol,
        "from_date": req.from_date,
        "to_date": req.to_date,
        "total_trades": total_trades,
        "win_rate": win_rate,
        "total_pnl": total_pnl,
        "avg_pnl_pct": avg_pnl_pct,
    }


@router.get("/special/backtest/results")
def list_special_backtest_results(db: Session = Depends(get_db)):
    rows = db.execute(
        text("""
            SELECT r.id, r.special_strategy_id, s.name, r.symbol,
                   r.from_date, r.to_date, r.total_trades, r.win_rate,
                   r.total_pnl, r.avg_pnl_pct, r.ran_at
            FROM special_backtest_results r
            JOIN special_strategies s ON s.id = r.special_strategy_id
            ORDER BY r.ran_at DESC
        """)
    ).fetchall()
    return [
        {
            "id": r[0],
            "special_strategy_id": r[1],
            "strategy_name": r[2],
            "symbol": r[3],
            "from_date": r[4],
            "to_date": r[5],
            "total_trades": r[6],
            "win_rate": r[7],
            "total_pnl": r[8],
            "avg_pnl_pct": r[9],
            "ran_at": r[10],
        }
        for r in rows
    ]


@router.get("/special/backtest/results/{result_id}/trades")
def get_special_backtest_trades(result_id: int, db: Session = Depends(get_db)):
    rows = db.execute(
        text("""
            SELECT id, symbol, entry_date, entry_price, exit_date, exit_price,
                   quantity, pnl, pnl_pct, exit_reason, holding_days
            FROM special_backtest_trades
            WHERE backtest_result_id = :rid
            ORDER BY entry_date ASC
        """),
        {"rid": result_id},
    ).fetchall()
    return [
        {
            "id": r[0],
            "symbol": r[1],
            "entry_date": r[2],
            "entry_price": r[3],
            "exit_date": r[4],
            "exit_price": r[5],
            "quantity": r[6],
            "pnl": r[7],
            "pnl_pct": r[8],
            "exit_reason": r[9],
            "holding_days": r[10],
        }
        for r in rows
    ]


# ── Precompute endpoints ──────────────────────────────────────────────────────

def _run_precompute_bg(force: bool) -> None:
    global _precompute_state
    with _precompute_lock:
        _precompute_state.update(is_running=True, done=0, total=0,
                                  phase="starting", message="Initializing…", error=None)
    db = SessionLocal()
    try:
        from domains.special_strategies.runner import SpecialBacktestRunner
        SpecialBacktestRunner(db).precompute_all(force=force, _state=_precompute_state)
    except Exception as e:
        logger.exception("[special_precompute] failed")
        _precompute_state["error"] = str(e)
    finally:
        _precompute_state["is_running"] = False
        db.close()


@router.post("/special/precompute")
def trigger_special_precompute(force: bool = False, db: Session = Depends(get_db)):
    if _precompute_state.get("is_running"):
        return {"status": "already_running", "message": "Precompute already in progress"}
    threading.Thread(target=_run_precompute_bg, args=(force,), daemon=True,
                     name="special-precompute").start()
    n_strats = len(ALL_SPECIAL_STRATEGIES)
    return {
        "status": "started",
        "strategies_queued": n_strats,
        "force": force,
        "message": f"Precomputing {n_strats} special strategies across all symbols in background",
    }


@router.get("/special/precompute/status")
def get_special_precompute_status(db: Session = Depends(get_db)):
    done = _precompute_state.get("done", 0)
    total = _precompute_state.get("total", 0)
    pct = round(done / total * 100, 1) if total > 0 else 0.0

    pair_count = db.execute(
        text("SELECT COUNT(*) FROM special_strategy_performance")
    ).scalar() or 0
    sym_count = db.execute(
        text("SELECT COUNT(DISTINCT symbol) FROM special_strategy_performance")
    ).scalar() or 0
    last_updated = db.execute(
        text("SELECT MAX(computed_at) FROM special_strategy_performance")
    ).scalar()

    return {
        "is_running": _precompute_state.get("is_running", False),
        "done": done,
        "total": total,
        "pct_done": pct,
        "phase": _precompute_state.get("phase", "idle"),
        "message": _precompute_state.get("message", ""),
        "error": _precompute_state.get("error"),
        "symbol_strategy_pairs": pair_count,
        "symbols_computed": sym_count,
        "total_active_strategies": len(ALL_SPECIAL_STRATEGIES),
        "last_updated": str(last_updated) if last_updated else None,
    }


@router.get("/special/performance/trades")
def get_special_performance_trades(strategy_id: int, symbol: str, db: Session = Depends(get_db)):
    """Return cached trades for a precomputed (strategy, symbol) pair."""
    rows = db.execute(
        text("""
            SELECT id, entry_date, entry_price, exit_date, exit_price,
                   quantity, pnl, pnl_pct, exit_reason, holding_days
            FROM special_strategy_trades
            WHERE special_strategy_id = :sid AND symbol = :sym
            ORDER BY entry_date ASC
        """),
        {"sid": strategy_id, "sym": symbol},
    ).fetchall()
    return [
        {
            "id": r[0], "symbol": symbol,
            "entry_date": r[1], "entry_price": r[2],
            "exit_date": r[3], "exit_price": r[4],
            "quantity": r[5], "pnl": r[6], "pnl_pct": r[7],
            "exit_reason": r[8], "holding_days": r[9],
        }
        for r in rows
    ]


def _enrich_with_performance(signals: list[dict], db: Session) -> list[dict]:
    """Join scan signals with precomputed performance metrics and ML probability."""
    if not signals:
        return []
    strategy_ids = list({s["strategy_id"] for s in signals if s["strategy_id"] is not None})
    perf_rows = db.execute(
        text("""
            SELECT symbol, special_strategy_id, total_trades, win_rate, cagr,
                   sharpe_ratio, max_drawdown, profit_factor, total_pnl, avg_pnl_pct
            FROM special_strategy_performance
            WHERE special_strategy_id = ANY(:sids)
        """),
        {"sids": strategy_ids},
    ).fetchall()
    perf_map: dict[tuple, tuple] = {(r[0], r[1]): r for r in perf_rows}

    regime_row = db.execute(
        text("SELECT regime FROM market_regime ORDER BY date DESC LIMIT 1")
    ).fetchone()
    regime_code = special_regime_to_code(regime_row[0]) if regime_row else 3

    scorer = SpecialMLScorer()
    today = date.today()

    result = []
    for s in signals:
        p = perf_map.get((s["symbol"], s["strategy_id"]))
        ml_prob = None
        if s["strategy_id"] is not None:
            ml_prob = scorer.predict({
                "strategy_id": s["strategy_id"],
                "entry_month": today.month,
                "entry_dow": today.weekday(),
                "regime_code": regime_code,
                "strategy_avg_win_rate":  float(p[3]) if p and p[3] is not None else 0.5,
                "strategy_profit_factor": float(p[7]) if p and p[7] is not None else 1.0,
                "strategy_avg_pnl_pct":   float(p[9]) if p and p[9] is not None else 0.0,
            }, db=db, symbol=s["symbol"])
        result.append({
            **s,
            "total_trades":   p[2] if p else None,
            "win_rate":       p[3] if p else None,
            "cagr":           p[4] if p else None,
            "sharpe_ratio":   p[5] if p else None,
            "max_drawdown":   p[6] if p else None,
            "profit_factor":  p[7] if p else None,
            "total_pnl":      p[8] if p else None,
            "avg_pnl_pct":    p[9] if p else None,
            "ml_probability": ml_prob,
        })
    result.sort(key=lambda r: (r["win_rate"] or 0, r["confidence"]), reverse=True)
    return result


def _add_earnings_days(results: list[dict], db: Session, today: date) -> None:
    """Inject days_to_earnings into each result dict in-place. Silently skips on error."""
    try:
        ec_rows = db.execute(text("""
            SELECT symbol, MIN(result_date) AS next_result
            FROM earnings_calendar
            WHERE result_date BETWEEN :today AND :cutoff
            GROUP BY symbol
        """), {"today": str(today), "cutoff": str(today + timedelta(days=30))}).fetchall()
        earnings_map: dict[str, int] = {}
        for ec in ec_rows:
            rd = ec[1]
            if isinstance(rd, str):
                rd = date.fromisoformat(rd[:10])
            earnings_map[ec[0]] = (rd - today).days
    except Exception:
        earnings_map = {}
    for r in results:
        r["days_to_earnings"] = earnings_map.get(r.get("symbol"))


def _save_scan_cache(signals: list[dict], scan_date: date, db: Session) -> None:
    db.execute(text("""
        INSERT INTO special_scan_cache (scan_date, results_json, scanned_at)
        VALUES (:d, :j, CURRENT_TIMESTAMP)
        ON CONFLICT (scan_date) DO UPDATE SET
            results_json = EXCLUDED.results_json,
            scanned_at   = CURRENT_TIMESTAMP
    """), {"d": str(scan_date), "j": json.dumps(signals)})
    db.commit()


@router.get("/special/recommendations")
def get_special_recommendations(force: bool = False, db: Session = Depends(get_db)):
    """Return today's BUY signals enriched with historical performance.

    Results are cached per calendar day. Pass ?force=true to bypass the cache
    and re-run the live scan (also updates the cache).
    """
    today = date.today()

    if not force:
        row = db.execute(
            text("SELECT results_json, scanned_at FROM special_scan_cache WHERE scan_date = :d"),
            {"d": str(today)},
        ).fetchone()
        if row:
            cached = json.loads(row[0])
            _add_earnings_days(cached, db, today)
            return {"scanned_at": str(row[1]), "results": cached}

    # Cache miss or force — run live scan
    scanner = SpecialScanner(db)
    signals = scanner.scan()
    result = _enrich_with_performance(signals, db)
    _save_scan_cache(result, today, db)
    _add_earnings_days(result, db, today)
    scanned_at = db.execute(
        text("SELECT scanned_at FROM special_scan_cache WHERE scan_date = :d"), {"d": str(today)}
    ).scalar()
    return {"scanned_at": str(scanned_at), "results": result}


@router.get("/special/scan/results")
def get_special_scan_results(
    strategy_id: Optional[int] = None,
    min_trades: int = 0,
    db: Session = Depends(get_db),
):
    """Return precomputed (symbol, strategy) performance rows, optionally filtered."""
    params: dict = {"mt": min_trades}
    where = "p.total_trades >= :mt"
    if strategy_id is not None:
        where += " AND p.special_strategy_id = :sid"
        params["sid"] = strategy_id

    rows = db.execute(
        text(f"""
            SELECT p.symbol, p.special_strategy_id, s.name,
                   p.total_trades, p.win_rate, p.cagr, p.sharpe_ratio,
                   p.max_drawdown, p.profit_factor, p.total_pnl, p.avg_pnl_pct, p.to_date
            FROM special_strategy_performance p
            JOIN special_strategies s ON s.id = p.special_strategy_id
            WHERE {where}
            ORDER BY p.win_rate DESC NULLS LAST
        """),
        params,
    ).fetchall()

    return [
        {
            "symbol": r[0],
            "strategy_id": r[1],
            "strategy_name": r[2],
            "total_trades": r[3],
            "win_rate": r[4],
            "cagr": r[5],
            "sharpe_ratio": r[6],
            "max_drawdown": r[7],
            "profit_factor": r[8],
            "total_pnl": r[9],
            "avg_pnl_pct": r[10],
            "to_date": r[11],
        }
        for r in rows
    ]


# ── ML Model management ───────────────────────────────────────────────────────

@router.get("/special/ml-status")
def get_special_ml_status(db: Session = Depends(get_db)):
    """Model file existence, last-trained timestamp, sample count, and quality metrics."""
    exists = os.path.exists(SPECIAL_ML_MODEL_PATH)
    last_trained = None
    metrics: dict = {}
    if exists:
        last_trained = datetime.fromtimestamp(os.path.getmtime(SPECIAL_ML_MODEL_PATH)).isoformat()
        if os.path.exists(SPECIAL_ML_METRICS_PATH):
            with open(SPECIAL_ML_METRICS_PATH) as f:
                metrics = json.load(f)
    samples = db.execute(
        text("""
            SELECT COUNT(*) FROM special_strategy_trades
            WHERE entry_date IS NOT NULL AND pnl_pct IS NOT NULL
        """)
    ).scalar() or 0
    return {
        "exists": exists,
        "last_trained": last_trained,
        "samples_available": int(samples),
        "auc_roc": metrics.get("auc_roc"),
        "precision_at_60": metrics.get("precision_at_60"),
        "high_conf_signals": metrics.get("high_conf_signals"),
        "class_balance": metrics.get("class_balance"),
    }


@router.get("/special/ml/training-data-status")
def get_special_training_data_status(db: Session = Depends(get_db)):
    """Return count of labelled special backtest trades and whether enough exist to train."""
    from domains.special_strategies.ml_scorer import MIN_TRAINING_SAMPLES as SPECIAL_ML_MIN
    total = db.execute(
        text("SELECT COUNT(*) FROM special_strategy_trades WHERE entry_date IS NOT NULL AND pnl_pct IS NOT NULL")
    ).scalar() or 0
    return {
        "total_labelled_trades": int(total),
        "ready_to_train": int(total) >= SPECIAL_ML_MIN,
        "min_required": SPECIAL_ML_MIN,
    }


@router.post("/special/ml/train")
def train_special_ml_model(db: Session = Depends(get_db)):
    """Train the special-strategy ML model on special_backtest_trades data."""
    scorer = SpecialMLScorer()
    result = scorer.train(db)
    if result["samples"] == 0:
        return {
            "status": "skipped", "samples": 0,
            "message": f"Need at least {SPECIAL_ML_MIN_SAMPLES} labelled special_backtest_trades rows",
        }
    return {
        "status": "ok",
        "message": f"Trained on {result['samples']} samples",
        **result,
    }
