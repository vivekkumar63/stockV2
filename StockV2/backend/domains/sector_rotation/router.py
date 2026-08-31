"""Sector rotation API endpoints."""
import logging
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from database import get_db
from domains.sector_rotation.engine import SectorRotationEngine

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sector", tags=["sector-rotation"])


def _iso_week_start(d: date) -> date:
    """Return the Monday of the ISO week containing d."""
    return d - timedelta(days=d.weekday())


@router.get("/summary")
def get_summary(db: Session = Depends(get_db)):
    engine = SectorRotationEngine()
    phase   = engine.get_market_phase(db)
    sectors = engine.get_sector_summary(db)
    as_of   = db.execute(text(
        "SELECT MAX(trade_date) FROM sector_breadth_daily"
    )).scalar()
    return {
        "market_phase": phase,
        "as_of":        str(as_of) if as_of else None,
        "sectors":      sectors,
    }


@router.get("/breadth")
def get_breadth(days: int = 30, db: Session = Depends(get_db)):
    rows = db.execute(text("""
        SELECT sector_name, trade_date, pct_above_sma50, index_vs_sma20,
               return_1m, return_3m, sector_health_score, rotation_direction
        FROM sector_breadth_daily
        WHERE trade_date >= CURRENT_DATE - :days::int
        ORDER BY trade_date DESC, sector_health_score DESC
    """), {"days": days}).fetchall()
    return [dict(r._mapping) for r in rows]


@router.get("/signal-flow")
def get_signal_flow(weeks: int = 8, db: Session = Depends(get_db)):
    rows = db.execute(text("""
        SELECT sector_name, week_start, signal_count, prev_signal_count,
               avg_win_rate, top_strategy, stocks_with_signals
        FROM sector_signal_flow
        WHERE week_start >= CURRENT_DATE - (:weeks * 7)::int
        ORDER BY week_start DESC, signal_count DESC
    """), {"weeks": weeks}).fetchall()
    return [dict(r._mapping) for r in rows]


@router.post("/recompute")
def recompute(db: Session = Depends(get_db)):
    today = date.today()
    engine = SectorRotationEngine()
    breadth_written = engine.compute_breadth(db, today)
    flow_written    = engine.compute_signal_flow(db, _iso_week_start(today))
    return {
        "status":          "ok",
        "date":            str(today),
        "breadth_written": breadth_written,
        "flow_written":    flow_written,
    }
