"""BreakoutBacktester — historical simulation of the breakout-signal strategy.

Entry signal (mirrors BreakoutScanner, but uses rolling 20-day high as resistance
instead of pre-computed zone data so backtesting is fully self-contained):

  1. close > 20-day rolling high (prior bars, not today)  ← breakout condition
  2. Volume ≥ 1.5× 20-day avg vol
  3. RSI > 55
  4. Bullish body > 50% of candle range
  5. Close > EMA-50
  6. Bar range > 0.8× ATR

Require ≥ 4 out of 6 signals.

Exit logic:
  Stop Loss  : close back below resistance − 0.3 × ATR (breakout failed)
  Target     : entry + 2.5 × ATR
  Max hold   : 15 trading days  (force-close at close price)

One position at a time. New signal ignored while already in a trade.
"""
from __future__ import annotations
import logging
import math
from dataclasses import dataclass
from datetime import date

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from domains.data.indicators import IndicatorEngine

logger = logging.getLogger(__name__)

LOOKBACK       = 20    # bars for rolling resistance / avg-volume
CONVICTION_MIN = 4     # signals required
STOP_ATR       = 0.3   # SL = resistance − STOP_ATR × ATR
TARGET_ATR     = 2.5   # target = entry + TARGET_ATR × ATR
MAX_HOLD       = 15    # trading days before force-close


@dataclass
class BreakoutTrade:
    entry_date:      date
    entry_price:     float
    resistance:      float
    exit_date:       date
    exit_price:      float
    pnl_pct:         float
    exit_reason:     str   # target_hit | stop_loss | max_hold | end_of_period
    hold_days:       int
    # signal snapshot (used for ML training)
    volume_ratio:    float
    rsi:             float
    body_ratio:      float
    range_atr_ratio: float
    conviction_score: int
    breakout_pct:    float
    ema50_slope_pct: float


def _to_py_date(v) -> date:
    if isinstance(v, date):
        return v
    try:
        return v.date()
    except AttributeError:
        import datetime
        return datetime.date.fromisoformat(str(v)[:10])


class BreakoutBacktester:
    def run(self, symbol: str, from_date: date, to_date: date,
            db: Session) -> list[BreakoutTrade]:
        rows = db.execute(text("""
            SELECT date, open, high, low, close, volume FROM (
                SELECT date, open, high, low, close, volume
                FROM stock_prices_daily
                WHERE symbol = :s
                ORDER BY date DESC LIMIT 700
            ) sub ORDER BY date ASC
        """), {"s": symbol}).fetchall()

        if not rows or len(rows) < LOOKBACK + 10:
            return []

        df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"])
        for c in ("open", "high", "low", "close", "volume"):
            df[c] = df[c].astype(float)

        try:
            df_ind = IndicatorEngine.compute(df)
        except Exception as e:
            logger.debug("[BreakoutBacktester] indicator compute failed for %s: %s", symbol, e)
            return []

        n = len(df_ind)
        trades: list[BreakoutTrade] = []
        pos: dict | None = None  # open position info

        high_arr  = df_ind["high"].to_numpy()
        low_arr   = df_ind["low"].to_numpy()
        close_arr = df_ind["close"].to_numpy()
        open_arr  = df_ind["open"].to_numpy()
        vol_arr   = df_ind["volume"].to_numpy()
        date_arr  = [_to_py_date(df_ind["date"].iloc[i]) for i in range(n)]

        def _safe(col: str, idx: int, default: float = 0.0) -> float:
            if col not in df_ind.columns:
                return default
            v = df_ind[col].iloc[idx]
            try:
                x = float(v)
                return x if math.isfinite(x) else default
            except (TypeError, ValueError):
                return default

        for i in range(LOOKBACK + 5, n):
            d = date_arr[i]
            if d < from_date:
                continue
            if d > to_date:
                break

            close = close_arr[i]
            high  = high_arr[i]
            low_p = low_arr[i]
            opn   = open_arr[i]
            vol   = vol_arr[i]

            atr = _safe("atr_14", i, close * 0.01)
            if atr <= 0:
                atr = close * 0.01

            # ── Manage open position ──────────────────────────────────────────
            if pos is not None:
                hold = i - pos["entry_idx"]
                if low_p <= pos["stop_loss"]:
                    exit_p = pos["stop_loss"]
                    pnl = (exit_p - pos["entry_price"]) / pos["entry_price"] * 100
                    trades.append(_make(pos, d, exit_p, pnl, "stop_loss", hold))
                    pos = None
                elif high >= pos["target"]:
                    exit_p = pos["target"]
                    pnl = (exit_p - pos["entry_price"]) / pos["entry_price"] * 100
                    trades.append(_make(pos, d, exit_p, pnl, "target_hit", hold))
                    pos = None
                elif hold >= MAX_HOLD:
                    pnl = (close - pos["entry_price"]) / pos["entry_price"] * 100
                    trades.append(_make(pos, d, close, pnl, "max_hold", hold))
                    pos = None
                # Do not scan for new signals while in trade
                continue

            # ── Breakout signal check ─────────────────────────────────────────
            # resistance = max high of the prior LOOKBACK bars (strictly before today)
            resistance = float(high_arr[i - LOOKBACK:i].max())
            if resistance <= 0:
                continue

            breakout_pct = (close - resistance) / resistance * 100
            if breakout_pct <= 0 or breakout_pct > 6.0:
                continue

            avg_vol   = float(vol_arr[i - LOOKBACK:i].mean()) or 1.0
            vol_ratio = vol / avg_vol

            rsi  = _safe("rsi_14", i, 50.0)
            ema50 = _safe("ema_50", i, 0.0)

            rng        = high - low_p
            body       = abs(close - opn)
            body_ratio = body / rng if rng > 0 else 0.0
            rng_atr    = rng / atr

            met = sum([
                close > resistance,
                vol_ratio >= 1.5,
                rsi > 55,
                body_ratio > 0.50 and close > opn,
                ema50 > 0 and close > ema50,
                rng > 0.8 * atr,
            ])
            if met < CONVICTION_MIN:
                continue

            # EMA50 slope over last 5 bars
            ema50_slope = 0.0
            if "ema_50" in df_ind.columns and i >= 5:
                prev = _safe("ema_50", i - 5)
                if prev > 0 and ema50 > 0:
                    ema50_slope = (ema50 - prev) / prev * 100

            pos = {
                "entry_idx":     i,
                "entry_date":    d,
                "entry_price":   close,
                "resistance":    round(resistance, 2),
                "stop_loss":     resistance - STOP_ATR * atr,
                "target":        close + TARGET_ATR * atr,
                "volume_ratio":  round(vol_ratio, 2),
                "rsi":           round(rsi, 1),
                "body_ratio":    round(body_ratio, 3),
                "range_atr_ratio": round(rng_atr, 2),
                "conviction_score": met,
                "breakout_pct":  round(breakout_pct, 2),
                "ema50_slope_pct": round(ema50_slope, 2),
            }

        # Force-close any remaining position
        if pos is not None:
            # Find the last bar on or before to_date
            last_i = max(
                (j for j in range(n - 1, pos["entry_idx"], -1) if date_arr[j] <= to_date),
                default=pos["entry_idx"],
            )
            last_close = close_arr[last_i]
            pnl = (last_close - pos["entry_price"]) / pos["entry_price"] * 100
            trades.append(_make(pos, date_arr[last_i], last_close, pnl,
                                "end_of_period", last_i - pos["entry_idx"]))

        return trades


def _make(pos: dict, exit_date: date, exit_price: float,
          pnl_pct: float, reason: str, hold: int) -> BreakoutTrade:
    return BreakoutTrade(
        entry_date=pos["entry_date"],
        entry_price=round(pos["entry_price"], 2),
        resistance=pos["resistance"],
        exit_date=exit_date,
        exit_price=round(exit_price, 2),
        pnl_pct=round(pnl_pct, 2),
        exit_reason=reason,
        hold_days=hold,
        volume_ratio=pos["volume_ratio"],
        rsi=pos["rsi"],
        body_ratio=pos["body_ratio"],
        range_atr_ratio=pos["range_atr_ratio"],
        conviction_score=pos["conviction_score"],
        breakout_pct=pos["breakout_pct"],
        ema50_slope_pct=pos["ema50_slope_pct"],
    )
