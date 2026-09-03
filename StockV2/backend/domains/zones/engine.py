from __future__ import annotations
import json
import logging
import math
from datetime import date

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from domains.data.indicators import IndicatorEngine
from .clusterer import ZoneClusterer
from .detectors import (
    FibonacciDetector, MADetector, MomentumDetector,
    PriceStructureDetector, VolatilityDetector, VolumeDetector,
    VWAPZoneDetector,
)
from .entry_engine import EntryEngine
from .models import Zone, ZoneLevel, ZoneResult
from .scorer import ZoneScorer

logger = logging.getLogger(__name__)

_DETECTORS = [
    PriceStructureDetector(),
    MADetector(),
    VolumeDetector(),
    VolatilityDetector(),
    MomentumDetector(),
    FibonacciDetector(),
]


def _load_prices(db: Session, symbol: str) -> pd.DataFrame:
    rows = db.execute(
        text("""
            SELECT date, open, high, low, close, volume FROM (
                SELECT date, open, high, low, close, volume
                FROM stock_prices_daily
                WHERE symbol = :s
                ORDER BY date DESC LIMIT 500
            ) sub ORDER BY date ASC
        """),
        {"s": symbol},
    ).fetchall()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"])
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = df[col].astype(float)
    return df


def _market_structure(df: pd.DataFrame) -> str:
    if "ema_50" not in df.columns or len(df) < 10:
        return "sideways"
    close = float(df["close"].iloc[-1])
    ema50 = float(df["ema_50"].iloc[-1])
    if not math.isfinite(ema50):
        return "sideways"
    if close > ema50 * 1.02:
        return "bullish"
    if close < ema50 * 0.98:
        return "bearish"
    return "sideways"


def _position_tag(price: float, demand_zones: list[Zone], supply_zones: list[Zone], atr: float) -> str:
    for z in demand_zones:
        if z.low <= price <= z.high:
            return "in_demand"
    for z in supply_zones:
        if z.low <= price <= z.high:
            return "in_supply"
    # breakout: price above the highest supply zone high + 0.2xATR
    if supply_zones:
        highest_supply = max(z.high for z in supply_zones)
        if price > highest_supply + 0.2 * atr:
            return "breakout"
    # near_demand: price above nearest demand by <= 1.5xATR
    if demand_zones:
        candidates = [z.high for z in demand_zones if z.high < price]
        if candidates:
            nearest_demand = max(candidates)
            if price - nearest_demand <= 1.5 * atr:
                return "near_demand"
    # near_supply: price below nearest supply by <= 1.5xATR
    if supply_zones:
        candidates = [z.low for z in supply_zones if z.low > price]
        if candidates:
            nearest_supply = min(candidates)
            if nearest_supply - price <= 1.5 * atr:
                return "near_supply"
    return "neutral"


def zone_to_dict(z: Zone) -> dict:
    return {
        "low": z.low, "high": z.high, "score": z.score,
        "freshness": z.freshness, "touch_count": z.touch_count,
        "last_reaction_pct": z.last_reaction_pct,
        "source_tags": z.source_tags,
        "source": z.source,
    }


def setup_to_dict(s) -> dict | None:
    if s is None:
        return None
    return {
        "score": s.score,
        "ideal_entry": s.ideal_entry, "aggressive_entry": s.aggressive_entry,
        "conservative_entry": s.conservative_entry, "stop_loss": s.stop_loss,
        "t1": s.t1, "t1_rr": s.t1_rr,
        "t2": s.t2, "t2_rr": s.t2_rr,
        "t3": s.t3, "t3_rr": s.t3_rr,
        "explanation": s.explanation, "invalidation": s.invalidation,
    }


class ZoneEngine:
    def analyze(self, symbol: str, db: Session) -> ZoneResult | None:
        df = _load_prices(db, symbol)
        if df.empty or len(df) < 30:
            logger.warning("[ZoneEngine] insufficient data for %s", symbol)
            return None
        try:
            df_ind = IndicatorEngine.compute(df)
        except Exception as e:
            logger.warning("[ZoneEngine] indicator compute failed for %s: %s", symbol, e)
            return None

        price = float(df_ind["close"].iloc[-1])
        atr   = float(df_ind["atr_14"].iloc[-1]) if "atr_14" in df_ind.columns else 0.0
        rvol  = float(df_ind["volume_ratio"].iloc[-1]) if "volume_ratio" in df_ind.columns else 1.0
        n = len(df_ind)
        if not math.isfinite(atr) or atr <= 0:
            atr = price * 0.01  # fallback: 1% of price

        # Detect raw levels
        levels: list[ZoneLevel] = []
        for det in _DETECTORS:
            try:
                levels.extend(det.detect(df_ind))
            except Exception as e:
                logger.debug("[ZoneEngine] detector %s failed on %s: %s", det.__class__.__name__, symbol, e)

        # Cluster
        all_zones = ZoneClusterer().cluster(levels, atr)

        # VWAP zones from intraday data (optional — skipped if data unavailable)
        try:
            vwap_zones = VWAPZoneDetector().detect(symbol, db, atr=atr, current_price=price)
            all_zones.extend(vwap_zones)
        except Exception:
            pass  # intraday data may be unavailable; never block daily analysis

        # Score (ZoneScorer.score() returns new Zone copies; single instance is stateless)
        scorer = ZoneScorer()
        demand_zones = scorer.score_all(
            [z for z in all_zones if z.zone_type == "demand"],
            atr=atr, n_bars=n, price=price,
        )
        supply_zones = scorer.score_all(
            [z for z in all_zones if z.zone_type == "supply"],
            atr=atr, n_bars=n, price=price,
        )

        # Sort by score desc
        demand_zones.sort(key=lambda z: z.score, reverse=True)
        supply_zones.sort(key=lambda z: z.score, reverse=True)

        # Market structure + RSI
        structure = _market_structure(df_ind)
        rsi = float(df_ind["rsi_14"].iloc[-1]) if "rsi_14" in df_ind.columns else 50.0
        if not math.isfinite(rsi):
            rsi = 50.0

        # Entry engine
        eng = EntryEngine()
        long_setup = eng.compute_long(
            demand_zones[0], supply_zones, atr, rsi=rsi, trend=structure, n_bars=n
        ) if demand_zones else None
        short_setup = eng.compute_short(
            supply_zones[0], demand_zones, atr, rsi=rsi, trend=structure, n_bars=n
        ) if supply_zones else None

        pos_tag = _position_tag(price, demand_zones, supply_zones, atr)

        result = ZoneResult(
            symbol=symbol,
            demand_zones=demand_zones[:5],
            supply_zones=supply_zones[:5],
            long_setup=long_setup,
            short_setup=short_setup,
            market_structure=structure,
            atr=round(atr, 2),
            rvol=round(rvol if math.isfinite(rvol) else 1.0, 2),
            price=round(price, 2),
            position_tag=pos_tag,
        )

        # Upsert to DB
        result_json = {
            "demand_zones": [zone_to_dict(z) for z in result.demand_zones],
            "supply_zones":  [zone_to_dict(z) for z in result.supply_zones],
            "long_setup":    setup_to_dict(long_setup),
            "short_setup":   setup_to_dict(short_setup),
            "market_structure": structure,
            "atr": result.atr, "rvol": result.rvol,
        }

        best_demand = max((z.score for z in demand_zones), default=None)
        best_supply = max((z.score for z in supply_zones), default=None)

        try:
            db.execute(
                text("""
                    INSERT INTO zone_analysis_results
                        (symbol, computed_date, best_demand_score, best_supply_score,
                         long_setup_score, short_setup_score, price_at_compute,
                         atr_at_compute, rvol_at_compute, position_tag,
                         best_long_rr, best_short_rr, result_json)
                    VALUES
                        (:sym, :dt, :bd, :bs, :ls, :ss, :pr, :atr, :rv, :pt, :lr, :sr, :rj)
                    ON CONFLICT (symbol, computed_date) DO UPDATE SET
                        best_demand_score = EXCLUDED.best_demand_score,
                        best_supply_score = EXCLUDED.best_supply_score,
                        long_setup_score  = EXCLUDED.long_setup_score,
                        short_setup_score = EXCLUDED.short_setup_score,
                        price_at_compute  = EXCLUDED.price_at_compute,
                        atr_at_compute    = EXCLUDED.atr_at_compute,
                        rvol_at_compute   = EXCLUDED.rvol_at_compute,
                        position_tag      = EXCLUDED.position_tag,
                        best_long_rr      = EXCLUDED.best_long_rr,
                        best_short_rr     = EXCLUDED.best_short_rr,
                        result_json       = EXCLUDED.result_json,
                        created_at        = CURRENT_TIMESTAMP
                """),
                {
                    "sym": symbol, "dt": date.today(),
                    "bd": best_demand, "bs": best_supply,
                    "ls": long_setup.score if long_setup else None,
                    "ss": short_setup.score if short_setup else None,
                    "pr": result.price, "atr": result.atr, "rv": result.rvol,
                    "pt": pos_tag,
                    "lr": long_setup.t2_rr if long_setup else None,
                    "sr": short_setup.t2_rr if short_setup else None,
                    "rj": json.dumps(result_json),
                },
            )
            db.commit()
        except Exception as e:
            db.rollback()
            logger.warning("[ZoneEngine] DB upsert failed for %s: %s", symbol, e)

        return result
