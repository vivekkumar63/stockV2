"""NSE FII/DII participant-wise equity flow fetcher."""
import logging
from datetime import date
from typing import Optional

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_NSE_HOME = "https://www.nseindia.com"
_NSE_FII_DII_URL = "https://www.nseindia.com/api/fiidiiTradeReact"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}


def _parse_fii_dii_response(rows: list[dict]) -> Optional[dict]:
    """
    Parse the flat list returned by NSE fiidiiTradeReact.
    Returns dict with fii_*/dii_* keys or None if no relevant rows found.
    NSE uses either 'category' or 'clientType' as the participant key.
    """
    def _key(row: dict) -> str:
        return (row.get("category") or row.get("clientType") or "").upper()

    def _float(val) -> Optional[float]:
        try:
            return float(str(val).replace(",", ""))
        except (TypeError, ValueError):
            return None

    fii_row = next((r for r in rows if "FII" in _key(r)), None)
    dii_row = next((r for r in rows if _key(r) == "DII"), None)

    if not fii_row and not dii_row:
        return None

    return {
        "fii_buy":        _float(fii_row.get("buyValue"))  if fii_row else None,
        "fii_sell":       _float(fii_row.get("sellValue")) if fii_row else None,
        "fii_net_equity": _float(fii_row.get("netValue"))  if fii_row else None,
        "dii_buy":        _float(dii_row.get("buyValue"))  if dii_row else None,
        "dii_sell":       _float(dii_row.get("sellValue")) if dii_row else None,
        "dii_net_equity": _float(dii_row.get("netValue"))  if dii_row else None,
    }


def fetch_and_store_fii_dii(db: Session) -> None:
    """
    Fetch today's FII/DII participant data from NSE and upsert into fii_dii_daily.
    NSE requires a two-step HTTP flow: first GET the home page to get cookies,
    then GET the API endpoint with those cookies.
    Logs a warning and returns silently on any failure.
    """
    today = str(date.today())
    try:
        with httpx.Client(headers=_HEADERS, follow_redirects=True, timeout=15.0) as client:
            client.get(_NSE_HOME)  # establish session cookie
            r = client.get(_NSE_FII_DII_URL)
            r.raise_for_status()
            raw = r.json()
    except Exception:
        logger.exception("[fii_dii] NSE fetch failed — skipping")
        return

    # The API may return a list directly or wrap it under a key
    if isinstance(raw, dict):
        raw = raw.get("data", []) or []

    parsed = _parse_fii_dii_response(raw)
    if not parsed:
        logger.warning("[fii_dii] could not parse response — no FII/DII rows found")
        return

    try:
        db.execute(
            text("""
                INSERT INTO fii_dii_daily
                    (date, fii_net_equity, dii_net_equity, fii_buy, fii_sell, dii_buy, dii_sell)
                VALUES (:date, :fii_net, :dii_net, :fii_buy, :fii_sell, :dii_buy, :dii_sell)
                ON CONFLICT(date) DO UPDATE SET
                    fii_net_equity=excluded.fii_net_equity,
                    dii_net_equity=excluded.dii_net_equity,
                    fii_buy=excluded.fii_buy, fii_sell=excluded.fii_sell,
                    dii_buy=excluded.dii_buy, dii_sell=excluded.dii_sell,
                    fetched_at=CURRENT_TIMESTAMP
            """),
            {
                "date":      today,
                "fii_net":   parsed["fii_net_equity"],
                "dii_net":   parsed["dii_net_equity"],
                "fii_buy":   parsed["fii_buy"],
                "fii_sell":  parsed["fii_sell"],
                "dii_buy":   parsed["dii_buy"],
                "dii_sell":  parsed["dii_sell"],
            },
        )
        db.commit()
        logger.info("[fii_dii] stored: FII net=%.0f Cr  DII net=%.0f Cr",
                    parsed["fii_net_equity"] or 0, parsed["dii_net_equity"] or 0)
    except Exception:
        logger.exception("[fii_dii] DB upsert failed")


def get_latest_fii_dii(db: Session) -> Optional[dict]:
    """Return the most recent row from fii_dii_daily, or None if table is empty."""
    row = db.execute(
        text("SELECT * FROM fii_dii_daily ORDER BY date DESC LIMIT 1")
    ).mappings().fetchone()
    return dict(row) if row else None
