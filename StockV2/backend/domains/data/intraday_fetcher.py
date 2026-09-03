from __future__ import annotations
import logging
import pandas as pd
import yfinance as yf
from sqlalchemy import text
from sqlalchemy.orm import Session
from domains.data.nse_universe import get_yfinance_symbol

logger = logging.getLogger(__name__)


class IntradayFetcher:
    def fetch_one(self, symbol: str) -> pd.DataFrame:
        """Download last 5 days of 5-min bars for a symbol. Returns empty DF on failure."""
        try:
            ticker = yf.Ticker(get_yfinance_symbol(symbol))
            raw = ticker.history(period="5d", interval="5m", auto_adjust=True)
            if raw.empty:
                return pd.DataFrame()
            df = raw.copy()
            df.columns = [c.lower() for c in df.columns]
            df = df[["open", "high", "low", "close", "volume"]].copy()
            df.index.name = "datetime"
            df = df.reset_index()
            df["datetime"] = pd.to_datetime(df["datetime"])
            if df["datetime"].dt.tz is not None:
                df["datetime"] = df["datetime"].dt.tz_convert("Asia/Kolkata").dt.tz_localize(None)
            df = df.dropna(subset=["open", "high", "low", "close"])
            df = df[df["close"] > 0]
            return df[["datetime", "open", "high", "low", "close", "volume"]].reset_index(drop=True)
        except Exception as e:
            logger.warning("[IntradayFetcher] fetch failed for %s: %s", symbol, e)
            return pd.DataFrame()

    def fetch_and_store(self, symbols: list[str], db: Session) -> int:
        """Fetch 5-min bars for all symbols and upsert into intraday_prices_5m. Returns number of rows fetched (not necessarily inserted)."""
        total = 0
        for symbol in symbols:
            df = self.fetch_one(symbol)
            if df.empty:
                continue
            try:
                rows_to_insert = [
                    {
                        "sym": symbol,
                        "dt": row["datetime"],
                        "o": float(row["open"]),
                        "h": float(row["high"]),
                        "l": float(row["low"]),
                        "c": float(row["close"]),
                        "v": int(row["volume"]) if pd.notna(row["volume"]) else 0,
                    }
                    for _, row in df.iterrows()
                ]
                db.execute(text("""
                    INSERT INTO intraday_prices_5m (symbol, datetime, open, high, low, close, volume)
                    VALUES (:sym, :dt, :o, :h, :l, :c, :v)
                    ON CONFLICT (symbol, datetime) DO NOTHING
                """), rows_to_insert)
                db.commit()
                total += len(df)
                logger.debug("[IntradayFetcher] stored %d rows for %s", len(df), symbol)
            except Exception as e:
                db.rollback()
                logger.warning("[IntradayFetcher] DB write failed for %s: %s", symbol, e)
        return total
