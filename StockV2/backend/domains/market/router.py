from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database import get_db
from domains.market.regime import MarketRegimeEngine
from domains.market.support_resistance import SupportResistanceEngine
from domains.market.multi_timeframe import MultiTimeframeEngine

router = APIRouter(tags=["market"])


@router.get("/market/regime")
def get_current_regime(db: Session = Depends(get_db)):
    """Current broad market regime, computed from stock-universe breadth."""
    result = MarketRegimeEngine().get_or_compute(db)
    return {
        "regime":                result.regime,
        "confidence":            result.confidence,
        "pct_above_sma50":       result.pct_above_sma50,
        "pct_above_sma200":      result.pct_above_sma200,
        "advance_decline_ratio": result.advance_decline_ratio,
        "avg_atr_ratio":         result.avg_atr_ratio,
        "stocks_counted":        result.stocks_counted,
        "as_of_date":            str(result.as_of_date),
    }


@router.get("/market/regime/history")
def get_regime_history(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
):
    """Recent regime history (up to 365 days)."""
    results = MarketRegimeEngine().get_history(db, days=days)
    return [
        {
            "date":                    str(r.as_of_date),
            "regime":                  r.regime,
            "confidence":              r.confidence,
            "pct_above_sma50":         r.pct_above_sma50,
            "pct_above_sma200":        r.pct_above_sma200,
            "advance_decline_ratio":   r.advance_decline_ratio,
        }
        for r in results
    ]


@router.get("/market/support-resistance/{symbol}")
def get_support_resistance(symbol: str, db: Session = Depends(get_db)):
    """Support and resistance levels for a symbol — swing pivots, static levels, SMAs."""
    result = SupportResistanceEngine().compute(db, symbol)
    return {
        "symbol":                    result.symbol,
        "current_price":             result.current_price,
        "as_of_date":                str(result.as_of_date),
        "nearest_support_pct":       result.support_distance_pct,
        "nearest_resistance_pct":    result.resistance_distance_pct,
        "levels": [
            {
                "price":        l.price,
                "level_type":   l.level_type,
                "level_source": l.level_source,
                "strength":     l.strength,
                "distance_pct": l.distance_pct,
            }
            for l in sorted(result.levels, key=lambda x: abs(x.distance_pct))
        ],
    }


@router.get("/market/timeframe-alignment/{symbol}")
def get_timeframe_alignment(symbol: str, db: Session = Depends(get_db)):
    """Multi-timeframe trend alignment for a symbol (daily / weekly / monthly)."""
    result = MultiTimeframeEngine().compute(db, symbol)

    def _view(v):
        if v is None:
            return None
        return {
            "timeframe":           v.timeframe,
            "trend":               v.trend,
            "ema20":               v.ema20,
            "ema50":               v.ema50,
            "last_close":          v.last_close,
            "ema_fast_above_slow": v.ema_fast_above_slow,
            "price_above_ema20":   v.price_above_ema20,
            "rsi":                 v.rsi,
            "macd_bullish":        v.macd_bullish,
            "bars_available":      v.bars_available,
        }

    return {
        "symbol":          result.symbol,
        "as_of_date":      str(result.as_of_date),
        "alignment_score": result.alignment_score,
        "alignment_label": result.alignment_label,
        "daily":           _view(result.daily),
        "weekly":          _view(result.weekly),
        "monthly":         _view(result.monthly),
    }
