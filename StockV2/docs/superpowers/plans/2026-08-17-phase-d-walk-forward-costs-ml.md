# Phase D: Walk-Forward Backtest, Transaction Costs, ML Probability Model — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add walk-forward out-of-sample testing, realistic transaction costs (commission + slippage), and ML-based signal probability scoring to detect overfitting and improve signal quality.

**Architecture:** `BacktestSimulator` is extended to model round-trip costs (0.30% default for Indian equities). `WalkForwardRunner` divides historical price data into rolling test windows (12-month lookback, 3-month test), runs simulator on each OOS window, and computes consistency metrics. `MLSignalScorer` trains a GradientBoostingClassifier on Phase C's `signal_outcomes` data (features: confidence, regime, strategy_id, temporal) and predicts probability for new signals. `OpportunityScorer` incorporates ML probability as an 8-weight component.

**Tech Stack:** Python 3.11, pandas, scikit-learn (GradientBoostingClassifier), joblib (model persistence), FastAPI, SQLAlchemy 2.0

**Existing foundation:**
- `backend/domains/backtest/simulator.py` — `BacktestSimulator.run()`, `SimTrade` dataclass, `_close()` method
- `backend/domains/backtest/runner.py` — `BacktestRunner.run()`, `scan_all()`, `precompute_all_for_strategy()`
- `backend/domains/backtest/metrics.py` — `compute_metrics()`
- `backend/domains/intelligence/opportunity_scorer.py` — `OpportunityScorer` with 7-component scoring
- `backend/models.py` — `SignalOutcome` table (Phase C)
- `backend/scheduler.py` — `MONTHLY_ML_RETRAIN` job stub

---

## File Map

```
backend/
├── domains/
│   ├── backtest/
│   │   ├── simulator.py          MODIFY — add round_trip_cost_pct param; add commission field to SimTrade; deduct costs in _close()
│   │   ├── walk_forward.py       NEW — WalkForwardRunner.run(), WalkForwardWindow/Result dataclasses
│   │   ├── router.py             MODIFY — add POST /backtests/walk-forward + GET /backtests/walk-forward/{symbol}/{strategy_id}
│   │   └── runner.py             MODIFY — pass round_trip_cost_pct=0.30 to simulator calls (run, scan_all, precompute_all_for_strategy)
│   ├── intelligence/
│   │   ├── ml_scorer.py          NEW — MLSignalScorer: train GBC on signal_outcomes, predict probability
│   │   ├── opportunity_scorer.py MODIFY — add ml_signal_probability component (weight 8), rebalance other weights
│   │   └── router.py             MODIFY — call MLSignalScorer.predict() in get_opportunity_score()
│   └── ...
├── models.py                     MODIFY — add WalkForwardResult table
├── scheduler.py                  MODIFY — wire _monthly_ml_retrain() to MLSignalScorer.train()
├── ml_models/                    NEW directory — .gitignore: *.pkl
└── tests/
    ├── test_backtest_simulator.py MODIFY — add cost tests
    ├── test_walk_forward.py       NEW — WalkForwardRunner tests
    └── test_ml_scorer.py          NEW — MLSignalScorer tests
```

---

### Task 1: Add transaction costs to BacktestSimulator

**Files:**
- Modify: `backend/domains/backtest/simulator.py`
- Test: `backend/tests/test_backtest_simulator.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_backtest_simulator.py (append to end of file)

def test_round_trip_cost_reduces_pnl():
    """Verify round-trip cost deducts from raw PnL."""
    from domains.backtest.simulator import BacktestSimulator
    df = _make_prices(250)  # existing helper
    from_date, to_date = df["date"][50], df["date"].iloc[-1]
    
    # Run with 0% cost
    trades_no_cost = BacktestSimulator().run(
        symbol="TCS", prices_df=df,
        from_date=from_date, to_date=to_date,
        strategies=[_AlwaysBuyStrategy()],
        use_aggregator=False, initial_capital=500_000.0,
        round_trip_cost_pct=0.0,
    )
    
    # Run with 0.30% cost
    trades_with_cost = BacktestSimulator().run(
        symbol="TCS", prices_df=df,
        from_date=from_date, to_date=to_date,
        strategies=[_AlwaysBuyStrategy()],
        use_aggregator=False, initial_capital=500_000.0,
        round_trip_cost_pct=0.30,
    )
    
    assert len(trades_no_cost) == len(trades_with_cost)
    for t_no, t_yes in zip(trades_no_cost, trades_with_cost):
        # PnL with cost should be lower
        assert t_yes.pnl < t_no.pnl
        # Commission should be > 0
        assert t_yes.commission > 0
        # Commission = entry_value * round_trip_cost_pct / 100
        entry_value = t_yes.entry_price * t_yes.quantity
        expected_commission = round(entry_value * 0.30 / 100, 2)
        assert abs(t_yes.commission - expected_commission) < 0.01


def test_zero_cost_pnl_unchanged():
    """Verify 0% cost produces same PnL as default (backward compat check)."""
    from domains.backtest.simulator import BacktestSimulator
    df = _make_prices(250)
    from_date, to_date = df["date"][50], df["date"].iloc[-1]
    
    trades_default = BacktestSimulator().run(
        symbol="TCS", prices_df=df,
        from_date=from_date, to_date=to_date,
        strategies=[_AlwaysBuyStrategy()],
        use_aggregator=False, initial_capital=500_000.0,
    )
    
    trades_explicit_zero = BacktestSimulator().run(
        symbol="TCS", prices_df=df,
        from_date=from_date, to_date=to_date,
        strategies=[_AlwaysBuyStrategy()],
        use_aggregator=False, initial_capital=500_000.0,
        round_trip_cost_pct=0.0,
    )
    
    assert len(trades_default) == len(trades_explicit_zero)
    for t1, t2 in zip(trades_default, trades_explicit_zero):
        assert t1.pnl == t2.pnl
        assert t1.commission == 0.0
        assert t2.commission == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_backtest_simulator.py::test_round_trip_cost_reduces_pnl -v`  
Expected: FAIL with "BacktestSimulator.run() got an unexpected keyword argument 'round_trip_cost_pct'"

- [ ] **Step 3: Modify SimTrade dataclass to add commission field**

```python
# backend/domains/backtest/simulator.py

@dataclass
class SimTrade:
    symbol: str
    entry_date: date
    entry_price: float
    exit_date: date
    exit_price: float
    quantity: int
    stop_loss_price: float
    target_price: float
    exit_reason: str
    pnl: float
    pnl_pct: float
    holding_days: int
    commission: float = 0.0   # ← ADD THIS LINE
```

- [ ] **Step 4: Add round_trip_cost_pct parameter to BacktestSimulator.run()**

```python
# backend/domains/backtest/simulator.py (modify run method signature, line 43)

def run(
    self,
    symbol: str,
    prices_df: pd.DataFrame,
    from_date: date,
    to_date: date,
    strategies: list,
    initial_capital: float = 500_000.0,
    risk_per_trade_pct: float = 2.0,
    max_single_stock_pct: float = 20.0,
    use_aggregator: bool = True,
    _df_ind_precomputed: Optional[pd.DataFrame] = None,
    stop_loss_pct_override: Optional[float] = None,
    target_pct_override: Optional[float] = None,
    round_trip_cost_pct: float = 0.0,   # ← ADD THIS LINE (default 0.0 for backward compat)
) -> list[SimTrade]:
```

- [ ] **Step 5: Modify _close() to compute and deduct commission**

```python
# backend/domains/backtest/simulator.py (modify _close method, currently line 167)

def _close(self, symbol: str, pos: _OpenPosition, price: float,
           exit_date: date, reason: str, round_trip_cost_pct: float) -> SimTrade:  # ← ADD PARAM
    raw_pnl = round((price - pos.entry_price) * pos.quantity, 2)
    entry_value = pos.entry_price * pos.quantity
    commission = round(entry_value * round_trip_cost_pct / 100, 2)  # ← ADD
    net_pnl = round(raw_pnl - commission, 2)   # ← ADD
    pnl_pct = round((price - pos.entry_price) / pos.entry_price * 100, 2)
    return SimTrade(
        symbol=symbol,
        entry_date=pos.entry_date,
        entry_price=pos.entry_price,
        exit_date=exit_date,
        exit_price=price,
        quantity=pos.quantity,
        stop_loss_price=pos.stop_loss_price,
        target_price=pos.target_price,
        exit_reason=reason,
        pnl=net_pnl,            # ← CHANGE from raw_pnl to net_pnl
        pnl_pct=pnl_pct,
        holding_days=(exit_date - pos.entry_date).days,
        commission=commission,  # ← ADD
    )
```

- [ ] **Step 6: Update all _close() calls in run() to pass round_trip_cost_pct**

```python
# backend/domains/backtest/simulator.py (modify lines 99-100 and 153-154)

# Line 99-100 (exit check within loop)
if reason:
    trades.append(self._close(symbol, open_pos, current_price, current_date, reason, round_trip_cost_pct))

# Line 153-154 (end-of-period force-close)
trades.append(self._close(symbol, open_pos, last_price, actual_last_date, "end_of_period", round_trip_cost_pct))
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `python -m pytest backend/tests/test_backtest_simulator.py -v`  
Expected: ALL PASS (including 2 new cost tests + 5 existing tests)

- [ ] **Step 8: Commit**

```bash
git add backend/domains/backtest/simulator.py backend/tests/test_backtest_simulator.py
git commit -m "feat: add transaction costs to BacktestSimulator

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 2: Update BacktestRunner to use 0.30% default cost

**Files:**
- Modify: `backend/domains/backtest/runner.py`

- [ ] **Step 1: Update BacktestRunner.run() to pass round_trip_cost_pct=0.30**

```python
# backend/domains/backtest/runner.py (modify line 72-82)

trades = self.simulator.run(
    symbol=symbol,
    prices_df=df,
    from_date=from_date,
    to_date=to_date,
    strategies=strategies,
    use_aggregator=use_aggregator,
    initial_capital=initial_capital,
    stop_loss_pct_override=stop_loss_pct,
    target_pct_override=target_pct,
    round_trip_cost_pct=0.30,   # ← ADD THIS LINE
)
```

- [ ] **Step 2: Update BacktestRunner.scan_all() to pass round_trip_cost_pct=0.30**

```python
# backend/domains/backtest/runner.py (modify line 193-205)

try:
    trades = self.simulator.run(
        symbol=symbol,
        prices_df=df,
        from_date=from_date,
        to_date=to_date,
        strategies=[strat],
        use_aggregator=False,
        initial_capital=initial_capital,
        _df_ind_precomputed=df_ind,
        stop_loss_pct_override=stop_loss_pct,
        target_pct_override=target_pct,
        round_trip_cost_pct=0.30,   # ← ADD THIS LINE
    )
```

- [ ] **Step 3: Update BacktestRunner.precompute_all_for_strategy() to pass round_trip_cost_pct=0.30**

```python
# backend/domains/backtest/runner.py (modify line 291-297)

try:
    trades = self.simulator.run(
        symbol=symbol, prices_df=df,
        from_date=from_date, to_date=to_date,
        strategies=[strat], use_aggregator=False,
        initial_capital=500_000.0,
        round_trip_cost_pct=0.30,   # ← ADD THIS LINE
    )
```

- [ ] **Step 4: Run backtest tests to verify no regression**

Run: `python -m pytest backend/tests/test_backtest_runner.py -v`  
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add backend/domains/backtest/runner.py
git commit -m "feat: apply 0.30% round-trip cost in BacktestRunner

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 3: Walk-forward runner

**Files:**
- Create: `backend/domains/backtest/walk_forward.py`
- Test: `backend/tests/test_walk_forward.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_walk_forward.py

import sys
import os
from datetime import date, timedelta
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _make_db_with_prices(symbol: str, n_days: int = 730):
    """In-memory DB with 2 years of daily prices."""
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session
    from database import Base
    import models

    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=eng)
    db = Session(bind=eng)

    # Insert strategy row
    db.execute(text(
        "INSERT INTO strategies (id, name, type, is_active, created_at) "
        "VALUES (1, 'TestStrat', 'technical', 1, CURRENT_TIMESTAMP)"
    ))

    # Insert prices (steadily rising)
    start_date = date(2022, 1, 1)
    rows = []
    for i in range(n_days):
        d = start_date + timedelta(days=i)
        c = 1000.0 + i * 2.0
        rows.append({
            "sym": symbol, "d": str(d),
            "o": c * 0.99, "h": c * 1.01, "l": c * 0.98, "c": c, "v": 1000000,
        })

    db.execute(text("""
        INSERT INTO stock_prices_daily (symbol, date, open, high, low, close, volume, data_source)
        VALUES (:sym, :d, :o, :h, :l, :c, :v, 'yfinance')
    """), rows)
    db.commit()
    return db


class _AlwaysBuyStrategy:
    name = "TestStrat"
    weight = 0.20
    strategy_type = "technical"

    def generate_signal(self, df, fundamentals=None):
        from domains.strategies.base import Signal
        if len(df) < 30:
            return Signal(signal_type="NONE")
        return Signal(signal_type="BUY", confidence=0.80)


def test_walk_forward_returns_result():
    from domains.backtest.walk_forward import WalkForwardRunner, WalkForwardResult
    db = _make_db_with_prices("TCS", n_days=730)
    runner = WalkForwardRunner()
    result = runner.run(symbol="TCS", strategy_id=1, db=db, train_months=12, test_months=3)

    assert isinstance(result, WalkForwardResult)
    assert result.symbol == "TCS"
    assert result.strategy_id == 1
    assert result.n_windows > 0
    assert result.oos_win_rate_mean is not None
    assert 0.0 <= result.consistency_score <= 1.0
    db.close()


def test_walk_forward_window_count():
    """2 years of data, test_months=3 → expect ~7-8 OOS windows."""
    from domains.backtest.walk_forward import WalkForwardRunner
    db = _make_db_with_prices("INFY", n_days=730)
    runner = WalkForwardRunner()
    result = runner.run(symbol="INFY", strategy_id=1, db=db, train_months=12, test_months=3)

    # 730 days ≈ 24 months. First window needs 12mo train → OOS starts at month 12.
    # Remaining 12 months / 3 months per window = 4 windows minimum.
    # With overlapping windows (step=test_months), expect 4-8 windows.
    assert 4 <= result.n_windows <= 8
    db.close()


def test_consistency_score_all_winning():
    """If all OOS windows have win_rate > 0.45, consistency_score = 1.0."""
    from domains.backtest.walk_forward import WalkForwardRunner
    # Steadily rising prices → all trades should be winning
    db = _make_db_with_prices("RELIANCE", n_days=730)
    runner = WalkForwardRunner()
    result = runner.run(symbol="RELIANCE", strategy_id=1, db=db, train_months=12, test_months=3)

    # All trades exit at higher prices → all windows should have high win rate
    assert result.consistency_score >= 0.75  # at least 75% of windows above 0.45 win rate
    db.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_walk_forward.py::test_walk_forward_returns_result -v`  
Expected: FAIL with "No module named 'domains.backtest.walk_forward'"

- [ ] **Step 3: Create walk_forward.py with dataclasses**

```python
# backend/domains/backtest/walk_forward.py

import logging
import statistics
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from domains.backtest.metrics import compute_metrics
from domains.backtest.simulator import BacktestSimulator
from domains.data.indicators import IndicatorEngine
from domains.strategies.engine import ALL_STRATEGIES

logger = logging.getLogger(__name__)


@dataclass
class WalkForwardWindow:
    """Single out-of-sample test window result."""
    window_index: int
    train_from: date
    train_to: date
    test_from: date
    test_to: date
    oos_metrics: dict  # result of compute_metrics on test window trades


@dataclass
class WalkForwardResult:
    """Aggregated walk-forward out-of-sample performance."""
    symbol: str
    strategy_id: int
    n_windows: int
    windows: list[WalkForwardWindow]
    oos_win_rate_mean: Optional[float]         # mean win rate across OOS windows
    oos_win_rate_std: Optional[float]          # std of win rates across windows
    consistency_score: float                   # % of windows with win_rate >= 0.45
    in_sample_win_rate: Optional[float]        # full-period win rate for comparison


class WalkForwardRunner:
    """
    Out-of-sample walk-forward backtest: divides full history into rolling windows.
    Each window: (train_months) data lookback → (test_months) OOS test period.
    Reports OOS performance consistency across windows.
    """

    def run(
        self,
        symbol: str,
        strategy_id: int,
        db: Session,
        train_months: int = 12,
        test_months: int = 3,
        round_trip_cost_pct: float = 0.30,
    ) -> WalkForwardResult:
        """
        Run walk-forward backtest for a given (symbol, strategy).
        Returns WalkForwardResult with OOS consistency metrics.
        """
        # Fetch strategy
        row = db.execute(
            text("SELECT name FROM strategies WHERE id = :id"), {"id": strategy_id}
        ).fetchone()
        if not row:
            raise ValueError(f"Strategy id={strategy_id} not found")
        strat_name = row[0]
        strat = next((s for s in ALL_STRATEGIES if s.name == strat_name), None)
        if not strat:
            raise ValueError(f"Strategy '{strat_name}' not in ALL_STRATEGIES")

        # Fetch full price history
        rows = db.execute(
            text("""
                SELECT date, open, high, low, close, volume
                FROM stock_prices_daily
                WHERE symbol = :sym
                ORDER BY date ASC
            """),
            {"sym": symbol},
        ).fetchall()

        if len(rows) < 50:
            raise ValueError(f"Insufficient price data for {symbol}: {len(rows)} bars")

        df = pd.DataFrame([dict(r._mapping) for r in rows])
        df["date"] = pd.to_datetime(df["date"]).dt.date

        min_date, max_date = df["date"].min(), df["date"].max()

        # Generate windows: step by test_months
        windows: list[WalkForwardWindow] = []
        window_idx = 0

        # Start first test window after train_months of data
        test_start = min_date + timedelta(days=train_months * 30)
        while test_start <= max_date:
            test_end = test_start + timedelta(days=test_months * 30)
            if test_end > max_date:
                test_end = max_date

            train_start = test_start - timedelta(days=train_months * 30)

            # Run simulator on test period only
            df_window = df[(df["date"] >= train_start) & (df["date"] <= test_end)]
            if df_window.empty or len(df_window) < 50:
                test_start += timedelta(days=test_months * 30)
                continue

            df_ind = IndicatorEngine.compute(df_window)
            simulator = BacktestSimulator()
            trades = simulator.run(
                symbol=symbol,
                prices_df=df_window,
                from_date=test_start,
                to_date=test_end,
                strategies=[strat],
                use_aggregator=False,
                initial_capital=500_000.0,
                _df_ind_precomputed=df_ind,
                round_trip_cost_pct=round_trip_cost_pct,
            )

            oos_metrics = compute_metrics(trades, 500_000.0, test_start, test_end)
            windows.append(WalkForwardWindow(
                window_index=window_idx,
                train_from=train_start,
                train_to=test_start - timedelta(days=1),
                test_from=test_start,
                test_to=test_end,
                oos_metrics=oos_metrics,
            ))

            window_idx += 1
            test_start += timedelta(days=test_months * 30)

        if not windows:
            return WalkForwardResult(
                symbol=symbol, strategy_id=strategy_id, n_windows=0, windows=[],
                oos_win_rate_mean=None, oos_win_rate_std=None,
                consistency_score=0.0, in_sample_win_rate=None,
            )

        # Aggregate OOS metrics
        oos_win_rates = [w.oos_metrics["win_rate"] for w in windows if w.oos_metrics["win_rate"] is not None]
        oos_win_rate_mean = round(statistics.mean(oos_win_rates), 4) if oos_win_rates else None
        oos_win_rate_std = round(statistics.stdev(oos_win_rates), 4) if len(oos_win_rates) > 1 else None

        # Consistency score: % of windows with win_rate >= 0.45
        winning_windows = sum(1 for wr in oos_win_rates if wr >= 0.45)
        consistency_score = round(winning_windows / len(oos_win_rates), 4) if oos_win_rates else 0.0

        # In-sample full-period win rate for comparison
        df_ind_full = IndicatorEngine.compute(df)
        is_trades = simulator.run(
            symbol=symbol, prices_df=df,
            from_date=min_date, to_date=max_date,
            strategies=[strat], use_aggregator=False,
            initial_capital=500_000.0, _df_ind_precomputed=df_ind_full,
            round_trip_cost_pct=round_trip_cost_pct,
        )
        is_metrics = compute_metrics(is_trades, 500_000.0, min_date, max_date)
        in_sample_win_rate = is_metrics["win_rate"]

        return WalkForwardResult(
            symbol=symbol,
            strategy_id=strategy_id,
            n_windows=len(windows),
            windows=windows,
            oos_win_rate_mean=oos_win_rate_mean,
            oos_win_rate_std=oos_win_rate_std,
            consistency_score=consistency_score,
            in_sample_win_rate=in_sample_win_rate,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest backend/tests/test_walk_forward.py -v`  
Expected: ALL 3 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/domains/backtest/walk_forward.py backend/tests/test_walk_forward.py
git commit -m "feat: walk-forward out-of-sample backtester

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 4: Walk-forward DB model + API endpoint

**Files:**
- Modify: `backend/models.py`
- Modify: `backend/domains/backtest/router.py`

- [ ] **Step 1: Add WalkForwardResult table to models.py**

```python
# backend/models.py (append after line 250, BacktestTrade)

class WalkForwardResult(Base):
    """Stores out-of-sample walk-forward consistency metrics per (symbol, strategy)."""
    __tablename__ = "walk_forward_results"
    __table_args__ = (
        UniqueConstraint("symbol", "strategy_id", name="uq_wf_result"),
        Index("idx_wf_strategy", "strategy_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    strategy_id: Mapped[int] = mapped_column(Integer, nullable=False)
    n_windows: Mapped[int] = mapped_column(Integer, default=0)
    oos_win_rate_mean: Mapped[Optional[float]] = mapped_column(Float)
    oos_win_rate_std: Mapped[Optional[float]] = mapped_column(Float)
    consistency_score: Mapped[float] = mapped_column(Float, default=0.0)
    in_sample_win_rate: Mapped[Optional[float]] = mapped_column(Float)
    windows_json: Mapped[Optional[str]] = mapped_column(Text)  # serialized list[WalkForwardWindow]
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
```

- [ ] **Step 2: Add walk-forward endpoint to router.py**

```python
# backend/domains/backtest/router.py (append to end, before leaderboard code if needed)

@router.post("/backtests/walk-forward")
def trigger_walk_forward(
    symbol: str = Query(...),
    strategy_id: int = Query(...),
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Trigger walk-forward out-of-sample backtest for (symbol, strategy).
    Runs in background — returns immediately. Check GET endpoint for results.
    """
    background_tasks.add_task(_run_walk_forward_bg, symbol.upper(), strategy_id)
    return {"status": "started", "symbol": symbol.upper(), "strategy_id": strategy_id}


@router.get("/backtests/walk-forward/{symbol}/{strategy_id}")
def get_walk_forward_result(
    symbol: str,
    strategy_id: int,
    db: Session = Depends(get_db),
):
    """Return stored walk-forward result for (symbol, strategy)."""
    import json
    row = db.execute(
        text("""
            SELECT symbol, strategy_id, n_windows, oos_win_rate_mean, oos_win_rate_std,
                   consistency_score, in_sample_win_rate, windows_json, computed_at
            FROM walk_forward_results
            WHERE symbol = :sym AND strategy_id = :sid
            LIMIT 1
        """),
        {"sym": symbol.upper(), "sid": strategy_id},
    ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Walk-forward result not found")

    windows = json.loads(row[7]) if row[7] else []
    return {
        "symbol": row[0],
        "strategy_id": row[1],
        "n_windows": row[2],
        "oos_win_rate_mean": row[3],
        "oos_win_rate_std": row[4],
        "consistency_score": row[5],
        "in_sample_win_rate": row[6],
        "windows": windows,
        "computed_at": str(row[8]),
    }


def _run_walk_forward_bg(symbol: str, strategy_id: int) -> None:
    """Background task: run walk-forward and persist to DB."""
    import json
    from database import SessionLocal
    from domains.backtest.walk_forward import WalkForwardRunner

    db = SessionLocal()
    try:
        runner = WalkForwardRunner()
        result = runner.run(symbol=symbol, strategy_id=strategy_id, db=db)
        windows_json = json.dumps([
            {
                "window_index": w.window_index,
                "train_from": str(w.train_from),
                "train_to": str(w.train_to),
                "test_from": str(w.test_from),
                "test_to": str(w.test_to),
                "oos_metrics": w.oos_metrics,
            }
            for w in result.windows
        ])

        db.execute(
            text("""
                INSERT OR REPLACE INTO walk_forward_results
                    (symbol, strategy_id, n_windows, oos_win_rate_mean, oos_win_rate_std,
                     consistency_score, in_sample_win_rate, windows_json, computed_at)
                VALUES (:sym, :sid, :nw, :mean, :std, :cs, :iswr, :wj, datetime('now'))
            """),
            {
                "sym": result.symbol, "sid": result.strategy_id,
                "nw": result.n_windows, "mean": result.oos_win_rate_mean,
                "std": result.oos_win_rate_std, "cs": result.consistency_score,
                "iswr": result.in_sample_win_rate, "wj": windows_json,
            },
        )
        db.commit()
        logger.info("[walk-forward] %s/%d: %d windows, consistency=%.2f",
                    symbol, strategy_id, result.n_windows, result.consistency_score)
    except Exception:
        logger.exception("[walk-forward] %s/%d failed", symbol, strategy_id)
    finally:
        db.close()
```

- [ ] **Step 3: Add BackgroundTasks import to router.py if not present**

```python
# backend/domains/backtest/router.py (add to imports at top if missing)

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
```

- [ ] **Step 4: Run backtest router tests to verify no regression**

Run: `python -m pytest backend/tests/test_backtest_router.py -v`  
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add backend/models.py backend/domains/backtest/router.py
git commit -m "feat: walk-forward API endpoints + DB persistence

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 5: ML signal probability scorer

**Files:**
- Create: `backend/domains/intelligence/ml_scorer.py`
- Create: `backend/ml_models/.gitignore`
- Test: `backend/tests/test_ml_scorer.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_ml_scorer.py

import sys
import os
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _make_db_with_outcomes(n_outcomes: int = 60):
    """In-memory DB with signal_outcomes + strategy_signals + market_regime."""
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session
    from database import Base
    import models

    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=eng)
    db = Session(bind=eng)

    # Insert strategy
    db.execute(text(
        "INSERT INTO strategies (id, name, type, is_active, created_at) "
        "VALUES (1, 'TestStrat', 'technical', 1, CURRENT_TIMESTAMP)"
    ))

    # Insert signal_outcomes
    base = date(2024, 1, 1)
    rows_signals = []
    rows_outcomes = []
    rows_regime = []
    for i in range(n_outcomes):
        sig_date = base + timedelta(days=i)
        is_prof = 1 if i % 2 == 0 else 0  # 50% win rate
        rows_signals.append({
            "sid": i + 1, "sym": "TCS", "strat": 1, "sdate": str(sig_date),
            "stype": "BUY", "conf": 0.75, "price": 100.0,
        })
        rows_outcomes.append({
            "sig_id": i + 1, "sym": "TCS", "strat": 1, "sdate": str(sig_date),
            "stype": "BUY", "price": 100.0, "oprice": 110.0 if is_prof else 90.0,
            "odate": str(sig_date + timedelta(days=15)), "pnl": 10.0 if is_prof else -10.0,
            "prof": is_prof, "hdays": 15,
        })
        rows_regime.append({
            "d": str(sig_date), "regime": "BULL", "conf": 0.8,
            "pct50": 0.6, "pct200": 0.5, "adr": 1.2, "atr": 0.02, "stocks": 200,
        })

    db.execute(text("""
        INSERT INTO strategy_signals
            (id, symbol, strategy_id, signal_date, signal_type, confidence_score,
             price_at_signal, created_at)
        VALUES (:sid, :sym, :strat, :sdate, :stype, :conf, :price, CURRENT_TIMESTAMP)
    """), rows_signals)

    db.execute(text("""
        INSERT INTO signal_outcomes
            (signal_id, symbol, strategy_id, signal_date, signal_type,
             price_at_signal, outcome_price, outcome_date, pnl_pct,
             is_profitable, holding_days_actual, computed_at)
        VALUES (:sig_id, :sym, :strat, :sdate, :stype,
                :price, :oprice, :odate, :pnl, :prof, :hdays, CURRENT_TIMESTAMP)
    """), rows_outcomes)

    db.execute(text("""
        INSERT INTO market_regime
            (date, regime, confidence, pct_above_sma50, pct_above_sma200,
             advance_decline_ratio, avg_atr_ratio, stocks_counted, computed_at)
        VALUES (:d, :regime, :conf, :pct50, :pct200, :adr, :atr, :stocks, CURRENT_TIMESTAMP)
    """), rows_regime)

    db.commit()
    return db


def test_train_returns_zero_below_min_samples():
    """Fewer than 50 outcomes → train returns 0."""
    from domains.intelligence.ml_scorer import MLSignalScorer
    db = _make_db_with_outcomes(n_outcomes=40)
    scorer = MLSignalScorer()
    n = scorer.train(db)
    assert n == 0
    db.close()


def test_predict_returns_none_when_no_model():
    """No .pkl file → predict returns None."""
    from domains.intelligence.ml_scorer import MLSignalScorer
    import os
    # Remove model file if exists
    model_path = os.path.join(os.path.dirname(__file__), "..", "ml_models", "signal_scorer.pkl")
    if os.path.exists(model_path):
        os.remove(model_path)
    
    scorer = MLSignalScorer()
    prob = scorer.predict({
        "confidence_score": 0.75,
        "regime_code": 4,  # BULL
        "strategy_id": 1,
        "month": 1,
        "day_of_week": 0,
    })
    assert prob is None


def test_train_and_predict():
    """Insert 60 outcomes, train, predict → returns float in [0,1]."""
    from domains.intelligence.ml_scorer import MLSignalScorer
    db = _make_db_with_outcomes(n_outcomes=60)
    scorer = MLSignalScorer()
    n = scorer.train(db)
    assert n == 60

    prob = scorer.predict({
        "confidence_score": 0.80,
        "regime_code": 4,  # BULL
        "strategy_id": 1,
        "month": 2,
        "day_of_week": 1,
    })
    assert prob is not None
    assert 0.0 <= prob <= 1.0
    db.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_ml_scorer.py::test_train_and_predict -v`  
Expected: FAIL with "No module named 'domains.intelligence.ml_scorer'"

- [ ] **Step 3: Create ml_models directory + .gitignore**

```bash
mkdir -p backend/ml_models
echo "*.pkl" > backend/ml_models/.gitignore
```

- [ ] **Step 4: Create ml_scorer.py**

```python
# backend/domains/intelligence/ml_scorer.py

import logging
import os
import pickle
from typing import Optional

import numpy as np
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

MIN_TRAINING_SAMPLES = 50
MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "ml_models", "signal_scorer.pkl")

# Regime encoding: STRONG_BULL=5, BULL=4, SIDEWAYS=3, BEAR=2, STRONG_BEAR=1, HIGH_VOLATILITY=0
_REGIME_MAP = {
    "STRONG_BULL": 5,
    "BULL": 4,
    "SIDEWAYS": 3,
    "BEAR": 2,
    "STRONG_BEAR": 1,
    "HIGH_VOLATILITY": 0,
}


class MLSignalScorer:
    """
    ML-based signal probability predictor.
    Trains GradientBoostingClassifier on Phase C signal_outcomes data.
    Features: confidence, regime, strategy_id, month, day_of_week.
    """

    def train(self, db: Session) -> int:
        """
        Load features from signal_outcomes + strategy_signals + market_regime,
        train GBC, persist to MODEL_PATH. Returns n_samples trained on.
        """
        X, y = self._extract_features(db)
        if len(X) < MIN_TRAINING_SAMPLES:
            logger.warning("[ml_scorer] insufficient training samples: %d < %d", len(X), MIN_TRAINING_SAMPLES)
            return 0

        from sklearn.ensemble import GradientBoostingClassifier

        model = GradientBoostingClassifier(
            n_estimators=100,
            max_depth=3,
            learning_rate=0.1,
            random_state=42,
        )
        model.fit(X, y)

        os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
        with open(MODEL_PATH, "wb") as f:
            pickle.dump(model, f)

        logger.info("[ml_scorer] trained on %d samples, saved to %s", len(X), MODEL_PATH)
        return len(X)

    def predict(self, features: dict) -> Optional[float]:
        """
        Predict probability in [0,1] for a signal with given features.
        Returns None if model not available.
        
        Expected keys in features:
        - confidence_score (float)
        - regime_code (int 0-5)
        - strategy_id (int)
        - month (int 1-12)
        - day_of_week (int 0-4)
        """
        model = self._load_model()
        if model is None:
            return None

        X_row = np.array([[
            features["confidence_score"],
            features["regime_code"],
            features["strategy_id"],
            features["month"],
            features["day_of_week"],
        ]])
        prob = model.predict_proba(X_row)[0][1]  # probability of class 1 (profitable)
        return round(float(prob), 4)

    def _load_model(self):
        """Load pickled model; return None if not found."""
        if not os.path.exists(MODEL_PATH):
            return None
        try:
            with open(MODEL_PATH, "rb") as f:
                return pickle.load(f)
        except Exception as e:
            logger.warning("[ml_scorer] failed to load model: %s", e)
            return None

    def _extract_features(self, db: Session) -> tuple[np.ndarray, np.ndarray]:
        """
        JOIN signal_outcomes + strategy_signals + market_regime.
        Returns (X, y) where X = [n_samples, 5], y = [n_samples] bool.
        """
        rows = db.execute(text("""
            SELECT 
                ss.confidence_score,
                mr.regime,
                ss.strategy_id,
                so.signal_date,
                so.is_profitable
            FROM signal_outcomes so
            JOIN strategy_signals ss ON ss.id = so.signal_id
            LEFT JOIN market_regime mr ON mr.date = so.signal_date
            WHERE so.is_profitable IS NOT NULL
        """)).fetchall()

        if not rows:
            return np.array([]), np.array([])

        X_list = []
        y_list = []
        for r in rows:
            conf_score = float(r[0]) if r[0] is not None else 0.5
            regime_code = _REGIME_MAP.get(r[1], 3)  # default SIDEWAYS if missing
            strat_id = int(r[2])
            sig_date = r[3]
            is_prof = bool(r[4])

            # Extract month, day_of_week from signal_date
            if isinstance(sig_date, str):
                from datetime import datetime
                sig_date = datetime.strptime(sig_date, "%Y-%m-%d").date()
            month = sig_date.month
            day_of_week = sig_date.weekday()  # 0=Mon, 4=Fri

            X_list.append([conf_score, regime_code, strat_id, month, day_of_week])
            y_list.append(1 if is_prof else 0)

        return np.array(X_list), np.array(y_list)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest backend/tests/test_ml_scorer.py -v`  
Expected: ALL 3 PASS

- [ ] **Step 6: Commit**

```bash
git add backend/domains/intelligence/ml_scorer.py backend/tests/test_ml_scorer.py backend/ml_models/.gitignore
git commit -m "feat: ML signal probability scorer (GBC)

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 6: Wire ML into OpportunityScorer + scheduler

**Files:**
- Modify: `backend/domains/intelligence/opportunity_scorer.py`
- Modify: `backend/domains/intelligence/router.py`
- Modify: `backend/scheduler.py`
- Test: `backend/tests/test_ml_scorer.py` (add integration test)

- [ ] **Step 1: Write the failing integration test**

```python
# backend/tests/test_ml_scorer.py (append to end)

def test_probability_in_breakdown():
    """full_score with ml_probability → "ml_signal_probability" in breakdown."""
    from domains.intelligence.opportunity_scorer import OpportunityScorer
    from domains.intelligence.ml_scorer import MLSignalScorer

    # Train model first
    db = _make_db_with_outcomes(n_outcomes=60)
    MLSignalScorer().train(db)
    db.close()

    scorer = OpportunityScorer()
    opp = scorer.full_score(
        symbol="TCS",
        strategy_id=1,
        confidence=0.75,
        historical_win_rate=0.60,
        regime="BULL",
        regime_strategy_win_rate=0.55,
        mtf_alignment=0.8,
        volume_score=0.7,
        sr_score=0.6,
        false_signal_rate=0.30,
        ml_probability=0.65,  # ← NEW PARAM
    )

    assert "ml_signal_probability" in opp.breakdown
    assert opp.breakdown["ml_signal_probability"] == 0.65
    assert opp.score > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_ml_scorer.py::test_probability_in_breakdown -v`  
Expected: FAIL with "full_score() got an unexpected keyword argument 'ml_probability'"

- [ ] **Step 3: Update _WEIGHTS in opportunity_scorer.py**

```python
# backend/domains/intelligence/opportunity_scorer.py (modify _WEIGHTS dict, line 33-41)

_WEIGHTS: dict[str, int] = {
    "historical_win_rate":  22,  # was 25
    "strategy_confidence":  18,  # was 20
    "regime_alignment":     16,  # was 18
    "mtf_alignment":        14,  # was 15
    "volume":               10,
    "sr_context":            8,
    "regime_strategy":       4,
    "ml_signal_probability": 8,  # ← ADD THIS LINE
}
```

- [ ] **Step 4: Add ml_probability param to full_score()**

```python
# backend/domains/intelligence/opportunity_scorer.py (modify full_score signature, line 92-103)

def full_score(
    self,
    symbol: str,
    strategy_id: Optional[int],
    confidence: float,
    historical_win_rate: Optional[float],
    regime: str,
    regime_strategy_win_rate: Optional[float],
    mtf_alignment: Optional[float],
    volume_score: Optional[float],
    sr_score: Optional[float],
    false_signal_rate: Optional[float] = None,
    ml_probability: Optional[float] = None,   # ← ADD THIS LINE
) -> OpportunityScore:
```

- [ ] **Step 5: Add ml_probability to parts dict in full_score()**

```python
# backend/domains/intelligence/opportunity_scorer.py (modify full_score body, line 104-112)

parts: dict[str, Optional[float]] = {
    "historical_win_rate": historical_win_rate,
    "strategy_confidence": min(1.0, max(0.0, confidence)),
    "regime_alignment":    _REGIME_BUY_SCORE.get(regime, 0.5),
    "regime_strategy":     regime_strategy_win_rate,
    "mtf_alignment":       mtf_alignment,
    "volume":              volume_score,
    "sr_context":          sr_score,
    "ml_signal_probability": ml_probability,   # ← ADD THIS LINE
}
```

- [ ] **Step 6: Update get_opportunity_score() endpoint to call MLSignalScorer**

```python
# backend/domains/intelligence/router.py (modify get_opportunity_score, line 52-122)

@router.get("/intelligence/opportunity-score/{symbol}")
def get_opportunity_score(
    symbol: str,
    strategy_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    """
    Full opportunity score (0–100) for a symbol, using all intelligence signals:
    historical win rate, strategy confidence, regime alignment, MTF, volume, S/R, and ML probability.
    """
    sym = symbol.upper()
    regime_result = MarketRegimeEngine().get_or_compute(db)
    regime = regime_result.regime

    # Regime-strategy win rate
    regime_perf = RegimePerformanceEngine().get_for_regime(db, regime)
    regime_wr: Optional[float] = regime_perf[strategy_id].win_rate if (strategy_id and strategy_id in regime_perf) else None

    # Historical win rate from scan_result_cache
    hist_wr: Optional[float] = None
    if strategy_id:
        row = db.execute(
            text("""
                SELECT win_rate FROM scan_result_cache
                WHERE symbol = :s AND strategy_id = :sid
                  AND stop_loss_pct = 5.0 AND target_pct = 10.0
                  AND from_date = '2015-01-01'
                LIMIT 1
            """),
            {"s": sym, "sid": strategy_id},
        ).fetchone()
        if row and row[0] is not None:
            hist_wr = float(row[0])

    # MTF alignment
    mtf_result = MultiTimeframeEngine().compute(db, sym)
    mtf_score: Optional[float] = mtf_result.alignment_score if mtf_result.daily else None

    # Volume score
    vol_score = _compute_volume_score(db, sym)

    # S/R context score
    sr_result = SupportResistanceEngine().compute(db, sym)
    sr_score = _compute_sr_score(sr_result)

    false_rate: Optional[float] = None
    if strategy_id:
        false_rate = FalseSignalDetector().get_rate_for_strategy(db, strategy_id)

    # ← ADD ML PROBABILITY BLOCK HERE
    ml_prob: Optional[float] = None
    if strategy_id:
        from domains.intelligence.ml_scorer import MLSignalScorer, _REGIME_MAP
        from datetime import date
        features = {
            "confidence_score": 0.5,  # default when not from active signal
            "regime_code": _REGIME_MAP.get(regime, 3),
            "strategy_id": strategy_id,
            "month": date.today().month,
            "day_of_week": date.today().weekday(),
        }
        ml_prob = MLSignalScorer().predict(features)

    opp = OpportunityScorer().full_score(
        symbol=sym,
        strategy_id=strategy_id,
        confidence=0.5,   # no active signal context; caller may pass via query param
        historical_win_rate=hist_wr,
        regime=regime,
        regime_strategy_win_rate=regime_wr,
        mtf_alignment=mtf_score,
        volume_score=vol_score,
        sr_score=sr_score,
        false_signal_rate=false_rate,
        ml_probability=ml_prob,   # ← ADD THIS LINE
    )

    return {
        "symbol":      opp.symbol,
        "strategy_id": opp.strategy_id,
        "score":       opp.score,
        "grade":       opp.grade,
        "regime":      regime,
        "mtf_alignment_score": mtf_score,
        "ml_probability": ml_prob,   # ← ADD THIS LINE (for visibility)
        "breakdown":   opp.breakdown,
    }
```

- [ ] **Step 7: Wire _monthly_ml_retrain() in scheduler.py**

```python
# backend/scheduler.py (modify existing stub function, find line with def _weekly_fundamentals or similar, add this new function)

def _monthly_ml_retrain():
    """Retrain ML signal probability model monthly after signal outcomes accumulate."""
    from database import SessionLocal
    from domains.intelligence.ml_scorer import MLSignalScorer
    db = SessionLocal()
    try:
        n = MLSignalScorer().train(db)
        logger.info("[ml_retrain] trained on %d signal outcomes", n)
    except Exception:
        logger.exception("[ml_retrain] failed")
    finally:
        db.close()
```

- [ ] **Step 8: Register _monthly_ml_retrain() job in scheduler.py**

```python
# backend/scheduler.py (modify register_jobs(), add after other scheduler.add_job calls)

# Last Sunday of every month at 10 PM (after signal outcomes have accumulated)
scheduler.add_job(
    _monthly_ml_retrain,
    CronTrigger(day_of_week="sun", hour=22, minute=0, day="last"),
    id=JobIds.MONTHLY_ML_RETRAIN,
    replace_existing=True,
)
```

- [ ] **Step 9: Verify JobIds.MONTHLY_ML_RETRAIN exists (it's already a stub)**

```python
# backend/scheduler.py (check line 10-23, JobIds class)

class JobIds:
    DAILY_EOD_UPDATE = "daily_eod_update"
    DAILY_DATA_REFRESH = "daily_data_refresh"
    INTRADAY_SCAN = "intraday_scan"
    WEEKLY_FUNDAMENTALS = "weekly_fundamentals"
    MONTHLY_ML_RETRAIN = "monthly_ml_retrain"   # ← ALREADY EXISTS
    # ...
```

- [ ] **Step 10: Run tests to verify they pass**

Run: `python -m pytest backend/tests/test_ml_scorer.py::test_probability_in_breakdown -v`  
Expected: PASS

Run: `python -m pytest backend/tests/test_intelligence_engines.py -v`  
Expected: ALL PASS (no regression in OpportunityScorer tests)

- [ ] **Step 11: Commit**

```bash
git add backend/domains/intelligence/opportunity_scorer.py backend/domains/intelligence/router.py backend/scheduler.py backend/tests/test_ml_scorer.py
git commit -m "feat: wire ML probability into OpportunityScorer + monthly retrain job

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 7: Run full test suite + final commit

**Files:**
- None (verification only)

- [ ] **Step 1: Run full test suite**

Run: `python -m pytest backend/tests/ -v --tb=short`  
Expected: ALL PASS (261 existing + 12 new Phase D tests = 273 total)

- [ ] **Step 2: Verify no untracked files except .pkl**

Run: `git status`  
Expected: All Phase D files staged, ml_models/*.pkl ignored

- [ ] **Step 3: Final integration commit (if needed)**

If all tests pass, no additional commit needed (already committed per-task).  
Otherwise, fix failing tests and commit fixes.

```bash
# Only if fixes needed:
git add <fixed-files>
git commit -m "fix: Phase D test failures

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Self-Review Checklist

**1. Spec coverage:**
- ✅ Transaction costs (commission + slippage) added to simulator
- ✅ Walk-forward OOS testing implemented with consistency metrics
- ✅ ML probability model (GBC) trained on signal_outcomes
- ✅ ML integrated into OpportunityScorer as 8-weight component
- ✅ Scheduler job for monthly ML retrain
- ✅ API endpoints for walk-forward results

**2. Placeholder scan:**
- No TBD/TODO placeholders
- All code blocks complete
- All file paths exact
- All SQL queries complete

**3. Type consistency:**
- `SimTrade.commission` field added (float)
- `WalkForwardResult` dataclass matches DB model
- `MLSignalScorer.predict()` returns `Optional[float]`
- `full_score()` ml_probability param type matches

**4. Test coverage:**
- Transaction costs: 2 tests
- Walk-forward: 3 tests
- ML scorer: 4 tests
- Total new: 9+ tests

