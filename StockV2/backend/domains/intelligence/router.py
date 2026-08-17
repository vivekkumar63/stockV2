"""Intelligence API endpoints — opportunity scores, strategy ranking, regime backfill."""

import logging
from datetime import date
from typing import Optional

import pandas as pd
from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from database import get_db
from domains.intelligence.false_signal_detector import FalseSignalDetector
from domains.intelligence.opportunity_scorer import OpportunityScorer
from domains.intelligence.regime_performance import RegimePerformanceEngine
from domains.intelligence.strategy_correlation import StrategyCorrelationEngine
from domains.intelligence.strategy_selector import StrategySelectionEngine
from domains.market.multi_timeframe import MultiTimeframeEngine
from domains.market.regime import MarketRegimeEngine
from domains.market.support_resistance import SupportResistanceEngine
from domains.market.volume_analysis import VolumeAnalysisEngine

logger = logging.getLogger(__name__)
router = APIRouter(tags=["intelligence"])


# ── Strategy ranking ──────────────────────────────────────────────────────────

@router.get("/intelligence/strategy-ranking")
def get_strategy_ranking(
    regime: Optional[str] = Query(None, description="Override regime; uses current if omitted"),
    db: Session = Depends(get_db),
):
    """Strategies ranked by historical win rate in the current (or specified) market regime."""
    engine = StrategySelectionEngine()
    ranks = engine.rank_for_regime(db, regime.upper()) if regime else engine.rank_for_current_regime(db)
    return [
        {
            "rank":             r.rank,
            "strategy_id":      r.strategy_id,
            "strategy_name":    r.strategy_name,
            "regime_win_rate":  r.regime_win_rate,
            "overall_win_rate": r.overall_win_rate,
            "regime_trades":    r.regime_total_trades,
        }
        for r in ranks
    ]


# ── Full opportunity score ────────────────────────────────────────────────────

@router.get("/intelligence/opportunity-score/{symbol}")
def get_opportunity_score(
    symbol: str,
    strategy_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    """
    Full opportunity score (0–100) for a symbol, using all intelligence signals:
    historical win rate, strategy confidence, regime alignment, MTF, volume, and S/R.
    """
    sym = symbol.upper()
    regime_result = MarketRegimeEngine().get_or_compute(db)
    regime = regime_result.regime

    # Regime-strategy win rate
    regime_perf = RegimePerformanceEngine().get_for_regime(db, regime)
    regime_wr: Optional[float] = regime_perf[strategy_id].win_rate if (strategy_id and strategy_id in regime_perf) else None

    # Historical win rate from scan_result_cache
    hist_wr: Optional[float] = None
    if strategy_id:
        row = db.execute(
            text("""
                SELECT win_rate FROM scan_result_cache
                WHERE symbol = :s AND strategy_id = :sid
                  AND stop_loss_pct = 5.0 AND target_pct = 10.0
                  AND from_date = '2015-01-01'
                LIMIT 1
            """),
            {"s": sym, "sid": strategy_id},
        ).fetchone()
        if row and row[0] is not None:
            hist_wr = float(row[0])

    # MTF alignment
    mtf_result = MultiTimeframeEngine().compute(db, sym)
    mtf_score: Optional[float] = mtf_result.alignment_score if mtf_result.daily else None

    # Volume score
    vol_score = _compute_volume_score(db, sym)

    # S/R context score
    sr_result = SupportResistanceEngine().compute(db, sym)
    sr_score = _compute_sr_score(sr_result)

    false_rate: Optional[float] = None
    if strategy_id:
        false_rate = FalseSignalDetector().get_rate_for_strategy(db, strategy_id)

    opp = OpportunityScorer().full_score(
        symbol=sym,
        strategy_id=strategy_id,
        confidence=0.5,   # no active signal context; caller may pass via query param
        historical_win_rate=hist_wr,
        regime=regime,
        regime_strategy_win_rate=regime_wr,
        mtf_alignment=mtf_score,
        volume_score=vol_score,
        sr_score=sr_score,
        false_signal_rate=false_rate,
    )

    return {
        "symbol":      opp.symbol,
        "strategy_id": opp.strategy_id,
        "score":       opp.score,
        "grade":       opp.grade,
        "regime":      regime,
        "mtf_alignment_score": mtf_score,
        "breakdown":   opp.breakdown,
    }


# ── Regime backfill trigger ───────────────────────────────────────────────────

@router.post("/intelligence/regime-backfill")
def trigger_regime_backfill(
    background_tasks: BackgroundTasks,
    start_year: int = Query(2015, ge=2000, le=2030),
    db: Session = Depends(get_db),
):
    """
    Trigger vectorized historical regime backfill and regime-performance computation.
    Runs in the background — returns immediately. Check logs for progress.
    """
    start = date(start_year, 1, 1)
    today = date.today()
    background_tasks.add_task(_run_backfill, start, today)
    return {"status": "started", "start_year": start_year, "end_date": str(today)}


# ── False signal stats ────────────────────────────────────────────────────────

@router.get("/intelligence/false-signal-stats")
def get_false_signal_stats(db: Session = Depends(get_db)):
    """
    Rolling false-signal rates per strategy, computed from evaluated BUY signal outcomes.
    Only strategies with at least 5 evaluated outcomes are shown.
    """
    return FalseSignalDetector().get_stats(db)


# ── Strategy correlation matrix ───────────────────────────────────────────────

@router.get("/intelligence/strategy-correlations")
def get_strategy_correlations(db: Session = Depends(get_db)):
    """
    Pairwise signal-overlap correlation between strategies.
    High correlation = strategies fire on the same stocks simultaneously.
    """
    return StrategyCorrelationEngine().get_matrix(db)


@router.post("/intelligence/compute-correlations")
def compute_strategy_correlations(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Recompute strategy correlation matrix in the background."""
    background_tasks.add_task(_run_correlation_compute)
    return {"status": "started"}


# ── Risk check ────────────────────────────────────────────────────────────────

@router.get("/intelligence/risk-check/{symbol}")
def get_risk_check(
    symbol: str,
    strategy_id: Optional[int] = Query(None),
    opportunity_score: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    """
    Portfolio risk check for a potential position entry.
    Returns whether entry is allowed, with per-check breakdown.
    """
    from domains.portfolio.risk_guard import RiskGuard
    result = RiskGuard().check_entry(
        db, symbol=symbol, strategy_id=strategy_id, opportunity_score=opportunity_score
    )
    return {
        "allowed":  result.allowed,
        "symbol":   result.symbol,
        "summary":  result.summary,
        "checks": [
            {
                "name":     c.name,
                "passed":   c.passed,
                "blocking": c.blocking,
                "reason":   c.reason,
            }
            for c in result.checks
        ],
    }


def _run_correlation_compute() -> None:
    from database import SessionLocal
    db = SessionLocal()
    try:
        engine = StrategyCorrelationEngine()
        pairs = engine.compute(db)
        engine.save(db, pairs)
        logger.info("[correlation] computed %d pairs", len(pairs))
    except Exception:
        logger.exception("[correlation] failed")
    finally:
        db.close()


def _run_backfill(start: date, end: date) -> None:
    from database import SessionLocal
    db = SessionLocal()
    try:
        regime_engine = MarketRegimeEngine()
        results = regime_engine.compute_bulk(db, start, end)
        inserted = regime_engine.save_bulk(db, results)
        logger.info("[backfill] regime rows inserted: %d", inserted)

        perf_engine = RegimePerformanceEngine()
        perfs = perf_engine.compute_all(db)
        perf_engine.save(db, perfs)
        logger.info("[backfill] regime-performance rows saved: %d", len(perfs))
    except Exception:
        logger.exception("[backfill] failed")
    finally:
        db.close()


# ── Scoring helpers ───────────────────────────────────────────────────────────

def _compute_volume_score(db: Session, symbol: str) -> Optional[float]:
    """0.0–1.0 normalised volume score from 60 days of price data."""
    rows = db.execute(
        text("""
            SELECT date, open, high, low, close, volume FROM (
                SELECT date, open, high, low, close, volume
                FROM stock_prices_daily
                WHERE symbol = :s
                ORDER BY date DESC LIMIT 60
            ) ORDER BY date ASC
        """),
        {"s": symbol},
    ).fetchall()
    if not rows or len(rows) < 20:
        return None

    df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"])
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = df[col].astype(float)

    vol = VolumeAnalysisEngine().analyze(df)
    score = 0.5
    if vol.volume_ratio_20 >= 1.5:
        score = min(1.0, 0.5 + (vol.volume_ratio_20 - 1.0) / 4.0)
    elif vol.volume_ratio_20 < 0.7:
        score = max(0.0, vol.volume_ratio_20 / 1.4)
    if vol.obv_trend == "RISING":
        score = min(1.0, score + 0.10)
    elif vol.obv_trend == "FALLING":
        score = max(0.0, score - 0.10)
    if vol.volume_spike:
        score = min(1.0, score + 0.15)
    if vol.breakout_volume_confirmed:
        score = min(1.0, score + 0.10)
    return round(score, 4)


def _compute_sr_score(sr) -> Optional[float]:
    """
    0.0–1.0 S/R context score.
    Best: support very close below, resistance far above.
    Worst: price near strong resistance with no support nearby.
    """
    if sr is None or sr.current_price == 0:
        return None

    support_dist = abs(sr.support_distance_pct) if sr.support_distance_pct is not None else 10.0
    resist_dist  = abs(sr.resistance_distance_pct) if sr.resistance_distance_pct is not None else 10.0

    # Support within 3% → ideal; 6%+ away → poor
    support_score = max(0.0, 1.0 - support_dist / 6.0)
    # Resistance ≥ 5% away → room to run; 0% → trapped
    resist_score  = min(1.0, resist_dist / 5.0)

    return round((support_score + resist_score) / 2.0, 4)
