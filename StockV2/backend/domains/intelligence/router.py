"""Intelligence API endpoints — opportunity scores, strategy ranking, regime backfill."""

import logging
from datetime import date
from typing import Optional

from ist import ist_today

import pandas as pd
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from database import get_db
from domains.intelligence.false_signal_detector import FalseSignalDetector
from domains.intelligence.ml_scorer import MLSignalScorer, regime_to_code
from domains.intelligence.opportunity_scorer import OpportunityScorer
from domains.intelligence.regime_performance import RegimePerformanceEngine
from domains.intelligence.strategy_correlation import StrategyCorrelationEngine
from domains.intelligence.strategy_selector import StrategySelectionEngine
from domains.data.index_fetcher import compute_index_alignment_score
from domains.data.index_universe import STOCK_INDEX_MAP
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

    # ML probability
    ml_prob: Optional[float] = None
    if strategy_id:
        ml_prob = MLSignalScorer().predict({
            "confidence_score": 0.5,
            "regime_code": regime_to_code(regime),
            "strategy_id": strategy_id,
            "month": date.today().month,
            "day_of_week": date.today().weekday(),
        })

    # Index alignment — same lookup as top-opportunities
    _idx_rows = db.execute(
        text("SELECT index_name, above_sma20, above_sma50 FROM index_trend WHERE date = (SELECT MAX(date) FROM index_trend)")
    ).mappings().fetchall()
    _itm = {r["index_name"]: dict(r) for r in _idx_rows}
    _parent_index = STOCK_INDEX_MAP.get(sym)
    idx_alignment_raw = compute_index_alignment_score(_itm.get(_parent_index) if _parent_index else None)

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
        ml_probability=ml_prob,
        index_alignment_score=idx_alignment_raw,
    )

    return {
        "symbol":      opp.symbol,
        "strategy_id": opp.strategy_id,
        "score":       opp.score,
        "grade":       opp.grade,
        "regime":      regime,
        "mtf_alignment_score": mtf_score,
        "ml_probability": ml_prob,
        "breakdown":   opp.breakdown,
    }


# ── Top opportunities (bulk scored today's BUY signals) ──────────────────────

@router.get("/intelligence/top-opportunities")
def get_top_opportunities(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    today = ist_today()

    rows = db.execute(
        text("""
            SELECT ss.id, ss.symbol, ss.strategy_id, s.name AS strategy_name,
                   ss.signal_date, ss.confidence_score, ss.price_at_signal,
                   ss.suggested_stop_loss, ss.suggested_target, ss.holding_period_days,
                   ss.reasoning_json
            FROM strategy_signals ss
            JOIN strategies s ON s.id = ss.strategy_id
            WHERE ss.signal_date = :today AND ss.signal_type = 'BUY'
            ORDER BY ss.confidence_score DESC
            LIMIT 500
        """),
        {"today": str(today)},
    ).fetchall()

    if not rows:
        return []

    # Get regime once — reused for all signals
    try:
        regime_result = MarketRegimeEngine().get_or_compute(db)
        regime = regime_result.regime
    except Exception:
        logger.exception("[top-opportunities] failed to compute market regime")
        raise HTTPException(status_code=503, detail="Market regime unavailable")

    # Bulk-fetch historical win rates
    symbols = list({r[1] for r in rows})
    strategy_ids = list({r[2] for r in rows})
    hist_wr_map: dict[tuple, Optional[float]] = {}
    if symbols and strategy_ids:
        hist_rows = db.execute(
            text("""
                SELECT symbol, strategy_id, win_rate FROM scan_result_cache
                WHERE symbol IN :syms AND strategy_id IN :sids
                  AND stop_loss_pct = 5.0 AND target_pct = 10.0
                  AND from_date = '2015-01-01'
            """).bindparams(
                bindparam("syms", expanding=True),
                bindparam("sids", expanding=True),
            ),
            {"syms": symbols, "sids": strategy_ids},
        ).fetchall()
        for hr in hist_rows:
            hist_wr_map[(hr[0], hr[1])] = float(hr[2]) if hr[2] is not None else None

    # Regime-strategy performance
    regime_perf = RegimePerformanceEngine().get_for_regime(db, regime)

    # False signal rates — bulk dict {strategy_id: rate}
    false_rates = FalseSignalDetector().get_false_signal_rates(db)

    # Pre-load latest index trends — one query for all 7 indices
    index_trend_rows = db.execute(
        text("""
            SELECT index_name, above_sma20, above_sma50, trend_label
            FROM index_trend
            WHERE date = (SELECT MAX(date) FROM index_trend)
        """)
    ).mappings().fetchall()
    index_trend_map: dict[str, dict] = {
        r["index_name"]: dict(r) for r in index_trend_rows
    }

    # Pre-compute per-symbol data once to avoid redundant DB calls
    mtf_cache: dict[str, object] = {}
    vol_cache: dict[str, object] = {}
    sr_cache:  dict[str, object] = {}
    for sym in symbols:
        try:
            mtf_cache[sym] = MultiTimeframeEngine().compute(db, sym)
        except Exception:
            logger.warning("[top-opportunities] MTF compute failed for %s", sym)
            mtf_cache[sym] = None
        try:
            vol_cache[sym] = _compute_volume_score(db, sym)
        except Exception:
            logger.warning("[top-opportunities] volume compute failed for %s", sym)
            vol_cache[sym] = None
        try:
            sr_cache[sym] = SupportResistanceEngine().compute(db, sym)
        except Exception:
            logger.warning("[top-opportunities] S/R compute failed for %s", sym)
            sr_cache[sym] = None
    ml_scorer  = MLSignalScorer()
    opp_scorer = OpportunityScorer()

    seen: set[tuple] = set()
    results = []
    for r in rows:
        (signal_id, symbol, strategy_id, strategy_name,
         signal_date, confidence_score, price_at_signal,
         suggested_stop_loss, suggested_target, holding_period_days, reasoning_json) = r

        pair = (symbol, strategy_id)
        if pair in seen:
            continue
        seen.add(pair)

        if price_at_signal is None:
            stop_loss_price = target_price = rr = None
        else:
            sl_pct  = suggested_stop_loss or 7.0
            tgt_pct = suggested_target    or 15.0
            stop_loss_price = round(price_at_signal * (1 - sl_pct / 100), 2)
            target_price    = round(price_at_signal * (1 + tgt_pct / 100), 2)
            rr = round(
                (target_price - price_at_signal) / (price_at_signal - stop_loss_price), 2
            ) if price_at_signal > stop_loss_price else None

        hist_wr    = hist_wr_map.get((symbol, strategy_id))
        regime_wr  = regime_perf[strategy_id].win_rate if strategy_id in regime_perf else None
        false_rate = false_rates.get(strategy_id)

        mtf_result = mtf_cache[symbol]
        mtf_score  = mtf_result.alignment_score if mtf_result and mtf_result.daily else None

        vol_score = vol_cache[symbol]

        sr_result = sr_cache[symbol]
        sr_score  = _compute_sr_score(sr_result) if sr_result is not None else None

        # Index alignment
        parent_index = STOCK_INDEX_MAP.get(symbol)
        index_trend_row = index_trend_map.get(parent_index) if parent_index else None
        idx_alignment_raw = compute_index_alignment_score(index_trend_row)

        ml_prob = ml_scorer.predict({
            "confidence_score": confidence_score or 0.5,
            "regime_code":      regime_to_code(regime),
            "strategy_id":      strategy_id,
            "month":            today.month,
            "day_of_week":      today.weekday(),
        })

        opp = opp_scorer.full_score(
            symbol=symbol,
            strategy_id=strategy_id,
            confidence=confidence_score or 0.5,
            historical_win_rate=hist_wr,
            regime=regime,
            regime_strategy_win_rate=regime_wr,
            mtf_alignment=mtf_score,
            volume_score=vol_score,
            sr_score=sr_score,
            false_signal_rate=false_rate,
            ml_probability=ml_prob,
            index_alignment_score=idx_alignment_raw,
        )

        results.append({
            "signal_id":        signal_id,
            "symbol":           symbol,
            "strategy_id":      strategy_id,
            "strategy_name":    strategy_name,
            "signal_date":      str(signal_date)[:10],
            "confidence_score": confidence_score,
            "price_at_signal":  price_at_signal,
            "stop_loss_price":  stop_loss_price,
            "target_price":     target_price,
            "stop_loss_pct":    suggested_stop_loss,
            "target_pct":       suggested_target,
            "holding_days":     holding_period_days,
            "rr":               rr,
            "reasoning_json":   reasoning_json,
            "score":            opp.score,
            "grade":            opp.grade,
            "regime":           regime,
            "mtf_alignment":    mtf_score,
            "ml_probability":   ml_prob,
            "false_signal_rate": false_rate,
            "breakdown":        opp.breakdown,
            "index_name":       parent_index,
            "index_trend":      index_trend_row["trend_label"] if index_trend_row else None,
        })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:limit]


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
