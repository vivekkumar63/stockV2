"""Index OHLCV fetcher and trend computer for the 7 NSE sector indices."""
import logging
from datetime import date
from typing import Optional

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from domains.data.index_universe import INDEX_DEFINITIONS

logger = logging.getLogger(__name__)


# ── Pure helpers (no DB) ──────────────────────────────────────────────────────

def _compute_trend_label(above_sma20: bool, above_sma50: bool) -> str:
    if above_sma20 and above_sma50:
        return "STRONG_BULL"
    if above_sma20 and not above_sma50:
        return "BULL"
    if not above_sma20 and above_sma50:
        return "NEUTRAL"
    return "BEAR"


def compute_index_alignment_score(index_trend_row: Optional[dict]) -> int:
    """
    Returns a 0–100 raw score for the index alignment component.
    Pass None if the stock is not mapped to any sector index (returns 50 = neutral).
    """
    if index_trend_row is None:
        return 50
    above20 = bool(index_trend_row.get("above_sma20"))
    above50 = bool(index_trend_row.get("above_sma50"))
    if above20 and above50:
        return 100
    if above20 and not above50:
        return 70
    if not above20 and above50:
        return 40
    return 15


# ── DB-backed functions ────────────────────────────────────────────────────────

def compute_index_trends(db: Session) -> None:
    """Read index_prices_daily, compute SMA20/SMA50 for each index, upsert to index_trend."""
    today = date.today()

    for index_name in INDEX_DEFINITIONS:
        rows = db.execute(
            text("""
                SELECT date, close FROM index_prices_daily
                WHERE index_name = :name
                ORDER BY date DESC
                LIMIT 60
            """),
            {"name": index_name},
        ).fetchall()

        if not rows:
            logger.warning("[index_trend] no price data for %s — skipping", index_name)
            continue

        closes = pd.Series(
            [r[1] for r in reversed(rows)],
            index=[r[0] for r in reversed(rows)],
            dtype=float,
        )
        latest_close = float(closes.iloc[-1])
        sma20 = float(closes.rolling(20).mean().iloc[-1]) if len(closes) >= 20 else None
        sma50 = float(closes.rolling(50).mean().iloc[-1]) if len(closes) >= 50 else None

        above_sma20 = int(latest_close > sma20) if sma20 is not None else 0
        above_sma50 = int(latest_close > sma50) if sma50 is not None else 0
        trend_label = _compute_trend_label(bool(above_sma20), bool(above_sma50))

        db.execute(
            text("""
                INSERT INTO index_trend
                    (index_name, date, close, sma20, sma50, above_sma20, above_sma50, trend_label)
                VALUES (:name, :date, :close, :sma20, :sma50, :a20, :a50, :label)
                ON CONFLICT(index_name, date) DO UPDATE SET
                    close=excluded.close, sma20=excluded.sma20, sma50=excluded.sma50,
                    above_sma20=excluded.above_sma20, above_sma50=excluded.above_sma50,
                    trend_label=excluded.trend_label, computed_at=CURRENT_TIMESTAMP
            """),
            {
                "name": index_name, "date": str(today),
                "close": latest_close, "sma20": sma20, "sma50": sma50,
                "a20": above_sma20, "a50": above_sma50, "label": trend_label,
            },
        )
        logger.info("[index_trend] %s: close=%.1f sma20=%s sma50=%s → %s",
                    index_name, latest_close,
                    f"{sma20:.1f}" if sma20 else "N/A",
                    f"{sma50:.1f}" if sma50 else "N/A",
                    trend_label)

    db.commit()


def fetch_and_store_index_prices(db: Session, days: int = 365) -> None:
    """Download last `days` of daily OHLCV for all 7 sector indices and upsert."""
    import yfinance as yf
    import time as _time

    for index_name, meta in INDEX_DEFINITIONS.items():
        yf_symbol = meta["yf_symbol"]
        try:
            df = yf.download(
                yf_symbol,
                period=f"{days}d",
                interval="1d",
                progress=False,
                auto_adjust=True,
            )
            if df.empty:
                logger.warning("[index_fetch] %s (%s): empty response", index_name, yf_symbol)
                continue

            df = df.reset_index()
            df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
            df["date"] = pd.to_datetime(df["Date"]).dt.date

            for _, row in df.iterrows():
                db.execute(
                    text("""
                        INSERT INTO index_prices_daily
                            (index_name, date, open, high, low, close, volume)
                        VALUES (:name, :date, :open, :high, :low, :close, :volume)
                        ON CONFLICT(index_name, date) DO UPDATE SET
                            open=excluded.open, high=excluded.high, low=excluded.low,
                            close=excluded.close, volume=excluded.volume
                    """),
                    {
                        "name": index_name,
                        "date": str(row["date"]),
                        "open":   float(row.get("Open",   row.get("open",   0))) or None,
                        "high":   float(row.get("High",   row.get("high",   0))) or None,
                        "low":    float(row.get("Low",    row.get("low",    0))) or None,
                        "close":  float(row.get("Close",  row.get("close",  0))),
                        "volume": float(row.get("Volume", row.get("volume", 0))) or None,
                    },
                )
            db.commit()
            logger.info("[index_fetch] %s: %d rows upserted", index_name, len(df))
        except Exception:
            logger.exception("[index_fetch] %s (%s): failed", index_name, yf_symbol)
        _time.sleep(0.3)
