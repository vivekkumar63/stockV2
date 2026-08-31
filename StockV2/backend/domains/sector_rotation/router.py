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


@router.get("/{sector_name}/stocks")
def get_sector_stocks(sector_name: str, db: Session = Depends(get_db)):
    """Per-stock metrics for all stocks in a sector: latest close, above SMA20/50, 3M return."""
    from domains.sector_rotation.engine import _SECTOR_STOCKS
    stocks = _SECTOR_STOCKS.get(sector_name.upper())
    if not stocks:
        raise HTTPException(status_code=404, detail=f"Unknown sector: {sector_name}")

    placeholders = ",".join(f"'{s}'" for s in stocks)

    rows = db.execute(text(f"""
        WITH ranked AS (
            SELECT symbol, close, date,
                   ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) AS rn
            FROM stock_prices_daily
            WHERE symbol IN ({placeholders})
        ),
        latest  AS (SELECT symbol, close, date FROM ranked WHERE rn = 1),
        sma20   AS (
            SELECT symbol, AVG(close) AS sma
            FROM ranked WHERE rn <= 20
            GROUP BY symbol HAVING COUNT(*) >= 5
        ),
        sma50   AS (
            SELECT symbol, AVG(close) AS sma
            FROM ranked WHERE rn <= 50
            GROUP BY symbol HAVING COUNT(*) >= 10
        ),
        price3m AS (
            SELECT symbol, close AS close_3m
            FROM ranked WHERE rn = 63
        )
        SELECT
            l.symbol,
            l.close,
            l.date                                           AS last_date,
            CASE WHEN l.close > s20.sma THEN true ELSE false END AS above_sma20,
            CASE WHEN l.close > s50.sma THEN true ELSE false END AS above_sma50,
            ROUND(((l.close - s20.sma) / s20.sma * 100)::numeric, 2)  AS pct_vs_sma20,
            ROUND(((l.close - s50.sma) / s50.sma * 100)::numeric, 2)  AS pct_vs_sma50,
            ROUND(((l.close - p3m.close_3m) / p3m.close_3m * 100)::numeric, 2) AS return_3m
        FROM latest l
        LEFT JOIN sma20   s20 ON s20.symbol = l.symbol
        LEFT JOIN sma50   s50 ON s50.symbol = l.symbol
        LEFT JOIN price3m p3m ON p3m.symbol = l.symbol
        ORDER BY above_sma50 DESC NULLS LAST, pct_vs_sma50 DESC NULLS LAST
    """)).fetchall()

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
