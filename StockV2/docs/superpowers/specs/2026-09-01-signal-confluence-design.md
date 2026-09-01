# Signal Confluence Score — Design Spec

**Date:** 2026-09-01

## Goal

When multiple strategies independently fire a BUY signal on the same stock on the same day, that agreement is a stronger signal than any single strategy firing alone. Surface this "confluence" as a bonus on the opportunity score and as a visible badge in the UI.

---

## How Confluence Is Computed

The `strategy_signals` table has a UNIQUE constraint on `(symbol, strategy_id, signal_date)`. Counting strategies per symbol per day is therefore a SQL window function with no extra joins or tables:

```sql
COUNT(*) OVER (PARTITION BY ss.symbol, ss.signal_date) AS confluence_count
```

This is added to the existing `GET /intelligence/top-opportunities` query. Each signal row in the result set carries the count of how many strategies agree on that symbol today.

---

## Score Integration

Confluence is applied as a **post-computation bonus multiplier** inside `OpportunityScorer.full_score()` and `quick_score()`, analogous to the existing `false_signal_rate` multiplier:

| Strategies agreeing | Multiplier | Effect on score of 70 |
|---|---|---|
| 1 | ×1.00 | 70 |
| 2 | ×1.05 | 74 |
| 3 | ×1.10 | 77 |
| 4+ | ×1.15 | 81 |

Score is capped at 100 after the bonus. The `confluence_count` is stored in the breakdown dict so callers can see why the score is elevated.

`full_score()` and `quick_score()` gain a new `confluence_count: int = 1` parameter. Default of 1 means no change to existing callers that don't pass it.

---

## Files Changed

| File | Change |
|---|---|
| `backend/domains/intelligence/opportunity_scorer.py` | Add `confluence_count` param to `full_score()` and `quick_score()`; apply multiplier; store in breakdown |
| `backend/domains/intelligence/router.py` | Add window function to top-opportunities SQL; compute `confluence_map: dict[str, int]` (symbol → count) before the loop; pass to scorer; include `confluence_count` in each result dict |
| `frontend/src/api/intelligence.ts` | Add `confluence_count: number` to the signal/opportunity interface |
| `frontend/src/pages/DashboardPage.tsx` (or TopOpportunities component) | Show "2 strats" / "3 strats" badge (amber for 2, green for 3+) on each row |

---

## API Response Change

`GET /intelligence/top-opportunities` response adds one field per item:

```json
{
  "symbol": "RELIANCE",
  "strategy_id": 3,
  "confluence_count": 3,
  "score": 77,
  ...
}
```

---

## Behaviour Details

- Confluence is computed across **all active strategies**, not just the one shown in the row. If 3 strategies fired on RELIANCE today and this row is for strategy 2, `confluence_count` is still 3.
- The `quick_score()` path (scanner endpoint) also accepts `confluence_count` but the scanner doesn't compute it — defaults to 1 (no bonus). Only the top-opportunities endpoint computes and applies confluence.
- Walk-forward and earnings calendar features are independent — no dependency.

---

## Verification

1. Seed two strategy signals for the same symbol on the same date in different strategy_ids → `GET /api/v1/intelligence/top-opportunities` → both rows have `confluence_count: 2` and higher scores than a symbol with only 1 strategy.
2. Symbol with only 1 strategy → `confluence_count: 1`, score unchanged.
3. Frontend: row with confluence ≥ 2 shows badge.
