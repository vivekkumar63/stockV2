import logging
from datetime import date, datetime
from typing import Optional

import pandas as pd
import yfinance as yf
from sqlalchemy import text
from sqlalchemy.orm import Session

from domains.data.nse_universe import get_yfinance_symbol

logger = logging.getLogger(__name__)


class YFinanceFeed:
    """Downloads and validates historical OHLCV data from Yahoo Finance."""

    def download_since(self, symbol: str, since: date) -> pd.DataFrame:
        """Download only data from since to today — used for incremental daily updates."""
        try:
            ticker = yf.Ticker(get_yfinance_symbol(symbol))
            raw = ticker.history(start=str(since), interval="1d", auto_adjust=True)
            if raw.empty:
                return pd.DataFrame()
            df = raw.copy()
            df.columns = [c.lower() for c in df.columns]
            df.index = pd.to_datetime(df.index.date)
            df = df[["open", "high", "low", "close", "volume"]].copy()
            return df
        except Exception as e:
            logger.warning("yfinance incremental download failed for %s: %s", symbol, e)
            return pd.DataFrame()

    def download(self, symbol: str, years: int = 15) -> pd.DataFrame:
        """Download historical daily OHLCV for a single NSE symbol.

        Returns empty DataFrame on any failure — caller decides what to do.
        """
        try:
            ticker = yf.Ticker(get_yfinance_symbol(symbol))
            raw = ticker.history(period=f"{years}y", interval="1d", auto_adjust=True)
            if raw.empty:
                return pd.DataFrame()
            df = raw.copy()
            df.columns = [c.lower() for c in df.columns]
            df.index = pd.to_datetime(df.index.date)
            df = df[["open", "high", "low", "close", "volume"]].copy()
            return df
        except Exception as e:
            logger.warning("yfinance download failed for %s: %s", symbol, e)
            return pd.DataFrame()

    def validate_row(self, high: float, low: float, close: float, volume: int) -> bool:
        """Return False if a row fails basic sanity checks."""
        if volume <= 0:
            return False
        if high <= 0 or low <= 0 or close <= 0:
            return False
        if low > high:
            return False
        if high / max(low, 0.01) > 2.0:
            return False
        return True

    def get_last_date(self, db: Session, symbol: str) -> Optional[date]:
        """Return the most recent date stored for this symbol, or None."""
        result = db.execute(
            text("SELECT MAX(date) FROM stock_prices_daily WHERE symbol = :s"),
            {"s": symbol},
        )
        value = result.scalar()
        if value is None:
            return None
        return datetime.strptime(str(value), "%Y-%m-%d").date()

    def upsert_prices(self, db: Session, symbol: str, df: pd.DataFrame) -> int:
        """Insert rows from df into stock_prices_daily, skipping invalid rows.

        Uses INSERT OR IGNORE (SQLite) to handle duplicates gracefully.
        Returns count of rows inserted.
        """
        if df.empty:
            return 0

        inserted = 0
        for row_date, row in df.iterrows():
            if not self.validate_row(
                high=row["high"], low=row["low"],
                close=row["close"], volume=int(row["volume"])
            ):
                db.execute(
                    text("""
                        INSERT OR IGNORE INTO data_quality_log
                            (symbol, date, issue_type, details)
                        VALUES (:sym, :dt, 'bad_tick', :det)
                    """),
                    {
                        "sym": symbol,
                        "dt": str(row_date),
                        "det": f"high={row['high']}, low={row['low']}, vol={row['volume']}",
                    },
                )
                continue

            db.execute(
                text("""
                    INSERT OR IGNORE INTO stock_prices_daily
                        (symbol, date, open, high, low, close, volume, data_source)
                    VALUES (:sym, :dt, :o, :h, :l, :c, :v, 'yfinance')
                """),
                {
                    "sym": symbol, "dt": str(row_date),
                    "o": float(row["open"]),   "h": float(row["high"]),
                    "l": float(row["low"]),    "c": float(row["close"]),
                    "v": int(row["volume"]),
                },
            )
            inserted += 1

        db.commit()
        return inserted
