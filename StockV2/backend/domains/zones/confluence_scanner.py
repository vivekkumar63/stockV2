"""ConfluenceScanner — combine zone quality + breakout momentum into one ranked list.

Two categories returned:
  BREAKOUT      price already above resistance (0–6%) with ≥4/6 conviction signals
                AND zone ML confidence ≥ 0.45
  NEAR_BREAKOUT price within 3% below the best supply zone (resistance), zone quality good

Combined score formula
  BREAKOUT:      0.35 × breakout_ml_prob + 0.35 × zone_ml_conf
                 + 0.20 × (conviction/6) + 0.10 × min(vol_ratio/3, 1)
  NEAR_BREAKOUT: 0.50 × zone_ml_conf + 0.30 × (supply_score/100)
                 + 0.20 × min(vol_ratio/2, 1)
"""
from __future__ import annotations
import json
import logging
import math
from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

from .ml_scorer import MLZoneScorer
from .breakout_ml import BreakoutMLScorer

logger = logging.getLogger(__name__)

_BREAKOUT_MAX_PCT   = 6.0
_NEAR_RESIST_PCT    = 3.0   # within 3% below resistance
_ZONE_ML_MIN        = 0.45  # min zone ML for breakout confirmation
_NEAR_ZONE_ML_MIN   = 0.40  # min zone ML for near-breakout watchlist
_CONVICTION_MIN     = 4


def _safe(v, default: float = 0.0) -> float:
    try:
        x = float(v)
        return x if math.isfinite(x) else default
    except (TypeError, ValueError):
        return default


class ConfluenceScanner:
    def scan(self, db: Session) -> dict:
        today = str(date.today())

        # ── Load zone analysis results ─────────────────────────────────────
        zone_rows = db.execute(text("""
            SELECT symbol, price_at_compute, atr_at_compute,
                   best_supply_score, result_json, position_tag
            FROM zone_analysis_results
            WHERE computed_date = :dt
        """), {"dt": today}).fetchall()

        if not zone_rows:
            logger.info("[ConfluenceScanner] no zone data for %s", today)
            return {"breakouts": [], "near_breakout": []}

        symbols = [r[0] for r in zone_rows]

        # ── Batch OHLCV + 20d avg volume + 52-week high/low ───────────────
        ohlcv_map: dict[str, dict] = {}
        week52_map: dict[str, dict] = {}
        if symbols:
            ohlcv_rows = db.execute(text("""
                WITH ranked AS (
                    SELECT symbol, date, close, volume, high, low, open,
                           ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) AS rn
                    FROM stock_prices_daily WHERE symbol = ANY(:syms)
                ),
                avg_vol AS (
                    SELECT symbol, AVG(volume) AS avg_vol_20
                    FROM ranked WHERE rn <= 20 GROUP BY symbol
                )
                SELECT r.symbol, r.close, r.volume, r.high, r.low, r.open, a.avg_vol_20
                FROM ranked r
                JOIN avg_vol a ON a.symbol = r.symbol
                WHERE r.rn = 1
            """), {"syms": symbols}).fetchall()

            for r in ohlcv_rows:
                ohlcv_map[r[0]] = {
                    "close": float(r[1] or 0), "volume": float(r[2] or 0),
                    "high": float(r[3] or 0), "low": float(r[4] or 0),
                    "open": float(r[5] or 0), "avg_vol_20": float(r[6] or 1),
                }

            w52_rows = db.execute(text("""
                SELECT symbol,
                       MAX(high) AS high_52w,
                       MIN(low)  AS low_52w
                FROM (
                    SELECT symbol, high, low,
                           ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) AS rn
                    FROM stock_prices_daily WHERE symbol = ANY(:syms)
                ) sub
                WHERE rn <= 252
                GROUP BY symbol
            """), {"syms": symbols}).fetchall()

            for r in w52_rows:
                week52_map[r[0]] = {"high_52w": float(r[1] or 0), "low_52w": float(r[2] or 0)}

        # ── Batch indicators: RSI, EMA50, EMA50 slope ─────────────────────
        ind_map: dict[str, dict] = {}
        try:
            ind_rows = db.execute(text("""
                WITH ranked AS (
                    SELECT symbol, rsi_14, ema_50,
                           ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) AS rn
                    FROM stock_indicators_daily WHERE symbol = ANY(:syms)
                )
                SELECT symbol,
                       MAX(CASE WHEN rn = 1 THEN rsi_14 END) AS rsi,
                       MAX(CASE WHEN rn = 1 THEN ema_50  END) AS ema50_now,
                       MAX(CASE WHEN rn = 5 THEN ema_50  END) AS ema50_prev
                FROM ranked WHERE rn <= 5
                GROUP BY symbol
            """), {"syms": symbols}).fetchall()

            for r in ind_rows:
                ema_now  = float(r[2]) if r[2] is not None else 0.0
                ema_prev = float(r[3]) if r[3] is not None else 0.0
                slope = 0.0
                if ema_prev > 0 and ema_now > 0 and math.isfinite(ema_now):
                    slope = (ema_now - ema_prev) / ema_prev * 100
                ind_map[r[0]] = {
                    "rsi": float(r[1]) if r[1] is not None else 50.0,
                    "ema50": ema_now,
                    "ema50_slope_pct": round(slope, 2),
                }
        except Exception as e:
            logger.debug("[ConfluenceScanner] indicator load failed: %s", e)

        breakouts: list[dict]      = []
        near_breakout: list[dict]  = []

        for zrow in zone_rows:
            sym, price_at, atr_at, sup_score, rj_raw, pos_tag = zrow

            rj = rj_raw if isinstance(rj_raw, dict) else json.loads(rj_raw or "{}")
            supply_zones = rj.get("supply_zones", [])
            demand_zones = rj.get("demand_zones", [])
            long_setup   = rj.get("long_setup")
            short_setup  = rj.get("short_setup")

            valid_supply = [z for z in supply_zones if z.get("freshness") != "broken"]
            if not valid_supply:
                continue
            best_supply = max(valid_supply, key=lambda z: z.get("score", 0))
            resistance  = best_supply.get("high") or 0.0
            if not resistance or not math.isfinite(resistance):
                continue

            ohlcv = ohlcv_map.get(sym)
            if not ohlcv:
                continue
            close   = ohlcv["close"]
            vol     = ohlcv["volume"]
            high    = ohlcv["high"]
            low     = ohlcv["low"]
            opn     = ohlcv["open"]
            avg_v   = ohlcv["avg_vol_20"]

            if close <= 0 or not math.isfinite(close):
                continue

            w52     = week52_map.get(sym, {})
            high52  = w52.get("high_52w", close)
            low52   = w52.get("low_52w", close)
            pct_52h = (close - high52) / high52 * 100 if high52 > 0 else 0.0
            pct_52l = (close - low52)  / low52  * 100 if low52  > 0 else 0.0

            ind           = ind_map.get(sym, {"rsi": 50.0, "ema50": 0.0, "ema50_slope_pct": 0.0})
            rsi           = ind["rsi"]
            ema50         = ind["ema50"]
            ema50_slope   = ind["ema50_slope_pct"]

            atr        = _safe(atr_at, close * 0.01)
            if atr <= 0:
                atr = close * 0.01
            vol_ratio  = vol / avg_v if avg_v > 0 else 1.0
            rng        = high - low
            body       = abs(close - opn)
            body_ratio = body / rng if rng > 0 else 0.0
            rng_atr    = rng / atr if atr > 0 else 0.0

            # ── Build zone-ML feature dict ─────────────────────────────────
            ls_score  = _safe(rj.get("long_setup_score")  or (long_setup or {}).get("score", 0))
            ss_score  = _safe(rj.get("short_setup_score") or (short_setup or {}).get("score", 0))
            best_d_sc = max((_safe(z.get("score", 0)) for z in demand_zones), default=0.0)
            best_lr   = _safe((long_setup  or {}).get("t2_rr") or (long_setup  or {}).get("t1_rr"))
            best_sr   = _safe((short_setup or {}).get("t2_rr") or (short_setup or {}).get("t1_rr"))

            zone_row_dict = {
                "long_setup_score":  ls_score,
                "short_setup_score": ss_score,
                "best_demand_score": best_d_sc,
                "best_supply_score": _safe(sup_score),
                "best_long_rr":      best_lr,
                "best_short_rr":     best_sr,
                "rvol_at_compute":   vol_ratio,
                "position_tag":      pos_tag or "neutral",
                "pct_from_52w_high": pct_52h,
                "pct_from_52w_low":  pct_52l,
            }
            zone_ml_conf = MLZoneScorer.predict(zone_row_dict)

            dist_pct = (close - resistance) / resistance * 100  # + = above, − = below

            # ── BREAKOUT path ──────────────────────────────────────────────
            if 0 < dist_pct <= _BREAKOUT_MAX_PCT:
                # Check 6 conviction signals
                signals_met:    list[str] = []
                signals_failed: list[str] = []

                def chk(label: str, cond: bool) -> None:
                    (signals_met if cond else signals_failed).append(label)

                chk("Closed above resistance",          close > resistance)
                chk("Volume ≥ 1.5× 20d avg",           vol_ratio >= 1.5)
                chk("RSI > 55 (momentum building)",     rsi > 55)
                chk("Bullish candle body > 50%",        body_ratio > 0.50 and close > opn)
                chk("Above EMA-50 (trend aligned)",     ema50 > 0 and close > ema50)
                chk("Breakout bar range > 0.8× ATR",    rng > 0.8 * atr)

                conviction = len(signals_met)
                if conviction < _CONVICTION_MIN:
                    continue
                if zone_ml_conf < _ZONE_ML_MIN:
                    continue

                bt_signal = {
                    "volume_ratio":     round(vol_ratio, 2),
                    "rsi":              round(rsi, 1),
                    "body_ratio":       round(body_ratio, 3),
                    "range_atr_ratio":  round(rng_atr, 2),
                    "conviction_score": conviction,
                    "breakout_pct":     round(dist_pct, 2),
                    "ema50_slope_pct":  ema50_slope,
                }
                bk_ml_prob = BreakoutMLScorer.predict(bt_signal)

                combined = (
                    0.35 * bk_ml_prob
                    + 0.35 * zone_ml_conf
                    + 0.20 * (conviction / 6)
                    + 0.10 * min(vol_ratio / 3, 1.0)
                )

                breakouts.append({
                    "symbol":                   sym,
                    "category":                 "breakout",
                    "current_price":            round(close, 2),
                    "resistance":               round(resistance, 2),
                    "breakout_pct":             round(dist_pct, 2),
                    "volume_ratio":             round(vol_ratio, 2),
                    "rsi":                      round(rsi, 1),
                    "ema50_slope_pct":          ema50_slope,
                    "body_ratio":               round(body_ratio, 3),
                    "range_atr_ratio":          round(rng_atr, 2),
                    "conviction_score":         conviction,
                    "signals_met":              signals_met,
                    "signals_failed":           signals_failed,
                    "zone_ml_confidence":       round(zone_ml_conf, 3),
                    "breakout_ml_probability":  round(bk_ml_prob, 3),
                    "combined_score":           round(combined, 3),
                    "zone_score":               _safe(sup_score),
                    "market_structure":         rj.get("market_structure", "sideways"),
                    "candle_signal":            rj.get("candle_signal", "NONE"),
                    "position_tag":             pos_tag or "neutral",
                    "long_setup":               long_setup,
                    "short_setup":              short_setup,
                })

            # ── NEAR_BREAKOUT path ─────────────────────────────────────────
            elif -_NEAR_RESIST_PCT <= dist_pct <= 0:
                if zone_ml_conf < _NEAR_ZONE_ML_MIN:
                    continue

                combined = (
                    0.50 * zone_ml_conf
                    + 0.30 * (_safe(sup_score) / 100)
                    + 0.20 * min(vol_ratio / 2, 1.0)
                )

                near_breakout.append({
                    "symbol":               sym,
                    "category":             "near_breakout",
                    "current_price":        round(close, 2),
                    "resistance":           round(resistance, 2),
                    "dist_to_resistance":   round(dist_pct, 2),   # negative = below
                    "volume_ratio":         round(vol_ratio, 2),
                    "rsi":                  round(rsi, 1),
                    "ema50_slope_pct":      ema50_slope,
                    "zone_ml_confidence":   round(zone_ml_conf, 3),
                    "combined_score":       round(combined, 3),
                    "zone_score":           _safe(sup_score),
                    "market_structure":     rj.get("market_structure", "sideways"),
                    "candle_signal":        rj.get("candle_signal", "NONE"),
                    "position_tag":         pos_tag or "neutral",
                    "long_setup":           long_setup,
                    "demand_zones":         demand_zones,
                })

        breakouts.sort(key=lambda x: x["combined_score"], reverse=True)
        near_breakout.sort(key=lambda x: x["combined_score"], reverse=True)

        logger.info(
            "[ConfluenceScanner] %d breakouts, %d near-breakout for %s",
            len(breakouts), len(near_breakout), today,
        )
        return {"breakouts": breakouts, "near_breakout": near_breakout}
