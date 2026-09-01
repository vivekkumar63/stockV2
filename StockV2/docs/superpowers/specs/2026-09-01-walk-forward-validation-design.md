# Walk-Forward Validation — Design Spec

**Date:** 2026-09-01

## Goal

Validate that each strategy's historical backtest performance is consistent across time, not just an artifact of a single lucky period. Walk-forward testing divides history into multiple non-overlapping out-of-sample windows and checks whether the strategy was profitable in each one. A strategy that is consistently profitable across many windows is trustworthy; one that only looked good in one period is not.

---

## Methodology

**Window approach:** Non-overlapping 6-month test windows over a 3-year lookback. No separate training phase is needed because strategy parameters (indicators, entry/exit conditions) are fixed — we are only validating consistency, not optimising parameters.

Example windows over 2022-01-01 → 2024-12-31:
```
Window 1: 2022-01-01 → 2022-06-30
Window 2: 2022-07-01 → 2022-12-31
Window 3: 2023-01-01 → 2023-06-30
Window 4: 2023-07-01 → 2023-12-31
Window 5: 2024-01-01 → 2024-06-30
Window 6: 2024-07-01 → 2024-12-31
```

**Symbol sample:** For each window, run `BacktestRunner.run()` on up to 30 symbols selected from stocks already present in `scan_result_cache` (symbols with at least 1 completed backtest). This avoids running on symbols with no historical data. If fewer than 10 symbols are available for a strategy, the validation is skipped.

**Per-window metric:** Average `win_rate` across all symbols that had ≥ 1 trade in the window.

**Per-strategy metrics:**
- `oos_win_rate`: mean win rate across all (window × symbol) observations
- `windows_profitable_pct`: fraction of windows where average win_rate > 50%
- `grade`: derived from both metrics (see below)

---

## Grading

| Grade | OOS Win Rate | Windows Profitable |
|---|---|---|
| A | ≥ 60% | ≥ 5 of 6 |
| B | ≥ 52% | ≥ 4 of 6 |
| C | ≥ 45% | ≥ 3 of 6 |
| D | below C | below C |

If a window has no trades for a symbol (strategy didn't fire), that symbol is excluded from that window's average (not counted as 0%). A window with fewer than 3 symbols with trades is excluded from the grade calculation.

---

## Architecture

### New file: `backend/domains/backtest/walk_forward.py`

```python
class WalkForwardEngine:
    def run(self, db, strategy_id: int,
            lookback_years: int = 3,
            window_months: int = 6,
            max_symbols: int = 30) -> dict:
        """Run walk-forward validation. Returns metrics dict."""

    def _get_symbols(self, db, strategy_id: int, max_symbols: int) -> list[str]:
        """Select symbols from scan_result_cache that have trades for this strategy."""

    def _generate_windows(self, lookback_years, window_months) -> list[tuple[date, date]]:
        """Return list of (start, end) date pairs."""

    def _run_window(self, db, strategy_id, symbols, start, end) -> dict:
        """Run BacktestRunner on each symbol for this window. Return aggregated metrics."""

    def _grade(self, oos_win_rate, windows_profitable_pct) -> str:
        """Return A/B/C/D grade."""
```

### New DB table

```sql
CREATE TABLE IF NOT EXISTS walk_forward_results (
    id SERIAL PRIMARY KEY,
    strategy_id INTEGER NOT NULL,
    lookback_years INTEGER NOT NULL,
    window_months INTEGER NOT NULL,
    n_symbols INTEGER,
    n_windows INTEGER,
    oos_win_rate REAL,
    windows_profitable_pct REAL,
    grade VARCHAR(2),
    windows_json TEXT,
    ran_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_wf_strategy ON walk_forward_results (strategy_id);
```

`windows_json` stores the per-window breakdown:
```json
[
  {"start": "2022-01-01", "end": "2022-06-30", "win_rate": 0.56, "n_symbols": 28, "n_trades": 143},
  ...
]
```

### New API endpoints (in `backend/domains/backtest/router.py`)

| Method | Path | Purpose |
|---|---|---|
| POST | `/backtest/walk-forward/run` | Start background job for all strategies |
| GET | `/backtest/walk-forward/status` | Job running/idle, progress |
| GET | `/backtest/walk-forward/results` | All stored results (latest per strategy) |

Background job state stored as a module-level dict (same pattern as `special/precompute`).

### Frontend

New "Walk-Forward" accordion section at the bottom of `BacktestPage.tsx`:
- "Run Validation" button → POST to `/backtest/walk-forward/run`
- Progress bar while running (polls `/backtest/walk-forward/status`)
- Results table: Strategy | Grade | OOS Win Rate | Windows Profitable | Last Run

---

## Files Changed

| File | Action |
|---|---|
| `backend/domains/backtest/walk_forward.py` | NEW — `WalkForwardEngine` |
| `backend/domains/backtest/router.py` | MODIFY — 3 new endpoints |
| `backend/main.py` | MODIFY — add `walk_forward_results` table |
| `frontend/src/api/backtest.ts` | MODIFY — add walk-forward API functions |
| `frontend/src/pages/BacktestPage.tsx` | MODIFY — add walk-forward section |

---

## Verification

1. `POST /api/v1/backtest/walk-forward/run` → status 200, job starts
2. `GET /api/v1/backtest/walk-forward/status` → `{"is_running": true, "done": 2, "total": 8}`
3. After completion: `GET /api/v1/backtest/walk-forward/results` → list with one row per strategy, each with `grade`, `oos_win_rate`, `windows_profitable_pct`
4. Frontend: results table populates, grades shown as coloured chips (A=green, B=blue, C=yellow, D=red)
