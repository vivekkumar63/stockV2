# backend/domains/combinations/router.py
"""REST API endpoints for the Strategy Combination Engine."""

import json
import logging
import threading

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session
from typing import Optional

from database import get_db
from domains.combinations.engine import CombinationEngine

logger = logging.getLogger(__name__)
router = APIRouter(tags=["combinations"])


# ── GET /combinations/run-status ─────────────────────────────────────────────

@router.get("/combinations/run-status")
def get_run_status(db: Session = Depends(get_db)):
    """Return status of the most recent analysis run."""
    row = db.execute(text("""
        SELECT id, status, completed_at, combinations_tested, top_combination_id
        FROM combination_run_log
        ORDER BY started_at DESC
        LIMIT 1
    """)).fetchone()

    if row is None:
        return {
            "status": "never_run",
            "last_completed_at": None,
            "last_run_id": None,
            "combinations_tested": None,
            "top_combination": None,
        }

    run_id, status, completed_at, combinations_tested, top_combo_id = row

    top_combination = None
    if top_combo_id is not None:
        tc_row = db.execute(text("""
            SELECT sc.name, cr.oos_cagr, cr.reliability_label
            FROM strategy_combinations sc
            JOIN combination_results cr ON cr.combination_id = sc.id
            WHERE sc.id = :cid AND cr.run_id = (
                SELECT MAX(id) FROM combination_run_log WHERE status = 'complete'
            )
            ORDER BY cr.computed_at DESC
            LIMIT 1
        """), {"cid": top_combo_id}).fetchone()
        if tc_row:
            top_combination = {
                "name": tc_row[0],
                "oos_cagr": tc_row[1],
                "reliability_label": tc_row[2],
            }

    return {
        "status": status,
        "last_completed_at": completed_at,
        "last_run_id": run_id,
        "combinations_tested": combinations_tested,
        "top_combination": top_combination,
    }


# ── GET /combinations/rankings ────────────────────────────────────────────────

@router.get("/combinations/rankings")
def get_rankings(
    size: Optional[int] = Query(None, description="Filter by combination size (2=pairs, 3=triplets)"),
    sort_by: str = Query("reliability_score", description="Sort field: reliability_score, oos_cagr, oos_sharpe, oos_win_rate"),
    db: Session = Depends(get_db),
):
    """Return top combinations from the most recent completed run."""
    valid_sort_fields = {"reliability_score", "oos_cagr", "oos_sharpe", "oos_win_rate"}
    if sort_by not in valid_sort_fields:
        sort_by = "reliability_score"

    engine = CombinationEngine(db)
    results = engine.get_top_combinations(n=50)

    if size is not None:
        results = [r for r in results if r.get("size") == size]

    # Sort by the requested field (descending)
    results.sort(key=lambda x: (x.get(sort_by) or 0), reverse=True)

    # Parse strategy_names JSON into a list
    for r in results:
        raw = r.get("strategy_names")
        if raw and isinstance(raw, str):
            try:
                r["strategies"] = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                r["strategies"] = []
        else:
            r["strategies"] = raw if isinstance(raw, list) else []

    return results


# ── GET /combinations/best ────────────────────────────────────────────────────

@router.get("/combinations/best")
def get_best(db: Session = Depends(get_db)):
    """Return the best combination per category from the most recent completed run."""

    def _fetch_best(order_col: str, where: str = "") -> Optional[dict]:
        where_clause = f"AND {where}" if where else ""
        row = db.execute(text(f"""
            SELECT sc.id, sc.name, sc.strategy_names, sc.size,
                   cr.oos_cagr, cr.oos_max_drawdown, cr.oos_sharpe, cr.oos_win_rate,
                   cr.oos_total_trades, cr.train_cagr, cr.wf_consistency_score,
                   cr.reliability_score, cr.reliability_label, cr.sensitivity_score,
                   cr.vs_buy_and_hold_cagr, cr.vs_best_single_cagr
            FROM combination_results cr
            JOIN strategy_combinations sc ON sc.id = cr.combination_id
            WHERE cr.run_id = (SELECT MAX(id) FROM combination_run_log WHERE status = 'complete')
            {where_clause}
            ORDER BY cr.{order_col} DESC
            LIMIT 1
        """)).fetchone()

        if row is None:
            return None

        result = dict(row._mapping)
        raw = result.get("strategy_names")
        if raw and isinstance(raw, str):
            try:
                result["strategies"] = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                result["strategies"] = []
        else:
            result["strategies"] = raw if isinstance(raw, list) else []
        return result

    return {
        "overall": _fetch_best("reliability_score"),
        "low_risk": _fetch_best("reliability_score", "cr.oos_max_drawdown > -20"),
        "high_growth": _fetch_best("oos_cagr"),
        "most_consistent": _fetch_best("wf_consistency_score"),
    }


# ── GET /combinations/avoid ───────────────────────────────────────────────────

@router.get("/combinations/avoid")
def get_avoid(db: Session = Depends(get_db)):
    """Return likely overfitted or data-insufficient combinations from the most recent run."""
    rows = db.execute(text("""
        SELECT sc.id, sc.name, sc.strategy_names, sc.size,
               cr.oos_cagr, cr.oos_max_drawdown, cr.oos_sharpe, cr.oos_win_rate,
               cr.oos_total_trades, cr.train_cagr, cr.wf_consistency_score,
               cr.reliability_score, cr.reliability_label, cr.sensitivity_score,
               cr.vs_buy_and_hold_cagr, cr.vs_best_single_cagr
        FROM combination_results cr
        JOIN strategy_combinations sc ON sc.id = cr.combination_id
        WHERE cr.run_id = (SELECT MAX(id) FROM combination_run_log WHERE status = 'complete')
          AND cr.reliability_label IN ('Likely Overfitted', 'Insufficient Data')
        ORDER BY cr.reliability_score ASC
        LIMIT 20
    """)).fetchall()

    results = []
    for row in rows:
        r = dict(row._mapping)
        raw = r.get("strategy_names")
        if raw and isinstance(raw, str):
            try:
                r["strategies"] = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                r["strategies"] = []
        else:
            r["strategies"] = raw if isinstance(raw, list) else []
        results.append(r)

    return results


# ── POST /combinations/analyze ────────────────────────────────────────────────

@router.post("/combinations/analyze")
def trigger_analysis(db: Session = Depends(get_db)):
    """Trigger a full combination analysis in the background."""
    running_row = db.execute(text("""
        SELECT id FROM combination_run_log
        WHERE status = 'running'
        ORDER BY started_at DESC
        LIMIT 1
    """)).fetchone()

    if running_row is not None:
        return {"status": "already_running", "run_id": running_row[0]}

    def _run():
        from database import SessionLocal
        bg_db = SessionLocal()
        try:
            engine = CombinationEngine(bg_db)
            engine.run_full_analysis()
        except Exception:
            logger.exception("[combinations] Background analysis failed")
        finally:
            bg_db.close()

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    return {"status": "started", "message": "Analysis running in background"}


# ── GET /combinations/{combination_id} ────────────────────────────────────────
# MUST be last to avoid matching /combinations/rankings etc. as combination_id

@router.get("/combinations/{combination_id}")
def get_combination_detail(combination_id: int, db: Session = Depends(get_db)):
    """Return full detail for a specific combination (most recent result)."""
    combo_row = db.execute(text("""
        SELECT id, name, strategy_ids, strategy_names, size, search_method, created_at
        FROM strategy_combinations
        WHERE id = :cid
    """), {"cid": combination_id}).fetchone()

    if combo_row is None:
        raise HTTPException(status_code=404, detail=f"Combination {combination_id} not found")

    combo = dict(combo_row._mapping)

    # Parse strategy_names
    raw = combo.get("strategy_names")
    if raw and isinstance(raw, str):
        try:
            combo["strategies"] = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            combo["strategies"] = []
    else:
        combo["strategies"] = raw if isinstance(raw, list) else []

    # Most recent result for this combination
    result_row = db.execute(text("""
        SELECT *
        FROM combination_results
        WHERE combination_id = :cid
        ORDER BY computed_at DESC
        LIMIT 1
    """), {"cid": combination_id}).fetchone()

    result = dict(result_row._mapping) if result_row else {}

    # Parse explanation_json
    exp_raw = result.get("explanation_json")
    if exp_raw and isinstance(exp_raw, str):
        try:
            result["explanation"] = json.loads(exp_raw)
        except (json.JSONDecodeError, TypeError):
            result["explanation"] = None
    else:
        result["explanation"] = None

    # Regime performance rows
    regime_rows = db.execute(text("""
        SELECT regime, win_rate, avg_pnl_pct, trade_count, cagr
        FROM combination_regime_perf
        WHERE combination_id = :cid
          AND run_id = (
              SELECT run_id FROM combination_results
              WHERE combination_id = :cid
              ORDER BY computed_at DESC
              LIMIT 1
          )
    """), {"cid": combination_id}).fetchall()
    regime_perf = [dict(r._mapping) for r in regime_rows]

    return {
        **combo,
        **result,
        "regime_perf": regime_perf,
    }
