# Earnings Calendar — Design Spec

**Date:** 2026-09-01

## Goal

Flag signals where the underlying stock is announcing quarterly results within the next 5 days. Entering a position before earnings is high-risk regardless of what technical signals say. Show a visible warning on Top Opportunities and Special Recommendations so the user can make an informed decision — but never silently hide signals.

---

## Data Source

NSE's event calendar endpoint returns upcoming corporate events including board meetings and results announcements. It requires a session (NSE blocks raw requests without cookies).

**Fetch procedure:**
1. `GET https://www.nseindia.com/` — establishes session, receives `nsit` and `nseappid` cookies
2. `GET https://www.nseindia.com/api/event-calendar` — returns JSON array of upcoming corporate events with cookies + `Referer: https://www.nseindia.com/` header
3. Filter events where `purpose` field contains "Result" (case-insensitive)
4. Extract `symbol`, `date` (the result announcement date), `purpose`

**Refresh schedule:** Daily at 06:00 IST via the existing scheduler. Fetches events for the next 30 days and upserts into `earnings_calendar`. Old events (result_date < today) are not deleted — kept for historical reference.

**Fragility note:** NSE changes their API endpoints periodically. The fetcher isolates all NSE-specific logic in one file (`earnings_fetcher.py`) so it can be updated without touching other code.

---

## New DB Table

```sql
CREATE TABLE IF NOT EXISTS earnings_calendar (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    result_date DATE NOT NULL,
    event_type VARCHAR(100),
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (symbol, result_date)
);
CREATE INDEX IF NOT EXISTS idx_earnings_symbol ON earnings_calendar (symbol);
CREATE INDEX IF NOT EXISTS idx_earnings_date ON earnings_calendar (result_date);
```

---

## Architecture

### New file: `backend/domains/data/earnings_fetcher.py`

```python
class EarningsFetcher:
    NSE_HOME = "https://www.nseindia.com/"
    NSE_EVENTS = "https://www.nseindia.com/api/event-calendar"

    def fetch(self) -> list[dict]:
        """Establish NSE session and return list of upcoming earnings events.
        Returns: [{"symbol": "TCS", "result_date": date(...), "event_type": "Quarterly Results"}, ...]
        """

    def refresh(self, db) -> int:
        """Fetch and upsert into earnings_calendar. Returns count of rows upserted."""
```

Session management: use `requests.Session()`, GET the homepage first, reuse cookies for the API call. Set `User-Agent` to a modern browser string to avoid blocks.

On fetch failure (NSE down, API changed): log a warning and return empty list. Never raise — a missing earnings calendar is acceptable; a broken scheduler is not.

### Integration: `days_to_earnings` field

Both `GET /intelligence/top-opportunities` and `GET /special/recommendations` add a `days_to_earnings: int | null` field to each signal in the response.

**Computation (bulk, not per-signal):**
```python
# One query for all symbols in the result set
upcoming = db.execute(text("""
    SELECT symbol, MIN(result_date) as next_result
    FROM earnings_calendar
    WHERE result_date BETWEEN :today AND :cutoff
    GROUP BY symbol
"""), {"today": today, "cutoff": today + timedelta(days=30)}).fetchall()
earnings_map = {r[0]: (r[1] - today).days for r in upcoming}

# Per signal:
days_to_earnings = earnings_map.get(symbol)  # None if no upcoming earnings
```

### Scheduler integration

Add a new daily job in `backend/scheduler.py`:

```python
scheduler.add_job(
    _refresh_earnings,
    CronTrigger(hour=6, minute=15, timezone="Asia/Kolkata"),
    id="earnings_calendar_refresh",
    replace_existing=True,
)
```

---

## Frontend Changes

### Top Opportunities table

Each row that has `days_to_earnings` ≤ 5 shows an amber warning:
- Icon: ⚠️
- Tooltip or inline text: "Earnings in X days"
- Row background: no change (don't visually bury the signal)

### Special Recommendations

Same treatment on the Special Strategies scan results table.

---

## Files Changed

| File | Action |
|---|---|
| `backend/domains/data/earnings_fetcher.py` | NEW — `EarningsFetcher` |
| `backend/main.py` | MODIFY — add `earnings_calendar` table, trigger initial fetch on startup if table is empty |
| `backend/scheduler.py` | MODIFY — add daily refresh job at 06:15 IST |
| `backend/domains/intelligence/router.py` | MODIFY — add `days_to_earnings` bulk lookup and include in top-opportunities response |
| `backend/domains/special_strategies/router.py` | MODIFY — same for special recommendations |
| `frontend/src/api/intelligence.ts` | MODIFY — add `days_to_earnings: number | null` to signal type |
| `frontend/src/api/special.ts` | MODIFY — same |
| `frontend` top-opportunities and special scan tables | MODIFY — render earnings warning badge |

---

## Verification

1. `EarningsFetcher().fetch()` returns a non-empty list of dicts with `symbol`, `result_date`, `event_type` keys (requires network access to NSE)
2. `EarningsFetcher().refresh(db)` returns int > 0 and rows appear in `earnings_calendar`
3. Seed a row in `earnings_calendar` for symbol "RELIANCE" with `result_date = today + 3 days` → `GET /api/v1/intelligence/top-opportunities` → any RELIANCE signal has `days_to_earnings: 3`
4. Symbol with no upcoming earnings → `days_to_earnings: null`
5. Frontend: RELIANCE row shows ⚠️ "Earnings in 3 days" badge
