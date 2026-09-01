"""NSE earnings / results-announcement calendar fetcher.

NSE blocks unauthenticated requests — must GET the home page first to
obtain session cookies, then call the event-calendar API with those cookies.

On any failure the fetcher logs a warning and returns empty results so
the scheduler loop is never broken by a transient NSE outage.
"""
import logging
from datetime import date

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_NSE_HOME = "https://www.nseindia.com/"
_NSE_EVENTS = "https://www.nseindia.com/api/event-calendar"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}


class EarningsFetcher:
    def fetch(self) -> list[dict]:
        """Establish NSE session and return upcoming earnings events.

        Returns list of dicts with keys: symbol, result_date (date), event_type (str).
        Returns empty list on any error.
        """
        try:
            with httpx.Client(headers=_HEADERS, follow_redirects=True, timeout=15.0) as client:
                client.get(_NSE_HOME)  # obtain session cookies
                resp = client.get(_NSE_EVENTS)
                resp.raise_for_status()
                events = resp.json()
        except Exception:
            logger.warning("[EarningsFetcher] NSE fetch failed", exc_info=True)
            return []

        if not isinstance(events, list):
            logger.warning("[EarningsFetcher] unexpected response shape: %s", type(events))
            return []

        results = []
        for e in events:
            purpose = (e.get("purpose") or "").strip()
            if "result" not in purpose.lower():
                continue
            symbol = (e.get("symbol") or "").strip().upper()
            raw_date = e.get("date") or e.get("from") or ""
            if not symbol or not raw_date:
                continue
            try:
                result_date = date.fromisoformat(str(raw_date)[:10])
            except (ValueError, TypeError):
                continue
            results.append({
                "symbol": symbol,
                "result_date": result_date,
                "event_type": purpose,
            })

        logger.info("[EarningsFetcher] fetched %d upcoming earnings events", len(results))
        return results

    def refresh(self, db: Session) -> int:
        """Fetch from NSE and upsert into earnings_calendar. Returns row count upserted."""
        events = self.fetch()
        if not events:
            return 0

        count = 0
        for e in events:
            try:
                db.execute(text("""
                    INSERT INTO earnings_calendar (symbol, result_date, event_type)
                    VALUES (:sym, :rd, :et)
                    ON CONFLICT (symbol, result_date) DO UPDATE SET
                        event_type = EXCLUDED.event_type,
                        fetched_at = CURRENT_TIMESTAMP
                """), {
                    "sym": e["symbol"],
                    "rd": str(e["result_date"]),
                    "et": e["event_type"],
                })
                count += 1
            except Exception:
                logger.warning("[EarningsFetcher] upsert failed for %s", e["symbol"], exc_info=True)

        db.commit()
        logger.info("[EarningsFetcher] upserted %d earnings rows", count)
        return count
