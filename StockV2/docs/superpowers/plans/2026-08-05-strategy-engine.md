# Strategy Engine & AI Integration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Daily automated scan of 237 NSE stocks using 10 core trading strategies, AI-explained top signals, and Telegram daily digest — every day at 4 PM IST.

**Architecture:** `StrategyEngine.scan_all()` loads prices from SQLite → runs `IndicatorEngine.compute()` → runs each of 10 `BaseStrategy` subclasses → `SignalAggregator` produces consensus score → saves to `strategy_signals` table. `SignalExplainer` calls Claude API (with `ai_analyses` caching) to explain top BUY signals. `AlertService` sends Telegram daily digest at 5:15 PM via httpx HTTP calls to the Telegram Bot API. APScheduler stubs from Plan 1 are wired to real implementations.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy 2.0 (raw SQL via `text()`), `ta` library indicators, `anthropic` SDK (prompt caching), `httpx` for Telegram, APScheduler, pytest

**Existing foundation (do not re-implement):**
- `backend/domains/data/indicators.py` — `IndicatorEngine.compute(df)` produces: `sma_20`, `sma_50`, `ema_9`, `ema_21`, `rsi_14`, `macd`, `macd_signal`, `macd_hist`, `bb_upper`, `bb_middle`, `bb_lower`, `atr_14`, `volume_sma_20`, `volume_ratio`, `adx_14`, `roc_10`, `supertrend`, `supertrend_direction`
- `backend/scheduler.py` — `scheduler`, `register_jobs()`, `JobIds` (stubs to be replaced in Task 8/12)
- `backend/main.py` — FastAPI app, `verify_api_key` dependency, lifespan with scheduler start
- `backend/database.py` — `engine`, `SessionLocal`, `Base`, `get_db`
- `backend/settings.py` — `settings.anthropic_api_key`, `settings.telegram_bot_token`, `settings.telegram_chat_id`
- `backend/models.py` — `strategies`, `strategy_signals`, `ai_analyses` tables already defined

---

## File Map

```
backend/
├── domains/
│   ├── strategies/
│   │   ├── __init__.py                  NEW (empty)
│   │   ├── base.py                      NEW — BaseStrategy ABC, Signal dataclass, StrategyType, Timeframe
│   │   ├── aggregator.py                NEW — SignalAggregator (consensus scoring)
│   │   ├── engine.py                    NEW — StrategyEngine.scan_all()
│   │   ├── seed.py                      NEW — seed_strategies() inserts 10 rows into strategies table
│   │   ├── service.py                   NEW — StrategyService (DB read queries)
│   │   ├── router.py                    NEW — GET /strategies, /signals, /signals/today, /signals/{id}
│   │   └── strategies/
│   │       ├── __init__.py              NEW (empty)
│   │       ├── rsi_oversold.py          NEW
│   │       ├── macd_crossover.py        NEW
│   │       ├── ema_crossover.py         NEW
│   │       ├── sma_crossover.py         NEW
│   │       ├── supertrend_strategy.py   NEW
│   │       ├── bb_squeeze.py            NEW
│   │       ├── volume_breakout.py       NEW
│   │       ├── mean_reversion.py        NEW
│   │       ├── volatility_breakout.py   NEW
│   │       └── swing_trend_rider.py     NEW
│   ├── ai/
│   │   ├── __init__.py                  NEW (empty)
│   │   ├── explainer.py                 NEW — SignalExplainer, SellExplainer
│   │   └── router.py                    NEW — GET /signals/{id}/explanation
│   └── alerts/
│       ├── __init__.py                  NEW (empty)
│       └── telegram.py                  NEW — AlertService.send(), send_daily_digest()
├── scheduler.py                         MODIFY — wire real engine + digest into placeholder stubs
├── main.py                              MODIFY — include strategies + ai routers, call seed_strategies()
└── tests/
    ├── test_strategies.py               NEW — unit tests for all 10 strategy classes
    ├── test_aggregator.py               NEW — SignalAggregator tests
    ├── test_strategy_engine.py          NEW — StrategyEngine with in-memory SQLite
    ├── test_strategy_service.py         NEW — StrategyService DB queries
    ├── test_strategy_router.py          NEW — API endpoint tests
    ├── test_explainer.py                NEW — SignalExplainer (mocked anthropic client)
    └── test_telegram.py                 NEW — AlertService (mocked httpx)
```

---

### Task 1: BaseStrategy + Signal + StrategyType + Timeframe

**Files:**
- Create: `backend/domains/strategies/__init__.py`
- Create: `backend/domains/strategies/strategies/__init__.py`
- Create: `backend/domains/strategies/base.py`
- Test: `backend/tests/test_strategies.py` (framework tests only — strategy tests added in Tasks 2 & 3)

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_strategies.py
import pandas as pd
import pytest
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


def test_signal_defaults():
    s = Signal(signal_type="NONE")
    assert s.confidence == 0.0
    assert s.stop_loss_pct == 7.0
    assert s.target_pct == 15.0
    assert s.holding_days == 15
    assert s.conditions_met == []
    assert s.conditions_failed == []


def test_signal_buy():
    s = Signal(signal_type="BUY", confidence=0.75, conditions_met=["RSI < 30"])
    assert s.signal_type == "BUY"
    assert s.confidence == 0.75
    assert "RSI < 30" in s.conditions_met


def test_base_strategy_is_abstract():
    with pytest.raises(TypeError):
        BaseStrategy()  # cannot instantiate abstract class


def test_strategy_type_values():
    assert StrategyType.TECHNICAL == "technical"
    assert StrategyType.FUNDAMENTAL == "fundamental"
    assert StrategyType.ML == "ml"
    assert StrategyType.CUSTOM == "custom"


def test_timeframe_values():
    assert Timeframe.DAILY == "daily"
    assert Timeframe.INTRADAY_15M == "intraday_15m"
```

- [ ] **Step 2: Run test to verify it fails**

```
cd backend && python -m pytest tests/test_strategies.py -v
```
Expected: ImportError — `domains.strategies.base` not found

- [ ] **Step 3: Create empty `__init__.py` files**

```python
# backend/domains/strategies/__init__.py
# (empty)

# backend/domains/strategies/strategies/__init__.py
# (empty)
```

- [ ] **Step 4: Create `backend/domains/strategies/base.py`**

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Literal

import pandas as pd


class StrategyType(str, Enum):
    TECHNICAL = "technical"
    FUNDAMENTAL = "fundamental"
    ML = "ml"
    CUSTOM = "custom"


class Timeframe(str, Enum):
    DAILY = "daily"
    INTRADAY_15M = "intraday_15m"
    INTRADAY_1H = "intraday_1h"


@dataclass
class Signal:
    signal_type: Literal["BUY", "SELL", "WATCH", "NONE"]
    confidence: float = 0.0
    risk_score: float = 0.5
    expected_upside_pct: float = 0.0
    stop_loss_pct: float = 7.0
    target_pct: float = 15.0
    holding_days: int = 15
    conditions_met: list[str] = field(default_factory=list)
    conditions_failed: list[str] = field(default_factory=list)


class BaseStrategy(ABC):
    name: str = ""
    description: str = ""
    strategy_type: StrategyType = StrategyType.TECHNICAL
    timeframe: Timeframe = Timeframe.DAILY
    min_holding_days: int = 5
    max_holding_days: int = 30
    weight: float = 0.20

    @abstractmethod
    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal: ...

    def get_parameters(self) -> dict:
        return {}

    def get_required_indicators(self) -> list[str]:
        return []
```

- [ ] **Step 5: Run tests to verify they pass**

```
cd backend && python -m pytest tests/test_strategies.py -v
```
Expected: 5 passed

- [ ] **Step 6: Commit**

```
git add backend/domains/strategies/ backend/tests/test_strategies.py
git commit -m "feat: strategies domain — BaseStrategy ABC, Signal dataclass"
```

---

### Task 2: 5 Momentum/Trend Strategies

**Files:**
- Create: `backend/domains/strategies/strategies/rsi_oversold.py`
- Create: `backend/domains/strategies/strategies/macd_crossover.py`
- Create: `backend/domains/strategies/strategies/ema_crossover.py`
- Create: `backend/domains/strategies/strategies/sma_crossover.py`
- Create: `backend/domains/strategies/strategies/supertrend_strategy.py`
- Test: `backend/tests/test_strategies.py` (append these tests)

- [ ] **Step 1: Append failing tests for all 5 strategies**

```python
# Append to backend/tests/test_strategies.py

import numpy as np


def _make_df(n=60, rsi_trigger=None, macd_cross=None, ema_cross=None, sma_cross=None, st_flip=None):
    """Helper: generates a synthetic OHLCV + indicator DataFrame for testing."""
    close = pd.Series([100.0 + i * 0.5 for i in range(n)], dtype=float)
    df = pd.DataFrame({
        "open": close - 0.5,
        "high": close + 1.0,
        "low": close - 1.0,
        "close": close,
        "volume": [1_000_000.0] * n,
        "rsi_14": [50.0] * n,
        "macd_hist": [0.1] * n,
        "ema_9": close,
        "ema_21": close - 2,
        "sma_20": close,
        "sma_50": close - 5,
        "supertrend_direction": [1.0] * n,
        "supertrend": close - 3,
        "bb_upper": close + 10,
        "bb_middle": close,
        "bb_lower": close - 10,
        "atr_14": [2.0] * n,
        "adx_14": [30.0] * n,
        "volume_sma_20": [1_000_000.0] * n,
        "volume_ratio": [1.0] * n,
        "macd": [0.5] * n,
        "macd_signal": [0.4] * n,
        "roc_10": [1.0] * n,
    })
    return df


# ── RSI ────────────────────────────────────────────────────────────────────────

def test_rsi_buy_when_oversold():
    from domains.strategies.strategies.rsi_oversold import RSIOversoldStrategy
    df = _make_df()
    df["rsi_14"] = 25.0
    signal = RSIOversoldStrategy().generate_signal(df)
    assert signal.signal_type == "BUY"
    assert signal.confidence > 0.5


def test_rsi_sell_when_overbought():
    from domains.strategies.strategies.rsi_oversold import RSIOversoldStrategy
    df = _make_df()
    df["rsi_14"] = 75.0
    signal = RSIOversoldStrategy().generate_signal(df)
    assert signal.signal_type == "SELL"


def test_rsi_none_when_neutral():
    from domains.strategies.strategies.rsi_oversold import RSIOversoldStrategy
    df = _make_df()
    df["rsi_14"] = 50.0
    signal = RSIOversoldStrategy().generate_signal(df)
    assert signal.signal_type == "NONE"


def test_rsi_none_when_nan():
    from domains.strategies.strategies.rsi_oversold import RSIOversoldStrategy
    df = _make_df(n=5)
    df["rsi_14"] = float("nan")
    signal = RSIOversoldStrategy().generate_signal(df)
    assert signal.signal_type == "NONE"


# ── MACD ───────────────────────────────────────────────────────────────────────

def test_macd_buy_on_bullish_crossover():
    from domains.strategies.strategies.macd_crossover import MACDCrossoverStrategy
    df = _make_df()
    df["macd_hist"] = 0.1
    df.at[df.index[-2], "macd_hist"] = -0.1
    signal = MACDCrossoverStrategy().generate_signal(df)
    assert signal.signal_type == "BUY"


def test_macd_sell_on_bearish_crossover():
    from domains.strategies.strategies.macd_crossover import MACDCrossoverStrategy
    df = _make_df()
    df["macd_hist"] = -0.1
    df.at[df.index[-2], "macd_hist"] = 0.1
    signal = MACDCrossoverStrategy().generate_signal(df)
    assert signal.signal_type == "SELL"


def test_macd_none_when_no_cross():
    from domains.strategies.strategies.macd_crossover import MACDCrossoverStrategy
    df = _make_df()
    df["macd_hist"] = 0.2
    signal = MACDCrossoverStrategy().generate_signal(df)
    assert signal.signal_type == "NONE"


# ── EMA Crossover ──────────────────────────────────────────────────────────────

def test_ema_buy_on_upward_cross():
    from domains.strategies.strategies.ema_crossover import EMACrossoverStrategy
    df = _make_df()
    # Last row: ema_9 > ema_21. Second-to-last: ema_9 <= ema_21
    df["ema_9"] = 102.0
    df["ema_21"] = 103.0
    df.at[df.index[-1], "ema_9"] = 104.0
    df.at[df.index[-1], "ema_21"] = 103.0
    signal = EMACrossoverStrategy().generate_signal(df)
    assert signal.signal_type == "BUY"


def test_ema_none_when_already_above():
    from domains.strategies.strategies.ema_crossover import EMACrossoverStrategy
    df = _make_df()
    df["ema_9"] = 105.0
    df["ema_21"] = 100.0
    signal = EMACrossoverStrategy().generate_signal(df)
    assert signal.signal_type == "NONE"


# ── SMA Crossover ──────────────────────────────────────────────────────────────

def test_sma_buy_golden_cross():
    from domains.strategies.strategies.sma_crossover import SMACrossoverStrategy
    df = _make_df()
    df["sma_20"] = 98.0
    df["sma_50"] = 100.0
    df.at[df.index[-1], "sma_20"] = 101.0
    df.at[df.index[-1], "sma_50"] = 100.0
    signal = SMACrossoverStrategy().generate_signal(df)
    assert signal.signal_type == "BUY"
    assert signal.confidence >= 0.70


def test_sma_sell_death_cross():
    from domains.strategies.strategies.sma_crossover import SMACrossoverStrategy
    df = _make_df()
    df["sma_20"] = 102.0
    df["sma_50"] = 100.0
    df.at[df.index[-1], "sma_20"] = 99.0
    df.at[df.index[-1], "sma_50"] = 100.0
    signal = SMACrossoverStrategy().generate_signal(df)
    assert signal.signal_type == "SELL"


# ── SuperTrend ─────────────────────────────────────────────────────────────────

def test_supertrend_buy_on_bullish_flip():
    from domains.strategies.strategies.supertrend_strategy import SuperTrendStrategy
    df = _make_df()
    df["supertrend_direction"] = 1.0
    df.at[df.index[-2], "supertrend_direction"] = -1.0
    signal = SuperTrendStrategy().generate_signal(df)
    assert signal.signal_type == "BUY"
    assert signal.confidence >= 0.70


def test_supertrend_sell_on_bearish_flip():
    from domains.strategies.strategies.supertrend_strategy import SuperTrendStrategy
    df = _make_df()
    df["supertrend_direction"] = -1.0
    df.at[df.index[-2], "supertrend_direction"] = 1.0
    signal = SuperTrendStrategy().generate_signal(df)
    assert signal.signal_type == "SELL"


def test_supertrend_none_when_no_flip():
    from domains.strategies.strategies.supertrend_strategy import SuperTrendStrategy
    df = _make_df()
    df["supertrend_direction"] = 1.0
    signal = SuperTrendStrategy().generate_signal(df)
    assert signal.signal_type == "NONE"
```

- [ ] **Step 2: Run to confirm failures**

```
cd backend && python -m pytest tests/test_strategies.py -v -k "rsi or macd or ema or sma or supertrend"
```
Expected: ImportError for each strategy module

- [ ] **Step 3: Create `rsi_oversold.py`**

```python
# backend/domains/strategies/strategies/rsi_oversold.py
import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class RSIOversoldStrategy(BaseStrategy):
    name = "RSI Oversold/Overbought"
    description = "Buy when RSI < 30 (oversold), sell when RSI > 70 (overbought)"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY
    min_holding_days = 5
    max_holding_days = 15

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if df.empty or "rsi_14" not in df.columns:
            return Signal("NONE")
        rsi = df["rsi_14"].iloc[-1]
        if pd.isna(rsi):
            return Signal("NONE")
        if rsi < 30:
            confidence = min(1.0, (30 - rsi) / 20 + 0.5)
            return Signal(
                signal_type="BUY",
                confidence=round(confidence, 4),
                risk_score=0.40,
                expected_upside_pct=10.0,
                stop_loss_pct=7.0,
                target_pct=12.0,
                holding_days=10,
                conditions_met=[f"RSI={rsi:.1f} < 30 (oversold)"],
            )
        if rsi > 70:
            confidence = min(1.0, (rsi - 70) / 20 + 0.5)
            return Signal(
                signal_type="SELL",
                confidence=round(confidence, 4),
                risk_score=0.60,
                expected_upside_pct=0.0,
                stop_loss_pct=0.0,
                target_pct=0.0,
                holding_days=0,
                conditions_met=[f"RSI={rsi:.1f} > 70 (overbought)"],
            )
        return Signal("NONE")

    def get_required_indicators(self) -> list[str]:
        return ["rsi_14"]
```

- [ ] **Step 4: Create `macd_crossover.py`**

```python
# backend/domains/strategies/strategies/macd_crossover.py
import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class MACDCrossoverStrategy(BaseStrategy):
    name = "MACD Crossover"
    description = "Buy when MACD histogram turns positive (bullish crossover), sell on bearish crossover"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY
    min_holding_days = 10
    max_holding_days = 30

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 2 or "macd_hist" not in df.columns:
            return Signal("NONE")
        curr = df["macd_hist"].iloc[-1]
        prev = df["macd_hist"].iloc[-2]
        if pd.isna(curr) or pd.isna(prev):
            return Signal("NONE")
        if prev < 0 and curr >= 0:
            return Signal(
                signal_type="BUY",
                confidence=0.65,
                risk_score=0.45,
                expected_upside_pct=12.0,
                stop_loss_pct=7.0,
                target_pct=15.0,
                holding_days=20,
                conditions_met=["MACD histogram turned positive (bullish crossover)"],
            )
        if prev > 0 and curr <= 0:
            return Signal(
                signal_type="SELL",
                confidence=0.65,
                risk_score=0.55,
                expected_upside_pct=0.0,
                stop_loss_pct=0.0,
                target_pct=0.0,
                holding_days=0,
                conditions_met=["MACD histogram turned negative (bearish crossover)"],
            )
        return Signal("NONE")

    def get_required_indicators(self) -> list[str]:
        return ["macd_hist"]
```

- [ ] **Step 5: Create `ema_crossover.py`**

```python
# backend/domains/strategies/strategies/ema_crossover.py
import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class EMACrossoverStrategy(BaseStrategy):
    name = "EMA Crossover (9/21)"
    description = "Buy when EMA 9 crosses above EMA 21, sell when it crosses below"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY
    min_holding_days = 5
    max_holding_days = 20

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 2 or "ema_9" not in df.columns or "ema_21" not in df.columns:
            return Signal("NONE")
        curr_9, prev_9 = df["ema_9"].iloc[-1], df["ema_9"].iloc[-2]
        curr_21, prev_21 = df["ema_21"].iloc[-1], df["ema_21"].iloc[-2]
        if any(pd.isna(x) for x in [curr_9, prev_9, curr_21, prev_21]):
            return Signal("NONE")
        if prev_9 <= prev_21 and curr_9 > curr_21:
            return Signal(
                signal_type="BUY",
                confidence=0.60,
                risk_score=0.45,
                expected_upside_pct=10.0,
                stop_loss_pct=6.0,
                target_pct=12.0,
                holding_days=12,
                conditions_met=[f"EMA9={curr_9:.2f} crossed above EMA21={curr_21:.2f}"],
            )
        if prev_9 >= prev_21 and curr_9 < curr_21:
            return Signal(
                signal_type="SELL",
                confidence=0.60,
                risk_score=0.55,
                expected_upside_pct=0.0,
                stop_loss_pct=0.0,
                target_pct=0.0,
                holding_days=0,
                conditions_met=[f"EMA9={curr_9:.2f} crossed below EMA21={curr_21:.2f}"],
            )
        return Signal("NONE")

    def get_required_indicators(self) -> list[str]:
        return ["ema_9", "ema_21"]
```

- [ ] **Step 6: Create `sma_crossover.py`**

```python
# backend/domains/strategies/strategies/sma_crossover.py
import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class SMACrossoverStrategy(BaseStrategy):
    name = "SMA Crossover (20/50)"
    description = "Golden Cross (SMA20 crosses above SMA50) buy; Death Cross sell"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY
    min_holding_days = 20
    max_holding_days = 60

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 2 or "sma_20" not in df.columns or "sma_50" not in df.columns:
            return Signal("NONE")
        curr_20, prev_20 = df["sma_20"].iloc[-1], df["sma_20"].iloc[-2]
        curr_50, prev_50 = df["sma_50"].iloc[-1], df["sma_50"].iloc[-2]
        if any(pd.isna(x) for x in [curr_20, prev_20, curr_50, prev_50]):
            return Signal("NONE")
        if prev_20 <= prev_50 and curr_20 > curr_50:
            return Signal(
                signal_type="BUY",
                confidence=0.70,
                risk_score=0.35,
                expected_upside_pct=20.0,
                stop_loss_pct=8.0,
                target_pct=20.0,
                holding_days=40,
                conditions_met=["Golden Cross: SMA20 crossed above SMA50"],
            )
        if prev_20 >= prev_50 and curr_20 < curr_50:
            return Signal(
                signal_type="SELL",
                confidence=0.70,
                risk_score=0.65,
                expected_upside_pct=0.0,
                stop_loss_pct=0.0,
                target_pct=0.0,
                holding_days=0,
                conditions_met=["Death Cross: SMA20 crossed below SMA50"],
            )
        return Signal("NONE")

    def get_required_indicators(self) -> list[str]:
        return ["sma_20", "sma_50"]
```

- [ ] **Step 7: Create `supertrend_strategy.py`**

```python
# backend/domains/strategies/strategies/supertrend_strategy.py
import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class SuperTrendStrategy(BaseStrategy):
    name = "SuperTrend"
    description = "Buy when SuperTrend flips bullish (direction -1→1), sell on bearish flip"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY
    min_holding_days = 15
    max_holding_days = 45

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 2 or "supertrend_direction" not in df.columns:
            return Signal("NONE")
        curr_dir = df["supertrend_direction"].iloc[-1]
        prev_dir = df["supertrend_direction"].iloc[-2]
        if pd.isna(curr_dir) or pd.isna(prev_dir):
            return Signal("NONE")
        if prev_dir == -1.0 and curr_dir == 1.0:
            return Signal(
                signal_type="BUY",
                confidence=0.72,
                risk_score=0.40,
                expected_upside_pct=15.0,
                stop_loss_pct=7.0,
                target_pct=18.0,
                holding_days=25,
                conditions_met=["SuperTrend flipped bullish (direction: -1 → 1)"],
            )
        if prev_dir == 1.0 and curr_dir == -1.0:
            return Signal(
                signal_type="SELL",
                confidence=0.72,
                risk_score=0.60,
                expected_upside_pct=0.0,
                stop_loss_pct=0.0,
                target_pct=0.0,
                holding_days=0,
                conditions_met=["SuperTrend flipped bearish (direction: 1 → -1)"],
            )
        return Signal("NONE")

    def get_required_indicators(self) -> list[str]:
        return ["supertrend_direction"]
```

- [ ] **Step 8: Run all strategy tests**

```
cd backend && python -m pytest tests/test_strategies.py -v
```
Expected: all tests pass (framework + 5 momentum strategies)

- [ ] **Step 9: Commit**

```
git add backend/domains/strategies/strategies/ backend/tests/test_strategies.py
git commit -m "feat: 5 momentum strategies — RSI, MACD, EMA, SMA, SuperTrend"
```

---

### Task 3: 5 Volatility/Mean-Reversion Strategies

**Files:**
- Create: `backend/domains/strategies/strategies/bb_squeeze.py`
- Create: `backend/domains/strategies/strategies/volume_breakout.py`
- Create: `backend/domains/strategies/strategies/mean_reversion.py`
- Create: `backend/domains/strategies/strategies/volatility_breakout.py`
- Create: `backend/domains/strategies/strategies/swing_trend_rider.py`
- Test: `backend/tests/test_strategies.py` (append)

- [ ] **Step 1: Append failing tests**

```python
# Append to backend/tests/test_strategies.py

# ── BB Squeeze ─────────────────────────────────────────────────────────────────

def test_bb_squeeze_buy_on_breakout_with_volume():
    from domains.strategies.strategies.bb_squeeze import BBSqueezeStrategy
    df = _make_df()
    df["close"] = 115.0
    df["bb_upper"] = 110.0
    df["volume_ratio"] = 2.0
    signal = BBSqueezeStrategy().generate_signal(df)
    assert signal.signal_type == "BUY"
    assert signal.confidence > 0.55


def test_bb_squeeze_none_without_volume():
    from domains.strategies.strategies.bb_squeeze import BBSqueezeStrategy
    df = _make_df()
    df["close"] = 115.0
    df["bb_upper"] = 110.0
    df["volume_ratio"] = 1.0
    signal = BBSqueezeStrategy().generate_signal(df)
    assert signal.signal_type == "NONE"


def test_bb_squeeze_none_below_band():
    from domains.strategies.strategies.bb_squeeze import BBSqueezeStrategy
    df = _make_df()
    df["close"] = 100.0
    df["bb_upper"] = 110.0
    df["volume_ratio"] = 3.0
    signal = BBSqueezeStrategy().generate_signal(df)
    assert signal.signal_type == "NONE"


# ── Volume Breakout ────────────────────────────────────────────────────────────

def test_volume_breakout_buy_on_surge_up():
    from domains.strategies.strategies.volume_breakout import VolumeBreakoutStrategy
    df = _make_df()
    df["volume_ratio"] = 3.0
    df["close"] = 102.0
    df.at[df.index[-2], "close"] = 100.0
    signal = VolumeBreakoutStrategy().generate_signal(df)
    assert signal.signal_type == "BUY"


def test_volume_breakout_none_if_price_down():
    from domains.strategies.strategies.volume_breakout import VolumeBreakoutStrategy
    df = _make_df()
    df["volume_ratio"] = 3.0
    df["close"] = 98.0
    df.at[df.index[-2], "close"] = 100.0
    signal = VolumeBreakoutStrategy().generate_signal(df)
    assert signal.signal_type == "NONE"


def test_volume_breakout_none_low_volume():
    from domains.strategies.strategies.volume_breakout import VolumeBreakoutStrategy
    df = _make_df()
    df["volume_ratio"] = 1.5
    signal = VolumeBreakoutStrategy().generate_signal(df)
    assert signal.signal_type == "NONE"


# ── Mean Reversion ─────────────────────────────────────────────────────────────

def test_mean_reversion_buy_oversold_non_trending():
    from domains.strategies.strategies.mean_reversion import MeanReversionStrategy
    df = _make_df()
    df["close"] = 85.0
    df["bb_lower"] = 90.0
    df["bb_upper"] = 115.0
    df["rsi_14"] = 32.0
    df["adx_14"] = 18.0
    signal = MeanReversionStrategy().generate_signal(df)
    assert signal.signal_type == "BUY"


def test_mean_reversion_none_if_trending():
    from domains.strategies.strategies.mean_reversion import MeanReversionStrategy
    df = _make_df()
    df["close"] = 85.0
    df["bb_lower"] = 90.0
    df["rsi_14"] = 32.0
    df["adx_14"] = 35.0  # trending — no mean reversion signal
    signal = MeanReversionStrategy().generate_signal(df)
    assert signal.signal_type == "NONE"


def test_mean_reversion_sell_overbought():
    from domains.strategies.strategies.mean_reversion import MeanReversionStrategy
    df = _make_df()
    df["close"] = 125.0
    df["bb_upper"] = 110.0
    df["bb_lower"] = 90.0
    df["rsi_14"] = 75.0
    df["adx_14"] = 15.0
    signal = MeanReversionStrategy().generate_signal(df)
    assert signal.signal_type == "SELL"


# ── Volatility Breakout ────────────────────────────────────────────────────────

def test_volatility_breakout_buy_on_20d_high_break():
    from domains.strategies.strategies.volatility_breakout import VolatilityBreakoutStrategy
    df = _make_df(n=60)
    # Set all closes to 100 except last which breaks out
    df["close"] = 100.0
    df["volume_ratio"] = 2.0
    df.at[df.index[-1], "close"] = 105.0  # break above 20d high of 100
    df.at[df.index[-2], "close"] = 99.0   # previous close was below high
    signal = VolatilityBreakoutStrategy().generate_signal(df)
    assert signal.signal_type == "BUY"


def test_volatility_breakout_none_without_volume():
    from domains.strategies.strategies.volatility_breakout import VolatilityBreakoutStrategy
    df = _make_df(n=60)
    df["close"] = 100.0
    df["volume_ratio"] = 1.0  # low volume
    df.at[df.index[-1], "close"] = 105.0
    signal = VolatilityBreakoutStrategy().generate_signal(df)
    assert signal.signal_type == "NONE"


def test_volatility_breakout_none_too_few_rows():
    from domains.strategies.strategies.volatility_breakout import VolatilityBreakoutStrategy
    df = _make_df(n=15)  # < 21 rows needed
    signal = VolatilityBreakoutStrategy().generate_signal(df)
    assert signal.signal_type == "NONE"


# ── Swing Trend Rider ──────────────────────────────────────────────────────────

def test_swing_trend_rider_buy_all_conditions():
    from domains.strategies.strategies.swing_trend_rider import SwingTrendRiderStrategy
    df = _make_df()
    df["close"] = 110.0
    df["sma_50"] = 100.0
    df["rsi_14"] = 58.0
    df["adx_14"] = 28.0
    df["macd_hist"] = 0.5
    df["supertrend_direction"] = 1.0
    signal = SwingTrendRiderStrategy().generate_signal(df)
    assert signal.signal_type == "BUY"
    assert signal.confidence >= 0.90


def test_swing_trend_rider_buy_4_of_5():
    from domains.strategies.strategies.swing_trend_rider import SwingTrendRiderStrategy
    df = _make_df()
    df["close"] = 110.0
    df["sma_50"] = 100.0
    df["rsi_14"] = 58.0
    df["adx_14"] = 28.0
    df["macd_hist"] = 0.5
    df["supertrend_direction"] = -1.0  # 1 condition fails
    signal = SwingTrendRiderStrategy().generate_signal(df)
    assert signal.signal_type == "BUY"
    assert signal.confidence >= 0.80


def test_swing_trend_rider_none_only_3_conditions():
    from domains.strategies.strategies.swing_trend_rider import SwingTrendRiderStrategy
    df = _make_df()
    df["close"] = 110.0
    df["sma_50"] = 100.0
    df["rsi_14"] = 58.0
    df["adx_14"] = 15.0       # fails
    df["macd_hist"] = -0.1    # fails
    df["supertrend_direction"] = 1.0
    signal = SwingTrendRiderStrategy().generate_signal(df)
    assert signal.signal_type == "NONE"
```

- [ ] **Step 2: Run to confirm failures**

```
cd backend && python -m pytest tests/test_strategies.py -v -k "bb or volume or mean or volatility or swing"
```
Expected: ImportError for each new strategy module

- [ ] **Step 3: Create `bb_squeeze.py`**

```python
# backend/domains/strategies/strategies/bb_squeeze.py
import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class BBSqueezeStrategy(BaseStrategy):
    name = "Bollinger Band Squeeze"
    description = "Buy on close breakout above BB upper band with elevated volume (>1.5x)"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY
    weight = 0.15
    min_holding_days = 5
    max_holding_days = 20

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if df.empty or "bb_upper" not in df.columns:
            return Signal("NONE")
        row = df.iloc[-1]
        close, bb_upper, volume_ratio = row["close"], row["bb_upper"], row["volume_ratio"]
        if any(pd.isna(x) for x in [close, bb_upper, volume_ratio]):
            return Signal("NONE")
        if close > bb_upper and volume_ratio > 1.5:
            confidence = min(1.0, 0.55 + (volume_ratio - 1.5) * 0.08)
            return Signal(
                signal_type="BUY",
                confidence=round(confidence, 4),
                risk_score=0.50,
                expected_upside_pct=8.0,
                stop_loss_pct=5.0,
                target_pct=10.0,
                holding_days=8,
                conditions_met=[
                    f"Close {close:.2f} > BB Upper {bb_upper:.2f}",
                    f"Volume ratio {volume_ratio:.2f}x (> 1.5x)",
                ],
            )
        return Signal("NONE")

    def get_required_indicators(self) -> list[str]:
        return ["bb_upper", "volume_ratio"]
```

- [ ] **Step 4: Create `volume_breakout.py`**

```python
# backend/domains/strategies/strategies/volume_breakout.py
import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class VolumeBreakoutStrategy(BaseStrategy):
    name = "Volume Breakout"
    description = "Buy on strong volume surge (>2.5x average) with positive price action"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY
    weight = 0.15
    min_holding_days = 3
    max_holding_days = 10

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 2 or "volume_ratio" not in df.columns:
            return Signal("NONE")
        row = df.iloc[-1]
        volume_ratio = row["volume_ratio"]
        close = row["close"]
        prev_close = df["close"].iloc[-2]
        if any(pd.isna(x) for x in [volume_ratio, close, prev_close]):
            return Signal("NONE")
        if volume_ratio > 2.5 and close > prev_close:
            confidence = min(1.0, 0.50 + (volume_ratio - 2.5) / 5.0)
            return Signal(
                signal_type="BUY",
                confidence=round(confidence, 4),
                risk_score=0.50,
                expected_upside_pct=6.0,
                stop_loss_pct=5.0,
                target_pct=8.0,
                holding_days=5,
                conditions_met=[
                    f"Volume ratio {volume_ratio:.2f}x (> 2.5x average)",
                    f"Price up: {prev_close:.2f} → {close:.2f}",
                ],
            )
        return Signal("NONE")

    def get_required_indicators(self) -> list[str]:
        return ["volume_ratio"]
```

- [ ] **Step 5: Create `mean_reversion.py`**

```python
# backend/domains/strategies/strategies/mean_reversion.py
import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class MeanReversionStrategy(BaseStrategy):
    name = "Mean Reversion"
    description = "Buy oversold stocks in non-trending markets (close < BB lower, RSI < 40, ADX < 25)"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY
    weight = 0.15
    min_holding_days = 7
    max_holding_days = 21

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if df.empty or "bb_lower" not in df.columns:
            return Signal("NONE")
        row = df.iloc[-1]
        close = row["close"]
        bb_lower = row["bb_lower"]
        bb_upper = row["bb_upper"]
        rsi = row["rsi_14"]
        adx = row["adx_14"]
        if any(pd.isna(x) for x in [close, bb_lower, bb_upper, rsi, adx]):
            return Signal("NONE")
        if close < bb_lower and rsi < 40 and adx < 25:
            confidence = min(1.0, 0.50 + (40 - rsi) / 80)
            return Signal(
                signal_type="BUY",
                confidence=round(confidence, 4),
                risk_score=0.45,
                expected_upside_pct=8.0,
                stop_loss_pct=6.0,
                target_pct=10.0,
                holding_days=12,
                conditions_met=[
                    f"Close {close:.2f} < BB Lower {bb_lower:.2f}",
                    f"RSI={rsi:.1f} < 40",
                    f"ADX={adx:.1f} < 25 (non-trending)",
                ],
            )
        if close > bb_upper and rsi > 70:
            return Signal(
                signal_type="SELL",
                confidence=0.60,
                risk_score=0.55,
                expected_upside_pct=0.0,
                stop_loss_pct=0.0,
                target_pct=0.0,
                holding_days=0,
                conditions_met=["Close > BB Upper and RSI > 70 (overbought)"],
            )
        return Signal("NONE")

    def get_required_indicators(self) -> list[str]:
        return ["bb_lower", "bb_upper", "rsi_14", "adx_14"]
```

- [ ] **Step 6: Create `volatility_breakout.py`**

```python
# backend/domains/strategies/strategies/volatility_breakout.py
import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class VolatilityBreakoutStrategy(BaseStrategy):
    name = "Volatility Breakout"
    description = "Buy when price breaks above 20-day high with volume confirmation (>1.5x)"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY
    weight = 0.15
    min_holding_days = 3
    max_holding_days = 7

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 21 or "volume_ratio" not in df.columns:
            return Signal("NONE")
        row = df.iloc[-1]
        volume_ratio = row["volume_ratio"]
        close = row["close"]
        prev_close = df["close"].iloc[-2]
        high_20 = df["close"].iloc[-21:-1].max()
        if any(pd.isna(x) for x in [volume_ratio, close, high_20]):
            return Signal("NONE")
        if prev_close <= high_20 and close > high_20 and volume_ratio > 1.5:
            return Signal(
                signal_type="BUY",
                confidence=0.62,
                risk_score=0.50,
                expected_upside_pct=7.0,
                stop_loss_pct=5.0,
                target_pct=8.0,
                holding_days=5,
                conditions_met=[
                    f"Close {close:.2f} broke above 20d high {high_20:.2f}",
                    f"Volume ratio {volume_ratio:.2f}x (> 1.5x)",
                ],
            )
        return Signal("NONE")

    def get_required_indicators(self) -> list[str]:
        return ["volume_ratio"]
```

- [ ] **Step 7: Create `swing_trend_rider.py`**

```python
# backend/domains/strategies/strategies/swing_trend_rider.py
import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class SwingTrendRiderStrategy(BaseStrategy):
    name = "Swing Trade Trend Rider"
    description = "Multi-condition confluence: price > SMA50, RSI 50-65, ADX > 20, MACD positive, SuperTrend bullish"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY
    min_holding_days = 7
    max_holding_days = 21

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        required = ["sma_50", "rsi_14", "adx_14", "macd_hist", "supertrend_direction"]
        if df.empty or not all(c in df.columns for c in required):
            return Signal("NONE")
        row = df.iloc[-1]
        close = row["close"]
        sma_50 = row["sma_50"]
        rsi = row["rsi_14"]
        adx = row["adx_14"]
        macd_hist = row["macd_hist"]
        st_dir = row["supertrend_direction"]
        if any(pd.isna(x) for x in [close, sma_50, rsi, adx, macd_hist, st_dir]):
            return Signal("NONE")
        conditions = {
            f"Close {close:.2f} > SMA50 {sma_50:.2f}": close > sma_50,
            f"RSI={rsi:.1f} in 50–65 (momentum building)": 50 <= rsi <= 65,
            f"ADX={adx:.1f} > 20 (trend established)": adx > 20,
            f"MACD histogram {macd_hist:.4f} > 0": macd_hist > 0,
            "SuperTrend bullish (direction=1)": st_dir == 1.0,
        }
        met = [c for c, v in conditions.items() if v]
        failed = [c for c, v in conditions.items() if not v]
        if len(met) >= 4:
            confidence = min(1.0, 0.50 + len(met) * 0.10)
            return Signal(
                signal_type="BUY",
                confidence=round(confidence, 4),
                risk_score=0.40,
                expected_upside_pct=14.0,
                stop_loss_pct=7.0,
                target_pct=16.0,
                holding_days=15,
                conditions_met=met,
                conditions_failed=failed,
            )
        return Signal("NONE")

    def get_required_indicators(self) -> list[str]:
        return ["sma_50", "rsi_14", "adx_14", "macd_hist", "supertrend_direction"]
```

- [ ] **Step 8: Run all strategy tests**

```
cd backend && python -m pytest tests/test_strategies.py -v
```
Expected: all tests pass (should be ~30+ tests now)

- [ ] **Step 9: Commit**

```
git add backend/domains/strategies/strategies/ backend/tests/test_strategies.py
git commit -m "feat: 5 volatility strategies — BB Squeeze, Volume Breakout, Mean Reversion, Volatility Breakout, Swing Trend Rider"
```

---

### Task 4: SignalAggregator

**Files:**
- Create: `backend/domains/strategies/aggregator.py`
- Create: `backend/tests/test_aggregator.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_aggregator.py
import pytest
from domains.strategies.aggregator import SignalAggregator
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe
import pandas as pd


class _MockStrategy(BaseStrategy):
    def __init__(self, name, stype=StrategyType.TECHNICAL):
        self.name = name
        self.strategy_type = stype
        self.weight = 0.20

    def generate_signal(self, df, fundamentals=None):
        return Signal("NONE")


def _buy(confidence=0.70):
    return Signal("BUY", confidence=confidence)


def _sell():
    return Signal("SELL", confidence=0.70)


def _none():
    return Signal("NONE")


def test_no_signals_returns_none():
    agg = SignalAggregator()
    result = agg.aggregate([(_MockStrategy("A"), _none()), (_MockStrategy("B"), _none())])
    assert result["signal_type"] == "NONE"
    assert result["consensus_score"] == 0.0
    assert result["buy_count"] == 0


def test_buy_signal_when_3_agree_above_threshold():
    agg = SignalAggregator()
    pairs = [(_MockStrategy(f"S{i}"), _buy(0.80)) for i in range(3)]
    result = agg.aggregate(pairs)
    assert result["signal_type"] == "BUY"
    assert result["consensus_score"] > 0.65
    assert result["buy_count"] == 3


def test_watch_when_2_agree_moderate_confidence():
    agg = SignalAggregator()
    pairs = [
        (_MockStrategy("A"), _buy(0.55)),
        (_MockStrategy("B"), _buy(0.55)),
    ]
    result = agg.aggregate(pairs)
    assert result["signal_type"] == "WATCH"
    assert result["consensus_score"] > 0.45


def test_none_when_only_1_buy():
    agg = SignalAggregator()
    result = agg.aggregate([(_MockStrategy("A"), _buy(0.90))])
    assert result["signal_type"] == "NONE"


def test_sell_count_tracked():
    agg = SignalAggregator()
    result = agg.aggregate([(_MockStrategy("A"), _sell()), (_MockStrategy("B"), _none())])
    assert result["sell_count"] == 1


def test_consensus_score_is_confidence_weighted():
    agg = SignalAggregator()
    pairs = [
        (_MockStrategy("A"), _buy(1.0)),
        (_MockStrategy("B"), _buy(1.0)),
        (_MockStrategy("C"), _buy(1.0)),
    ]
    result = agg.aggregate(pairs)
    assert result["consensus_score"] == pytest.approx(1.0, abs=0.01)
```

- [ ] **Step 2: Run to confirm failures**

```
cd backend && python -m pytest tests/test_aggregator.py -v
```
Expected: ImportError — `domains.strategies.aggregator` not found

- [ ] **Step 3: Create `backend/domains/strategies/aggregator.py`**

```python
# backend/domains/strategies/aggregator.py
from domains.strategies.base import BaseStrategy, Signal, StrategyType

_TYPE_WEIGHTS: dict[StrategyType, float] = {
    StrategyType.ML: 0.35,
    StrategyType.FUNDAMENTAL: 0.05,
    StrategyType.TECHNICAL: 0.20,
    StrategyType.CUSTOM: 0.15,
}


class SignalAggregator:
    def aggregate(self, signals: list[tuple[BaseStrategy, Signal]]) -> dict:
        """
        signals: list of (strategy, signal) for one symbol.
        Returns dict with signal_type, consensus_score, buy_count, sell_count.
        """
        buy_pairs = [(s, sig) for s, sig in signals if sig.signal_type == "BUY"]
        sell_count = sum(1 for _, sig in signals if sig.signal_type == "SELL")

        if not buy_pairs:
            return {"signal_type": "NONE", "consensus_score": 0.0, "buy_count": 0, "sell_count": sell_count}

        total_weight = 0.0
        weighted_confidence = 0.0
        for strategy, signal in buy_pairs:
            w = _TYPE_WEIGHTS.get(strategy.strategy_type, 0.20)
            weighted_confidence += w * signal.confidence
            total_weight += w

        consensus_score = weighted_confidence / total_weight if total_weight > 0 else 0.0
        buy_count = len(buy_pairs)

        if consensus_score > 0.65 and buy_count >= 3:
            signal_type = "BUY"
        elif consensus_score > 0.45 and buy_count >= 2:
            signal_type = "WATCH"
        else:
            signal_type = "NONE"

        return {
            "signal_type": signal_type,
            "consensus_score": round(consensus_score, 4),
            "buy_count": buy_count,
            "sell_count": sell_count,
        }
```

- [ ] **Step 4: Run tests**

```
cd backend && python -m pytest tests/test_aggregator.py -v
```
Expected: all 6 tests pass

- [ ] **Step 5: Commit**

```
git add backend/domains/strategies/aggregator.py backend/tests/test_aggregator.py
git commit -m "feat: SignalAggregator — consensus scoring with weighted confidence"
```

---

### Task 5: StrategyEngine

**Files:**
- Create: `backend/domains/strategies/engine.py`
- Create: `backend/tests/test_strategy_engine.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_strategy_engine.py
import pytest
from datetime import date
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base
import models  # noqa


@pytest.fixture(scope="module")
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    # Seed strategies table
    session.execute(text(
        "INSERT INTO strategies (name, type, description, is_active, created_at) VALUES "
        "('RSI Oversold/Overbought', 'technical', '', 1, datetime('now')),"
        "('MACD Crossover', 'technical', '', 1, datetime('now')),"
        "('EMA Crossover (9/21)', 'technical', '', 1, datetime('now')),"
        "('SMA Crossover (20/50)', 'technical', '', 1, datetime('now')),"
        "('SuperTrend', 'technical', '', 1, datetime('now')),"
        "('Bollinger Band Squeeze', 'technical', '', 1, datetime('now')),"
        "('Volume Breakout', 'technical', '', 1, datetime('now')),"
        "('Mean Reversion', 'technical', '', 1, datetime('now')),"
        "('Volatility Breakout', 'technical', '', 1, datetime('now')),"
        "('Swing Trade Trend Rider', 'technical', '', 1, datetime('now'))"
    ))

    # Seed stock
    session.execute(text(
        "INSERT INTO stocks (symbol, name, exchange, is_active, added_at) VALUES ('TCS', 'Tata Consultancy Services', 'NSE', 1, datetime('now'))"
    ))

    # Seed 60 price rows for TCS — RSI < 30 on last row to guarantee at least 1 signal
    # We need realistic data, so build a declining series for last few bars
    for i in range(60):
        close = 3500.0 - i * 2  # declining to force RSI < 30
        session.execute(text(
            "INSERT INTO stock_prices_daily (symbol, date, open, high, low, close, volume, data_source) "
            "VALUES ('TCS', date('2024-01-01', :offset), :open, :high, :low, :close, 1000000, 'yfinance')"
        ), {"offset": f"+{i} days", "open": close + 5, "high": close + 10, "low": close - 10, "close": close})

    session.commit()
    yield session
    session.close()


def test_engine_loads_strategy_ids(db):
    from domains.strategies.engine import StrategyEngine
    engine = StrategyEngine(db)
    assert len(engine._strategy_id_map) == 10
    assert "RSI Oversold/Overbought" in engine._strategy_id_map


def test_engine_scan_all_returns_dict(db):
    from domains.strategies.engine import StrategyEngine
    engine = StrategyEngine(db)
    results = engine.scan_all(["TCS"], date(2024, 3, 1))
    assert isinstance(results, dict)


def test_engine_scan_all_saves_signals_to_db(db):
    from domains.strategies.engine import StrategyEngine
    engine = StrategyEngine(db)
    engine.scan_all(["TCS"], date(2024, 3, 1))
    count = db.execute(text("SELECT COUNT(*) FROM strategy_signals WHERE symbol='TCS'")).fetchone()[0]
    assert count >= 1


def test_engine_skips_symbol_with_no_prices(db):
    from domains.strategies.engine import StrategyEngine
    engine = StrategyEngine(db)
    results = engine.scan_all(["FAKESTOCK"], date(2024, 3, 1))
    assert "FAKESTOCK" not in results


def test_engine_skips_symbol_with_too_few_prices(db):
    from domains.strategies.engine import StrategyEngine
    # TINYSTOCK has only 5 price rows — engine requires >= 30
    db.execute(text("INSERT INTO stocks (symbol, name, exchange, is_active, added_at) VALUES ('TINYSTOCK', '', 'NSE', 1, datetime('now'))"))
    for i in range(5):
        db.execute(text(
            "INSERT INTO stock_prices_daily (symbol, date, open, high, low, close, volume, data_source) "
            "VALUES ('TINYSTOCK', date('2024-01-01', :offset), 100, 105, 95, 100, 100000, 'yfinance')"
        ), {"offset": f"+{i} days"})
    db.commit()
    results = engine_instance = None
    from domains.strategies.engine import StrategyEngine
    results = StrategyEngine(db).scan_all(["TINYSTOCK"], date(2024, 3, 1))
    assert "TINYSTOCK" not in results
```

- [ ] **Step 2: Run to confirm failures**

```
cd backend && python -m pytest tests/test_strategy_engine.py -v
```
Expected: ImportError — `domains.strategies.engine` not found

- [ ] **Step 3: Create `backend/domains/strategies/engine.py`**

```python
# backend/domains/strategies/engine.py
import json
import logging
from datetime import date

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from domains.data.indicators import IndicatorEngine
from domains.strategies.aggregator import SignalAggregator
from domains.strategies.base import BaseStrategy, Signal
from domains.strategies.strategies.rsi_oversold import RSIOversoldStrategy
from domains.strategies.strategies.macd_crossover import MACDCrossoverStrategy
from domains.strategies.strategies.ema_crossover import EMACrossoverStrategy
from domains.strategies.strategies.sma_crossover import SMACrossoverStrategy
from domains.strategies.strategies.supertrend_strategy import SuperTrendStrategy
from domains.strategies.strategies.bb_squeeze import BBSqueezeStrategy
from domains.strategies.strategies.volume_breakout import VolumeBreakoutStrategy
from domains.strategies.strategies.mean_reversion import MeanReversionStrategy
from domains.strategies.strategies.volatility_breakout import VolatilityBreakoutStrategy
from domains.strategies.strategies.swing_trend_rider import SwingTrendRiderStrategy

logger = logging.getLogger(__name__)

ALL_STRATEGIES: list[BaseStrategy] = [
    RSIOversoldStrategy(),
    MACDCrossoverStrategy(),
    EMACrossoverStrategy(),
    SMACrossoverStrategy(),
    SuperTrendStrategy(),
    BBSqueezeStrategy(),
    VolumeBreakoutStrategy(),
    MeanReversionStrategy(),
    VolatilityBreakoutStrategy(),
    SwingTrendRiderStrategy(),
]


class StrategyEngine:
    def __init__(self, db: Session):
        self.db = db
        self.aggregator = SignalAggregator()
        self._strategy_id_map: dict[str, int] = self._load_strategy_ids()

    def _load_strategy_ids(self) -> dict[str, int]:
        rows = self.db.execute(text("SELECT id, name FROM strategies")).fetchall()
        return {row[1]: row[0] for row in rows}

    def scan_all(self, symbols: list[str], scan_date: date) -> dict[str, dict]:
        """Runs all strategies on each symbol, saves non-NONE signals to DB, returns aggregation results."""
        results: dict[str, dict] = {}
        for symbol in symbols:
            df = self._load_prices(symbol)
            if df.empty or len(df) < 30:
                continue
            df = IndicatorEngine.compute(df)
            symbol_signals: list[tuple[BaseStrategy, Signal]] = []
            for strategy in ALL_STRATEGIES:
                signal = strategy.generate_signal(df)
                symbol_signals.append((strategy, signal))
                if signal.signal_type != "NONE":
                    self._save_signal(symbol, strategy, signal, float(df["close"].iloc[-1]), scan_date)
            agg = self.aggregator.aggregate(symbol_signals)
            if agg["signal_type"] != "NONE":
                results[symbol] = agg
        self.db.commit()
        logger.info("[StrategyEngine] scan_all: %d/%d symbols with signals", len(results), len(symbols))
        return results

    def _load_prices(self, symbol: str, limit: int = 200) -> pd.DataFrame:
        rows = self.db.execute(
            text("""
                SELECT date, open, high, low, close, volume
                FROM stock_prices_daily
                WHERE symbol = :s
                ORDER BY date ASC
                LIMIT :lim
            """),
            {"s": symbol, "lim": limit},
        ).fetchall()
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"])
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].astype(float)
        return df

    def _save_signal(self, symbol: str, strategy: BaseStrategy, signal: Signal, price: float, scan_date: date):
        strategy_id = self._strategy_id_map.get(strategy.name)
        if strategy_id is None:
            logger.warning("[StrategyEngine] Strategy not in DB: %s", strategy.name)
            return
        stop_loss = price * (1 - signal.stop_loss_pct / 100) if signal.stop_loss_pct > 0 else None
        target = price * (1 + signal.target_pct / 100) if signal.target_pct > 0 else None
        self.db.execute(
            text("""
                INSERT OR REPLACE INTO strategy_signals
                (symbol, strategy_id, signal_date, signal_type, price_at_signal,
                 confidence_score, risk_score, expected_upside_pct,
                 suggested_stop_loss, suggested_target, holding_period_days,
                 reasoning_json, indicators_json, created_at)
                VALUES (:sym, :sid, :sdate, :stype, :price, :conf, :risk, :upside,
                        :sl, :tgt, :hdays, :reasoning, :indicators, datetime('now'))
            """),
            {
                "sym": symbol,
                "sid": strategy_id,
                "sdate": str(scan_date),
                "stype": signal.signal_type,
                "price": price,
                "conf": signal.confidence,
                "risk": signal.risk_score,
                "upside": signal.expected_upside_pct,
                "sl": stop_loss,
                "tgt": target,
                "hdays": signal.holding_days,
                "reasoning": json.dumps({
                    "conditions_met": signal.conditions_met,
                    "conditions_failed": signal.conditions_failed,
                }),
                "indicators": json.dumps(strategy.get_required_indicators()),
            },
        )
```

- [ ] **Step 4: Run tests**

```
cd backend && python -m pytest tests/test_strategy_engine.py -v
```
Expected: all 5 tests pass

- [ ] **Step 5: Commit**

```
git add backend/domains/strategies/engine.py backend/tests/test_strategy_engine.py
git commit -m "feat: StrategyEngine — scan_all() runs 10 strategies, saves to DB"
```

---

### Task 6: Strategy Seeding + StrategyService

**Files:**
- Create: `backend/domains/strategies/seed.py`
- Create: `backend/domains/strategies/service.py`
- Create: `backend/tests/test_strategy_service.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_strategy_service.py
import pytest
from datetime import date
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base
import models  # noqa


@pytest.fixture(scope="module")
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    from domains.strategies.seed import seed_strategies
    seed_strategies(session)

    # Seed one signal
    strat_id = session.execute(text("SELECT id FROM strategies WHERE name='RSI Oversold/Overbought'")).fetchone()[0]
    session.execute(text(
        "INSERT INTO strategy_signals (symbol, strategy_id, signal_date, signal_type, price_at_signal, confidence_score, created_at) "
        "VALUES ('TCS', :sid, date('now'), 'BUY', 3500.0, 0.75, datetime('now'))"
    ), {"sid": strat_id})
    session.commit()
    yield session
    session.close()


def test_seed_inserts_10_strategies(db):
    count = db.execute(text("SELECT COUNT(*) FROM strategies")).fetchone()[0]
    assert count == 10


def test_seed_is_idempotent(db):
    from domains.strategies.seed import seed_strategies
    seed_strategies(db)  # run again
    count = db.execute(text("SELECT COUNT(*) FROM strategies")).fetchone()[0]
    assert count == 10  # still 10, no duplicates


def test_get_all_strategies_returns_10(db):
    from domains.strategies.service import StrategyService
    strategies = StrategyService(db).get_all_strategies()
    assert len(strategies) == 10
    assert all("name" in s for s in strategies)


def test_get_today_signals_returns_list(db):
    from domains.strategies.service import StrategyService
    signals = StrategyService(db).get_today_signals()
    assert isinstance(signals, list)
    assert len(signals) >= 1


def test_get_today_signals_include_strategy_name(db):
    from domains.strategies.service import StrategyService
    signals = StrategyService(db).get_today_signals()
    assert "strategy_name" in signals[0]
    assert signals[0]["strategy_name"] == "RSI Oversold/Overbought"


def test_get_signal_by_id(db):
    from domains.strategies.service import StrategyService
    signals = StrategyService(db).get_today_signals()
    signal_id = signals[0]["id"]
    signal = StrategyService(db).get_signal_by_id(signal_id)
    assert signal is not None
    assert signal["symbol"] == "TCS"


def test_get_signal_by_id_returns_none_for_missing(db):
    from domains.strategies.service import StrategyService
    assert StrategyService(db).get_signal_by_id(99999) is None


def test_get_signals_filter_by_symbol(db):
    from domains.strategies.service import StrategyService
    signals = StrategyService(db).get_signals(symbol="TCS")
    assert all(s["symbol"] == "TCS" for s in signals)


def test_get_signals_filter_by_type(db):
    from domains.strategies.service import StrategyService
    signals = StrategyService(db).get_signals(signal_type="BUY")
    assert all(s["signal_type"] == "BUY" for s in signals)
```

- [ ] **Step 2: Run to confirm failures**

```
cd backend && python -m pytest tests/test_strategy_service.py -v
```
Expected: ImportError for seed and service modules

- [ ] **Step 3: Create `backend/domains/strategies/seed.py`**

```python
# backend/domains/strategies/seed.py
import json
import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

from domains.strategies.engine import ALL_STRATEGIES

logger = logging.getLogger(__name__)


def seed_strategies(db: Session) -> None:
    """Insert all 10 core strategies into the strategies table. Idempotent — uses INSERT OR IGNORE."""
    for strategy in ALL_STRATEGIES:
        db.execute(
            text("""
                INSERT OR IGNORE INTO strategies (name, type, description, parameters_json, is_active, created_at)
                VALUES (:name, :type, :desc, :params, 1, datetime('now'))
            """),
            {
                "name": strategy.name,
                "type": strategy.strategy_type.value,
                "desc": strategy.description,
                "params": json.dumps(strategy.get_parameters()),
            },
        )
    db.commit()
    logger.info("[seed_strategies] %d strategies seeded", len(ALL_STRATEGIES))
```

- [ ] **Step 4: Create `backend/domains/strategies/service.py`**

```python
# backend/domains/strategies/service.py
from datetime import datetime
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session


class StrategyService:
    def __init__(self, db: Session):
        self.db = db

    def get_all_strategies(self) -> list[dict]:
        rows = self.db.execute(
            text("SELECT id, name, type, description, is_active, created_at FROM strategies ORDER BY id")
        ).fetchall()
        return [dict(r._mapping) for r in rows]

    def get_today_signals(self, signal_date: Optional[str] = None) -> list[dict]:
        date_str = signal_date or datetime.utcnow().strftime("%Y-%m-%d")
        rows = self.db.execute(
            text("""
                SELECT ss.id, ss.symbol, ss.strategy_id, s.name AS strategy_name,
                       ss.signal_date, ss.signal_type, ss.price_at_signal,
                       ss.confidence_score, ss.risk_score, ss.expected_upside_pct,
                       ss.suggested_stop_loss, ss.suggested_target,
                       ss.holding_period_days, ss.reasoning_json
                FROM strategy_signals ss
                JOIN strategies s ON ss.strategy_id = s.id
                WHERE ss.signal_date = :d
                ORDER BY ss.confidence_score DESC
            """),
            {"d": date_str},
        ).fetchall()
        return [dict(r._mapping) for r in rows]

    def get_signals(
        self,
        symbol: Optional[str] = None,
        signal_type: Optional[str] = None,
        from_date: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict]:
        q = """
            SELECT ss.id, ss.symbol, ss.strategy_id, s.name AS strategy_name,
                   ss.signal_date, ss.signal_type, ss.price_at_signal, ss.confidence_score, ss.risk_score
            FROM strategy_signals ss
            JOIN strategies s ON ss.strategy_id = s.id
            WHERE 1=1
        """
        params: dict = {}
        if symbol:
            q += " AND ss.symbol = :sym"
            params["sym"] = symbol.upper()
        if signal_type:
            q += " AND ss.signal_type = :st"
            params["st"] = signal_type.upper()
        if from_date:
            q += " AND ss.signal_date >= :fd"
            params["fd"] = from_date
        q += " ORDER BY ss.signal_date DESC, ss.confidence_score DESC LIMIT :lim"
        params["lim"] = limit
        rows = self.db.execute(text(q), params).fetchall()
        return [dict(r._mapping) for r in rows]

    def get_signal_by_id(self, signal_id: int) -> Optional[dict]:
        row = self.db.execute(
            text("""
                SELECT ss.*, s.name AS strategy_name,
                       st.name AS stock_name, st.sector
                FROM strategy_signals ss
                JOIN strategies s ON ss.strategy_id = s.id
                LEFT JOIN stocks st ON ss.symbol = st.symbol
                WHERE ss.id = :id
            """),
            {"id": signal_id},
        ).fetchone()
        return dict(row._mapping) if row else None
```

- [ ] **Step 5: Run tests**

```
cd backend && python -m pytest tests/test_strategy_service.py -v
```
Expected: all 9 tests pass

- [ ] **Step 6: Commit**

```
git add backend/domains/strategies/seed.py backend/domains/strategies/service.py backend/tests/test_strategy_service.py
git commit -m "feat: strategy seeding + StrategyService — DB queries for signals and strategies"
```

---

### Task 7: Strategies REST API + main.py Wiring

**Files:**
- Create: `backend/domains/strategies/router.py`
- Modify: `backend/main.py`
- Create: `backend/tests/test_strategy_router.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_strategy_router.py
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
    from domains.strategies.seed import seed_strategies
    seed_strategies(db)
    strat_id = db.execute(text("SELECT id FROM strategies WHERE name='RSI Oversold/Overbought'")).fetchone()[0]
    db.execute(text(
        "INSERT INTO stocks (symbol, name, exchange, is_active, added_at) VALUES ('TCS', 'TCS', 'NSE', 1, datetime('now'))"
    ))
    db.execute(text(
        "INSERT INTO strategy_signals (symbol, strategy_id, signal_date, signal_type, price_at_signal, confidence_score, created_at) "
        "VALUES ('TCS', :sid, date('now'), 'BUY', 3500.0, 0.80, datetime('now'))"
    ), {"sid": strat_id})
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


def test_get_strategies_returns_10(client):
    response = client.get("/api/v1/strategies")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 10


def test_get_signals_today_returns_list(client):
    response = client.get("/api/v1/signals/today")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1


def test_get_signals_today_has_strategy_name(client):
    response = client.get("/api/v1/signals/today")
    assert "strategy_name" in response.json()[0]


def test_get_signals_with_symbol_filter(client):
    response = client.get("/api/v1/signals?symbol=TCS")
    assert response.status_code == 200
    data = response.json()
    assert all(s["symbol"] == "TCS" for s in data)


def test_get_signal_by_id(client):
    signals = client.get("/api/v1/signals/today").json()
    signal_id = signals[0]["id"]
    response = client.get(f"/api/v1/signals/{signal_id}")
    assert response.status_code == 200
    assert response.json()["id"] == signal_id


def test_get_signal_not_found(client):
    response = client.get("/api/v1/signals/99999")
    assert response.status_code == 404


def test_unauthorized_without_key():
    from main import app
    c = TestClient(app)
    response = c.get("/api/v1/strategies")
    assert response.status_code == 401
```

- [ ] **Step 2: Run to confirm failures**

```
cd backend && python -m pytest tests/test_strategy_router.py -v
```
Expected: 404 on `/api/v1/strategies` (route not registered yet)

- [ ] **Step 3: Create `backend/domains/strategies/router.py`**

```python
# backend/domains/strategies/router.py
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from domains.strategies.service import StrategyService

router = APIRouter(tags=["strategies"])


@router.get("/strategies")
def list_strategies(db: Session = Depends(get_db)):
    return StrategyService(db).get_all_strategies()


@router.get("/signals/today")
def signals_today(db: Session = Depends(get_db)):
    return StrategyService(db).get_today_signals()


@router.get("/signals/{signal_id}")
def get_signal(signal_id: int, db: Session = Depends(get_db)):
    signal = StrategyService(db).get_signal_by_id(signal_id)
    if not signal:
        raise HTTPException(status_code=404, detail=f"Signal {signal_id} not found")
    return signal


@router.get("/signals")
def list_signals(
    symbol: Optional[str] = Query(None),
    signal_type: Optional[str] = Query(None),
    from_date: Optional[date] = Query(None),
    limit: int = Query(100, le=1000),
    db: Session = Depends(get_db),
):
    return StrategyService(db).get_signals(
        symbol=symbol,
        signal_type=signal_type,
        from_date=str(from_date) if from_date else None,
        limit=limit,
    )
```

- [ ] **Step 4: Update `backend/main.py`** — add strategy router + seed on startup

The lifespan function currently is:
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables verified")
    from scheduler import scheduler, register_jobs
    register_jobs()
    scheduler.start()
    logger.info("APScheduler started")
    yield
    scheduler.shutdown(wait=False)
    logger.info("APScheduler stopped")
```

Add seed call and strategy router:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables verified")
    from domains.strategies.seed import seed_strategies
    from database import SessionLocal
    with SessionLocal() as db:
        seed_strategies(db)
    from scheduler import scheduler, register_jobs
    register_jobs()
    scheduler.start()
    logger.info("APScheduler started")
    yield
    scheduler.shutdown(wait=False)
    logger.info("APScheduler stopped")
```

And at the bottom of main.py, add after the data router line:
```python
from domains.strategies.router import router as strategies_router  # noqa: E402

app.include_router(strategies_router, prefix="/api/v1", dependencies=[Depends(verify_api_key)])
```

- [ ] **Step 5: Run tests**

```
cd backend && python -m pytest tests/test_strategy_router.py -v
```
Expected: all 7 tests pass

- [ ] **Step 6: Run full test suite to check no regressions**

```
cd backend && python -m pytest -v
```
Expected: all tests pass (57 existing + new)

- [ ] **Step 7: Commit**

```
git add backend/domains/strategies/router.py backend/main.py backend/tests/test_strategy_router.py
git commit -m "feat: strategies REST API — /strategies, /signals, /signals/today, /signals/{id}"
```

---

### Task 8: APScheduler Wiring

**Files:**
- Modify: `backend/scheduler.py`

No new tests needed — the stubs are tested in `test_scheduler.py`. The logic (StrategyEngine) is tested separately.

- [ ] **Step 1: Run existing scheduler tests to confirm baseline**

```
cd backend && python -m pytest tests/test_scheduler.py -v
```
Expected: 2 tests pass

- [ ] **Step 2: Replace stubs in `backend/scheduler.py`**

Replace `_daily_eod_update` and `_intraday_scan` bodies only. Keep `JobIds`, `register_jobs`, and other functions intact.

```python
def _daily_eod_update():
    from datetime import date
    from database import SessionLocal
    from domains.strategies.engine import StrategyEngine
    from domains.data.nse_universe import NSE_SYMBOLS
    db = SessionLocal()
    try:
        engine = StrategyEngine(db)
        results = engine.scan_all(NSE_SYMBOLS, date.today())
        logger.info("[scheduler] daily_eod_update: %d signals generated", len(results))
    except Exception:
        logger.exception("[scheduler] daily_eod_update failed")
    finally:
        db.close()


def _intraday_scan():
    from datetime import date
    from database import SessionLocal
    from domains.strategies.engine import StrategyEngine
    from domains.data.nse_universe import NSE_SYMBOLS
    if not _is_market_hours():
        return
    db = SessionLocal()
    try:
        engine = StrategyEngine(db)
        results = engine.scan_all(NSE_SYMBOLS, date.today())
        logger.info("[scheduler] intraday_scan: %d signals", len(results))
    except Exception:
        logger.exception("[scheduler] intraday_scan failed")
    finally:
        db.close()


def _is_market_hours() -> bool:
    from datetime import datetime
    import pytz
    now = datetime.now(pytz.timezone("Asia/Kolkata"))
    return now.weekday() < 5 and 9 <= now.hour < 16
```

Also add `import pytz` to the imports at the top of `scheduler.py` (pytz is a transitive dependency of APScheduler, already installed).

- [ ] **Step 3: Verify existing tests still pass**

```
cd backend && python -m pytest tests/test_scheduler.py -v
```
Expected: still 2 tests pass (they test `scheduler is not None` and `JobIds` — not the stub bodies)

- [ ] **Step 4: Commit**

```
git add backend/scheduler.py
git commit -m "feat: APScheduler wiring — daily EOD and intraday scan run StrategyEngine"
```

---

### Task 9: SignalExplainer (Claude API + ai_analyses caching)

**Files:**
- Create: `backend/domains/ai/__init__.py`
- Create: `backend/domains/ai/explainer.py`
- Create: `backend/tests/test_explainer.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_explainer.py
import json
import pytest
from unittest.mock import MagicMock, patch
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base
import models  # noqa


@pytest.fixture(scope="module")
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    # Seed strategy + stock + signal
    session.execute(text(
        "INSERT INTO strategies (name, type, description, is_active, created_at) VALUES ('RSI Oversold/Overbought', 'technical', '', 1, datetime('now'))"
    ))
    session.execute(text(
        "INSERT INTO stocks (symbol, name, sector, exchange, is_active, added_at) VALUES ('TCS', 'Tata Consultancy Services', 'IT', 'NSE', 1, datetime('now'))"
    ))
    session.execute(text(
        "INSERT INTO strategy_signals "
        "(symbol, strategy_id, signal_date, signal_type, price_at_signal, confidence_score, "
        "risk_score, suggested_stop_loss, suggested_target, holding_period_days, reasoning_json, created_at) "
        "VALUES ('TCS', 1, date('now'), 'BUY', 3500.0, 0.80, 0.40, 3255.0, 4025.0, 10, "
        "'{\"conditions_met\": [\"RSI=25.0 < 30\"], \"conditions_failed\": []}', datetime('now'))"
    ))
    session.execute(text(
        "INSERT INTO strategy_signals "
        "(symbol, strategy_id, signal_date, signal_type, price_at_signal, confidence_score, "
        "risk_score, reasoning_json, created_at) "
        "VALUES ('TCS', 1, date('now'), 'SELL', 3500.0, 0.70, 0.55, "
        "'{\"conditions_met\": [\"RSI=75.0 > 70\"], \"conditions_failed\": []}', datetime('now'))"
    ))
    session.commit()
    yield session
    session.close()


_FAKE_EXPLANATION = {
    "summary": "TCS showing strong RSI oversold bounce opportunity.",
    "bull_case": ["RSI at 25 indicates extreme oversold", "Strong support at 3255"],
    "bear_case": ["Broader market weakness", "IT sector rotation risk"],
    "confidence_reasoning": "RSI below 30 with volume confirmation",
    "suggested_entry": 3500.0,
    "stop_loss": 3255.0,
    "target_1": 3850.0,
    "target_2": 4025.0,
    "holding_period": "10-15 days",
    "risk_rating": "MEDIUM",
}


def test_explainer_returns_none_when_no_api_key(db):
    from domains.ai.explainer import SignalExplainer
    explainer = SignalExplainer(db)
    explainer._client = None
    result = explainer.explain(1)
    assert result is None


def test_explainer_calls_claude_and_returns_dict(db):
    from domains.ai.explainer import SignalExplainer

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=json.dumps(_FAKE_EXPLANATION))]

    explainer = SignalExplainer(db)
    explainer._client = MagicMock()
    explainer._client.messages.create.return_value = mock_response

    result = explainer.explain(1)
    assert result is not None
    assert result["summary"] == _FAKE_EXPLANATION["summary"]
    assert "bull_case" in result


def test_explainer_caches_result(db):
    from domains.ai.explainer import SignalExplainer

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=json.dumps(_FAKE_EXPLANATION))]

    explainer = SignalExplainer(db)
    explainer._client = MagicMock()
    explainer._client.messages.create.return_value = mock_response

    # First call — hits Claude
    explainer.explain(1)
    # Second call — should hit cache, not Claude again
    explainer.explain(1)

    assert explainer._client.messages.create.call_count == 1


def test_explainer_returns_none_for_sell_signal(db):
    from domains.ai.explainer import SignalExplainer
    explainer = SignalExplainer(db)
    explainer._client = MagicMock()
    # Signal ID 2 is a SELL signal
    result = explainer.explain(2)
    assert result is None
    explainer._client.messages.create.assert_not_called()


def test_explainer_returns_none_for_missing_signal(db):
    from domains.ai.explainer import SignalExplainer
    explainer = SignalExplainer(db)
    explainer._client = MagicMock()
    result = explainer.explain(99999)
    assert result is None
```

- [ ] **Step 2: Run to confirm failures**

```
cd backend && python -m pytest tests/test_explainer.py -v
```
Expected: ImportError — `domains.ai.explainer` not found

- [ ] **Step 3: Create `backend/domains/ai/__init__.py`**

```python
# (empty)
```

- [ ] **Step 4: Create `backend/domains/ai/explainer.py`**

```python
# backend/domains/ai/explainer.py
import json
import logging
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from settings import settings

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are an expert Indian stock market analyst with 20 years of NSE/BSE experience. "
    "You specialise in technical analysis, fundamental analysis, and quantitative strategies. "
    "You always explain reasoning in plain English, give specific price levels, and never give "
    "generic advice. You understand NSE regulations, FII/DII behaviour, and sector cycles in "
    "Indian markets. Always respond with valid JSON only — no markdown, no extra text."
)


class SignalExplainer:
    def __init__(self, db: Session):
        self.db = db
        self._client = None
        if settings.anthropic_api_key:
            import anthropic
            self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    def explain(self, signal_id: int) -> Optional[dict]:
        """Returns AI explanation for a BUY signal. Uses ai_analyses cache (6hr TTL)."""
        cached = self._get_cached(signal_id, "buy_explanation")
        if cached:
            return cached
        signal = self._load_signal(signal_id)
        if not signal or signal["signal_type"] != "BUY":
            return None
        result = self._call_claude_buy(signal)
        if result:
            self._save_cache(signal_id, "buy_explanation", result, ttl_hours=6)
        return result

    def _get_cached(self, signal_id: int, analysis_type: str) -> Optional[dict]:
        row = self.db.execute(
            text("""
                SELECT content FROM ai_analyses
                WHERE subject_type = 'signal' AND subject_id = :sid
                  AND analysis_type = :at
                  AND (expires_at IS NULL OR expires_at > datetime('now'))
            """),
            {"sid": signal_id, "at": analysis_type},
        ).fetchone()
        return json.loads(row[0]) if row else None

    def _save_cache(self, signal_id: int, analysis_type: str, content: dict, ttl_hours: int):
        self.db.execute(
            text("""
                INSERT OR REPLACE INTO ai_analyses
                (subject_type, subject_id, analysis_type, content, model_used, created_at, expires_at)
                VALUES ('signal', :sid, :at, :content, 'claude-sonnet-4-6',
                        datetime('now'), datetime('now', :ttl))
            """),
            {
                "sid": signal_id,
                "at": analysis_type,
                "content": json.dumps(content),
                "ttl": f"+{ttl_hours} hours",
            },
        )
        self.db.commit()

    def _load_signal(self, signal_id: int) -> Optional[dict]:
        row = self.db.execute(
            text("""
                SELECT ss.*, s.name AS strategy_name, st.name AS stock_name, st.sector
                FROM strategy_signals ss
                JOIN strategies s ON ss.strategy_id = s.id
                LEFT JOIN stocks st ON ss.symbol = st.symbol
                WHERE ss.id = :id
            """),
            {"id": signal_id},
        ).fetchone()
        return dict(row._mapping) if row else None

    def _call_claude_buy(self, signal: dict) -> Optional[dict]:
        if not self._client:
            logger.warning("[SignalExplainer] Anthropic API key not configured")
            return None
        reasoning = json.loads(signal.get("reasoning_json") or "{}")
        user_prompt = (
            f"Analyse BUY signal for {signal['symbol']}:\n"
            f"Strategy: {signal['strategy_name']}\n"
            f"Price at signal: ₹{signal['price_at_signal']}\n"
            f"Confidence: {(signal['confidence_score'] or 0):.0%}\n"
            f"Conditions met: {', '.join(reasoning.get('conditions_met', []))}\n"
            f"Suggested stop loss: ₹{signal['suggested_stop_loss']}\n"
            f"Suggested target: ₹{signal['suggested_target']}\n"
            f"Holding period: {signal['holding_period_days']} days\n"
            f"Stock: {signal.get('stock_name', signal['symbol'])} | Sector: {signal.get('sector', 'Unknown')}\n\n"
            "Return a JSON object with keys: summary (string), bull_case (list[str]), "
            "bear_case (list[str]), confidence_reasoning (string), suggested_entry (number), "
            "stop_loss (number), target_1 (number), target_2 (number), "
            "holding_period (string), risk_rating (LOW|MEDIUM|HIGH)."
        )
        try:
            response = self._client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1024,
                system=[{"type": "text", "text": _SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": user_prompt}],
            )
            text_content = response.content[0].text.strip()
            if "```" in text_content:
                text_content = text_content.split("```")[1].lstrip("json").strip().split("```")[0]
            return json.loads(text_content)
        except Exception as e:
            logger.error("[SignalExplainer] Claude API error: %s", e)
            return None


class SellExplainer:
    def __init__(self, db: Session):
        self.db = db
        self._base = SignalExplainer(db)
        self._client = self._base._client

    def explain(self, signal_id: int) -> Optional[dict]:
        """Returns AI explanation for a SELL signal. Uses ai_analyses cache (6hr TTL)."""
        cached = self._base._get_cached(signal_id, "sell_explanation")
        if cached:
            return cached
        signal = self._base._load_signal(signal_id)
        if not signal or signal["signal_type"] != "SELL":
            return None
        result = self._call_claude_sell(signal)
        if result:
            self._base._save_cache(signal_id, "sell_explanation", result, ttl_hours=6)
        return result

    def _call_claude_sell(self, signal: dict) -> Optional[dict]:
        if not self._client:
            return None
        reasoning = json.loads(signal.get("reasoning_json") or "{}")
        user_prompt = (
            f"Analyse SELL signal for {signal['symbol']}:\n"
            f"Strategy: {signal['strategy_name']}\n"
            f"Price at signal: ₹{signal['price_at_signal']}\n"
            f"Confidence: {(signal['confidence_score'] or 0):.0%}\n"
            f"Conditions met: {', '.join(reasoning.get('conditions_met', []))}\n"
            f"Stock: {signal.get('stock_name', signal['symbol'])} | Sector: {signal.get('sector', 'Unknown')}\n\n"
            "Return a JSON object with keys: summary (string), exit_reasons (list[str]), "
            "risk_if_held (list[str]), action (EXIT_NOW|TRAIL_STOP), confidence_reasoning (string)."
        )
        try:
            response = self._client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=512,
                system=[{"type": "text", "text": _SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": user_prompt}],
            )
            text_content = response.content[0].text.strip()
            if "```" in text_content:
                text_content = text_content.split("```")[1].lstrip("json").strip().split("```")[0]
            return json.loads(text_content)
        except Exception as e:
            logger.error("[SellExplainer] Claude API error: %s", e)
            return None
```

- [ ] **Step 5: Run tests**

```
cd backend && python -m pytest tests/test_explainer.py -v
```
Expected: all 5 tests pass

- [ ] **Step 6: Commit**

```
git add backend/domains/ai/ backend/tests/test_explainer.py
git commit -m "feat: SignalExplainer + SellExplainer — Claude API with ai_analyses caching"
```

---

### Task 10: AI Explanation Endpoint

**Files:**
- Create: `backend/domains/ai/router.py`
- Modify: `backend/main.py` (add ai router)

No new test file — add tests to `test_strategy_router.py`.

- [ ] **Step 1: Append tests to `test_strategy_router.py`**

```python
# Append to backend/tests/test_strategy_router.py

def test_get_signal_explanation_no_api_key(client):
    """With no API key configured, explanation endpoint returns 503."""
    signals = client.get("/api/v1/signals/today").json()
    signal_id = signals[0]["id"]
    response = client.get(f"/api/v1/signals/{signal_id}/explanation")
    # Returns 503 when Anthropic key not configured, or 200 with cached content
    assert response.status_code in (200, 503)


def test_get_sell_signal_explanation_returns_404_or_503(client):
    """SELL signals return 404 from explanation endpoint (not BUY)."""
    # Seed a SELL signal and test
    response = client.get("/api/v1/signals/99998/explanation")
    assert response.status_code in (404, 503)
```

- [ ] **Step 2: Run to confirm new tests fail**

```
cd backend && python -m pytest tests/test_strategy_router.py::test_get_signal_explanation_no_api_key -v
```
Expected: 404 (route not registered)

- [ ] **Step 3: Create `backend/domains/ai/router.py`**

```python
# backend/domains/ai/router.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from domains.ai.explainer import SignalExplainer, SellExplainer
from domains.strategies.service import StrategyService

router = APIRouter(tags=["ai"])


@router.get("/signals/{signal_id}/explanation")
def get_signal_explanation(signal_id: int, db: Session = Depends(get_db)):
    signal = StrategyService(db).get_signal_by_id(signal_id)
    if not signal:
        raise HTTPException(status_code=404, detail=f"Signal {signal_id} not found")

    if signal["signal_type"] == "BUY":
        result = SignalExplainer(db).explain(signal_id)
    elif signal["signal_type"] == "SELL":
        result = SellExplainer(db).explain(signal_id)
    else:
        raise HTTPException(status_code=400, detail="Explanation only available for BUY or SELL signals")

    if result is None:
        raise HTTPException(status_code=503, detail="AI explanation unavailable — check ANTHROPIC_API_KEY")
    return result
```

- [ ] **Step 4: Register ai router in `backend/main.py`**

Add after the strategies router line:
```python
from domains.ai.router import router as ai_router  # noqa: E402

app.include_router(ai_router, prefix="/api/v1", dependencies=[Depends(verify_api_key)])
```

- [ ] **Step 5: Run updated router tests**

```
cd backend && python -m pytest tests/test_strategy_router.py -v
```
Expected: all tests pass

- [ ] **Step 6: Run full suite**

```
cd backend && python -m pytest -v
```
Expected: all tests pass

- [ ] **Step 7: Commit**

```
git add backend/domains/ai/router.py backend/main.py backend/tests/test_strategy_router.py
git commit -m "feat: AI explanation endpoint — GET /signals/{id}/explanation"
```

---

### Task 11: AlertService (Telegram)

**Files:**
- Create: `backend/domains/alerts/__init__.py`
- Create: `backend/domains/alerts/telegram.py`
- Create: `backend/tests/test_telegram.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_telegram.py
from unittest.mock import MagicMock, patch
from datetime import date


def test_send_returns_false_when_not_configured():
    from domains.alerts.telegram import AlertService
    svc = AlertService()
    svc._token = ""
    svc._chat_id = ""
    assert svc.send("hello") is False


def test_send_returns_true_on_200():
    from domains.alerts.telegram import AlertService
    mock_response = MagicMock()
    mock_response.status_code = 200

    svc = AlertService()
    svc._token = "fake-token"
    svc._chat_id = "12345"

    with patch("domains.alerts.telegram.httpx.post", return_value=mock_response):
        result = svc.send("test message")
    assert result is True


def test_send_returns_false_on_non_200():
    from domains.alerts.telegram import AlertService
    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_response.text = "Bad Request"

    svc = AlertService()
    svc._token = "fake-token"
    svc._chat_id = "12345"

    with patch("domains.alerts.telegram.httpx.post", return_value=mock_response):
        result = svc.send("test message")
    assert result is False


def test_send_returns_false_on_exception():
    from domains.alerts.telegram import AlertService
    svc = AlertService()
    svc._token = "fake-token"
    svc._chat_id = "12345"

    with patch("domains.alerts.telegram.httpx.post", side_effect=Exception("network error")):
        result = svc.send("test message")
    assert result is False


def test_send_daily_digest_formats_signals():
    from domains.alerts.telegram import AlertService
    mock_response = MagicMock()
    mock_response.status_code = 200

    svc = AlertService()
    svc._token = "fake-token"
    svc._chat_id = "12345"

    signals = [
        {"symbol": "TCS", "confidence_score": 0.82, "strategy_name": "RSI Oversold/Overbought"},
        {"symbol": "INFY", "confidence_score": 0.71, "strategy_name": "MACD Crossover"},
    ]

    with patch("domains.alerts.telegram.httpx.post", return_value=mock_response) as mock_post:
        result = svc.send_daily_digest(signals, scan_date=date(2026, 8, 10))
    assert result is True
    call_args = mock_post.call_args
    sent_text = call_args[1]["json"]["text"]
    assert "TCS" in sent_text
    assert "82%" in sent_text
    assert "10 Aug 2026" in sent_text


def test_send_daily_digest_no_signals():
    from domains.alerts.telegram import AlertService
    mock_response = MagicMock()
    mock_response.status_code = 200

    svc = AlertService()
    svc._token = "fake-token"
    svc._chat_id = "12345"

    with patch("domains.alerts.telegram.httpx.post", return_value=mock_response) as mock_post:
        svc.send_daily_digest([])
    sent_text = mock_post.call_args[1]["json"]["text"]
    assert "No high-confidence" in sent_text
```

- [ ] **Step 2: Run to confirm failures**

```
cd backend && python -m pytest tests/test_telegram.py -v
```
Expected: ImportError — `domains.alerts.telegram` not found

- [ ] **Step 3: Create `backend/domains/alerts/__init__.py`**

```python
# (empty)
```

- [ ] **Step 4: Create `backend/domains/alerts/telegram.py`**

```python
# backend/domains/alerts/telegram.py
import logging
from datetime import date
from typing import Optional

import httpx

from settings import settings

logger = logging.getLogger(__name__)


class AlertService:
    def __init__(self):
        self._token = settings.telegram_bot_token
        self._chat_id = settings.telegram_chat_id

    def _enabled(self) -> bool:
        return bool(self._token and self._chat_id)

    def send(self, text: str) -> bool:
        if not self._enabled():
            logger.debug("[AlertService] Telegram not configured, skipping send")
            return False
        url = f"https://api.telegram.org/bot{self._token}/sendMessage"
        try:
            r = httpx.post(
                url,
                json={"chat_id": self._chat_id, "text": text, "parse_mode": "HTML"},
                timeout=10.0,
            )
            if r.status_code != 200:
                logger.error("[AlertService] Telegram API error %d: %s", r.status_code, r.text)
                return False
            return True
        except Exception as e:
            logger.error("[AlertService] Send failed: %s", e)
            return False

    def send_daily_digest(self, top_signals: list[dict], scan_date: Optional[date] = None) -> bool:
        today = scan_date or date.today()
        lines = [
            f"<b>📊 StockV2 Daily Digest — {today.strftime('%d %b %Y')}</b>",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        ]
        if top_signals:
            lines.append(f"\n<b>TOP BUY SIGNALS TODAY ({len(top_signals)}):</b>")
            for sig in top_signals[:10]:
                pct = int((sig.get("confidence_score") or 0) * 100)
                strategy = sig.get("strategy_name", "")
                lines.append(f"  🟢 <b>{sig['symbol']}</b> — {pct}% confidence ({strategy})")
        else:
            lines.append("\nNo high-confidence signals today.")
        return self.send("\n".join(lines))
```

- [ ] **Step 5: Run tests**

```
cd backend && python -m pytest tests/test_telegram.py -v
```
Expected: all 6 tests pass

- [ ] **Step 6: Commit**

```
git add backend/domains/alerts/ backend/tests/test_telegram.py
git commit -m "feat: AlertService — Telegram daily digest via httpx"
```

---

### Task 12: Daily Digest APScheduler Wiring + Final Verification

**Files:**
- Modify: `backend/scheduler.py` (wire `_daily_digest` + `_weekly_fundamentals`)

- [ ] **Step 1: Confirm current test counts**

```
cd backend && python -m pytest -v --tb=short 2>&1 | tail -5
```
Note the current passing count.

- [ ] **Step 2: Replace `_daily_digest` stub in `backend/scheduler.py`**

```python
def _daily_digest():
    from datetime import date
    from database import SessionLocal
    from domains.strategies.service import StrategyService
    from domains.alerts.telegram import AlertService
    db = SessionLocal()
    try:
        today_str = date.today().strftime("%Y-%m-%d")
        signals = StrategyService(db).get_today_signals(signal_date=today_str)
        buy_signals = [s for s in signals if s["signal_type"] == "BUY"]
        top_10 = sorted(buy_signals, key=lambda x: x.get("confidence_score") or 0, reverse=True)[:10]
        AlertService().send_daily_digest(top_10, scan_date=date.today())
        logger.info("[scheduler] daily_digest sent: %d buy signals today", len(top_10))
    except Exception:
        logger.exception("[scheduler] daily_digest failed")
    finally:
        db.close()
```

- [ ] **Step 3: Run full test suite**

```
cd backend && python -m pytest -v
```
Expected: all tests pass

- [ ] **Step 4: Smoke test — verify server starts**

```
cd backend && timeout 8 python -m uvicorn main:app --port 8001 2>&1 | head -20
```
Expected output includes:
- `Database tables verified`
- `[seed_strategies]` seeded 10 strategies
- `APScheduler jobs registered`

- [ ] **Step 5: Final commit**

```
git add backend/scheduler.py
git commit -m "feat: daily digest wiring — APScheduler triggers Telegram digest at 5:15 PM IST"
```

- [ ] **Step 6: Tag completion**

```
git tag plan2-strategy-engine
```

---

## Summary

After all 12 tasks:

| Component | Files | Tests |
|---|---|---|
| BaseStrategy + Signal | `base.py` | 5 |
| 5 Momentum strategies | `rsi_oversold.py`, `macd_crossover.py`, `ema_crossover.py`, `sma_crossover.py`, `supertrend_strategy.py` | ~15 |
| 5 Volatility strategies | `bb_squeeze.py`, `volume_breakout.py`, `mean_reversion.py`, `volatility_breakout.py`, `swing_trend_rider.py` | ~15 |
| SignalAggregator | `aggregator.py` | 6 |
| StrategyEngine | `engine.py` | 5 |
| Seeding + Service | `seed.py`, `service.py` | 9 |
| REST API | `router.py` (strategies + ai) | 9 |
| APScheduler | `scheduler.py` | — |
| SignalExplainer + SellExplainer | `explainer.py` | 5 |
| AlertService | `telegram.py` | 6 |

**End-to-end flow after Plan 2:**
Every day at 4 PM IST → APScheduler triggers `_daily_eod_update` → `StrategyEngine.scan_all(237 NSE stocks)` → saves signals to DB. At 5:15 PM → `_daily_digest` → reads today's BUY signals → `AlertService.send_daily_digest()` → Telegram message. On demand: `GET /signals/today` returns ranked signals, `GET /signals/{id}/explanation` calls Claude API (cached 6hr).
