"""
Multi-timeframe trend alignment using resampled daily OHLCV.

Intraday data is not populated in this application, so higher timeframes are
derived by resampling the daily OHLCV series:
  - Daily   : raw data (no resampling)
  - Weekly  : OHLCV aggregated per ISO-week (resample 'W')
  - Monthly : OHLCV aggregated per calendar month (resample 'MS')

Each timeframe is independently evaluated for:
  - EMA(20) vs EMA(50) relationship
  - Price vs EMA(20)
  - RSI(14)
  - MACD(12, 26, 9) direction

Alignment score weights (daily is most actionable, monthly is context):
  Monthly : 0.20
  Weekly  : 0.35
  Daily   : 0.45

Score 0.0 = all timeframes bearish, 1.0 = all timeframes bullish.
"""

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)

# Minimum bars per timeframe to produce a meaningful reading
MIN_BARS_DAILY   = 30
MIN_BARS_WEEKLY  = 12   # ~3 months
MIN_BARS_MONTHLY = 6    # 6 months

# Calendar days to load for resampling (need ~24 months for monthly context)
HISTORY_LOAD_DAYS = 550

# Timeframe weights for alignment score
TIMEFRAME_WEIGHTS = {
    "MONTHLY": 0.20,
    "WEEKLY":  0.35,
    "DAILY":   0.45,
}

# Trend classification thresholds
RSI_BULLISH_THRESHOLD = 52   # RSI above this → bullish momentum bias
RSI_BEARISH_THRESHOLD = 48   # RSI below this → bearish momentum bias


@dataclass
class TimeframeView:
    timeframe: str          # "DAILY" | "WEEKLY" | "MONTHLY"
    trend: str              # "BULLISH" | "NEUTRAL" | "BEARISH"
    ema20: float
    ema50: float
    last_close: float
    ema_fast_above_slow: bool   # EMA20 > EMA50
    price_above_ema20: bool     # close > EMA20
    rsi: float
    macd_bullish: bool          # MACD line > signal line
    bars_available: int


@dataclass
class MTFResult:
    symbol: str
    as_of_date: date
    daily: Optional[TimeframeView]
    weekly: Optional[TimeframeView]
    monthly: Optional[TimeframeView]
    alignment_score: float   # 0.0–1.0
    alignment_label: str     # STRONGLY_BULLISH | BULLISH | MIXED | BEARISH | STRONGLY_BEARISH


class MultiTimeframeEngine:
    """
    Analyses trend alignment across daily, weekly, and monthly timeframes
    using only the existing daily price database — no intraday dependency.
    """

    def compute(self, db: Session, symbol: str, as_of_date: Optional[date] = None) -> MTFResult:
        from ist import ist_today
        target = as_of_date or ist_today()
        cutoff = target - timedelta(days=HISTORY_LOAD_DAYS)

        rows = db.execute(
            text("""
                SELECT date, open, high, low, close, volume
                FROM stock_prices_daily
                WHERE symbol = :sym AND date >= :cutoff AND date <= :target
                ORDER BY date ASC
            """),
            {"sym": symbol.upper(), "cutoff": str(cutoff), "target": str(target)},
        ).fetchall()

        if len(rows) < MIN_BARS_DAILY:
            return self._empty(symbol, target)

        df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"])
        df["date"] = pd.to_datetime(df["date"])
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].astype(float)
        df = df.set_index("date").sort_index()

        daily_view   = self._analyze(df,                             "DAILY",   MIN_BARS_DAILY)
        weekly_view  = self._analyze(self._resample(df, "W"),        "WEEKLY",  MIN_BARS_WEEKLY)
        monthly_view = self._analyze(self._resample(df, "MS"),       "MONTHLY", MIN_BARS_MONTHLY)

        score, label = self._alignment_score([daily_view, weekly_view, monthly_view])

        return MTFResult(
            symbol=symbol,
            as_of_date=target,
            daily=daily_view,
            weekly=weekly_view,
            monthly=monthly_view,
            alignment_score=round(score, 4),
            alignment_label=label,
        )

    # ── Resampling ────────────────────────────────────────────────────────────

    def _resample(self, df: pd.DataFrame, freq: str) -> pd.DataFrame:
        """Aggregate daily OHLCV to weekly ('W') or monthly ('MS') bars."""
        return df.resample(freq).agg({
            "open":   "first",
            "high":   "max",
            "low":    "min",
            "close":  "last",
            "volume": "sum",
        }).dropna(subset=["close"])

    # ── Per-timeframe analysis ────────────────────────────────────────────────

    def _analyze(self, df: pd.DataFrame, timeframe: str, min_bars: int) -> Optional[TimeframeView]:
        if df is None or len(df) < min_bars:
            return None

        closes = df["close"].astype(float)
        n      = len(closes)

        # EMA(20) and EMA(50) — span = period
        ema20_series = closes.ewm(span=20, adjust=False).mean()
        ema50_span   = min(50, max(10, n // 2))  # degrade gracefully when bars are limited
        ema50_series = closes.ewm(span=ema50_span, adjust=False).mean()

        last_close = float(closes.iloc[-1])
        last_ema20 = float(ema20_series.iloc[-1])
        last_ema50 = float(ema50_series.iloc[-1])

        ema_fast_above = last_ema20 > last_ema50
        price_above    = last_close > last_ema20

        rsi_val      = self._rsi(closes)
        macd_bull    = self._macd_bullish(closes)

        # Classify trend: requires alignment of EMA, price position, and RSI
        if ema_fast_above and price_above and rsi_val > RSI_BULLISH_THRESHOLD:
            trend = "BULLISH"
        elif not ema_fast_above and not price_above and rsi_val < RSI_BEARISH_THRESHOLD:
            trend = "BEARISH"
        else:
            trend = "NEUTRAL"

        return TimeframeView(
            timeframe=timeframe,
            trend=trend,
            ema20=round(last_ema20, 2),
            ema50=round(last_ema50, 2),
            last_close=round(last_close, 2),
            ema_fast_above_slow=ema_fast_above,
            price_above_ema20=price_above,
            rsi=round(rsi_val, 2),
            macd_bullish=macd_bull,
            bars_available=n,
        )

    # ── Indicator helpers ─────────────────────────────────────────────────────

    def _rsi(self, closes: pd.Series, period: int = 14) -> float:
        """RSI using Wilder's exponential smoothing (com = period - 1).

        When avg_loss == 0 (no down days), RS = infinity and RSI = 100.
        Using a tiny epsilon (1e-10) instead of float('inf') to avoid
        gain/inf = 0 which would incorrectly give RSI = 0.
        """
        delta = closes.diff()
        gain  = delta.clip(lower=0).ewm(com=period - 1, adjust=False).mean()
        loss  = (-delta.clip(upper=0)).ewm(com=period - 1, adjust=False).mean()
        rs    = gain / loss.replace(0, 1e-10)   # loss=0 → RS very large → RSI→100
        rsi   = 100 - (100 / (1 + rs))
        val   = float(rsi.iloc[-1])
        return val if pd.notna(val) else 50.0

    def _macd_bullish(self, closes: pd.Series) -> bool:
        """True when MACD line (EMA12 - EMA26) is above signal line (EMA9 of MACD)."""
        if len(closes) < 26:
            return False
        macd_line   = closes.ewm(span=12, adjust=False).mean() - closes.ewm(span=26, adjust=False).mean()
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        return float(macd_line.iloc[-1]) > float(signal_line.iloc[-1])

    # ── Alignment scoring ─────────────────────────────────────────────────────

    def _alignment_score(self, views: list[Optional[TimeframeView]]) -> tuple[float, str]:
        """
        Weighted average of per-timeframe scores.
        BULLISH = 1.0, NEUTRAL = 0.5, BEARISH = 0.0

        Alignment labels:
          ≥ 0.80 → STRONGLY_BULLISH
          ≥ 0.60 → BULLISH
          ≥ 0.40 → MIXED
          ≥ 0.20 → BEARISH
          <  0.20 → STRONGLY_BEARISH
        """
        total_weight = 0.0
        weighted_sum = 0.0

        for view in views:
            if view is None:
                continue
            w   = TIMEFRAME_WEIGHTS.get(view.timeframe, 0.33)
            val = 1.0 if view.trend == "BULLISH" else (0.0 if view.trend == "BEARISH" else 0.5)
            weighted_sum  += val * w
            total_weight  += w

        if total_weight == 0:
            return 0.5, "MIXED"

        score = weighted_sum / total_weight

        if score >= 0.80:
            label = "STRONGLY_BULLISH"
        elif score >= 0.60:
            label = "BULLISH"
        elif score >= 0.40:
            label = "MIXED"
        elif score >= 0.20:
            label = "BEARISH"
        else:
            label = "STRONGLY_BEARISH"

        return round(score, 4), label

    def _empty(self, symbol: str, as_of_date: date) -> MTFResult:
        return MTFResult(
            symbol=symbol, as_of_date=as_of_date,
            daily=None, weekly=None, monthly=None,
            alignment_score=0.5, alignment_label="MIXED",
        )
