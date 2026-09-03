from __future__ import annotations
import dataclasses
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
    CandlestickDetector, FibonacciDetector, MADetector, MomentumDetector,
    PivotPointDetector, PrevHighLowDetector, PriceStructureDetector,
    TrendlineDetector, VolatilityDetector, VolumeDetector, VWAPZoneDetector,
    Week52Detector,
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
    PivotPointDetector(),
    Week52Detector(),
    CandlestickDetector(),
    PrevHighLowDetector(),
    TrendlineDetector(),
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
    """Multi-signal market structure: EMA-50 position, SMA-200 position,
    EMA-50 slope, and HH/LL price structure. Majority vote from available signals."""
    if len(df) < 10:
        return "sideways"

    signals: list[int] = []  # +1 bullish, -1 bearish, 0 neutral
    close = float(df["close"].iloc[-1])

    # Signal 1: price vs EMA-50 with ±2% buffer
    if "ema_50" in df.columns:
        ema50 = float(df["ema_50"].iloc[-1])
        if math.isfinite(ema50) and ema50 > 0:
            if close > ema50 * 1.02:
                signals.append(1)
            elif close < ema50 * 0.98:
                signals.append(-1)
            else:
                signals.append(0)

    # Signal 2: price vs SMA-200
    if "sma_200" in df.columns and len(df) >= 200:
        sma200 = float(df["sma_200"].iloc[-1])
        if math.isfinite(sma200) and sma200 > 0:
            signals.append(1 if close > sma200 else -1 if close < sma200 else 0)

    # Signal 3: EMA-50 slope over last 10 bars (>1% rise/fall = trending)
    if "ema_50" in df.columns and len(df) >= 15:
        ema_now  = float(df["ema_50"].iloc[-1])
        ema_prev = float(df["ema_50"].iloc[-10])
        if math.isfinite(ema_now) and math.isfinite(ema_prev) and ema_prev > 0:
            slope_pct = (ema_now - ema_prev) / ema_prev * 100
            if slope_pct > 1.0:
                signals.append(1)
            elif slope_pct < -1.0:
                signals.append(-1)
            else:
                signals.append(0)

    # Signal 4: higher-highs / lower-lows structure over last 20 bars
    if len(df) >= 20 and "high" in df.columns and "low" in df.columns:
        h_arr = df["high"].to_numpy()[-20:]
        l_arr = df["low"].to_numpy()[-20:]
        q = 5  # four groups of 5 bars
        h_g = [h_arr[i * q:(i + 1) * q].max() for i in range(4)]
        l_g = [l_arr[i * q:(i + 1) * q].min() for i in range(4)]
        hh = all(h_g[i] > h_g[i - 1] for i in range(1, 4))
        hl = all(l_g[i] > l_g[i - 1] for i in range(1, 4))
        lh = all(h_g[i] < h_g[i - 1] for i in range(1, 4))
        ll = all(l_g[i] < l_g[i - 1] for i in range(1, 4))
        if hh and hl:
            signals.append(1)
        elif ll and lh:
            signals.append(-1)
        else:
            signals.append(0)

    if not signals:
        return "sideways"

    vote = sum(signals)
    threshold = max(2, len(signals) // 2)  # need majority
    if vote >= threshold:
        return "bullish"
    if vote <= -threshold:
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


def _detect_candle_signal(df: pd.DataFrame) -> str:
    """Return the last bar's candlestick pattern name, or 'NONE'."""
    if len(df) < 2:
        return "NONE"
    curr = df.iloc[-1]
    prev = df.iloc[-2]
    o, h, l, c = float(curr["open"]), float(curr["high"]), float(curr["low"]), float(curr["close"])
    po, pc = float(prev["open"]), float(prev["close"])
    if not all(math.isfinite(v) for v in (o, h, l, c, po, pc)):
        return "NONE"
    rng = h - l
    if rng <= 0:
        return "NONE"
    body = abs(c - o)
    upper_wick = h - max(o, c)
    lower_wick = min(o, c) - l

    if body / rng < 0.1:
        return "doji"
    if lower_wick >= 2 * body and upper_wick <= 0.3 * body:
        return "hammer"
    if upper_wick >= 2 * body and lower_wick <= 0.3 * body:
        return "shooting_star"
    if c > o and pc < po and c >= po and o <= pc:
        return "bullish_engulfing"
    if c < o and pc > po and c <= po and o >= pc:
        return "bearish_engulfing"
    return "NONE"


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

        # 52-week high/low from available price history (~250 trading days)
        bars_52w = min(250, n)
        high_52w = float(df_ind["high"].iloc[-bars_52w:].max()) if "high" in df_ind.columns else price
        low_52w  = float(df_ind["low"].iloc[-bars_52w:].min())  if "low"  in df_ind.columns else price
        pct_from_52w_high = round((price - high_52w) / high_52w * 100, 2) if high_52w > 0 else None
        pct_from_52w_low  = round((price - low_52w)  / low_52w  * 100, 2) if low_52w  > 0 else None

        # Detect raw levels
        levels: list[ZoneLevel] = []
        for det in _DETECTORS:
            try:
                levels.extend(det.detect(df_ind))
            except Exception as e:
                logger.debug("[ZoneEngine] detector %s failed on %s: %s", det.__class__.__name__, symbol, e)

        # Cluster
        all_zones = ZoneClusterer().cluster(levels, atr)

        # Mark broken zones: demand broken if close fell below zone.low after formation;
        # supply broken if close rose above zone.high after formation.
        close_arr = df_ind["close"].to_numpy()
        for i, zone in enumerate(all_zones):
            if zone.bar_index < 0 or zone.freshness == "broken":
                continue
            start = zone.bar_index + 1
            if start >= n:
                continue
            if zone.zone_type == "demand":
                if any(close_arr[j] < zone.low for j in range(start, n)):
                    all_zones[i] = dataclasses.replace(zone, freshness="broken")
            else:
                if any(close_arr[j] > zone.high for j in range(start, n)):
                    all_zones[i] = dataclasses.replace(zone, freshness="broken")

        # VWAP zones from intraday data (optional — skipped if data unavailable)
        try:
            vwap_zones = VWAPZoneDetector().detect(symbol, db, atr=atr, current_price=price)
            all_zones.extend(vwap_zones)
        except Exception as e:
            logger.debug("[ZoneEngine] VWAP detector failed for %s: %s", symbol, e)

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
        candle_signal = _detect_candle_signal(df_ind)

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
            candle_signal=candle_signal,
        )

        # Upsert to DB
        result_json = {
            "demand_zones": [zone_to_dict(z) for z in result.demand_zones],
            "supply_zones":  [zone_to_dict(z) for z in result.supply_zones],
            "long_setup":    setup_to_dict(long_setup),
            "short_setup":   setup_to_dict(short_setup),
            "market_structure": structure,
            "atr": result.atr, "rvol": result.rvol,
            "candle_signal": candle_signal,
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
                         best_long_rr, best_short_rr, result_json,
                         pct_from_52w_high, pct_from_52w_low,
                         long_entry_price, short_entry_price)
                    VALUES
                        (:sym, :dt, :bd, :bs, :ls, :ss, :pr, :atr, :rv, :pt, :lr, :sr, :rj,
                         :p52h, :p52l, :lep, :sep)
                    ON CONFLICT (symbol, computed_date) DO UPDATE SET
                        best_demand_score  = EXCLUDED.best_demand_score,
                        best_supply_score  = EXCLUDED.best_supply_score,
                        long_setup_score   = EXCLUDED.long_setup_score,
                        short_setup_score  = EXCLUDED.short_setup_score,
                        price_at_compute   = EXCLUDED.price_at_compute,
                        atr_at_compute     = EXCLUDED.atr_at_compute,
                        rvol_at_compute    = EXCLUDED.rvol_at_compute,
                        position_tag       = EXCLUDED.position_tag,
                        best_long_rr       = EXCLUDED.best_long_rr,
                        best_short_rr      = EXCLUDED.best_short_rr,
                        result_json        = EXCLUDED.result_json,
                        pct_from_52w_high  = EXCLUDED.pct_from_52w_high,
                        pct_from_52w_low   = EXCLUDED.pct_from_52w_low,
                        long_entry_price   = EXCLUDED.long_entry_price,
                        short_entry_price  = EXCLUDED.short_entry_price,
                        created_at         = CURRENT_TIMESTAMP
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
                    "p52h": pct_from_52w_high, "p52l": pct_from_52w_low,
                    "lep": long_setup.ideal_entry if long_setup else None,
                    "sep": short_setup.ideal_entry if short_setup else None,
                },
            )
            db.commit()
        except Exception as e:
            db.rollback()
            logger.warning("[ZoneEngine] DB upsert failed for %s: %s", symbol, e)

        return result
