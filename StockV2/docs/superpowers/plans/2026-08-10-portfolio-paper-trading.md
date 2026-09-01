# Portfolio & Paper Trading — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Paper trading engine that auto-enters positions from high-confidence signals, monitors stop loss and targets, and tracks portfolio P&L with a REST API.

**Architecture:** `PositionSizer` computes risk-based quantity from signal parameters and portfolio limits. `PaperTrader` executes enters/exits with DB writes to `portfolio_holdings`, `trades`, `exit_rules`. `ExitMonitor` scans open exit rules against current prices and calls `PaperTrader.exit()` for triggered exits. `PortfolioService` provides read-only queries. REST API exposes all operations. APScheduler wires `ExitMonitor` into the intraday scan using last daily close prices.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy 2.0 (raw SQL via `text()`), pydantic, pytest, SQLite (StaticPool for tests)

**Existing foundation (do not re-implement):**
- `backend/models.py` — `portfolio_holdings`, `trades`, `exit_rules`, `watchlist` tables already defined
- `backend/settings.py` — `paper_capital=500_000`, `risk_per_trade_pct=2.0`, `max_open_positions=8`, `max_single_stock_pct=20.0`
- `backend/domains/strategies/service.py` — `StrategyService.get_signal_by_id(id)` returns signal dict
- `backend/scheduler.py` — `_intraday_scan()` to be modified in Task 7
- `backend/main.py` — router includes at bottom, lifespan with seed

---

## File Map

```
backend/
├── domains/
│   └── portfolio/
│       ├── __init__.py              NEW (empty)
│       ├── position_sizer.py        NEW — PositionSize dataclass + PositionSizer.compute()
│       ├── paper_trader.py          NEW — PaperTrader.enter() + .exit()
│       ├── exit_monitor.py          NEW — ExitMonitor.scan_exits()
│       ├── service.py               NEW — PortfolioService read queries + P&L
│       ├── watchlist_service.py     NEW — WatchlistService CRUD
│       └── router.py                NEW — REST endpoints (portfolio + watchlist)
├── scheduler.py                     MODIFY — wire ExitMonitor into _intraday_scan
├── main.py                          MODIFY — include portfolio router
└── tests/
    ├── test_position_sizer.py       NEW
    ├── test_paper_trader.py         NEW
    ├── test_exit_monitor.py         NEW
    ├── test_portfolio_service.py    NEW
    └── test_portfolio_router.py     NEW
```

---

### Task 1: PositionSizer

**Files:**
- Create: `backend/domains/portfolio/__init__.py`
- Create: `backend/domains/portfolio/position_sizer.py`
- Create: `backend/tests/test_position_sizer.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_position_sizer.py
from types import SimpleNamespace

CFG = SimpleNamespace(
    total_capital=500_000.0,
    paper_capital=500_000.0,
    risk_per_trade_pct=2.0,
    max_open_positions=8,
    max_single_stock_pct=20.0,
)


def test_basic_valid_position():
    from domains.portfolio.position_sizer import PositionSizer
    sizer = PositionSizer()
    # risk=10_000, risk_per_share=100 (1000-900), qty=100, pos_value=100_000 (20% cap exact)
    result = sizer.compute(
        entry_price=1000.0, stop_loss_price=900.0, target_price=1150.0,
        open_positions=0, invested_capital=0.0, _cfg=CFG,
    )
    assert result.is_valid
    assert result.quantity == 100
    assert result.position_value == 100_000.0
    assert result.stop_loss_price == 900.0
    assert result.target_price == 1150.0


def test_caps_at_max_single_stock_pct():
    from domains.portfolio.position_sizer import PositionSizer
    sizer = PositionSizer()
    # Tight stop → qty would be huge; capped at 20% of capital
    result = sizer.compute(
        entry_price=1000.0, stop_loss_price=990.0, target_price=1100.0,
        open_positions=0, invested_capital=0.0, _cfg=CFG,
    )
    assert result.is_valid
    assert result.position_value <= 100_000.0 + 1000.0


def test_rejects_when_max_positions_reached():
    from domains.portfolio.position_sizer import PositionSizer
    result = PositionSizer().compute(
        entry_price=1000.0, stop_loss_price=900.0, target_price=1150.0,
        open_positions=8, invested_capital=0.0, _cfg=CFG,
    )
    assert not result.is_valid
    assert "Max open positions" in result.reject_reason


def test_rejects_when_insufficient_capital():
    from domains.portfolio.position_sizer import PositionSizer
    result = PositionSizer().compute(
        entry_price=1000.0, stop_loss_price=900.0, target_price=1150.0,
        open_positions=0, invested_capital=490_000.0, _cfg=CFG,
    )
    assert not result.is_valid
    assert "Insufficient capital" in result.reject_reason


def test_rejects_when_stop_loss_above_entry():
    from domains.portfolio.position_sizer import PositionSizer
    result = PositionSizer().compute(
        entry_price=1000.0, stop_loss_price=1050.0, target_price=1200.0,
        open_positions=0, invested_capital=0.0, _cfg=CFG,
    )
    assert not result.is_valid
    assert "Invalid stop loss" in result.reject_reason
```

- [ ] **Step 2: Run to confirm failure**

```
cd /c/DLP_Repos/MyRepo/StockV2/backend && python -m pytest tests/test_position_sizer.py -v 2>&1 | head -10
```
Expected: ImportError — `domains.portfolio.position_sizer` not found

- [ ] **Step 3: Create `backend/domains/portfolio/__init__.py`**

Empty file.

- [ ] **Step 4: Create `backend/domains/portfolio/position_sizer.py`**

```python
from dataclasses import dataclass
from typing import Optional

from settings import settings


@dataclass
class PositionSize:
    quantity: int
    position_value: float
    risk_amount: float
    stop_loss_price: float
    target_price: float
    reject_reason: Optional[str] = None

    @property
    def is_valid(self) -> bool:
        return self.reject_reason is None and self.quantity > 0


class PositionSizer:
    def compute(
        self,
        entry_price: float,
        stop_loss_price: float,
        target_price: float,
        open_positions: int,
        invested_capital: float,
        _cfg=None,
    ) -> PositionSize:
        cfg = _cfg or settings
        risk_per_share = entry_price - stop_loss_price

        if risk_per_share <= 0:
            return PositionSize(0, 0.0, 0.0, stop_loss_price, target_price,
                                "Invalid stop loss: stop_loss_price must be below entry_price")

        risk_amount = cfg.total_capital * cfg.risk_per_trade_pct / 100
        quantity = int(risk_amount / risk_per_share)

        if quantity <= 0:
            return PositionSize(0, 0.0, risk_amount, stop_loss_price, target_price,
                                "Quantity is 0 after risk sizing")

        max_pos_value = cfg.total_capital * cfg.max_single_stock_pct / 100
        if quantity * entry_price > max_pos_value:
            quantity = int(max_pos_value / entry_price)

        if quantity <= 0:
            return PositionSize(0, 0.0, risk_amount, stop_loss_price, target_price,
                                "Quantity is 0 after max-position cap")

        position_value = round(quantity * entry_price, 2)

        if open_positions >= cfg.max_open_positions:
            return PositionSize(0, 0.0, risk_amount, stop_loss_price, target_price,
                                f"Max open positions reached ({cfg.max_open_positions})")

        available = cfg.paper_capital - invested_capital
        if position_value > available:
            return PositionSize(0, 0.0, risk_amount, stop_loss_price, target_price,
                                f"Insufficient capital: need ₹{position_value:.0f}, available ₹{available:.0f}")

        return PositionSize(
            quantity=quantity,
            position_value=position_value,
            risk_amount=risk_amount,
            stop_loss_price=stop_loss_price,
            target_price=target_price,
        )
```

- [ ] **Step 5: Run tests**

```
cd /c/DLP_Repos/MyRepo/StockV2/backend && python -m pytest tests/test_position_sizer.py -v
```
Expected: 5 passed

- [ ] **Step 6: Commit**

```
git -C /c/DLP_Repos/MyRepo/StockV2 add backend/domains/portfolio/ backend/tests/test_position_sizer.py
git -C /c/DLP_Repos/MyRepo/StockV2 commit -m "feat: PositionSizer — risk-based position sizing with capital guards"
```

---

### Task 2: PaperTrader (enter + exit)

**Files:**
- Create: `backend/domains/portfolio/paper_trader.py`
- Create: `backend/tests/test_paper_trader.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_paper_trader.py
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

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

    session.execute(text(
        "INSERT INTO strategies (name, type, description, is_active, created_at) "
        "VALUES ('RSI', 'technical', '', 1, datetime('now'))"
    ))
    session.execute(text(
        "INSERT INTO stocks (symbol, name, exchange, is_active, added_at) "
        "VALUES ('TCS', 'TCS', 'NSE', 1, datetime('now'))"
    ))
    # Signal 1: BUY with stop_loss and target
    session.execute(text("""
        INSERT INTO strategy_signals
            (symbol, strategy_id, signal_date, signal_type, price_at_signal,
             confidence_score, suggested_stop_loss, suggested_target,
             holding_period_days, created_at)
        VALUES ('TCS', 1, date('now'), 'BUY', 1000.0, 0.80, 900.0, 1150.0, 15, datetime('now'))
    """))
    # Signal 2: SELL — should be rejected by enter()
    session.execute(text("""
        INSERT INTO strategy_signals
            (symbol, strategy_id, signal_date, signal_type, price_at_signal,
             confidence_score, created_at)
        VALUES ('TCS', 1, date('now'), 'SELL', 1000.0, 0.70, datetime('now'))
    """))
    session.commit()
    yield session
    session.close()


def test_enter_creates_buy_trade(db):
    from domains.portfolio.paper_trader import PaperTrader
    result = PaperTrader(db).enter(signal_id=1, price=1000.0)
    assert result is not None
    assert result["trade_type"] == "BUY"
    assert result["symbol"] == "TCS"
    assert result["quantity"] > 0
    assert result["mode"] == "paper"


def test_enter_creates_portfolio_holding(db):
    count = db.execute(
        text("SELECT COUNT(*) FROM portfolio_holdings WHERE symbol='TCS' AND is_active=1")
    ).fetchone()[0]
    assert count == 1


def test_enter_creates_exit_rule(db):
    count = db.execute(
        text("SELECT COUNT(*) FROM exit_rules WHERE symbol='TCS'")
    ).fetchone()[0]
    assert count >= 1


def test_enter_rejects_sell_signal(db):
    from domains.portfolio.paper_trader import PaperTrader
    result = PaperTrader(db).enter(signal_id=2, price=1000.0)
    assert result is None


def test_exit_creates_sell_trade_and_closes_holding(db):
    from domains.portfolio.paper_trader import PaperTrader
    result = PaperTrader(db).exit("TCS", 1100.0, "target_hit")
    assert result is not None
    assert result["trade_type"] == "SELL"
    assert result["price"] == 1100.0
    holding = db.execute(
        text("SELECT is_active FROM portfolio_holdings WHERE symbol='TCS'")
    ).fetchone()
    assert holding[0] == 0


def test_exit_returns_none_for_missing_holding(db):
    from domains.portfolio.paper_trader import PaperTrader
    result = PaperTrader(db).exit("NONEXISTENT", 500.0, "manual")
    assert result is None
```

- [ ] **Step 2: Run to confirm failures**

```
cd /c/DLP_Repos/MyRepo/StockV2/backend && python -m pytest tests/test_paper_trader.py -v 2>&1 | head -10
```
Expected: ImportError

- [ ] **Step 3: Create `backend/domains/portfolio/paper_trader.py`**

```python
import json
import logging
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from domains.portfolio.position_sizer import PositionSizer

logger = logging.getLogger(__name__)


class PaperTrader:
    def __init__(self, db: Session):
        self.db = db
        self.sizer = PositionSizer()

    def enter(self, signal_id: int, price: float) -> Optional[dict]:
        signal = self._load_signal(signal_id)
        if not signal or signal["signal_type"] != "BUY":
            return None

        stop_loss_price = signal.get("suggested_stop_loss") or round(price * 0.93, 2)
        target_price = signal.get("suggested_target") or round(price * 1.15, 2)

        open_positions, invested_capital = self._portfolio_state()
        pos = self.sizer.compute(
            entry_price=price,
            stop_loss_price=stop_loss_price,
            target_price=target_price,
            open_positions=open_positions,
            invested_capital=invested_capital,
        )
        if not pos.is_valid:
            logger.warning("[PaperTrader] enter rejected for %s: %s",
                           signal["symbol"], pos.reject_reason)
            return None

        symbol = signal["symbol"]
        total_value = round(pos.quantity * price, 2)
        trade_id = self._insert_trade(
            symbol=symbol, trade_type="BUY", quantity=pos.quantity,
            price=price, total_value=total_value,
            strategy_id=signal.get("strategy_id"), signal_id=signal_id,
        )
        self._upsert_holding(symbol, pos.quantity, price)
        self._insert_exit_rule(
            trade_id=trade_id, symbol=symbol, entry_price=price,
            stop_loss_price=pos.stop_loss_price, target_price=pos.target_price,
            holding_days=signal.get("holding_period_days") or 15,
        )
        self.db.commit()
        logger.info("[PaperTrader] entered %s: qty=%d @ ₹%.2f sl=₹%.2f tgt=₹%.2f",
                    symbol, pos.quantity, price, pos.stop_loss_price, pos.target_price)
        return self._load_trade(trade_id)

    def exit(self, symbol: str, current_price: float, reason: str = "manual") -> Optional[dict]:
        holding = self._load_holding(symbol)
        if not holding or holding["quantity"] <= 0:
            logger.warning("[PaperTrader] exit skipped — no active holding for %s", symbol)
            return None

        quantity = holding["quantity"]
        avg_buy = holding["avg_buy_price"]
        pnl = round((current_price - avg_buy) * quantity, 2)
        pnl_pct = round((current_price - avg_buy) / avg_buy * 100, 2)
        notes = json.dumps({"reason": reason, "buy_avg": avg_buy, "pnl": pnl, "pnl_pct": pnl_pct})
        trade_id = self._insert_trade(
            symbol=symbol, trade_type="SELL", quantity=quantity,
            price=current_price, total_value=round(quantity * current_price, 2),
            notes=notes,
        )
        self.db.execute(
            text("UPDATE portfolio_holdings SET is_active=0, quantity=0 "
                 "WHERE symbol=:s AND is_active=1"),
            {"s": symbol},
        )
        self.db.commit()
        logger.info("[PaperTrader] exited %s: qty=%d @ ₹%.2f pnl=₹%.2f (%.1f%%) — %s",
                    symbol, quantity, current_price, pnl, pnl_pct, reason)
        return self._load_trade(trade_id)

    # ── internal helpers ────────────────────────────────────────────────────────

    def _load_signal(self, signal_id: int) -> Optional[dict]:
        row = self.db.execute(
            text("""
                SELECT id, symbol, signal_type, strategy_id,
                       suggested_stop_loss, suggested_target, holding_period_days
                FROM strategy_signals WHERE id = :id
            """),
            {"id": signal_id},
        ).fetchone()
        return dict(row._mapping) if row else None

    def _portfolio_state(self) -> tuple[int, float]:
        row = self.db.execute(
            text("SELECT COUNT(*), COALESCE(SUM(quantity * avg_buy_price), 0.0) "
                 "FROM portfolio_holdings WHERE is_active=1")
        ).fetchone()
        return row[0], float(row[1])

    def _insert_trade(self, symbol: str, trade_type: str, quantity: int,
                      price: float, total_value: float,
                      strategy_id: Optional[int] = None,
                      signal_id: Optional[int] = None,
                      notes: Optional[str] = None) -> int:
        result = self.db.execute(
            text("""
                INSERT INTO trades
                    (symbol, trade_type, quantity, price, total_value, brokerage,
                     mode, strategy_id, signal_id, notes, trade_date)
                VALUES (:sym, :tt, :qty, :price, :tv, 0, 'paper',
                        :sid, :sigid, :notes, datetime('now'))
            """),
            {"sym": symbol, "tt": trade_type, "qty": quantity, "price": price,
             "tv": total_value, "sid": strategy_id, "sigid": signal_id, "notes": notes},
        )
        return result.lastrowid

    def _upsert_holding(self, symbol: str, quantity: int, price: float):
        existing = self.db.execute(
            text("SELECT id, quantity, avg_buy_price FROM portfolio_holdings "
                 "WHERE symbol=:s AND is_active=1"),
            {"s": symbol},
        ).fetchone()
        if existing:
            old_qty, old_avg = existing[1], existing[2]
            new_qty = old_qty + quantity
            new_avg = round((old_qty * old_avg + quantity * price) / new_qty, 4)
            self.db.execute(
                text("UPDATE portfolio_holdings SET quantity=:q, avg_buy_price=:a, "
                     "last_buy_date=date('now') WHERE id=:id"),
                {"q": new_qty, "a": new_avg, "id": existing[0]},
            )
        else:
            self.db.execute(
                text("""
                    INSERT INTO portfolio_holdings
                        (symbol, quantity, avg_buy_price, first_buy_date, last_buy_date, is_active)
                    VALUES (:sym, :qty, :avg, date('now'), date('now'), 1)
                """),
                {"sym": symbol, "qty": quantity, "avg": round(price, 4)},
            )

    def _insert_exit_rule(self, trade_id: int, symbol: str, entry_price: float,
                          stop_loss_price: float, target_price: float, holding_days: int):
        max_exit = date.today() + timedelta(days=holding_days)
        self.db.execute(
            text("""
                INSERT INTO exit_rules
                    (order_id, symbol, entry_price, stop_loss_price,
                     target_1_price, target_2_price, max_exit_date, partial_exit_at_t1)
                VALUES (:oid, :sym, :ep, :sl, :t1, :t2, :med, 0)
            """),
            {"oid": trade_id, "sym": symbol, "ep": entry_price,
             "sl": stop_loss_price, "t1": target_price,
             "t2": round(target_price * 1.05, 2), "med": str(max_exit)},
        )

    def _load_holding(self, symbol: str) -> Optional[dict]:
        row = self.db.execute(
            text("SELECT * FROM portfolio_holdings WHERE symbol=:s AND is_active=1"),
            {"s": symbol},
        ).fetchone()
        return dict(row._mapping) if row else None

    def _load_trade(self, trade_id: int) -> dict:
        row = self.db.execute(
            text("SELECT * FROM trades WHERE id=:id"), {"id": trade_id}
        ).fetchone()
        return dict(row._mapping) if row else {}
```

- [ ] **Step 4: Run tests**

```
cd /c/DLP_Repos/MyRepo/StockV2/backend && python -m pytest tests/test_paper_trader.py -v
```
Expected: 6 passed

- [ ] **Step 5: Commit**

```
git -C /c/DLP_Repos/MyRepo/StockV2 add backend/domains/portfolio/paper_trader.py backend/tests/test_paper_trader.py
git -C /c/DLP_Repos/MyRepo/StockV2 commit -m "feat: PaperTrader — paper enter/exit with position sizing and exit rules"
```

---

### Task 3: ExitMonitor

**Files:**
- Create: `backend/domains/portfolio/exit_monitor.py`
- Create: `backend/tests/test_exit_monitor.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_exit_monitor.py
import pytest
from datetime import date, timedelta
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base
import models  # noqa


@pytest.fixture
def db():
    """Function-scoped: each test gets a clean DB."""
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    Session = sessionmaker(bind=eng)
    session = Session()
    # Active holding
    session.execute(text("""
        INSERT INTO portfolio_holdings
            (symbol, quantity, avg_buy_price, first_buy_date, last_buy_date, is_active)
        VALUES ('TCS', 100, 1000.0, date('now'), date('now'), 1)
    """))
    # Exit rule: sl=930, t1=1150, expire in 10 days
    session.execute(text("""
        INSERT INTO exit_rules
            (order_id, symbol, entry_price, stop_loss_price,
             target_1_price, target_2_price, max_exit_date, partial_exit_at_t1)
        VALUES (1, 'TCS', 1000.0, 930.0, 1150.0, 1200.0, :med, 0)
    """), {"med": str(date.today() + timedelta(days=10))})
    session.commit()
    yield session
    session.close()


def test_stop_loss_triggers_exit(db):
    from domains.portfolio.exit_monitor import ExitMonitor
    exits = ExitMonitor(db).scan_exits({"TCS": 920.0})
    assert len(exits) == 1
    assert exits[0]["reason"] == "stop_loss"
    assert exits[0]["symbol"] == "TCS"


def test_target_hit_triggers_exit(db):
    from domains.portfolio.exit_monitor import ExitMonitor
    exits = ExitMonitor(db).scan_exits({"TCS": 1200.0})
    assert len(exits) == 1
    assert exits[0]["reason"] == "target_hit"


def test_no_exit_between_sl_and_target(db):
    from domains.portfolio.exit_monitor import ExitMonitor
    exits = ExitMonitor(db).scan_exits({"TCS": 1050.0})
    assert exits == []


def test_max_holding_days_triggers_exit(db):
    # Move max_exit_date to yesterday
    past = str(date.today() - timedelta(days=1))
    db.execute(text("UPDATE exit_rules SET max_exit_date=:d WHERE symbol='TCS'"), {"d": past})
    db.commit()
    from domains.portfolio.exit_monitor import ExitMonitor
    exits = ExitMonitor(db).scan_exits({"TCS": 1050.0})
    assert len(exits) == 1
    assert exits[0]["reason"] == "max_holding_days"
```

- [ ] **Step 2: Run to confirm failures**

```
cd /c/DLP_Repos/MyRepo/StockV2/backend && python -m pytest tests/test_exit_monitor.py -v 2>&1 | head -10
```
Expected: ImportError

- [ ] **Step 3: Create `backend/domains/portfolio/exit_monitor.py`**

```python
import logging
from datetime import date
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class ExitMonitor:
    def __init__(self, db: Session):
        self.db = db

    def scan_exits(self, current_prices: dict[str, float]) -> list[dict]:
        """Check open exit rules against current_prices. Returns list of executed exits."""
        from domains.portfolio.paper_trader import PaperTrader
        trader = PaperTrader(self.db)
        exits = []
        for rule in self._load_open_rules():
            symbol = rule["symbol"]
            price = current_prices.get(symbol)
            if price is None:
                continue
            reason = self._check_exit(rule, price)
            if reason:
                trade = trader.exit(symbol, price, reason)
                if trade:
                    exits.append({"symbol": symbol, "reason": reason, "price": price})
                    logger.info("[ExitMonitor] %s exited at ₹%.2f — %s", symbol, price, reason)
        return exits

    def _check_exit(self, rule: dict, price: float) -> Optional[str]:
        if price <= rule["stop_loss_price"]:
            return "stop_loss"
        if price >= rule["target_1_price"]:
            return "target_hit"
        if rule["max_exit_date"]:
            max_date = date.fromisoformat(str(rule["max_exit_date"]))
            if date.today() >= max_date:
                return "max_holding_days"
        return None

    def _load_open_rules(self) -> list[dict]:
        rows = self.db.execute(
            text("""
                SELECT er.id, er.symbol, er.stop_loss_price,
                       er.target_1_price, er.max_exit_date
                FROM exit_rules er
                JOIN portfolio_holdings ph
                    ON er.symbol = ph.symbol AND ph.is_active = 1
            """)
        ).fetchall()
        return [dict(r._mapping) for r in rows]
```

- [ ] **Step 4: Run tests**

```
cd /c/DLP_Repos/MyRepo/StockV2/backend && python -m pytest tests/test_exit_monitor.py -v
```
Expected: 4 passed

- [ ] **Step 5: Commit**

```
git -C /c/DLP_Repos/MyRepo/StockV2 add backend/domains/portfolio/exit_monitor.py backend/tests/test_exit_monitor.py
git -C /c/DLP_Repos/MyRepo/StockV2 commit -m "feat: ExitMonitor — stop loss, target, and max-holding-days exit triggers"
```

---

### Task 4: PortfolioService

**Files:**
- Create: `backend/domains/portfolio/service.py`
- Create: `backend/tests/test_portfolio_service.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_portfolio_service.py
import json
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

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

    # Active holding
    session.execute(text("""
        INSERT INTO portfolio_holdings
            (symbol, quantity, avg_buy_price, first_buy_date, last_buy_date, is_active)
        VALUES ('TCS', 100, 1000.0, date('now'), date('now'), 1)
    """))
    session.execute(text("""
        INSERT INTO exit_rules
            (order_id, symbol, entry_price, stop_loss_price,
             target_1_price, target_2_price, partial_exit_at_t1)
        VALUES (1, 'TCS', 1000.0, 930.0, 1150.0, 1200.0, 0)
    """))
    # BUY trade
    session.execute(text("""
        INSERT INTO trades
            (symbol, trade_type, quantity, price, total_value, brokerage, mode, trade_date)
        VALUES ('TCS', 'BUY', 100, 1000.0, 100000.0, 0, 'paper', datetime('now'))
    """))
    # SELL trade with P&L in notes
    pnl_notes = json.dumps({"reason": "target_hit", "buy_avg": 1000.0, "pnl": 15000.0, "pnl_pct": 15.0})
    session.execute(text("""
        INSERT INTO trades
            (symbol, trade_type, quantity, price, total_value, brokerage, mode, notes, trade_date)
        VALUES ('INFY', 'SELL', 100, 1150.0, 115000.0, 0, 'paper', :notes, datetime('now'))
    """), {"notes": pnl_notes})
    session.commit()
    yield session
    session.close()


def test_get_holdings_returns_active_position(db):
    from domains.portfolio.service import PortfolioService
    holdings = PortfolioService(db).get_holdings()
    assert any(h["symbol"] == "TCS" for h in holdings)


def test_get_holdings_includes_exit_rule_data(db):
    from domains.portfolio.service import PortfolioService
    holdings = PortfolioService(db).get_holdings()
    tcs = next(h for h in holdings if h["symbol"] == "TCS")
    assert tcs["stop_loss_price"] == 930.0
    assert tcs["target_1_price"] == 1150.0


def test_get_portfolio_summary_structure(db):
    from domains.portfolio.service import PortfolioService
    summary = PortfolioService(db).get_portfolio_summary()
    assert "paper_capital" in summary
    assert "cash_available" in summary
    assert "open_positions" in summary
    assert summary["open_positions"] >= 1
    assert summary["cash_available"] < summary["paper_capital"]


def test_get_trade_history_returns_all_paper_trades(db):
    from domains.portfolio.service import PortfolioService
    trades = PortfolioService(db).get_trade_history()
    assert len(trades) >= 2


def test_get_closed_pnl_parses_notes(db):
    from domains.portfolio.service import PortfolioService
    result = PortfolioService(db).get_closed_pnl()
    assert result["total_pnl"] == 15000.0
    assert len(result["closed_trades"]) >= 1
    assert result["closed_trades"][0]["pnl"] == 15000.0
```

- [ ] **Step 2: Run to confirm failures**

```
cd /c/DLP_Repos/MyRepo/StockV2/backend && python -m pytest tests/test_portfolio_service.py -v 2>&1 | head -10
```

- [ ] **Step 3: Create `backend/domains/portfolio/service.py`**

```python
import json
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from settings import settings


class PortfolioService:
    def __init__(self, db: Session):
        self.db = db

    def get_holdings(self) -> list[dict]:
        rows = self.db.execute(
            text("""
                SELECT ph.id, ph.symbol, ph.quantity, ph.avg_buy_price,
                       ph.first_buy_date, ph.last_buy_date,
                       ROUND(ph.quantity * ph.avg_buy_price, 2) AS invested_value,
                       er.stop_loss_price, er.target_1_price, er.max_exit_date
                FROM portfolio_holdings ph
                LEFT JOIN exit_rules er ON er.symbol = ph.symbol
                WHERE ph.is_active = 1
                ORDER BY ph.symbol
            """)
        ).fetchall()
        return [dict(r._mapping) for r in rows]

    def get_portfolio_summary(self) -> dict:
        holdings = self.get_holdings()
        total_invested = sum(h["invested_value"] or 0 for h in holdings)
        return {
            "paper_capital": settings.paper_capital,
            "total_invested": round(total_invested, 2),
            "cash_available": round(settings.paper_capital - total_invested, 2),
            "open_positions": len(holdings),
            "max_positions": settings.max_open_positions,
        }

    def get_trade_history(self, symbol: Optional[str] = None, limit: int = 50) -> list[dict]:
        q = "SELECT * FROM trades WHERE mode='paper'"
        params: dict = {}
        if symbol:
            q += " AND symbol=:sym"
            params["sym"] = symbol.upper()
        q += " ORDER BY trade_date DESC LIMIT :lim"
        params["lim"] = limit
        rows = self.db.execute(text(q), params).fetchall()
        return [dict(r._mapping) for r in rows]

    def get_closed_pnl(self) -> dict:
        rows = self.db.execute(
            text("SELECT * FROM trades WHERE trade_type='SELL' AND mode='paper' "
                 "ORDER BY trade_date DESC")
        ).fetchall()
        total_pnl = 0.0
        closed_trades = []
        for r in rows:
            row = dict(r._mapping)
            if row.get("notes"):
                try:
                    meta = json.loads(row["notes"])
                    row["pnl"] = meta.get("pnl", 0.0)
                    row["pnl_pct"] = meta.get("pnl_pct", 0.0)
                    row["buy_avg"] = meta.get("buy_avg")
                    total_pnl += meta.get("pnl", 0.0)
                except (json.JSONDecodeError, TypeError):
                    pass
            closed_trades.append(row)
        return {"total_pnl": round(total_pnl, 2), "closed_trades": closed_trades}
```

- [ ] **Step 4: Run tests**

```
cd /c/DLP_Repos/MyRepo/StockV2/backend && python -m pytest tests/test_portfolio_service.py -v
```
Expected: 5 passed

- [ ] **Step 5: Commit**

```
git -C /c/DLP_Repos/MyRepo/StockV2 add backend/domains/portfolio/service.py backend/tests/test_portfolio_service.py
git -C /c/DLP_Repos/MyRepo/StockV2 commit -m "feat: PortfolioService — holdings, summary, trade history, closed P&L"
```

---

### Task 5: Watchlist Service

**Files:**
- Create: `backend/domains/portfolio/watchlist_service.py`
- Test: append to a new `backend/tests/test_portfolio_router.py` (in next task), but write unit tests here first in `backend/tests/test_portfolio_service.py` (append)

- [ ] **Step 1: Append watchlist tests to `backend/tests/test_portfolio_service.py`**

Read the existing file first, then append:

```python
# Append to backend/tests/test_portfolio_service.py

@pytest.fixture(scope="module")
def wl_db():
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    Session = sessionmaker(bind=eng)
    session = Session()
    yield session
    session.close()


def test_watchlist_add_and_get(wl_db):
    from domains.portfolio.watchlist_service import WatchlistService
    svc = WatchlistService(wl_db)
    item = svc.add("TCS", reason="RSI oversold")
    assert item["symbol"] == "TCS"
    items = svc.get_all()
    assert any(i["symbol"] == "TCS" for i in items)


def test_watchlist_add_is_idempotent(wl_db):
    from domains.portfolio.watchlist_service import WatchlistService
    svc = WatchlistService(wl_db)
    svc.add("TCS")
    svc.add("TCS")  # duplicate
    items = svc.get_all()
    assert sum(1 for i in items if i["symbol"] == "TCS") == 1


def test_watchlist_remove(wl_db):
    from domains.portfolio.watchlist_service import WatchlistService
    svc = WatchlistService(wl_db)
    svc.add("INFY")
    removed = svc.remove("INFY")
    assert removed is True
    assert not any(i["symbol"] == "INFY" for i in svc.get_all())


def test_watchlist_remove_missing_returns_false(wl_db):
    from domains.portfolio.watchlist_service import WatchlistService
    result = WatchlistService(wl_db).remove("NONEXISTENT")
    assert result is False
```

- [ ] **Step 2: Create `backend/domains/portfolio/watchlist_service.py`**

```python
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session


class WatchlistService:
    def __init__(self, db: Session):
        self.db = db

    def get_all(self) -> list[dict]:
        rows = self.db.execute(
            text("SELECT * FROM watchlist ORDER BY added_at DESC")
        ).fetchall()
        return [dict(r._mapping) for r in rows]

    def add(self, symbol: str, reason: Optional[str] = None) -> dict:
        self.db.execute(
            text("INSERT OR IGNORE INTO watchlist (symbol, reason, added_at) "
                 "VALUES (:sym, :reason, datetime('now'))"),
            {"sym": symbol.upper(), "reason": reason},
        )
        self.db.commit()
        row = self.db.execute(
            text("SELECT * FROM watchlist WHERE symbol=:s"),
            {"s": symbol.upper()},
        ).fetchone()
        return dict(row._mapping)

    def remove(self, symbol: str) -> bool:
        result = self.db.execute(
            text("DELETE FROM watchlist WHERE symbol=:s"),
            {"s": symbol.upper()},
        )
        self.db.commit()
        return result.rowcount > 0
```

- [ ] **Step 3: Run watchlist tests**

```
cd /c/DLP_Repos/MyRepo/StockV2/backend && python -m pytest tests/test_portfolio_service.py -v -k "watchlist"
```
Expected: 4 passed

- [ ] **Step 4: Commit**

```
git -C /c/DLP_Repos/MyRepo/StockV2 add backend/domains/portfolio/watchlist_service.py backend/tests/test_portfolio_service.py
git -C /c/DLP_Repos/MyRepo/StockV2 commit -m "feat: WatchlistService — add/remove/list watched symbols"
```

---

### Task 6: Portfolio REST API + main.py Wiring

**Files:**
- Create: `backend/domains/portfolio/router.py`
- Modify: `backend/main.py`
- Create: `backend/tests/test_portfolio_router.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_portfolio_router.py
import json
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

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
    # Seed strategy + stock + BUY signal
    db.execute(text(
        "INSERT INTO strategies (name, type, description, is_active, created_at) "
        "VALUES ('RSI', 'technical', '', 1, datetime('now'))"
    ))
    db.execute(text(
        "INSERT INTO stocks (symbol, name, exchange, is_active, added_at) "
        "VALUES ('INFY', 'Infosys', 'NSE', 1, datetime('now'))"
    ))
    db.execute(text("""
        INSERT INTO strategy_signals
            (symbol, strategy_id, signal_date, signal_type, price_at_signal,
             confidence_score, suggested_stop_loss, suggested_target,
             holding_period_days, created_at)
        VALUES ('INFY', 1, date('now'), 'BUY', 1500.0, 0.78, 1395.0, 1725.0, 15, datetime('now'))
    """))
    # Seed holding for exit test
    db.execute(text("""
        INSERT INTO portfolio_holdings
            (symbol, quantity, avg_buy_price, first_buy_date, last_buy_date, is_active)
        VALUES ('WIPRO', 50, 400.0, date('now'), date('now'), 1)
    """))
    pnl_notes = json.dumps({"reason": "target_hit", "buy_avg": 400.0, "pnl": 2500.0, "pnl_pct": 12.5})
    db.execute(text("""
        INSERT INTO trades
            (symbol, trade_type, quantity, price, total_value, brokerage, mode, notes, trade_date)
        VALUES ('TCS', 'SELL', 100, 1150.0, 115000.0, 0, 'paper', :notes, datetime('now'))
    """), {"notes": pnl_notes})
    db.commit()
    db.close()

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    from main import app
    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app, headers={"X-API-Key": settings.api_key})


def test_get_portfolio_summary(client):
    r = client.get("/api/v1/portfolio/summary")
    assert r.status_code == 200
    data = r.json()
    assert "paper_capital" in data
    assert "cash_available" in data
    assert "open_positions" in data


def test_get_portfolio_holdings(client):
    r = client.get("/api/v1/portfolio/holdings")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_get_portfolio_trades(client):
    r = client.get("/api/v1/portfolio/trades")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_get_portfolio_pnl(client):
    r = client.get("/api/v1/portfolio/pnl")
    assert r.status_code == 200
    data = r.json()
    assert "total_pnl" in data
    assert data["total_pnl"] == 2500.0


def test_paper_enter_from_signal(client):
    r = client.post("/api/v1/portfolio/enter/1", json={"price": 1500.0})
    assert r.status_code == 200
    data = r.json()
    assert data["trade_type"] == "BUY"
    assert data["symbol"] == "INFY"


def test_paper_exit_symbol(client):
    r = client.post("/api/v1/portfolio/exit/WIPRO", json={"price": 450.0, "reason": "manual"})
    assert r.status_code == 200
    assert r.json()["trade_type"] == "SELL"


def test_paper_exit_missing_holding(client):
    r = client.post("/api/v1/portfolio/exit/NONSTOCK", json={"price": 100.0})
    assert r.status_code == 404


def test_get_watchlist(client):
    r = client.get("/api/v1/watchlist")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_add_to_watchlist(client):
    r = client.post("/api/v1/watchlist/HDFC", json={"reason": "breakout watch"})
    assert r.status_code == 200
    assert r.json()["symbol"] == "HDFC"


def test_remove_from_watchlist(client):
    client.post("/api/v1/watchlist/AXISBANK", json={})
    r = client.delete("/api/v1/watchlist/AXISBANK")
    assert r.status_code == 200


def test_unauthorized_without_key():
    from main import app
    c = TestClient(app)
    r = c.get("/api/v1/portfolio/summary")
    assert r.status_code == 401
```

- [ ] **Step 2: Run to confirm failures**

```
cd /c/DLP_Repos/MyRepo/StockV2/backend && python -m pytest tests/test_portfolio_router.py -v 2>&1 | head -15
```
Expected: 404 responses (routes not registered)

- [ ] **Step 3: Create `backend/domains/portfolio/router.py`**

```python
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from domains.portfolio.paper_trader import PaperTrader
from domains.portfolio.service import PortfolioService
from domains.portfolio.watchlist_service import WatchlistService

router = APIRouter(tags=["portfolio"])


class EnterBody(BaseModel):
    price: float


class ExitBody(BaseModel):
    price: float
    reason: str = "manual"


class WatchlistBody(BaseModel):
    reason: Optional[str] = None


@router.get("/portfolio/summary")
def portfolio_summary(db: Session = Depends(get_db)):
    return PortfolioService(db).get_portfolio_summary()


@router.get("/portfolio/holdings")
def portfolio_holdings(db: Session = Depends(get_db)):
    return PortfolioService(db).get_holdings()


@router.get("/portfolio/trades")
def portfolio_trades(
    symbol: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    return PortfolioService(db).get_trade_history(symbol=symbol, limit=limit)


@router.get("/portfolio/pnl")
def portfolio_pnl(db: Session = Depends(get_db)):
    return PortfolioService(db).get_closed_pnl()


@router.post("/portfolio/enter/{signal_id}")
def paper_enter(signal_id: int, body: EnterBody, db: Session = Depends(get_db)):
    trade = PaperTrader(db).enter(signal_id, body.price)
    if trade is None:
        raise HTTPException(
            status_code=400,
            detail="Entry rejected — check signal validity and position limits",
        )
    return trade


@router.post("/portfolio/exit/{symbol}")
def paper_exit(symbol: str, body: ExitBody, db: Session = Depends(get_db)):
    trade = PaperTrader(db).exit(symbol.upper(), body.price, body.reason)
    if trade is None:
        raise HTTPException(status_code=404, detail=f"No active position for {symbol}")
    return trade


@router.get("/watchlist")
def watchlist_list(db: Session = Depends(get_db)):
    return WatchlistService(db).get_all()


@router.post("/watchlist/{symbol}")
def watchlist_add(symbol: str, body: WatchlistBody, db: Session = Depends(get_db)):
    return WatchlistService(db).add(symbol.upper(), body.reason)


@router.delete("/watchlist/{symbol}")
def watchlist_remove(symbol: str, db: Session = Depends(get_db)):
    removed = WatchlistService(db).remove(symbol.upper())
    if not removed:
        raise HTTPException(status_code=404, detail=f"{symbol} not in watchlist")
    return {"removed": symbol.upper()}
```

- [ ] **Step 4: Read `backend/main.py` then add the portfolio router**

Add after the AI router line:
```python
from domains.portfolio.router import router as portfolio_router  # noqa: E402
app.include_router(portfolio_router, prefix="/api/v1", dependencies=[Depends(verify_api_key)])
```

- [ ] **Step 5: Run portfolio router tests**

```
cd /c/DLP_Repos/MyRepo/StockV2/backend && python -m pytest tests/test_portfolio_router.py -v
```
Expected: 12 passed

- [ ] **Step 6: Run full test suite**

```
cd /c/DLP_Repos/MyRepo/StockV2/backend && python -m pytest -v 2>&1 | tail -10
```
Expected: all pass (131 existing + new tests)

- [ ] **Step 7: Commit**

```
git -C /c/DLP_Repos/MyRepo/StockV2 add backend/domains/portfolio/router.py backend/main.py backend/tests/test_portfolio_router.py
git -C /c/DLP_Repos/MyRepo/StockV2 commit -m "feat: portfolio REST API — holdings, trades, P&L, enter/exit, watchlist"
```

---

### Task 7: APScheduler Exit Monitor Wiring

**Files:**
- Modify: `backend/scheduler.py`

No new test file — the existing scheduler tests verify the job list. ExitMonitor logic is tested separately.

- [ ] **Step 1: Run existing scheduler tests to confirm baseline**

```
cd /c/DLP_Repos/MyRepo/StockV2/backend && python -m pytest tests/test_scheduler.py -v
```
Expected: 2 passed

- [ ] **Step 2: Read `backend/scheduler.py` to see current `_intraday_scan`**

- [ ] **Step 3: Replace `_intraday_scan` body in `backend/scheduler.py`**

The new body fetches last daily close prices for open positions and runs ExitMonitor:

```python
def _intraday_scan():
    from datetime import date
    from database import SessionLocal
    from domains.strategies.engine import StrategyEngine
    from domains.data.nse_universe import NSE_SYMBOLS
    from sqlalchemy import text
    if not _is_market_hours():
        return
    db = SessionLocal()
    try:
        # Strategy scan
        engine = StrategyEngine(db)
        results = engine.scan_all(NSE_SYMBOLS, date.today())
        logger.info("[scheduler] intraday_scan: %d signals", len(results))

        # Exit monitor: get open positions and their last known close prices
        open_rows = db.execute(
            text("SELECT ph.symbol FROM portfolio_holdings ph WHERE ph.is_active=1")
        ).fetchall()
        open_symbols = [r[0] for r in open_rows]
        if open_symbols:
            placeholders = ",".join(f"'{s}'" for s in open_symbols)
            price_rows = db.execute(
                text(f"""
                    SELECT symbol, close FROM stock_prices_daily
                    WHERE (symbol, date) IN (
                        SELECT symbol, MAX(date) FROM stock_prices_daily
                        WHERE symbol IN ({placeholders})
                        GROUP BY symbol
                    )
                """)
            ).fetchall()
            current_prices = {r[0]: r[1] for r in price_rows}
            if current_prices:
                from domains.portfolio.exit_monitor import ExitMonitor
                exits = ExitMonitor(db).scan_exits(current_prices)
                if exits:
                    logger.info("[scheduler] intraday_scan: %d positions exited", len(exits))
    except Exception:
        logger.exception("[scheduler] intraday_scan failed")
    finally:
        db.close()
```

- [ ] **Step 4: Verify scheduler tests still pass**

```
cd /c/DLP_Repos/MyRepo/StockV2/backend && python -m pytest tests/test_scheduler.py -v
```
Expected: 2 passed

- [ ] **Step 5: Run full test suite**

```
cd /c/DLP_Repos/MyRepo/StockV2/backend && python -m pytest -v 2>&1 | tail -10
```
Expected: all tests pass

- [ ] **Step 6: Smoke test — verify server starts**

```
cd /c/DLP_Repos/MyRepo/StockV2/backend && timeout 8 python -m uvicorn main:app --port 8002 2>&1 | head -20
```
Expected: `Database tables verified`, `10 strategies seeded`, `APScheduler started`

- [ ] **Step 7: Commit and tag**

```
git -C /c/DLP_Repos/MyRepo/StockV2 add backend/scheduler.py
git -C /c/DLP_Repos/MyRepo/StockV2 commit -m "feat: wire ExitMonitor into intraday scan — auto-exit on stop loss and target"
git -C /c/DLP_Repos/MyRepo/StockV2 tag plan3-portfolio-paper-trading
```

---

## Summary

After all 7 tasks:

| Component | Files | Tests |
|---|---|---|
| PositionSizer | `position_sizer.py` | 5 |
| PaperTrader (enter + exit) | `paper_trader.py` | 6 |
| ExitMonitor | `exit_monitor.py` | 4 |
| PortfolioService + WatchlistService | `service.py`, `watchlist_service.py` | 9 |
| REST API | `router.py` | 12 |
| APScheduler wiring | `scheduler.py` | — |

**End-to-end flow after Plan 3:**
Strategy scan produces BUY signals → `POST /portfolio/enter/{signal_id}` (or manual trigger) → `PaperTrader.enter()` sizes position + records trade + creates exit rule. Every 15 min during market hours → `_intraday_scan` → `ExitMonitor.scan_exits()` checks stop loss / target / max holding days → auto-exits triggered positions. `GET /portfolio/summary` shows live portfolio state. `GET /portfolio/pnl` shows closed trade P&L.
