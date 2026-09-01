# Backtesting Engine — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replay historical NSE price data through the strategy engine, simulate entries/exits with position sizing, compute performance metrics (CAGR, Sharpe, max drawdown, win rate), and expose results via REST API.

**Architecture:** `BacktestSimulator` is a pure in-memory loop — it runs `IndicatorEngine` + strategies + `SignalAggregator` per bar, then manages a simulated position using `PositionSizer`. No DB writes during simulation; results are only written at the end. `BacktestMetrics` computes performance from the `SimTrade` list. `BacktestRunner` orchestrates DB loading and result saving. REST API exposes run + read endpoints.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy 2.0 (raw SQL via `text()`), pandas, pytest, SQLite (StaticPool for tests)

**Existing foundation (do not re-implement):**
- `backend/domains/data/indicators.py` — `IndicatorEngine.compute(df) -> pd.DataFrame`
- `backend/domains/strategies/engine.py` — `ALL_STRATEGIES` (list of 10 instantiated strategies), `StrategyEngine`
- `backend/domains/strategies/aggregator.py` — `SignalAggregator.aggregate(signals) -> dict`
- `backend/domains/strategies/base.py` — `Signal` dataclass with `stop_loss_pct`, `target_pct`, `holding_days`, `confidence`
- `backend/domains/portfolio/position_sizer.py` — `PositionSizer.compute(..., _cfg=None) -> PositionSize`
- `backend/models.py` — `backtest_results`, `backtest_trades` tables already defined
- `backend/main.py` — add backtest router at bottom in Task 4
- `backend/settings.py` — `total_capital=500_000`, `risk_per_trade_pct=2.0`, `max_single_stock_pct=20.0`

---

## File Map

```
backend/
├── domains/
│   └── backtest/
│       ├── __init__.py              NEW (empty)
│       ├── simulator.py             NEW — SimTrade dataclass + BacktestSimulator.run()
│       ├── metrics.py               NEW — compute_metrics() pure function
│       ├── runner.py                NEW — BacktestRunner: loads DB prices, saves results
│       ├── service.py               NEW — BacktestService: read queries
│       └── router.py                NEW — REST endpoints
├── main.py                          MODIFY — include backtest router
└── tests/
    ├── test_backtest_simulator.py   NEW
    ├── test_backtest_metrics.py     NEW
    ├── test_backtest_runner.py      NEW
    └── test_backtest_router.py      NEW
```

---

### Task 1: BacktestSimulator

**Files:**
- Create: `backend/domains/backtest/__init__.py`
- Create: `backend/domains/backtest/simulator.py`
- Create: `backend/tests/test_backtest_simulator.py`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_backtest_simulator.py
from datetime import date
import pandas as pd


def _make_prices(n: int = 250, start_close: float = 1000.0) -> pd.DataFrame:
    """Steadily rising prices: +2/day. Reliable for deterministic test entry/exit."""
    dates = pd.bdate_range("2023-01-01", periods=n).date
    closes = [start_close + i * 2.0 for i in range(n)]
    return pd.DataFrame({
        "date":   dates,
        "open":   [c * 0.995 for c in closes],
        "high":   [c * 1.010 for c in closes],
        "low":    [c * 0.990 for c in closes],
        "close":  closes,
        "volume": [1_000_000] * n,
    })


class _AlwaysBuyStrategy:
    """Test double: always BUY after 30-bar warmup. No ABC inheritance needed."""
    name = "always_buy"
    weight = 0.20

    def generate_signal(self, df, fundamentals=None):
        from domains.strategies.base import Signal
        if len(df) < 30:
            return Signal(signal_type="NONE")
        return Signal(signal_type="BUY", confidence=0.80)


def test_simulator_returns_trades_for_buy_signal():
    from domains.backtest.simulator import BacktestSimulator
    df = _make_prices(250)
    from_date, to_date = df["date"][50], df["date"][-1]
    trades = BacktestSimulator().run(
        symbol="TCS",
        prices_df=df,
        from_date=from_date,
        to_date=to_date,
        strategies=[_AlwaysBuyStrategy()],
        use_aggregator=False,
        initial_capital=500_000.0,
    )
    assert len(trades) >= 1


def test_simulator_trade_fields_are_populated():
    from domains.backtest.simulator import BacktestSimulator, SimTrade
    df = _make_prices(250)
    from_date, to_date = df["date"][50], df["date"][-1]
    trades = BacktestSimulator().run(
        symbol="TCS", prices_df=df,
        from_date=from_date, to_date=to_date,
        strategies=[_AlwaysBuyStrategy()],
        use_aggregator=False, initial_capital=500_000.0,
    )
    t = trades[0]
    assert isinstance(t, SimTrade)
    assert t.symbol == "TCS"
    assert t.entry_price > 0
    assert t.exit_price > 0
    assert t.quantity > 0
    assert t.exit_reason in ("stop_loss", "target_hit", "max_holding_days", "end_of_period")


def test_simulator_exit_on_target():
    """Rapidly rising prices → target_hit exit."""
    n = 120
    # Flat for 50 bars, then +15/bar so target (+15%) hits quickly
    closes = [1000.0] * 50 + [1001.0 + i * 15 for i in range(70)]
    dates = pd.bdate_range("2023-01-01", periods=n).date
    df = pd.DataFrame({
        "date":   dates,
        "open":   [c * 0.99 for c in closes],
        "high":   [c * 1.02 for c in closes],
        "low":    [c * 0.98 for c in closes],
        "close":  closes,
        "volume": [1_000_000] * n,
    })
    trades = BacktestSimulator().run(
        symbol="TCS", prices_df=df,
        from_date=dates[50], to_date=dates[-1],
        strategies=[_AlwaysBuyStrategy()],
        use_aggregator=False, initial_capital=500_000.0,
    )
    assert any(t.exit_reason == "target_hit" for t in trades)


def test_simulator_no_double_entry():
    """Entries must not overlap — exit_date[i] <= entry_date[i+1]."""
    from domains.backtest.simulator import BacktestSimulator
    df = _make_prices(250)
    from_date, to_date = df["date"][50], df["date"][-1]
    trades = BacktestSimulator().run(
        symbol="TCS", prices_df=df,
        from_date=from_date, to_date=to_date,
        strategies=[_AlwaysBuyStrategy()],
        use_aggregator=False, initial_capital=500_000.0,
    )
    for i in range(len(trades) - 1):
        assert trades[i].exit_date <= trades[i + 1].entry_date
```

- [ ] **Step 2: Run to confirm failure**

```
cd /c/DLP_Repos/MyRepo/StockV2/backend && python -m pytest tests/test_backtest_simulator.py -v 2>&1 | head -10
```
Expected: `ModuleNotFoundError: No module named 'domains.backtest'`

- [ ] **Step 3: Create `backend/domains/backtest/__init__.py`**

Empty file.

- [ ] **Step 4: Create `backend/domains/backtest/simulator.py`**

```python
import logging
from dataclasses import dataclass
from datetime import date, timedelta
from types import SimpleNamespace
from typing import Optional

import pandas as pd

from domains.data.indicators import IndicatorEngine
from domains.strategies.aggregator import SignalAggregator
from domains.portfolio.position_sizer import PositionSizer

logger = logging.getLogger(__name__)


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
    exit_reason: str  # "stop_loss" | "target_hit" | "max_holding_days" | "end_of_period"
    pnl: float
    pnl_pct: float
    holding_days: int


@dataclass
class _OpenPosition:
    entry_date: date
    entry_price: float
    quantity: int
    stop_loss_price: float
    target_price: float
    max_exit_date: date


class BacktestSimulator:
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
    ) -> list[SimTrade]:
        cfg = SimpleNamespace(
            total_capital=initial_capital,
            paper_capital=initial_capital,
            risk_per_trade_pct=risk_per_trade_pct,
            max_open_positions=8,
            max_single_stock_pct=max_single_stock_pct,
        )
        aggregator = SignalAggregator()
        sizer = PositionSizer()

        df = prices_df.copy()
        # Normalize date column to Python date objects
        if not df.empty and not isinstance(df["date"].iloc[0], date):
            df["date"] = pd.to_datetime(df["date"]).dt.date
        df = df.sort_values("date").reset_index(drop=True)

        mask = (df["date"] >= from_date) & (df["date"] <= to_date)
        trading_dates = df.loc[mask, "date"].tolist()

        trades: list[SimTrade] = []
        open_pos: Optional[_OpenPosition] = None

        for current_date in trading_dates:
            df_slice = df[df["date"] <= current_date].copy()
            if len(df_slice) < 30:
                continue

            current_price = float(df_slice["close"].iloc[-1])

            # Check exits before entries
            if open_pos:
                reason = self._check_exit(open_pos, current_price, current_date)
                if reason:
                    trades.append(self._close(symbol, open_pos, current_price, current_date, reason))
                    open_pos = None

            if open_pos is None:
                df_ind = IndicatorEngine.compute(df_slice)

                if use_aggregator:
                    pairs = [(s, s.generate_signal(df_ind)) for s in strategies]
                    consensus = aggregator.aggregate(pairs)
                    should_enter = consensus["signal_type"] == "BUY"
                    buy_sigs = [sig for _, sig in pairs if sig.signal_type == "BUY"]
                    stop_pct = (sum(s.stop_loss_pct for s in buy_sigs) / len(buy_sigs)) if buy_sigs else 7.0
                    tgt_pct = (sum(s.target_pct for s in buy_sigs) / len(buy_sigs)) if buy_sigs else 15.0
                    h_days = int(sum(s.holding_days for s in buy_sigs) / len(buy_sigs)) if buy_sigs else 15
                else:
                    sig = strategies[0].generate_signal(df_ind)
                    should_enter = sig.signal_type == "BUY"
                    stop_pct, tgt_pct, h_days = sig.stop_loss_pct, sig.target_pct, sig.holding_days

                if should_enter:
                    sl = round(current_price * (1 - stop_pct / 100), 2)
                    tgt = round(current_price * (1 + tgt_pct / 100), 2)
                    pos = sizer.compute(
                        entry_price=current_price,
                        stop_loss_price=sl,
                        target_price=tgt,
                        open_positions=0,
                        invested_capital=0.0,
                        _cfg=cfg,
                    )
                    if pos.is_valid:
                        open_pos = _OpenPosition(
                            entry_date=current_date,
                            entry_price=current_price,
                            quantity=pos.quantity,
                            stop_loss_price=pos.stop_loss_price,
                            target_price=pos.target_price,
                            max_exit_date=current_date + timedelta(days=h_days),
                        )

        # Force-close any open position at end of period
        if open_pos and trading_dates:
            last_price = float(df[df["date"] <= to_date]["close"].iloc[-1])
            trades.append(self._close(symbol, open_pos, last_price, to_date, "end_of_period"))

        return trades

    def _check_exit(self, pos: _OpenPosition, price: float, current_date: date) -> Optional[str]:
        if price <= pos.stop_loss_price:
            return "stop_loss"
        if price >= pos.target_price:
            return "target_hit"
        if current_date >= pos.max_exit_date:
            return "max_holding_days"
        return None

    def _close(self, symbol: str, pos: _OpenPosition, price: float,
               exit_date: date, reason: str) -> SimTrade:
        pnl = round((price - pos.entry_price) * pos.quantity, 2)
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
            pnl=pnl,
            pnl_pct=pnl_pct,
            holding_days=(exit_date - pos.entry_date).days,
        )
```

- [ ] **Step 5: Run tests**

```
cd /c/DLP_Repos/MyRepo/StockV2/backend && python -m pytest tests/test_backtest_simulator.py -v
```
Expected: 4 passed

- [ ] **Step 6: Commit**

```
git -C /c/DLP_Repos/MyRepo/StockV2 add backend/domains/backtest/ backend/tests/test_backtest_simulator.py
git -C /c/DLP_Repos/MyRepo/StockV2 commit -m "feat: BacktestSimulator — in-memory strategy replay with position sizing"
```

---

### Task 2: BacktestMetrics

**Files:**
- Create: `backend/domains/backtest/metrics.py`
- Create: `backend/tests/test_backtest_metrics.py`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_backtest_metrics.py
from datetime import date
from domains.backtest.simulator import SimTrade


def _trade(pnl: float, pnl_pct: float, entry: date, exit_: date) -> SimTrade:
    return SimTrade(
        symbol="TCS",
        entry_date=entry,
        entry_price=1000.0,
        exit_date=exit_,
        exit_price=1000.0 + pnl / 100,
        quantity=100,
        stop_loss_price=930.0,
        target_price=1150.0,
        exit_reason="target_hit",
        pnl=pnl,
        pnl_pct=pnl_pct,
        holding_days=(exit_ - entry).days,
    )


def test_empty_trades():
    from domains.backtest.metrics import compute_metrics
    result = compute_metrics([], 500_000.0, date(2023, 1, 1), date(2023, 12, 31))
    assert result["total_trades"] == 0
    assert result["total_pnl"] == 0.0
    assert result["win_rate"] is None


def test_all_wins():
    from domains.backtest.metrics import compute_metrics
    trades = [
        _trade(1000.0, 1.0, date(2023, 1, 2), date(2023, 1, 20)),
        _trade(2000.0, 2.0, date(2023, 2, 1), date(2023, 2, 20)),
    ]
    r = compute_metrics(trades, 500_000.0, date(2023, 1, 1), date(2023, 12, 31))
    assert r["win_rate"] == 1.0
    assert r["total_pnl"] == 3000.0
    assert r["total_trades"] == 2


def test_mixed_win_loss():
    from domains.backtest.metrics import compute_metrics
    trades = [
        _trade(1000.0, 1.0, date(2023, 1, 2), date(2023, 1, 20)),
        _trade(-500.0, -0.5, date(2023, 2, 1), date(2023, 2, 20)),
    ]
    r = compute_metrics(trades, 500_000.0, date(2023, 1, 1), date(2023, 12, 31))
    assert r["win_rate"] == 0.5
    assert r["total_pnl"] == 500.0


def test_profit_factor():
    from domains.backtest.metrics import compute_metrics
    trades = [
        _trade(2000.0, 2.0, date(2023, 1, 2), date(2023, 1, 20)),
        _trade(-1000.0, -1.0, date(2023, 2, 1), date(2023, 2, 20)),
    ]
    r = compute_metrics(trades, 500_000.0, date(2023, 1, 1), date(2023, 12, 31))
    assert r["profit_factor"] == 2.0


def test_cagr_positive():
    from domains.backtest.metrics import compute_metrics
    # 10% gain in ~1 year → CAGR ≈ 10%
    trades = [
        _trade(50_000.0, 10.0, date(2023, 1, 2), date(2023, 6, 30)),
    ]
    r = compute_metrics(trades, 500_000.0, date(2023, 1, 1), date(2023, 12, 31))
    assert r["cagr"] is not None
    assert r["cagr"] > 0


def test_max_drawdown_negative():
    from domains.backtest.metrics import compute_metrics
    # Loss followed by a gain — there should be a drawdown
    trades = [
        _trade(-10_000.0, -2.0, date(2023, 1, 2), date(2023, 1, 20)),
        _trade(5_000.0, 1.0, date(2023, 2, 1), date(2023, 2, 20)),
    ]
    r = compute_metrics(trades, 500_000.0, date(2023, 1, 1), date(2023, 12, 31))
    assert r["max_drawdown"] is not None
    assert r["max_drawdown"] < 0
```

- [ ] **Step 2: Run to confirm failure**

```
cd /c/DLP_Repos/MyRepo/StockV2/backend && python -m pytest tests/test_backtest_metrics.py -v 2>&1 | head -10
```
Expected: `ModuleNotFoundError: No module named 'domains.backtest.metrics'`

- [ ] **Step 3: Create `backend/domains/backtest/metrics.py`**

```python
import statistics
from datetime import date
from typing import Optional

import pandas as pd


def compute_metrics(
    trades: list,
    initial_capital: float,
    from_date: date,
    to_date: date,
) -> dict:
    if not trades:
        return {
            "total_trades": 0,
            "win_rate": None,
            "total_pnl": 0.0,
            "total_return_pct": 0.0,
            "cagr": None,
            "sharpe_ratio": None,
            "max_drawdown": None,
            "profit_factor": None,
            "avg_return_pct": None,
        }

    total_trades = len(trades)
    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl <= 0]
    win_rate = round(len(wins) / total_trades, 4)

    total_pnl = round(sum(t.pnl for t in trades), 2)
    total_return_pct = round(total_pnl / initial_capital * 100, 4)

    days = max((to_date - from_date).days, 1)
    final_capital = initial_capital + total_pnl
    cagr = None
    if final_capital > 0:
        cagr = round(((final_capital / initial_capital) ** (365.0 / days) - 1) * 100, 4)

    gross_profit = sum(t.pnl for t in wins) if wins else 0.0
    gross_loss = abs(sum(t.pnl for t in losses)) if losses else 0.0
    profit_factor = round(gross_profit / gross_loss, 4) if gross_loss > 0 else None

    avg_return_pct = round(sum(t.pnl_pct for t in trades) / total_trades, 4)

    equity_curve = _build_equity_curve(trades, initial_capital, from_date, to_date)
    sharpe = _compute_sharpe(equity_curve)
    max_dd = _compute_max_drawdown(equity_curve)

    return {
        "total_trades": total_trades,
        "win_rate": win_rate,
        "total_pnl": total_pnl,
        "total_return_pct": total_return_pct,
        "cagr": cagr,
        "sharpe_ratio": sharpe,
        "max_drawdown": max_dd,
        "profit_factor": profit_factor,
        "avg_return_pct": avg_return_pct,
    }


def _build_equity_curve(trades: list, initial_capital: float,
                         from_date: date, to_date: date) -> list[float]:
    pnl_by_date: dict[date, float] = {}
    for t in trades:
        pnl_by_date[t.exit_date] = pnl_by_date.get(t.exit_date, 0.0) + t.pnl

    bdays = pd.bdate_range(from_date, to_date)
    equity = initial_capital
    curve: list[float] = []
    for d in bdays:
        equity += pnl_by_date.get(d.date(), 0.0)
        curve.append(equity)
    return curve


def _compute_sharpe(curve: list[float]) -> Optional[float]:
    if len(curve) < 3:
        return None
    returns = [(curve[i] - curve[i - 1]) / curve[i - 1] for i in range(1, len(curve))]
    if len(returns) < 2:
        return None
    mean_r = statistics.mean(returns)
    std_r = statistics.stdev(returns)
    if std_r == 0:
        return None
    return round(mean_r / std_r * (252 ** 0.5), 4)


def _compute_max_drawdown(curve: list[float]) -> Optional[float]:
    if not curve:
        return None
    peak = curve[0]
    max_dd = 0.0
    for v in curve:
        peak = max(peak, v)
        dd = (v - peak) / peak * 100
        if dd < max_dd:
            max_dd = dd
    return round(max_dd, 4)
```

- [ ] **Step 4: Run tests**

```
cd /c/DLP_Repos/MyRepo/StockV2/backend && python -m pytest tests/test_backtest_metrics.py -v
```
Expected: 6 passed

- [ ] **Step 5: Commit**

```
git -C /c/DLP_Repos/MyRepo/StockV2 add backend/domains/backtest/metrics.py backend/tests/test_backtest_metrics.py
git -C /c/DLP_Repos/MyRepo/StockV2 commit -m "feat: compute_metrics — CAGR, Sharpe, max drawdown, win rate, profit factor"
```

---

### Task 3: BacktestRunner

**Files:**
- Create: `backend/domains/backtest/runner.py`
- Create: `backend/tests/test_backtest_runner.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_backtest_runner.py
import pytest
from datetime import date
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import pandas as pd
from database import Base
import models  # noqa


@pytest.fixture(scope="module")
def db():
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    Session = sessionmaker(bind=eng)
    session = Session()

    # Seed 300 days of steadily rising prices for TCS starting 2020-01-01.
    # from_date=2021-01-01 is bar ~262 → >200 bars of warmup history.
    dates = pd.bdate_range("2020-01-01", periods=300)
    for i, d in enumerate(dates):
        close = 1000.0 + i * 2.0
        session.execute(text("""
            INSERT INTO stock_prices_daily
                (symbol, date, open, high, low, close, volume, data_source)
            VALUES (:sym, :d, :o, :h, :l, :c, :v, 'test')
        """), {
            "sym": "TCS",
            "d": d.date().isoformat(),
            "o": round(close * 0.995, 2),
            "h": round(close * 1.010, 2),
            "l": round(close * 0.990, 2),
            "c": close,
            "v": 1_000_000,
        })
    session.commit()
    yield session
    session.close()


def test_runner_returns_result_id(db):
    from domains.backtest.runner import BacktestRunner
    result = BacktestRunner(db).run(
        symbol="TCS",
        from_date=date(2021, 1, 4),
        to_date=date(2021, 3, 31),
    )
    assert "error" not in result
    assert "result_id" in result
    assert result["result_id"] > 0
    assert result["symbol"] == "TCS"


def test_runner_saves_result_to_db(db):
    count = db.execute(text("SELECT COUNT(*) FROM backtest_results")).fetchone()[0]
    assert count >= 1


def test_runner_result_has_metrics(db):
    from domains.backtest.runner import BacktestRunner
    result = BacktestRunner(db).run(
        symbol="TCS",
        from_date=date(2021, 1, 4),
        to_date=date(2021, 3, 31),
    )
    assert "total_trades" in result
    assert "win_rate" in result
    assert "cagr" in result
    assert "total_pnl" in result


def test_runner_insufficient_data_returns_error(db):
    from domains.backtest.runner import BacktestRunner
    result = BacktestRunner(db).run(
        symbol="NONEXISTENT",
        from_date=date(2021, 1, 4),
        to_date=date(2021, 3, 31),
    )
    assert "error" in result
```

- [ ] **Step 2: Run to confirm failure**

```
cd /c/DLP_Repos/MyRepo/StockV2/backend && python -m pytest tests/test_backtest_runner.py -v 2>&1 | head -10
```
Expected: `ModuleNotFoundError: No module named 'domains.backtest.runner'`

- [ ] **Step 3: Create `backend/domains/backtest/runner.py`**

```python
import json
import logging
from datetime import date
from typing import Optional

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from domains.backtest.metrics import compute_metrics
from domains.backtest.simulator import BacktestSimulator, SimTrade
from domains.strategies.engine import ALL_STRATEGIES

logger = logging.getLogger(__name__)


class BacktestRunner:
    def __init__(self, db: Session):
        self.db = db
        self.simulator = BacktestSimulator()

    def run(
        self,
        symbol: str,
        from_date: date,
        to_date: date,
        strategy_id: Optional[int] = None,
        initial_capital: float = 500_000.0,
    ) -> dict:
        rows = self.db.execute(
            text("""
                SELECT date, open, high, low, close, volume
                FROM stock_prices_daily
                WHERE symbol = :sym
                ORDER BY date ASC
            """),
            {"sym": symbol.upper()},
        ).fetchall()

        if len(rows) < 50:
            return {"error": f"Insufficient price data for {symbol}: {len(rows)} bars (need ≥ 50)"}

        df = pd.DataFrame([dict(r._mapping) for r in rows])

        if strategy_id is not None:
            row = self.db.execute(
                text("SELECT name FROM strategies WHERE id = :id"), {"id": strategy_id}
            ).fetchone()
            if not row:
                return {"error": f"Strategy id={strategy_id} not found"}
            strat_name = row[0]
            strategies = [s for s in ALL_STRATEGIES if s.name == strat_name]
            if not strategies:
                return {"error": f"Strategy '{strat_name}' not in ALL_STRATEGIES"}
            use_aggregator = False
        else:
            strategies = list(ALL_STRATEGIES)
            use_aggregator = True

        trades = self.simulator.run(
            symbol=symbol.upper(),
            prices_df=df,
            from_date=from_date,
            to_date=to_date,
            strategies=strategies,
            use_aggregator=use_aggregator,
            initial_capital=initial_capital,
        )

        metrics = compute_metrics(trades, initial_capital, from_date, to_date)
        result_id = self._save_result(symbol.upper(), from_date, to_date, strategy_id, metrics, trades)

        logger.info("[BacktestRunner] %s %s→%s: %d trades, result_id=%d",
                    symbol, from_date, to_date, len(trades), result_id)
        return {
            "result_id": result_id,
            "symbol": symbol.upper(),
            "from_date": str(from_date),
            "to_date": str(to_date),
            **metrics,
        }

    def _save_result(
        self, symbol: str, from_date: date, to_date: date,
        strategy_id: Optional[int], metrics: dict, trades: list[SimTrade],
    ) -> int:
        result = self.db.execute(
            text("""
                INSERT INTO backtest_results
                    (strategy_id, symbol, from_date, to_date,
                     total_trades, win_rate, cagr, sharpe_ratio,
                     sortino_ratio, max_drawdown, profit_factor,
                     avg_return_pct, full_metrics_json, ran_at)
                VALUES (:sid, :sym, :fd, :td,
                        :tt, :wr, :cagr, :sharpe,
                        NULL, :dd, :pf, :ar, :fmj, datetime('now'))
            """),
            {
                "sid": strategy_id,
                "sym": symbol,
                "fd": str(from_date),
                "td": str(to_date),
                "tt": metrics["total_trades"],
                "wr": metrics["win_rate"],
                "cagr": metrics["cagr"],
                "sharpe": metrics["sharpe_ratio"],
                "dd": metrics["max_drawdown"],
                "pf": metrics["profit_factor"],
                "ar": metrics["avg_return_pct"],
                "fmj": json.dumps(metrics),
            },
        )
        result_id = result.lastrowid

        for t in trades:
            self.db.execute(
                text("""
                    INSERT INTO backtest_trades
                        (backtest_result_id, symbol, entry_date, entry_price,
                         exit_date, exit_price, quantity, pnl, pnl_pct,
                         exit_reason, holding_days)
                    VALUES (:rid, :sym, :ed, :ep, :xd, :xp, :qty, :pnl, :ppct, :er, :hd)
                """),
                {
                    "rid": result_id, "sym": t.symbol,
                    "ed": str(t.entry_date), "ep": t.entry_price,
                    "xd": str(t.exit_date), "xp": t.exit_price,
                    "qty": t.quantity, "pnl": t.pnl, "ppct": t.pnl_pct,
                    "er": t.exit_reason, "hd": t.holding_days,
                },
            )

        self.db.commit()
        return result_id
```

- [ ] **Step 4: Run tests**

```
cd /c/DLP_Repos/MyRepo/StockV2/backend && python -m pytest tests/test_backtest_runner.py -v
```
Expected: 4 passed

Note: `test_backtest_runner.py` runs the full strategy engine against 300 synthetic bars. It may take 10–30 seconds depending on machine speed — that is expected.

- [ ] **Step 5: Commit**

```
git -C /c/DLP_Repos/MyRepo/StockV2 add backend/domains/backtest/runner.py backend/tests/test_backtest_runner.py
git -C /c/DLP_Repos/MyRepo/StockV2 commit -m "feat: BacktestRunner — DB price loading, strategy replay, result persistence"
```

---

### Task 4: BacktestService + Router + main.py

**Files:**
- Create: `backend/domains/backtest/service.py`
- Create: `backend/domains/backtest/router.py`
- Modify: `backend/main.py`
- Create: `backend/tests/test_backtest_router.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_backtest_router.py
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import pandas as pd

from database import Base, get_db
from settings import settings
import models  # noqa


@pytest.fixture(scope="module")
def client():
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(test_engine)
    TestSession = sessionmaker(bind=test_engine)

    db = TestSession()
    # Seed 300 days for RELIANCE — same pattern as runner test
    dates = pd.bdate_range("2020-01-01", periods=300)
    for i, d in enumerate(dates):
        close = 2000.0 + i * 3.0
        db.execute(text("""
            INSERT INTO stock_prices_daily
                (symbol, date, open, high, low, close, volume, data_source)
            VALUES (:sym, :d, :o, :h, :l, :c, :v, 'test')
        """), {
            "sym": "RELIANCE",
            "d": d.date().isoformat(),
            "o": round(close * 0.995, 2),
            "h": round(close * 1.010, 2),
            "l": round(close * 0.990, 2),
            "c": close,
            "v": 1_000_000,
        })
    db.commit()
    db.close()

    def override_get_db():
        session = TestSession()
        try:
            yield session
        finally:
            session.close()

    from main import app
    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app, headers={"X-API-Key": settings.api_key})


def test_run_backtest_returns_metrics(client):
    r = client.post("/api/v1/backtest/run", json={
        "symbol": "RELIANCE",
        "from_date": "2021-01-04",
        "to_date": "2021-03-31",
    })
    assert r.status_code == 200
    data = r.json()
    assert "result_id" in data
    assert "total_trades" in data
    assert "win_rate" in data
    assert "cagr" in data


def test_run_backtest_bad_symbol(client):
    r = client.post("/api/v1/backtest/run", json={
        "symbol": "FAKESTK",
        "from_date": "2021-01-04",
        "to_date": "2021-03-31",
    })
    assert r.status_code == 400


def test_list_results(client):
    r = client.get("/api/v1/backtest/results")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
    assert len(r.json()) >= 1


def test_list_results_filtered_by_symbol(client):
    r = client.get("/api/v1/backtest/results?symbol=RELIANCE")
    assert r.status_code == 200
    for item in r.json():
        assert item["symbol"] == "RELIANCE"


def test_get_result_by_id(client):
    run_r = client.post("/api/v1/backtest/run", json={
        "symbol": "RELIANCE",
        "from_date": "2021-01-04",
        "to_date": "2021-03-31",
    })
    result_id = run_r.json()["result_id"]
    r = client.get(f"/api/v1/backtest/results/{result_id}")
    assert r.status_code == 200
    assert r.json()["id"] == result_id


def test_get_result_trades(client):
    run_r = client.post("/api/v1/backtest/run", json={
        "symbol": "RELIANCE",
        "from_date": "2021-01-04",
        "to_date": "2021-03-31",
    })
    result_id = run_r.json()["result_id"]
    r = client.get(f"/api/v1/backtest/results/{result_id}/trades")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_get_result_404(client):
    r = client.get("/api/v1/backtest/results/99999")
    assert r.status_code == 404


def test_unauthorized(client):
    from main import app
    c = TestClient(app)
    r = c.post("/api/v1/backtest/run", json={
        "symbol": "RELIANCE", "from_date": "2021-01-04", "to_date": "2021-03-31"
    })
    assert r.status_code == 401
```

- [ ] **Step 2: Run to confirm failure**

```
cd /c/DLP_Repos/MyRepo/StockV2/backend && python -m pytest tests/test_backtest_router.py -v 2>&1 | head -15
```
Expected: 404 / import error (routes not registered)

- [ ] **Step 3: Create `backend/domains/backtest/service.py`**

```python
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session


class BacktestService:
    def __init__(self, db: Session):
        self.db = db

    def get_results(self, symbol: Optional[str] = None, limit: int = 20) -> list[dict]:
        q = "SELECT * FROM backtest_results"
        params: dict = {}
        if symbol:
            q += " WHERE symbol = :sym"
            params["sym"] = symbol.upper()
        q += " ORDER BY ran_at DESC LIMIT :lim"
        params["lim"] = limit
        rows = self.db.execute(text(q), params).fetchall()
        return [dict(r._mapping) for r in rows]

    def get_result(self, result_id: int) -> Optional[dict]:
        row = self.db.execute(
            text("SELECT * FROM backtest_results WHERE id = :id"), {"id": result_id}
        ).fetchone()
        return dict(row._mapping) if row else None

    def get_trades(self, result_id: int, limit: int = 100) -> list[dict]:
        rows = self.db.execute(
            text("SELECT * FROM backtest_trades WHERE backtest_result_id = :id "
                 "ORDER BY entry_date LIMIT :lim"),
            {"id": result_id, "lim": limit},
        ).fetchall()
        return [dict(r._mapping) for r in rows]
```

- [ ] **Step 4: Create `backend/domains/backtest/router.py`**

```python
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from domains.backtest.runner import BacktestRunner
from domains.backtest.service import BacktestService

router = APIRouter(tags=["backtest"])


class BacktestRunRequest(BaseModel):
    symbol: str
    from_date: date
    to_date: date
    strategy_id: Optional[int] = None
    initial_capital: float = 500_000.0


@router.post("/backtest/run")
def run_backtest(body: BacktestRunRequest, db: Session = Depends(get_db)):
    result = BacktestRunner(db).run(
        symbol=body.symbol,
        from_date=body.from_date,
        to_date=body.to_date,
        strategy_id=body.strategy_id,
        initial_capital=body.initial_capital,
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/backtest/results")
def list_results(
    symbol: Optional[str] = None,
    limit: int = 20,
    db: Session = Depends(get_db),
):
    return BacktestService(db).get_results(symbol=symbol, limit=limit)


@router.get("/backtest/results/{result_id}")
def get_result(result_id: int, db: Session = Depends(get_db)):
    result = BacktestService(db).get_result(result_id)
    if not result:
        raise HTTPException(status_code=404, detail="Backtest result not found")
    return result


@router.get("/backtest/results/{result_id}/trades")
def get_result_trades(result_id: int, db: Session = Depends(get_db)):
    return BacktestService(db).get_trades(result_id)
```

- [ ] **Step 5: Read `backend/main.py` then add the backtest router**

After the portfolio router lines, add:

```python
from domains.backtest.router import router as backtest_router  # noqa: E402
app.include_router(backtest_router, prefix="/api/v1", dependencies=[Depends(verify_api_key)])
```

- [ ] **Step 6: Run backtest router tests**

```
cd /c/DLP_Repos/MyRepo/StockV2/backend && python -m pytest tests/test_backtest_router.py -v
```
Expected: 8 passed

Note: `test_run_backtest_returns_metrics` runs a full strategy replay and may take 10–30 seconds.

- [ ] **Step 7: Run full test suite**

```
cd /c/DLP_Repos/MyRepo/StockV2/backend && python -m pytest -v 2>&1 | tail -15
```
Expected: all pass (166 existing + new tests)

- [ ] **Step 8: Commit and tag**

```
git -C /c/DLP_Repos/MyRepo/StockV2 add backend/domains/backtest/service.py backend/domains/backtest/router.py backend/main.py backend/tests/test_backtest_router.py
git -C /c/DLP_Repos/MyRepo/StockV2 commit -m "feat: backtesting REST API — run, list results, trades"
git -C /c/DLP_Repos/MyRepo/StockV2 tag plan4-backtesting-engine
```

---

## Summary

After all 4 tasks:

| Component | Files | Tests |
|---|---|---|
| BacktestSimulator + SimTrade | `simulator.py` | 4 |
| BacktestMetrics | `metrics.py` | 6 |
| BacktestRunner | `runner.py` | 4 |
| BacktestService + Router + main.py | `service.py`, `router.py` | 8 |

**End-to-end flow after Plan 4:**
`POST /backtest/run {symbol, from_date, to_date}` → `BacktestRunner.run()` → loads all price history from `stock_prices_daily` → `BacktestSimulator.run()` iterates each trading day, computing indicators + running strategies + checking entry/exit → `compute_metrics()` computes CAGR, Sharpe, win rate, max drawdown → saves `BacktestResult` + `BacktestTrade` rows → returns summary. `GET /backtest/results/{id}/trades` shows individual trade-level detail.
