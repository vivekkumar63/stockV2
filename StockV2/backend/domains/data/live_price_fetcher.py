"""Fetches live intraday prices for a list of NSE symbols via yfinance."""
import logging
from typing import Optional

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)


def fetch_live_prices(symbols: list[str]) -> dict[str, float]:
    """
    Returns {symbol: latest_price} for each symbol using the most recent 5-min close.
    Symbols absent from the result had a fetch error — callers must handle missing keys.
    """
    if not symbols:
        return {}

    yf_symbols = [f"{s}.NS" for s in symbols]
    try:
        data = yf.download(
            yf_symbols if len(yf_symbols) > 1 else yf_symbols[0],
            period="1d",
            interval="5m",
            progress=False,
            auto_adjust=True,
            group_by="ticker",
        )
    except Exception:
        logger.exception("[live_price] yfinance download failed for %d symbols", len(symbols))
        return {}

    if data is None or (isinstance(data, pd.DataFrame) and data.empty):
        logger.warning("[live_price] empty response for symbols: %s", symbols)
        return {}

    result: dict[str, float] = {}

    if len(symbols) == 1:
        # Single symbol: flat columns (Close, Open, ...)
        try:
            closes = data["Close"].dropna()
            if not closes.empty:
                result[symbols[0]] = float(closes.iloc[-1])
        except (KeyError, IndexError):
            logger.warning("[live_price] no Close data for %s", symbols[0])
    else:
        # Multiple symbols: MultiIndex columns (yf_symbol, field)
        for sym, yf_sym in zip(symbols, yf_symbols):
            try:
                closes = data[yf_sym]["Close"].dropna()
                if not closes.empty:
                    result[sym] = float(closes.iloc[-1])
            except (KeyError, IndexError):
                logger.debug("[live_price] no data for %s", sym)

    logger.info("[live_price] fetched %d/%d symbols", len(result), len(symbols))
    return result
