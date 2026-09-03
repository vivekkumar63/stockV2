"""BreakoutScanner — detect stocks breaking above key resistance with conviction.

Six conviction signals per stock. Requires ≥4 to surface a result.
Reads from precomputed zone_analysis_results (today) + stock_prices_daily
+ stock_indicators_daily. Single batch query per table for speed.
"""
from __future__ import annotations
import json
import logging
import math
from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_CONVICTION_THRESHOLD = 4   # out of 6 signals
_MAX_BREAKOUT_PCT     = 6.0  # ignore stocks >6% above resistance (stale)


class BreakoutScanner:
    def scan(self, db: Session) -> list[dict]:
        """Return breakout signals for today, sorted by conviction desc."""
        today = str(date.today())

        # ── Load today's zone analysis results ────────────────────────────
        zone_rows = db.execute(text("""
            SELECT symbol, price_at_compute, atr_at_compute,
                   best_supply_score, result_json, position_tag
            FROM zone_analysis_results
            WHERE computed_date = :dt
        """), {"dt": today}).fetchall()

        if not zone_rows:
            logger.info("[BreakoutScanner] no zone data for %s", today)
            return []

        symbols = [r[0] for r in zone_rows]

        # ── Batch load: latest OHLCV + 20d avg volume ─────────────────────
        ohlcv_map: dict[str, dict] = {}
        if symbols:
            ohlcv_rows = db.execute(text("""
                WITH ranked AS (
                    SELECT symbol, date, close, volume, high, low, open,
                           ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) AS rn
                    FROM stock_prices_daily
                    WHERE symbol = ANY(:syms)
                ),
                avg_vol AS (
                    SELECT symbol, AVG(volume) AS avg_vol_20
                    FROM ranked WHERE rn <= 20
                    GROUP BY symbol
                )
                SELECT r.symbol, r.close, r.volume, r.high, r.low, r.open, a.avg_vol_20
                FROM ranked r
                JOIN avg_vol a ON a.symbol = r.symbol
                WHERE r.rn = 1
            """), {"syms": symbols}).fetchall()

            for r in ohlcv_rows:
                ohlcv_map[r[0]] = {
                    "close": float(r[1] or 0),
                    "volume": float(r[2] or 0),
                    "high": float(r[3] or 0),
                    "low": float(r[4] or 0),
                    "open": float(r[5] or 0),
                    "avg_vol_20": float(r[6] or 1),
                }

        # ── Batch load: latest indicators ─────────────────────────────────
        ind_map: dict[str, dict] = {}
        try:
            ind_rows = db.execute(text("""
                WITH ranked AS (
                    SELECT symbol, rsi_14, ema_50,
                           ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) AS rn
                    FROM stock_indicators_daily
                    WHERE symbol = ANY(:syms)
                )
                SELECT symbol, rsi_14, ema_50 FROM ranked WHERE rn = 1
            """), {"syms": symbols}).fetchall()

            for r in ind_rows:
                ind_map[r[0]] = {
                    "rsi": float(r[1]) if r[1] is not None else 50.0,
                    "ema50": float(r[2]) if r[2] is not None else 0.0,
                }
        except Exception as e:
            logger.debug("[BreakoutScanner] indicator load failed: %s", e)

        # ── Evaluate each stock ───────────────────────────────────────────
        signals: list[dict] = []

        for zrow in zone_rows:
            sym, price_at, atr_at, sup_score, rj_raw, pos_tag = zrow

            rj = rj_raw if isinstance(rj_raw, dict) else json.loads(rj_raw or "{}")
            supply_zones = rj.get("supply_zones", [])
            if not supply_zones:
                continue

            # Best (highest scored, non-broken) supply zone → key resistance
            valid_supply = [z for z in supply_zones if z.get("freshness") != "broken"]
            if not valid_supply:
                continue
            best_supply = max(valid_supply, key=lambda z: z.get("score", 0))
            resistance  = best_supply.get("high") or 0.0
            if not resistance or not math.isfinite(resistance):
                continue

            # Also check trendline resistance for additional S/R context
            tl_resistance = _nearest_trendline_resistance(supply_zones, resistance)

            ohlcv = ohlcv_map.get(sym)
            if not ohlcv:
                continue
            close  = ohlcv["close"]
            vol    = ohlcv["volume"]
            high   = ohlcv["high"]
            low    = ohlcv["low"]
            opn    = ohlcv["open"]
            avg_v  = ohlcv["avg_vol_20"]

            if close <= 0 or not math.isfinite(close):
                continue

            # Must be above resistance
            breakout_pct = (close - resistance) / resistance * 100
            if breakout_pct <= 0 or breakout_pct > _MAX_BREAKOUT_PCT:
                continue

            ind    = ind_map.get(sym, {"rsi": 50.0, "ema50": 0.0})
            rsi    = ind["rsi"]
            ema50  = ind["ema50"]

            vol_ratio  = vol / avg_v if avg_v > 0 else 1.0
            rng        = high - low
            body       = abs(close - opn)
            body_ratio = body / rng if rng > 0 else 0.0
            atr        = float(atr_at) if atr_at and math.isfinite(float(atr_at)) else close * 0.01

            # ── 6 conviction signals ──────────────────────────────────────
            met:    list[str] = []
            failed: list[str] = []

            def chk(label: str, cond: bool) -> None:
                (met if cond else failed).append(label)

            chk("Closed above resistance",             close > resistance)
            chk("Volume ≥ 1.5× 20d avg",              vol_ratio >= 1.5)
            chk("RSI > 55 (momentum building)",        rsi > 55)
            chk("Bullish candle body > 50%",           body_ratio > 0.50 and close > opn)
            chk("Above EMA-50 (trend aligned)",        ema50 > 0 and close > ema50)
            chk("Breakout bar range > 0.8× ATR",       rng > 0.8 * atr)

            score = len(met)
            if score < _CONVICTION_THRESHOLD:
                continue

            signals.append({
                "symbol":           sym,
                "current_price":    round(close, 2),
                "resistance":       round(resistance, 2),
                "breakout_pct":     round(breakout_pct, 2),
                "volume_ratio":     round(vol_ratio, 2),
                "rsi":              round(rsi, 1),
                "conviction_score": score,
                "signals_met":      met,
                "signals_failed":   failed,
                "zone_score":       sup_score,
                "market_structure": rj.get("market_structure", "sideways"),
                "candle_signal":    rj.get("candle_signal", "NONE"),
                "trendline_resistance": round(tl_resistance, 2) if tl_resistance else None,
            })

        signals.sort(key=lambda x: (x["conviction_score"], x["volume_ratio"]), reverse=True)
        logger.info("[BreakoutScanner] %d signal(s) found for %s", len(signals), today)
        return signals


def _nearest_trendline_resistance(supply_zones: list[dict], resistance: float) -> float | None:
    """Return trendline_resistance zone high closest to resistance, if any."""
    tl = [z for z in supply_zones
          if "trendline_resistance" in (z.get("source_tags") or [])]
    if not tl:
        return None
    candidates = [z.get("high", 0) for z in tl if z.get("high")]
    if not candidates:
        return None
    return min(candidates, key=lambda p: abs(p - resistance))
