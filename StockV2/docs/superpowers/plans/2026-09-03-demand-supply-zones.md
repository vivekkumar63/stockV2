# Demand & Supply Zone Detection Engine — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detect, score, and serve demand/supply zones for every stock using six detection methods; pre-compute nightly; expose via a dedicated Zones page and Opportunities badge.

**Architecture:** New `backend/domains/zones/` domain with modular detectors → clusterer → scorer → entry engine, all orchestrated by `ZoneEngine`. Results stored per `(symbol, computed_date)` in `zone_analysis_results`. Frontend `ZonesPage` shows stock analysis panel + sortable ranking table.

**Tech Stack:** Python / FastAPI / SQLAlchemy / pandas / ta-lib (TA) / React / TypeScript / TailwindCSS / TanStack Query

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `backend/domains/zones/__init__.py` | NEW | Empty package marker |
| `backend/domains/zones/models.py` | NEW | ZoneLevel, Zone, ZoneResult, LongSetup, ShortSetup dataclasses |
| `backend/domains/zones/detectors.py` | NEW | 6 detector classes (PriceStructure, MA, Volume, Volatility, Momentum, Fibonacci) |
| `backend/domains/zones/clusterer.py` | NEW | ZoneClusterer: merge levels within 0.5×ATR, pad, assign freshness |
| `backend/domains/zones/scorer.py` | NEW | ZoneScorer: 6-component 0–100 score per zone |
| `backend/domains/zones/entry_engine.py` | NEW | EntryEngine: long/short entry, SL, T1/T2/T3, R:R, setup confidence |
| `backend/domains/zones/engine.py` | NEW | ZoneEngine: orchestrates detectors → cluster → score → entry → upsert DB |
| `backend/domains/zones/precompute.py` | NEW | ZonePrecomputer: batch all-symbols recompute with progress state |
| `backend/domains/zones/router.py` | NEW | 5 FastAPI endpoints under /zones/ |
| `backend/domains/data/indicators.py` | MODIFY | Add ema_50 and sma_200 columns |
| `backend/main.py` | MODIFY | DB table + indexes + router registration |
| `backend/scheduler.py` | MODIFY | Call ZonePrecomputer after daily_eod_update |
| `backend/domains/intelligence/router.py` | MODIFY | Add zone_summary join to top-opportunities |
| `backend/tests/test_zone_detectors.py` | NEW | Tests for detectors |
| `backend/tests/test_zone_clusterer.py` | NEW | Tests for ZoneClusterer |
| `backend/tests/test_zone_scorer.py` | NEW | Tests for ZoneScorer |
| `backend/tests/test_zone_entry_engine.py` | NEW | Tests for EntryEngine |
| `frontend/src/api/zones.ts` | NEW | TypeScript API client for zones endpoints |
| `frontend/src/pages/ZonesPage.tsx` | NEW | Zones page with analysis panel + ranking table |
| `frontend/src/components/NavBar.tsx` | MODIFY | Add Zones nav link |
| `frontend/src/App.tsx` | MODIFY | Add /zones route |

---

## Task 1: DB Migration + ema_50/sma_200 + Router Wire-up

**Files:**
- Modify: `backend/main.py`
- Modify: `backend/domains/data/indicators.py`

- [ ] **Step 1: Add ema_50 and sma_200 to IndicatorEngine**

Open `backend/domains/data/indicators.py`. In the `# ── Moving Averages ──` block, add after the `ema_21` line:

```python
        out["ema_50"]  = ta.trend.EMAIndicator(close, window=50).ema_indicator()  if n >= 50 else pd.Series(float("nan"), index=close.index)
        out["sma_200"] = ta.trend.SMAIndicator(close, window=200).sma_indicator() if n >= 200 else pd.Series(float("nan"), index=close.index)
```

- [ ] **Step 2: Verify indicators test still passes**

```bash
cd backend && python -m pytest tests/test_indicators.py -v
```
Expected: all PASS.

- [ ] **Step 3: Add zone_analysis_results table to main.py**

In `backend/main.py`, inside the `lifespan` function after the last existing `CREATE TABLE IF NOT EXISTS` block, add a new `try/except` block:

```python
    # Demand & Supply Zones table
    try:
        with engine.connect() as _conn:
            _conn.execute(text("""
                CREATE TABLE IF NOT EXISTS zone_analysis_results (
                    id                  SERIAL PRIMARY KEY,
                    symbol              VARCHAR(20) NOT NULL,
                    computed_date       DATE NOT NULL,
                    best_demand_score   REAL,
                    best_supply_score   REAL,
                    long_setup_score    REAL,
                    short_setup_score   REAL,
                    price_at_compute    REAL,
                    atr_at_compute      REAL,
                    rvol_at_compute     REAL,
                    position_tag        VARCHAR(20),
                    best_long_rr        REAL,
                    best_short_rr       REAL,
                    result_json         JSONB NOT NULL,
                    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (symbol, computed_date)
                )
            """))
            _conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_zones_date ON zone_analysis_results (computed_date)"
            ))
            _conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_zones_long_score "
                "ON zone_analysis_results (computed_date, long_setup_score DESC)"
            ))
            _conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_zones_demand_score "
                "ON zone_analysis_results (computed_date, best_demand_score DESC)"
            ))
            _conn.commit()
        logger.info("zone_analysis_results table verified")
    except Exception as e:
        logger.warning("zones table migration failed: %s", e)
```

- [ ] **Step 4: Register zones router in main.py**

At the top of `main.py` where other routers are imported (find the `from domains.` import block), add:

```python
from domains.zones.router import router as zones_router
```

In the `app.include_router(...)` block, add:

```python
app.include_router(zones_router, prefix="/api/v1", dependencies=[Depends(verify_api_key)])
```

(Do this AFTER creating the router file in Task 8. For now just add the import + include, the server won't break because the import is inside a try/except in practice — but actually it will fail. So add a stub `router.py` first.)

- [ ] **Step 5: Create stub router to allow startup**

Create `backend/domains/zones/__init__.py` (empty):
```python
```

Create `backend/domains/zones/router.py` stub:
```python
from fastapi import APIRouter
router = APIRouter(tags=["zones"])
```

- [ ] **Step 6: Commit**

```bash
git add backend/domains/data/indicators.py backend/main.py \
        backend/domains/zones/__init__.py backend/domains/zones/router.py
git commit -m "feat(zones): DB table + indicator columns + router stub"
```

---

## Task 2: Data Models

**Files:**
- Create: `backend/domains/zones/models.py`

- [ ] **Step 1: Create models.py**

```python
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ZoneLevel:
    """A single raw price level emitted by one detector."""
    price: float
    zone_type: str           # "demand" | "supply"
    source_tag: str          # e.g. "swing_low", "ema_50", "vol_node", "fib_61.8"
    strength_hint: float     # 0–1 hint from detector (used in scoring)
    timeframe: str = "daily" # "daily" | "weekly"
    bar_index: int = -1      # index in df where level was detected (for recency)
    volume_ratio: float = 1.0  # volume ratio at detection bar


@dataclass
class Zone:
    """A clustered zone after merging nearby ZoneLevels."""
    low: float
    high: float
    zone_type: str           # "demand" | "supply"
    source_tags: list[str] = field(default_factory=list)
    touch_count: int = 0
    last_reaction_pct: float = 0.0
    freshness: str = "fresh" # "fresh" | "tested" | "weakened"
    score: int = 0           # filled by ZoneScorer
    volume_at_zone: float = 1.0
    bar_index: int = -1      # most recent bar_index among merged levels
    strength_hint: float = 0.5

    @property
    def midpoint(self) -> float:
        return (self.low + self.high) / 2.0


@dataclass
class LongSetup:
    score: int
    ideal_entry: float
    aggressive_entry: float
    conservative_entry: float
    stop_loss: float
    t1: float
    t1_rr: float
    t2: float
    t2_rr: float
    t3: float
    t3_rr: float
    explanation: str
    invalidation: str


@dataclass
class ShortSetup:
    score: int
    ideal_entry: float
    aggressive_entry: float
    conservative_entry: float
    stop_loss: float
    t1: float
    t1_rr: float
    t2: float
    t2_rr: float
    t3: float
    t3_rr: float
    explanation: str
    invalidation: str


@dataclass
class ZoneResult:
    symbol: str
    demand_zones: list[Zone] = field(default_factory=list)
    supply_zones: list[Zone] = field(default_factory=list)
    long_setup: Optional[LongSetup] = None
    short_setup: Optional[ShortSetup] = None
    market_structure: str = "sideways"  # "bullish" | "bearish" | "sideways"
    atr: float = 0.0
    rvol: float = 1.0
    price: float = 0.0
    position_tag: str = "neutral"
```

- [ ] **Step 2: Verify import**

```bash
cd backend && python -c "from domains.zones.models import ZoneResult, Zone, ZoneLevel, LongSetup, ShortSetup; print('OK')"
```
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/domains/zones/models.py
git commit -m "feat(zones): data models — ZoneLevel, Zone, ZoneResult, LongSetup, ShortSetup"
```

---

## Task 3: Detectors

**Files:**
- Create: `backend/domains/zones/detectors.py`
- Create: `backend/tests/test_zone_detectors.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_zone_detectors.py`:

```python
import numpy as np
import pandas as pd
import pytest

from domains.data.indicators import IndicatorEngine
from domains.zones.detectors import (
    PriceStructureDetector, MADetector, VolumeDetector,
    VolatilityDetector, MomentumDetector, FibonacciDetector,
)
from domains.zones.models import ZoneLevel


@pytest.fixture
def df_ind():
    """500-bar synthetic OHLCV DataFrame with indicators computed."""
    np.random.seed(0)
    n = 500
    close = 1000 + np.cumsum(np.random.randn(n) * 8)
    close = np.clip(close, 100, 5000)
    df = pd.DataFrame({
        "open":   close * (1 + np.random.uniform(-0.005, 0.005, n)),
        "high":   close * (1 + np.random.uniform(0.001, 0.015, n)),
        "low":    close * (1 - np.random.uniform(0.001, 0.015, n)),
        "close":  close,
        "volume": np.random.randint(500_000, 5_000_000, n),
    })
    df.index = pd.date_range("2023-01-01", periods=n, freq="B")
    return IndicatorEngine.compute(df)


def test_price_structure_returns_zone_levels(df_ind):
    levels = PriceStructureDetector().detect(df_ind)
    assert isinstance(levels, list)
    assert all(isinstance(z, ZoneLevel) for z in levels)


def test_price_structure_types_are_demand_or_supply(df_ind):
    levels = PriceStructureDetector().detect(df_ind)
    assert all(z.zone_type in ("demand", "supply") for z in levels)


def test_price_structure_tags(df_ind):
    levels = PriceStructureDetector().detect(df_ind)
    tags = {z.source_tag for z in levels}
    assert tags.issubset({"swing_low", "swing_high"})


def test_ma_detector_returns_list(df_ind):
    levels = MADetector().detect(df_ind)
    assert isinstance(levels, list)


def test_ma_tags_known(df_ind):
    levels = MADetector().detect(df_ind)
    valid_tags = {"ema_9", "ema_21", "ema_50", "sma_200"}
    assert all(z.source_tag in valid_tags for z in levels)


def test_volume_detector_returns_list(df_ind):
    levels = VolumeDetector().detect(df_ind)
    assert isinstance(levels, list)


def test_volatility_detector_returns_list(df_ind):
    levels = VolatilityDetector().detect(df_ind)
    assert isinstance(levels, list)


def test_momentum_detector_returns_list(df_ind):
    levels = MomentumDetector().detect(df_ind)
    assert isinstance(levels, list)


def test_fibonacci_detector_returns_list(df_ind):
    levels = FibonacciDetector().detect(df_ind)
    assert isinstance(levels, list)


def test_all_detectors_handle_short_df():
    """Detectors must not crash when given <50 bars."""
    short = pd.DataFrame({
        "open": [100.0] * 30, "high": [102.0] * 30,
        "low": [98.0] * 30, "close": [101.0] * 30,
        "volume": [1_000_000] * 30,
    })
    short.index = pd.date_range("2024-01-01", periods=30, freq="B")
    df_ind = IndicatorEngine.compute(short)
    for cls in (PriceStructureDetector, MADetector, VolumeDetector,
                VolatilityDetector, MomentumDetector, FibonacciDetector):
        levels = cls().detect(df_ind)
        assert isinstance(levels, list)
```

- [ ] **Step 2: Run tests — verify FAIL**

```bash
cd backend && python -m pytest tests/test_zone_detectors.py -v 2>&1 | head -30
```
Expected: ImportError — `detectors.py` does not exist yet.

- [ ] **Step 3: Create detectors.py**

```python
from __future__ import annotations
import math
import pandas as pd
from .models import ZoneLevel


class PriceStructureDetector:
    """Swing highs → supply levels; swing lows → demand levels."""

    def detect(self, df: pd.DataFrame, window: int = 10) -> list[ZoneLevel]:
        if len(df) < window * 2 + 1:
            return []
        levels: list[ZoneLevel] = []
        close = df["close"].to_numpy()
        high  = df["high"].to_numpy()
        low   = df["low"].to_numpy()
        n = len(df)
        last_demand_idx = last_supply_idx = -999

        for i in range(window, n - window):
            # Swing low (demand)
            if low[i] == min(low[i - window:i + window + 1]):
                if i - last_demand_idx >= 3:
                    # Estimate reaction: how much did price rally from this low
                    future_max = max(close[i:min(i + 20, n)]) if i + 1 < n else close[i]
                    reaction_pct = (future_max - low[i]) / low[i] * 100
                    volume_ratio = float(df["volume_ratio"].iloc[i]) if "volume_ratio" in df.columns else 1.0
                    levels.append(ZoneLevel(
                        price=float(low[i]),
                        zone_type="demand",
                        source_tag="swing_low",
                        strength_hint=min(1.0, reaction_pct / 10),
                        bar_index=i,
                        volume_ratio=volume_ratio if math.isfinite(volume_ratio) else 1.0,
                    ))
                    last_demand_idx = i

            # Swing high (supply)
            if high[i] == max(high[i - window:i + window + 1]):
                if i - last_supply_idx >= 3:
                    future_min = min(close[i:min(i + 20, n)]) if i + 1 < n else close[i]
                    reaction_pct = (high[i] - future_min) / high[i] * 100
                    volume_ratio = float(df["volume_ratio"].iloc[i]) if "volume_ratio" in df.columns else 1.0
                    levels.append(ZoneLevel(
                        price=float(high[i]),
                        zone_type="supply",
                        source_tag="swing_high",
                        strength_hint=min(1.0, reaction_pct / 10),
                        bar_index=i,
                        volume_ratio=volume_ratio if math.isfinite(volume_ratio) else 1.0,
                    ))
                    last_supply_idx = i

        return levels


class MADetector:
    """MA levels become zones if price bounced/rejected ≥2× in last 60 bars."""

    _MAS = [
        ("ema_9",   "ema_9"),
        ("ema_21",  "ema_21"),
        ("ema_50",  "ema_50"),
        ("sma_200", "sma_200"),
    ]

    def detect(self, df: pd.DataFrame) -> list[ZoneLevel]:
        if len(df) < 10:
            return []
        levels: list[ZoneLevel] = []
        price = float(df["close"].iloc[-1])
        n = len(df)
        close = df["close"].to_numpy()
        low   = df["low"].to_numpy()
        high  = df["high"].to_numpy()

        for col, tag in self._MAS:
            if col not in df.columns:
                continue
            ma_val = df[col].iloc[-1]
            if not math.isfinite(ma_val):
                continue
            ma_val = float(ma_val)
            ma_series = df[col].to_numpy()

            # Count bounces/rejections in last 60 bars
            lookback = min(60, n)
            touches = 0
            for i in range(n - lookback, n):
                if not math.isfinite(ma_series[i]):
                    continue
                # Demand bounce: price touched MA from above and bounced
                if low[i] <= ma_series[i] * 1.01 and close[i] > ma_series[i]:
                    touches += 1
                # Supply rejection: price touched MA from below and rejected
                if high[i] >= ma_series[i] * 0.99 and close[i] < ma_series[i]:
                    touches += 1

            if touches < 2:
                continue

            if price > ma_val:
                zone_type = "demand"
            else:
                zone_type = "supply"

            levels.append(ZoneLevel(
                price=ma_val,
                zone_type=zone_type,
                source_tag=tag,
                strength_hint=min(1.0, touches / 5),
                bar_index=n - 1,
            ))

        return levels


class VolumeDetector:
    """High-volume bars (vol ≥ 1.5× 20d avg) that preceded a directional move."""

    def detect(self, df: pd.DataFrame) -> list[ZoneLevel]:
        if len(df) < 22 or "volume_ratio" not in df.columns:
            return []
        levels: list[ZoneLevel] = []
        n = len(df)
        close = df["close"].to_numpy()
        vol_ratio = df["volume_ratio"].to_numpy()

        for i in range(1, n - 5):
            vr = vol_ratio[i]
            if not math.isfinite(vr) or vr < 1.5:
                continue
            future_close = close[min(i + 5, n - 1)]
            move_pct = (future_close - close[i]) / close[i] * 100
            if move_pct >= 1.5:
                levels.append(ZoneLevel(
                    price=float(close[i]),
                    zone_type="demand",
                    source_tag="vol_node",
                    strength_hint=min(1.0, abs(move_pct) / 10),
                    bar_index=i,
                    volume_ratio=float(vr),
                ))
            elif move_pct <= -1.5:
                levels.append(ZoneLevel(
                    price=float(close[i]),
                    zone_type="supply",
                    source_tag="vol_node",
                    strength_hint=min(1.0, abs(move_pct) / 10),
                    bar_index=i,
                    volume_ratio=float(vr),
                ))

        return levels


class VolatilityDetector:
    """Bollinger Bands: lower band → demand, upper band → supply.
    Only emit if current price is within 1×ATR of the band."""

    def detect(self, df: pd.DataFrame) -> list[ZoneLevel]:
        required = {"bb_lower", "bb_upper", "atr_14"}
        if len(df) < 20 or not required.issubset(df.columns):
            return []
        price = float(df["close"].iloc[-1])
        atr   = float(df["atr_14"].iloc[-1])
        if not math.isfinite(atr) or atr <= 0:
            return []

        levels: list[ZoneLevel] = []
        bb_lower = float(df["bb_lower"].iloc[-1])
        bb_upper = float(df["bb_upper"].iloc[-1])

        if math.isfinite(bb_lower) and abs(price - bb_lower) <= atr:
            levels.append(ZoneLevel(
                price=bb_lower,
                zone_type="demand",
                source_tag="bb_lower",
                strength_hint=0.5,
                bar_index=len(df) - 1,
            ))

        if math.isfinite(bb_upper) and abs(price - bb_upper) <= atr:
            levels.append(ZoneLevel(
                price=bb_upper,
                zone_type="supply",
                source_tag="bb_upper",
                strength_hint=0.5,
                bar_index=len(df) - 1,
            ))

        return levels


class MomentumDetector:
    """RSI oversold bounce → demand; RSI overbought rejection → supply."""

    def detect(self, df: pd.DataFrame) -> list[ZoneLevel]:
        if len(df) < 15 or "rsi_14" not in df.columns:
            return []
        levels: list[ZoneLevel] = []
        n = len(df)
        rsi = df["rsi_14"].to_numpy()
        close = df["close"].to_numpy()

        for i in range(1, n):
            if not math.isfinite(rsi[i]) or not math.isfinite(rsi[i - 1]):
                continue
            # Oversold bounce: RSI was < 35 and is now rising
            if rsi[i - 1] < 35 and rsi[i] > rsi[i - 1]:
                levels.append(ZoneLevel(
                    price=float(close[i]),
                    zone_type="demand",
                    source_tag="rsi_oversold",
                    strength_hint=min(1.0, (35 - rsi[i - 1]) / 35),
                    bar_index=i,
                ))
            # Overbought rejection: RSI was > 65 and is now falling
            if rsi[i - 1] > 65 and rsi[i] < rsi[i - 1]:
                levels.append(ZoneLevel(
                    price=float(close[i]),
                    zone_type="supply",
                    source_tag="rsi_overbought",
                    strength_hint=min(1.0, (rsi[i - 1] - 65) / 35),
                    bar_index=i,
                ))

        return levels


class FibonacciDetector:
    """Fibonacci retracement levels from the last major swing.
    Only emit if price reacted within 0.3×ATR of the level."""

    _FIBS = [0.236, 0.382, 0.5, 0.618, 0.786]

    def detect(self, df: pd.DataFrame) -> list[ZoneLevel]:
        if len(df) < 50 or "atr_14" not in df.columns:
            return []
        atr = float(df["atr_14"].iloc[-1])
        if not math.isfinite(atr) or atr <= 0:
            return []

        n = len(df)
        lookback = min(120, n)
        window = df.iloc[-lookback:]
        swing_high = float(window["high"].max())
        swing_low  = float(window["low"].min())
        rng = swing_high - swing_low
        if rng < atr:
            return []

        close_arr = df["close"].to_numpy()
        price_now = float(df["close"].iloc[-1])
        # Determine trend: uptrend if current price > midpoint
        uptrend = price_now > (swing_high + swing_low) / 2

        levels: list[ZoneLevel] = []
        for fib in self._FIBS:
            if uptrend:
                # Demand levels = retracements from high during uptrend
                fib_price = swing_high - fib * rng
                zone_type = "demand"
            else:
                # Supply levels = retracements from low during downtrend
                fib_price = swing_low + fib * rng
                zone_type = "supply"

            # Check if price reacted near this level in the last lookback
            reacted = False
            for i in range(n - lookback, n):
                if abs(close_arr[i] - fib_price) <= 0.3 * atr:
                    reacted = True
                    break
            if not reacted:
                continue

            tag = f"fib_{round(fib * 100, 1)}"  # e.g. "fib_61.8"
            levels.append(ZoneLevel(
                price=fib_price,
                zone_type=zone_type,
                source_tag=tag,
                strength_hint=0.6,
                bar_index=n - 1,
            ))

        return levels
```

- [ ] **Step 4: Run tests — verify PASS**

```bash
cd backend && python -m pytest tests/test_zone_detectors.py -v
```
Expected: all 11 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/domains/zones/detectors.py backend/tests/test_zone_detectors.py
git commit -m "feat(zones): detector classes — price, MA, volume, volatility, momentum, fibonacci"
```

---

## Task 4: Clusterer

**Files:**
- Create: `backend/domains/zones/clusterer.py`
- Create: `backend/tests/test_zone_clusterer.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_zone_clusterer.py`:

```python
import pytest
from domains.zones.clusterer import ZoneClusterer
from domains.zones.models import ZoneLevel, Zone


def _level(price: float, zone_type: str, tag: str = "swing_low") -> ZoneLevel:
    return ZoneLevel(price=price, zone_type=zone_type, source_tag=tag,
                     strength_hint=0.5, bar_index=10)


def test_single_level_becomes_zone():
    levels = [_level(1000.0, "demand")]
    atr = 20.0
    zones = ZoneClusterer().cluster(levels, atr)
    assert len(zones) == 1
    assert zones[0].zone_type == "demand"
    assert zones[0].low < 1000.0 < zones[0].high


def test_nearby_levels_merge():
    """Two demand levels within 0.5×ATR merge into one zone."""
    levels = [_level(1000.0, "demand"), _level(1005.0, "demand")]
    atr = 20.0  # 0.5*ATR = 10 — levels 5 apart should merge
    zones = ZoneClusterer().cluster(levels, atr)
    assert len(zones) == 1


def test_far_levels_stay_separate():
    """Two demand levels 15 points apart with ATR=20 (0.5×ATR=10) stay separate."""
    levels = [_level(1000.0, "demand"), _level(1020.0, "demand")]
    atr = 10.0  # 0.5*ATR = 5 — levels 20 apart should NOT merge
    zones = ZoneClusterer().cluster(levels, atr)
    assert len(zones) == 2


def test_demand_and_supply_not_merged():
    levels = [_level(1000.0, "demand"), _level(1000.0, "supply")]
    zones = ZoneClusterer().cluster(levels, atr=20.0)
    assert len(zones) == 2
    types = {z.zone_type for z in zones}
    assert "demand" in types and "supply" in types


def test_source_tags_collected():
    levels = [
        _level(1000.0, "demand", "swing_low"),
        _level(1004.0, "demand", "ema_50"),
    ]
    atr = 20.0
    zones = ZoneClusterer().cluster(levels, atr)
    assert len(zones) == 1
    assert "swing_low" in zones[0].source_tags
    assert "ema_50" in zones[0].source_tags


def test_freshness_fresh():
    levels = [_level(1000.0, "demand")]
    zones = ZoneClusterer().cluster(levels, atr=20.0)
    assert zones[0].freshness == "fresh"


def test_zone_padding():
    levels = [_level(1000.0, "demand")]
    atr = 20.0
    zone = ZoneClusterer().cluster(levels, atr)[0]
    assert zone.low == pytest.approx(1000.0 - 0.1 * atr)
    assert zone.high == pytest.approx(1000.0 + 0.1 * atr)
```

- [ ] **Step 2: Run — verify FAIL**

```bash
cd backend && python -m pytest tests/test_zone_clusterer.py -v 2>&1 | head -20
```
Expected: ImportError.

- [ ] **Step 3: Create clusterer.py**

```python
from __future__ import annotations
from .models import Zone, ZoneLevel


class ZoneClusterer:
    def cluster(self, levels: list[ZoneLevel], atr: float) -> list[Zone]:
        """Merge nearby ZoneLevels (within 0.5×ATR) into Zones."""
        if not levels or atr <= 0:
            return []

        demand = sorted([l for l in levels if l.zone_type == "demand"], key=lambda l: l.price)
        supply = sorted([l for l in levels if l.zone_type == "supply"], key=lambda l: l.price)

        return self._merge(demand, atr, "demand") + self._merge(supply, atr, "supply")

    def _merge(self, sorted_levels: list[ZoneLevel], atr: float, zone_type: str) -> list[Zone]:
        if not sorted_levels:
            return []
        threshold = 0.5 * atr
        groups: list[list[ZoneLevel]] = []
        current_group = [sorted_levels[0]]

        for lvl in sorted_levels[1:]:
            if lvl.price - current_group[-1].price <= threshold:
                current_group.append(lvl)
            else:
                groups.append(current_group)
                current_group = [lvl]
        groups.append(current_group)

        zones: list[Zone] = []
        for grp in groups:
            prices = [l.price for l in grp]
            min_p, max_p = min(prices), max(prices)
            source_tags = list(dict.fromkeys(l.source_tag for l in grp))  # dedup, preserve order
            avg_strength = sum(l.strength_hint for l in grp) / len(grp)
            best_bar    = max(l.bar_index for l in grp)
            avg_vol_ratio = sum(l.volume_ratio for l in grp) / len(grp)

            # Approximate touch count from number of overlapping levels
            touch_count = max(0, len(grp) - 1)
            if touch_count <= 1:
                freshness = "fresh"
            elif touch_count <= 3:
                freshness = "tested"
            else:
                freshness = "weakened"

            # last_reaction_pct: best strength_hint * 10 as proxy
            last_reaction_pct = round(avg_strength * 10, 2)

            zones.append(Zone(
                low=round(min_p - 0.1 * atr, 2),
                high=round(max_p + 0.1 * atr, 2),
                zone_type=zone_type,
                source_tags=source_tags,
                touch_count=touch_count,
                last_reaction_pct=last_reaction_pct,
                freshness=freshness,
                volume_at_zone=avg_vol_ratio,
                bar_index=best_bar,
                strength_hint=avg_strength,
            ))

        return zones
```

- [ ] **Step 4: Run — verify PASS**

```bash
cd backend && python -m pytest tests/test_zone_clusterer.py -v
```
Expected: all 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/domains/zones/clusterer.py backend/tests/test_zone_clusterer.py
git commit -m "feat(zones): ZoneClusterer — merge levels within 0.5×ATR, pad, assign freshness"
```

---

## Task 5: Scorer

**Files:**
- Create: `backend/domains/zones/scorer.py`
- Create: `backend/tests/test_zone_scorer.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_zone_scorer.py`:

```python
import pytest
from domains.zones.scorer import ZoneScorer
from domains.zones.models import Zone


def _zone(tags: list[str], reaction: float = 5.0, vol: float = 2.0,
          touch: int = 0, bar_index: int = 400, n_bars: int = 500) -> Zone:
    return Zone(
        low=950.0, high=960.0, zone_type="demand",
        source_tags=tags, touch_count=touch,
        last_reaction_pct=reaction, freshness="fresh",
        volume_at_zone=vol, bar_index=bar_index,
        strength_hint=0.6,
    )


def test_score_is_0_to_100():
    zone = _zone(["swing_low"])
    scored = ZoneScorer().score(zone, atr=20.0, n_bars=500, price=970.0)
    assert 0 <= scored.score <= 100


def test_more_unique_sources_scores_higher():
    few = _zone(["swing_low"])
    many = _zone(["swing_low", "ema_50", "vol_node", "fib_0.618"])
    s_few  = ZoneScorer().score(few,  atr=20.0, n_bars=500, price=970.0)
    s_many = ZoneScorer().score(many, atr=20.0, n_bars=500, price=970.0)
    assert s_many.score > s_few.score


def test_correlated_ema9_ema21_count_as_one():
    corr  = _zone(["ema_9", "ema_21"])       # correlated — counts as 1
    uncorr = _zone(["ema_9", "vol_node"])    # independent — counts as 2
    s_corr  = ZoneScorer().score(corr,  atr=20.0, n_bars=500, price=970.0)
    s_uncorr = ZoneScorer().score(uncorr, atr=20.0, n_bars=500, price=970.0)
    assert s_uncorr.score >= s_corr.score


def test_closer_zone_scores_higher():
    close_zone = _zone(["swing_low"])  # bar_index=400, price=970 (zone midpoint 955)
    far_zone   = _zone(["swing_low"], bar_index=10)
    s_close = ZoneScorer().score(close_zone, atr=20.0, n_bars=500, price=970.0)
    s_far   = ZoneScorer().score(far_zone,   atr=20.0, n_bars=500, price=970.0)
    # More recent bar_index = higher recency score
    assert s_close.score >= s_far.score


def test_score_returns_zone_with_score_field():
    zone = _zone(["swing_low", "ema_50"])
    result = ZoneScorer().score(zone, atr=20.0, n_bars=500, price=960.0)
    assert isinstance(result, Zone)
    assert result.score > 0
```

- [ ] **Step 2: Run — verify FAIL**

```bash
cd backend && python -m pytest tests/test_zone_scorer.py -v 2>&1 | head -20
```
Expected: ImportError.

- [ ] **Step 3: Create scorer.py**

```python
from __future__ import annotations
import math
from .models import Zone

# Tags that are correlated (EMA family) — counted as max 1 unique source each group
_CORRELATED_GROUPS = [
    {"ema_9", "ema_21"},
]


def _count_unique_sources(tags: list[str]) -> int:
    """Count independent confirmations, applying correlated-indicator guard."""
    counted: set[str] = set()
    merged: set[str] = set()
    for tag in tags:
        for group in _CORRELATED_GROUPS:
            if tag in group:
                representative = min(group)  # e.g. "ema_21"
                if representative not in merged:
                    merged.add(representative)
                    counted.add(representative)
                break
        else:
            counted.add(tag)
    return len(counted)


class ZoneScorer:
    """Score each Zone 0–100 from 6 independent components."""

    def score(self, zone: Zone, *, atr: float, n_bars: int, price: float) -> Zone:
        """Return a copy of zone with `.score` filled."""
        s = 0

        # 1. Confirmations (0–30): unique independent source tags
        unique = _count_unique_sources(zone.source_tags)
        s += min(30, unique * 8)

        # 2. Reaction quality (0–20): last_reaction_pct; 10% reaction → full 20 pts
        s += min(20, int(zone.last_reaction_pct / 10 * 20))

        # 3. Volume at zone (0–15): volume_ratio; 3× = full
        vol = zone.volume_at_zone if math.isfinite(zone.volume_at_zone) else 1.0
        s += min(15, int((vol - 1.0) / 2.0 * 15))

        # 4. Timeframe weight (0–15): daily zones always daily for now
        s += 10  # daily = 10/15

        # 5. Recency (0–10): more recent bar_index = higher
        if n_bars > 0:
            recency = zone.bar_index / n_bars
            s += int(recency * 10)

        # 6. ATR proximity (0–10): price within 2 ATR of zone midpoint
        if atr > 0:
            dist = abs(price - zone.midpoint)
            proximity = max(0.0, 1.0 - dist / (2 * atr))
            s += int(proximity * 10)

        zone.score = min(100, max(0, s))
        return zone

    def score_all(self, zones: list[Zone], *, atr: float, n_bars: int, price: float) -> list[Zone]:
        return [self.score(z, atr=atr, n_bars=n_bars, price=price) for z in zones]
```

- [ ] **Step 4: Run — verify PASS**

```bash
cd backend && python -m pytest tests/test_zone_scorer.py -v
```
Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/domains/zones/scorer.py backend/tests/test_zone_scorer.py
git commit -m "feat(zones): ZoneScorer — 6-component 0-100 scoring with correlated-indicator guard"
```

---

## Task 6: Entry Engine

**Files:**
- Create: `backend/domains/zones/entry_engine.py`
- Create: `backend/tests/test_zone_entry_engine.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_zone_entry_engine.py`:

```python
import pytest
from domains.zones.entry_engine import EntryEngine
from domains.zones.models import Zone


def _zone(low: float, high: float, zone_type: str = "demand", score: int = 80) -> Zone:
    z = Zone(low=low, high=high, zone_type=zone_type, score=score)
    return z


def test_long_entry_ideal_is_midpoint():
    demand = _zone(960.0, 980.0)
    result = EntryEngine().compute_long(demand, supply_zones=[], atr=20.0,
                                        rsi=45.0, trend="bullish", n_bars=500)
    assert result.ideal_entry == pytest.approx((960.0 + 980.0) / 2.0)


def test_long_stop_loss_below_zone():
    demand = _zone(960.0, 980.0)
    result = EntryEngine().compute_long(demand, supply_zones=[], atr=20.0,
                                        rsi=45.0, trend="bullish", n_bars=500)
    assert result.stop_loss == pytest.approx(960.0 - 0.3 * 20.0)


def test_long_t1_uses_supply_zone():
    demand = _zone(960.0, 980.0)
    supply = _zone(1050.0, 1070.0, zone_type="supply")
    result = EntryEngine().compute_long(demand, supply_zones=[supply], atr=20.0,
                                        rsi=45.0, trend="bullish", n_bars=500)
    assert result.t1 == pytest.approx(1050.0)


def test_long_t1_fallback_when_no_supply():
    demand = _zone(960.0, 980.0)
    result = EntryEngine().compute_long(demand, supply_zones=[], atr=20.0,
                                        rsi=45.0, trend="bullish", n_bars=500)
    assert result.t1 == pytest.approx(970.0 + 2 * 20.0)  # midpoint + 2*ATR


def test_long_rr_positive():
    demand = _zone(960.0, 980.0)
    supply = _zone(1050.0, 1070.0, zone_type="supply")
    result = EntryEngine().compute_long(demand, supply_zones=[supply], atr=20.0,
                                        rsi=45.0, trend="bullish", n_bars=500)
    assert result.t1_rr > 0


def test_short_entry_ideal_is_midpoint():
    supply = _zone(1050.0, 1070.0, zone_type="supply")
    result = EntryEngine().compute_short(supply, demand_zones=[], atr=20.0,
                                          rsi=65.0, trend="bearish", n_bars=500)
    assert result.ideal_entry == pytest.approx((1050.0 + 1070.0) / 2.0)


def test_short_stop_loss_above_zone():
    supply = _zone(1050.0, 1070.0, zone_type="supply")
    result = EntryEngine().compute_short(supply, demand_zones=[], atr=20.0,
                                          rsi=65.0, trend="bearish", n_bars=500)
    assert result.stop_loss == pytest.approx(1070.0 + 0.3 * 20.0)


def test_setup_score_0_to_100():
    demand = _zone(960.0, 980.0)
    result = EntryEngine().compute_long(demand, supply_zones=[], atr=20.0,
                                        rsi=45.0, trend="bullish", n_bars=500)
    assert 0 <= result.score <= 100
```

- [ ] **Step 2: Run — verify FAIL**

```bash
cd backend && python -m pytest tests/test_zone_entry_engine.py -v 2>&1 | head -20
```
Expected: ImportError.

- [ ] **Step 3: Create entry_engine.py**

```python
from __future__ import annotations
import math
from .models import Zone, LongSetup, ShortSetup


class EntryEngine:

    def compute_long(
        self,
        demand_zone: Zone,
        supply_zones: list[Zone],
        atr: float,
        rsi: float = 50.0,
        trend: str = "sideways",
        n_bars: int = 500,
    ) -> LongSetup:
        ideal = demand_zone.midpoint
        aggressive = demand_zone.high
        conservative = demand_zone.low - 0.2 * atr
        sl = round(demand_zone.low - 0.3 * atr, 2)

        # Targets: use supply zones sorted by low ascending
        supply_above = sorted(
            [z for z in supply_zones if z.low > ideal],
            key=lambda z: z.low,
        )

        def _rr(target: float) -> float:
            denom = ideal - sl
            if denom <= 0:
                return 0.0
            return round((target - ideal) / denom, 2)

        t1 = round(supply_above[0].low, 2) if supply_above else round(ideal + 2 * atr, 2)
        t2 = round(supply_above[1].low, 2) if len(supply_above) > 1 else round(ideal + 4 * atr, 2)
        t3 = round(supply_above[2].low, 2) if len(supply_above) > 2 else round(ideal + 6 * atr, 2)

        score = self._long_score(demand_zone, _rr(t1), trend, rsi)
        explanation = self._long_explanation(demand_zone, ideal, sl, t1, _rr(t1), t2, atr)
        invalidation = f"Invalidated if close below ₹{sl:,.2f} on above-average volume"

        return LongSetup(
            score=score,
            ideal_entry=round(ideal, 2),
            aggressive_entry=round(aggressive, 2),
            conservative_entry=round(conservative, 2),
            stop_loss=sl,
            t1=t1, t1_rr=_rr(t1),
            t2=t2, t2_rr=_rr(t2),
            t3=t3, t3_rr=_rr(t3),
            explanation=explanation,
            invalidation=invalidation,
        )

    def compute_short(
        self,
        supply_zone: Zone,
        demand_zones: list[Zone],
        atr: float,
        rsi: float = 50.0,
        trend: str = "sideways",
        n_bars: int = 500,
    ) -> ShortSetup:
        ideal = supply_zone.midpoint
        aggressive = supply_zone.low
        conservative = supply_zone.high + 0.2 * atr
        sl = round(supply_zone.high + 0.3 * atr, 2)

        demand_below = sorted(
            [z for z in demand_zones if z.high < ideal],
            key=lambda z: z.high, reverse=True,
        )

        def _rr(target: float) -> float:
            denom = sl - ideal
            if denom <= 0:
                return 0.0
            return round((ideal - target) / denom, 2)

        t1 = round(demand_below[0].high, 2) if demand_below else round(ideal - 2 * atr, 2)
        t2 = round(demand_below[1].high, 2) if len(demand_below) > 1 else round(ideal - 4 * atr, 2)
        t3 = round(demand_below[2].high, 2) if len(demand_below) > 2 else round(ideal - 6 * atr, 2)

        score = self._short_score(supply_zone, _rr(t1), trend, rsi)
        explanation = self._short_explanation(supply_zone, ideal, sl, t1, _rr(t1), t2, atr)
        invalidation = f"Invalidated if close above ₹{sl:,.2f} on above-average volume"

        return ShortSetup(
            score=score,
            ideal_entry=round(ideal, 2),
            aggressive_entry=round(aggressive, 2),
            conservative_entry=round(conservative, 2),
            stop_loss=sl,
            t1=t1, t1_rr=_rr(t1),
            t2=t2, t2_rr=_rr(t2),
            t3=t3, t3_rr=_rr(t3),
            explanation=explanation,
            invalidation=invalidation,
        )

    # ── Scoring helpers ────────────────────────────────────────────────────────

    def _long_score(self, zone: Zone, best_rr: float, trend: str, rsi: float) -> int:
        # Zone strength 40%, R:R 30%, trend alignment 20%, RSI 10%
        zone_pts  = int(zone.score * 0.4)
        rr_pts    = min(30, int(max(0.0, min(best_rr, 5.0)) / 5.0 * 30))
        trend_pts = 20 if trend == "bullish" else 10 if trend == "sideways" else 0
        rsi_pts   = min(10, int(max(0.0, (50 - rsi)) / 50.0 * 10)) if rsi < 50 else 0
        return min(100, zone_pts + rr_pts + trend_pts + rsi_pts)

    def _short_score(self, zone: Zone, best_rr: float, trend: str, rsi: float) -> int:
        zone_pts  = int(zone.score * 0.4)
        rr_pts    = min(30, int(max(0.0, min(best_rr, 5.0)) / 5.0 * 30))
        trend_pts = 20 if trend == "bearish" else 10 if trend == "sideways" else 0
        rsi_pts   = min(10, int(max(0.0, (rsi - 50)) / 50.0 * 10)) if rsi > 50 else 0
        return min(100, zone_pts + rr_pts + trend_pts + rsi_pts)

    def _long_explanation(self, zone: Zone, entry: float, sl: float,
                           t1: float, rr: float, t2: float, atr: float) -> str:
        tags = ", ".join(zone.source_tags[:3]) if zone.source_tags else "price structure"
        dist_atr = round(abs(entry - zone.midpoint) / atr, 1) if atr > 0 else 0
        return (
            f"Price is {dist_atr} ATR above a {zone.freshness} demand zone "
            f"(₹{zone.low:,.0f}–₹{zone.high:,.0f}) supported by {tags}. "
            f"Entry at ₹{entry:,.0f} with SL ₹{sl:,.0f}, "
            f"first target ₹{t1:,.0f} (R:R 1:{rr}), second target ₹{t2:,.0f}."
        )

    def _short_explanation(self, zone: Zone, entry: float, sl: float,
                            t1: float, rr: float, t2: float, atr: float) -> str:
        tags = ", ".join(zone.source_tags[:3]) if zone.source_tags else "price structure"
        dist_atr = round(abs(entry - zone.midpoint) / atr, 1) if atr > 0 else 0
        return (
            f"Price is {dist_atr} ATR below a {zone.freshness} supply zone "
            f"(₹{zone.low:,.0f}–₹{zone.high:,.0f}) confirmed by {tags}. "
            f"Short entry at ₹{entry:,.0f} with SL ₹{sl:,.0f}, "
            f"first target ₹{t1:,.0f} (R:R 1:{rr})."
        )
```

- [ ] **Step 4: Run — verify PASS**

```bash
cd backend && python -m pytest tests/test_zone_entry_engine.py -v
```
Expected: all 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/domains/zones/entry_engine.py backend/tests/test_zone_entry_engine.py
git commit -m "feat(zones): EntryEngine — long/short entry, SL, T1/T2/T3, R:R, setup confidence"
```

---

## Task 7: ZoneEngine + ZonePrecomputer

**Files:**
- Create: `backend/domains/zones/engine.py`
- Create: `backend/domains/zones/precompute.py`

- [ ] **Step 1: Create engine.py**

```python
from __future__ import annotations
import json
import logging
import math
from dataclasses import asdict
from datetime import date

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from domains.data.indicators import IndicatorEngine
from .clusterer import ZoneClusterer
from .detectors import (
    FibonacciDetector, MADetector, MomentumDetector,
    PriceStructureDetector, VolatilityDetector, VolumeDetector,
)
from .entry_engine import EntryEngine
from .models import Zone, ZoneLevel, ZoneResult
from .scorer import ZoneScorer

logger = logging.getLogger(__name__)

_DETECTORS = [
    PriceStructureDetector(),
    MADetector(),
    VolumeDetector(),
    VolatilityDetector(),
    MomentumDetector(),
    FibonacciDetector(),
]


def _load_prices(db: Session, symbol: str) -> pd.DataFrame:
    rows = db.execute(
        text("""
            SELECT date, open, high, low, close, volume FROM (
                SELECT date, open, high, low, close, volume
                FROM stock_prices_daily
                WHERE symbol = :s
                ORDER BY date DESC LIMIT 500
            ) ORDER BY date ASC
        """),
        {"s": symbol},
    ).fetchall()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"])
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = df[col].astype(float)
    return df


def _market_structure(df: pd.DataFrame) -> str:
    if "ema_50" not in df.columns or len(df) < 10:
        return "sideways"
    close = float(df["close"].iloc[-1])
    ema50 = float(df["ema_50"].iloc[-1])
    if not math.isfinite(ema50):
        return "sideways"
    if close > ema50 * 1.02:
        return "bullish"
    if close < ema50 * 0.98:
        return "bearish"
    return "sideways"


def _position_tag(price: float, demand_zones: list[Zone], supply_zones: list[Zone], atr: float) -> str:
    for z in demand_zones:
        if z.low <= price <= z.high:
            return "in_demand"
    for z in supply_zones:
        if z.low <= price <= z.high:
            return "in_supply"
    # breakout: price above the highest supply zone high + 0.2×ATR
    if supply_zones:
        highest_supply = max(z.high for z in supply_zones)
        if price > highest_supply + 0.2 * atr:
            return "breakout"
    # near_demand: price above nearest demand by <= 1.5×ATR
    if demand_zones:
        candidates = [z.high for z in demand_zones if z.high < price]
        if candidates:
            nearest_demand = max(candidates)
            if price - nearest_demand <= 1.5 * atr:
                return "near_demand"
    # near_supply: price below nearest supply by <= 1.5×ATR
    if supply_zones:
        candidates = [z.low for z in supply_zones if z.low > price]
        if candidates:
            nearest_supply = min(candidates)
            if nearest_supply - price <= 1.5 * atr:
                return "near_supply"
    return "neutral"


def _zone_to_dict(z: Zone) -> dict:
    return {
        "low": z.low, "high": z.high, "score": z.score,
        "freshness": z.freshness, "touch_count": z.touch_count,
        "last_reaction_pct": z.last_reaction_pct,
        "source_tags": z.source_tags,
    }


def _setup_to_dict(s) -> dict | None:
    if s is None:
        return None
    return {
        "score": s.score,
        "ideal_entry": s.ideal_entry, "aggressive_entry": s.aggressive_entry,
        "conservative_entry": s.conservative_entry, "stop_loss": s.stop_loss,
        "t1": s.t1, "t1_rr": s.t1_rr,
        "t2": s.t2, "t2_rr": s.t2_rr,
        "t3": s.t3, "t3_rr": s.t3_rr,
        "explanation": s.explanation, "invalidation": s.invalidation,
    }


class ZoneEngine:
    def analyze(self, symbol: str, db: Session) -> ZoneResult | None:
        df = _load_prices(db, symbol)
        if df.empty or len(df) < 30:
            logger.warning("[ZoneEngine] insufficient data for %s", symbol)
            return None
        try:
            df_ind = IndicatorEngine.compute(df)
        except Exception as e:
            logger.warning("[ZoneEngine] indicator compute failed for %s: %s", symbol, e)
            return None

        price = float(df_ind["close"].iloc[-1])
        atr   = float(df_ind["atr_14"].iloc[-1]) if "atr_14" in df_ind.columns else 0.0
        rvol  = float(df_ind["volume_ratio"].iloc[-1]) if "volume_ratio" in df_ind.columns else 1.0
        n = len(df_ind)
        if not math.isfinite(atr) or atr <= 0:
            atr = price * 0.01  # fallback: 1% of price

        # Detect raw levels
        levels: list[ZoneLevel] = []
        for det in _DETECTORS:
            try:
                levels.extend(det.detect(df_ind))
            except Exception as e:
                logger.debug("[ZoneEngine] detector %s failed on %s: %s", det.__class__.__name__, symbol, e)

        # Cluster
        all_zones = ZoneClusterer().cluster(levels, atr)

        # Score
        demand_zones = ZoneScorer().score_all(
            [z for z in all_zones if z.zone_type == "demand"],
            atr=atr, n_bars=n, price=price,
        )
        supply_zones = ZoneScorer().score_all(
            [z for z in all_zones if z.zone_type == "supply"],
            atr=atr, n_bars=n, price=price,
        )

        # Sort by score desc
        demand_zones.sort(key=lambda z: z.score, reverse=True)
        supply_zones.sort(key=lambda z: z.score, reverse=True)

        # Market structure
        structure = _market_structure(df_ind)
        rsi = float(df_ind["rsi_14"].iloc[-1]) if "rsi_14" in df_ind.columns else 50.0
        if not math.isfinite(rsi):
            rsi = 50.0

        # Entry engine
        eng = EntryEngine()
        long_setup = eng.compute_long(
            demand_zones[0], supply_zones, atr, rsi=rsi, trend=structure, n_bars=n
        ) if demand_zones else None
        short_setup = eng.compute_short(
            supply_zones[0], demand_zones, atr, rsi=rsi, trend=structure, n_bars=n
        ) if supply_zones else None

        pos_tag = _position_tag(price, demand_zones, supply_zones, atr)

        result = ZoneResult(
            symbol=symbol,
            demand_zones=demand_zones[:5],
            supply_zones=supply_zones[:5],
            long_setup=long_setup,
            short_setup=short_setup,
            market_structure=structure,
            atr=round(atr, 2),
            rvol=round(rvol if math.isfinite(rvol) else 1.0, 2),
            price=round(price, 2),
            position_tag=pos_tag,
        )

        # Upsert to DB
        result_json = {
            "demand_zones": [_zone_to_dict(z) for z in result.demand_zones],
            "supply_zones":  [_zone_to_dict(z) for z in result.supply_zones],
            "long_setup":    _setup_to_dict(long_setup),
            "short_setup":   _setup_to_dict(short_setup),
            "market_structure": structure,
            "atr": result.atr, "rvol": result.rvol,
        }

        best_demand = max((z.score for z in demand_zones), default=None)
        best_supply = max((z.score for z in supply_zones), default=None)

        try:
            db.execute(
                text("""
                    INSERT INTO zone_analysis_results
                        (symbol, computed_date, best_demand_score, best_supply_score,
                         long_setup_score, short_setup_score, price_at_compute,
                         atr_at_compute, rvol_at_compute, position_tag,
                         best_long_rr, best_short_rr, result_json)
                    VALUES
                        (:sym, :dt, :bd, :bs, :ls, :ss, :pr, :atr, :rv, :pt, :lr, :sr, :rj)
                    ON CONFLICT (symbol, computed_date) DO UPDATE SET
                        best_demand_score = EXCLUDED.best_demand_score,
                        best_supply_score = EXCLUDED.best_supply_score,
                        long_setup_score  = EXCLUDED.long_setup_score,
                        short_setup_score = EXCLUDED.short_setup_score,
                        price_at_compute  = EXCLUDED.price_at_compute,
                        atr_at_compute    = EXCLUDED.atr_at_compute,
                        rvol_at_compute   = EXCLUDED.rvol_at_compute,
                        position_tag      = EXCLUDED.position_tag,
                        best_long_rr      = EXCLUDED.best_long_rr,
                        best_short_rr     = EXCLUDED.best_short_rr,
                        result_json       = EXCLUDED.result_json,
                        created_at        = CURRENT_TIMESTAMP
                """),
                {
                    "sym": symbol, "dt": date.today(),
                    "bd": best_demand, "bs": best_supply,
                    "ls": long_setup.score if long_setup else None,
                    "ss": short_setup.score if short_setup else None,
                    "pr": result.price, "atr": result.atr, "rv": result.rvol,
                    "pt": pos_tag,
                    "lr": long_setup.t2_rr if long_setup else None,
                    "sr": short_setup.t2_rr if short_setup else None,
                    "rj": json.dumps(result_json),
                },
            )
            db.commit()
        except Exception as e:
            db.rollback()
            logger.warning("[ZoneEngine] DB upsert failed for %s: %s", symbol, e)

        return result
```

- [ ] **Step 2: Create precompute.py**

```python
from __future__ import annotations
import logging
from sqlalchemy import text
from sqlalchemy.orm import Session
from .engine import ZoneEngine

logger = logging.getLogger(__name__)

# Module-level state dict shared with router for status endpoint
_precompute_state: dict = {
    "is_running": False,
    "done": 0,
    "total": 0,
    "finished": False,
    "started_at": None,
    "error": None,
}


def get_precompute_state() -> dict:
    return _precompute_state


class ZonePrecomputer:
    def run_all(self, db: Session) -> None:
        global _precompute_state
        rows = db.execute(
            text("""
                SELECT DISTINCT symbol FROM stock_prices_daily
                WHERE date >= CURRENT_DATE - INTERVAL '10 days'
                ORDER BY symbol
            """)
        ).fetchall()
        symbols = [r[0] for r in rows]
        total = len(symbols)
        _precompute_state.update(is_running=True, done=0, total=total,
                                  finished=False, error=None)
        logger.info("[zone_precompute] starting — %d symbols", total)
        engine = ZoneEngine()
        for i, symbol in enumerate(symbols):
            try:
                engine.analyze(symbol, db)
            except Exception as e:
                logger.warning("[zone_precompute] failed for %s: %s", symbol, e)
            _precompute_state["done"] = i + 1
            if (i + 1) % 50 == 0:
                logger.info("[zone_precompute] done %d/%d symbols", i + 1, total)

        _precompute_state.update(is_running=False, finished=True)
        logger.info("[zone_precompute] complete — %d symbols processed", total)
```

- [ ] **Step 3: Smoke-test imports**

```bash
cd backend && python -c "
from domains.zones.engine import ZoneEngine
from domains.zones.precompute import ZonePrecomputer
print('OK')
"
```
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add backend/domains/zones/engine.py backend/domains/zones/precompute.py
git commit -m "feat(zones): ZoneEngine (orchestrator) + ZonePrecomputer (batch)"
```

---

## Task 8: Router

**Files:**
- Modify: `backend/domains/zones/router.py` (replace stub)

- [ ] **Step 1: Replace stub with full router**

```python
from __future__ import annotations
import json
import logging
import threading
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from database import get_db, SessionLocal
from .engine import ZoneEngine
from .precompute import ZonePrecomputer, get_precompute_state

router = APIRouter(tags=["zones"])
logger = logging.getLogger(__name__)

_recompute_lock = threading.Lock()


def _serialize_result(r: object) -> dict:
    """Convert ZoneResult to a JSON-serializable dict."""
    from .engine import _zone_to_dict, _setup_to_dict
    return {
        "symbol":           r.symbol,
        "demand_zones":     [_zone_to_dict(z) for z in r.demand_zones],
        "supply_zones":     [_zone_to_dict(z) for z in r.supply_zones],
        "long_setup":       _setup_to_dict(r.long_setup),
        "short_setup":      _setup_to_dict(r.short_setup),
        "market_structure": r.market_structure,
        "atr":              r.atr,
        "rvol":             r.rvol,
        "price":            r.price,
        "position_tag":     r.position_tag,
    }


@router.get("/zones/analyze/{symbol}")
def analyze_symbol(symbol: str, db: Session = Depends(get_db)):
    """Run (or refresh) zone analysis for one symbol. Stores result and returns it."""
    result = ZoneEngine().analyze(symbol.upper(), db)
    if result is None:
        raise HTTPException(status_code=404, detail=f"No price data for {symbol}")
    return _serialize_result(result)


@router.get("/zones/results/{symbol}")
def get_stored_result(symbol: str, db: Session = Depends(get_db)):
    """Return the most recent stored result for a symbol (no recompute)."""
    row = db.execute(
        text("""
            SELECT result_json, computed_date, price_at_compute, atr_at_compute,
                   rvol_at_compute, position_tag, long_setup_score, short_setup_score,
                   best_demand_score, best_supply_score, created_at
            FROM zone_analysis_results
            WHERE symbol = :s
            ORDER BY computed_date DESC
            LIMIT 1
        """),
        {"s": symbol.upper()},
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"No stored zones for {symbol}")
    result = json.loads(row[0])
    result["symbol"]           = symbol.upper()
    result["computed_date"]    = str(row[1])
    result["price"]            = row[2]
    result["atr"]              = row[3]
    result["rvol"]             = row[4]
    result["position_tag"]     = row[5]
    result["long_setup_score"] = row[6]
    result["short_setup_score"]= row[7]
    result["best_demand_score"]= row[8]
    result["best_supply_score"]= row[9]
    result["computed_at"]      = str(row[10])
    return result


_SORT_MAP = {
    "long_score":    "long_setup_score",
    "short_score":   "short_setup_score",
    "demand_score":  "best_demand_score",
    "supply_score":  "best_supply_score",
    "rvol":          "rvol_at_compute",
    "atr":           "atr_at_compute",
}

_FILTER_TAGS = {"in_demand", "near_supply", "breakout", "in_supply", "near_demand"}


@router.get("/zones/rankings")
def get_rankings(
    sort_by: str = Query("long_score"),
    filter: str  = Query(None),
    limit: int   = Query(200, ge=1, le=500),
    db: Session  = Depends(get_db),
):
    """All stocks with today's pre-computed results, sorted and optionally filtered."""
    col = _SORT_MAP.get(sort_by, "long_setup_score")
    today = date.today()

    where = "computed_date = :dt"
    params: dict = {"dt": str(today), "lim": limit}

    # For "long" / "short" filters, require setup score to be >= 50
    if filter == "long":
        where += " AND long_setup_score >= 50"
    elif filter == "short":
        where += " AND short_setup_score >= 50"
    elif filter in _FILTER_TAGS:
        where += " AND position_tag = :pt"
        params["pt"] = filter

    rows = db.execute(
        text(f"""
            SELECT symbol, long_setup_score, short_setup_score,
                   best_demand_score, best_supply_score, position_tag,
                   price_at_compute, atr_at_compute, rvol_at_compute,
                   best_long_rr, best_short_rr, created_at,
                   ROW_NUMBER() OVER (ORDER BY {col} DESC NULLS LAST) AS rank
            FROM zone_analysis_results
            WHERE {where}
            ORDER BY {col} DESC NULLS LAST
            LIMIT :lim
        """),
        params,
    ).fetchall()

    return [
        {
            "rank":              int(r[12]),
            "symbol":            r[0],
            "long_setup_score":  r[1],
            "short_setup_score": r[2],
            "best_demand_score": r[3],
            "best_supply_score": r[4],
            "position_tag":      r[5],
            "price":             r[6],
            "atr":               r[7],
            "rvol":              r[8],
            "best_long_rr":      r[9],
            "best_short_rr":     r[10],
            "computed_at":       str(r[11]),
        }
        for r in rows
    ]


def _run_recompute_bg() -> None:
    import datetime
    state = get_precompute_state()
    state["started_at"] = str(datetime.datetime.now())
    db = SessionLocal()
    try:
        ZonePrecomputer().run_all(db)
    except Exception as e:
        logger.exception("[zones/recompute-all] failed")
        state["error"] = str(e)
    finally:
        db.close()


@router.post("/zones/recompute-all")
def recompute_all(db: Session = Depends(get_db)):
    """Start background recompute of zones for all symbols."""
    state = get_precompute_state()
    if state.get("is_running"):
        return {"status": "already_running",
                "done": state["done"], "total": state["total"]}

    sym_count = db.execute(
        text("SELECT COUNT(DISTINCT symbol) FROM stock_prices_daily WHERE date >= CURRENT_DATE - INTERVAL '10 days'")
    ).scalar() or 0

    threading.Thread(target=_run_recompute_bg, daemon=True, name="zone-recompute").start()
    return {"status": "started", "symbol_count": sym_count}


@router.get("/zones/recompute-status")
def recompute_status():
    state = get_precompute_state()
    return {
        "done":       state.get("done", 0),
        "total":      state.get("total", 0),
        "finished":   state.get("finished", False),
        "is_running": state.get("is_running", False),
        "started_at": state.get("started_at"),
        "error":      state.get("error"),
    }
```

- [ ] **Step 2: Start backend and verify routes exist**

```bash
cd backend && python -c "
from main import app
routes = [r.path for r in app.routes]
for r in routes:
    if 'zones' in r:
        print(r)
"
```
Expected output (5 lines):
```
/api/v1/zones/analyze/{symbol}
/api/v1/zones/results/{symbol}
/api/v1/zones/rankings
/api/v1/zones/recompute-all
/api/v1/zones/recompute-status
```

- [ ] **Step 3: Commit**

```bash
git add backend/domains/zones/router.py
git commit -m "feat(zones): FastAPI router — 5 endpoints for analyze, results, rankings, recompute"
```

---

## Task 9: Scheduler + Intelligence Zone Badge

**Files:**
- Modify: `backend/scheduler.py`
- Modify: `backend/domains/intelligence/router.py`

- [ ] **Step 1: Add zone precompute to daily EOD scheduler**

In `backend/scheduler.py`, inside `_daily_eod_update()`, add after the `_check_special_sell_alerts(db)` call:

```python
        # Zone precompute (after prices are fresh)
        try:
            from domains.zones.precompute import ZonePrecomputer
            ZonePrecomputer().run_all(db)
        except Exception:
            logger.exception("[scheduler] zone precompute failed")
```

- [ ] **Step 2: Add zone_summary to top-opportunities**

In `backend/domains/intelligence/router.py`, inside `get_top_opportunities()`:

After the existing `earnings_map` bulk lookup block (around line 211), add a zone summary bulk lookup:

```python
    # Bulk zone summary lookup for today
    zone_map: dict[str, dict] = {}
    try:
        zone_rows = db.execute(text("""
            SELECT symbol, position_tag, best_demand_score, long_setup_score
            FROM zone_analysis_results
            WHERE computed_date = :dt
        """), {"dt": str(today)}).fetchall()
        zone_map = {
            r[0]: {
                "position_tag": r[1],
                "best_demand_score": r[2],
                "long_setup_score": r[3],
            }
            for r in zone_rows
        }
    except Exception:
        logger.warning("[top-opportunities] zone summary lookup failed", exc_info=True)
```

Then in the `results.append({...})` call at the end of the loop, add:

```python
            "zone_summary": zone_map.get(symbol),
```

- [ ] **Step 3: Verify backend starts cleanly**

```bash
cd backend && python -c "from main import app; print('OK')"
```
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add backend/scheduler.py backend/domains/intelligence/router.py
git commit -m "feat(zones): scheduler nightly precompute + zone_summary in top-opportunities"
```

---

## Task 10: Frontend — API Module + ZonesPage + Nav + Route

**Files:**
- Create: `frontend/src/api/zones.ts`
- Create: `frontend/src/pages/ZonesPage.tsx`
- Modify: `frontend/src/components/NavBar.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Create frontend/src/api/zones.ts**

```typescript
import { apiFetch } from './client'

export interface ZoneCard {
  low: number
  high: number
  score: number
  freshness: 'fresh' | 'tested' | 'weakened'
  touch_count: number
  last_reaction_pct: number
  source_tags: string[]
}

export interface ZoneSetup {
  score: number
  ideal_entry: number
  aggressive_entry: number
  conservative_entry: number
  stop_loss: number
  t1: number
  t1_rr: number
  t2: number
  t2_rr: number
  t3: number
  t3_rr: number
  explanation: string
  invalidation: string
}

export interface ZoneResult {
  symbol: string
  demand_zones: ZoneCard[]
  supply_zones: ZoneCard[]
  long_setup: ZoneSetup | null
  short_setup: ZoneSetup | null
  market_structure: 'bullish' | 'bearish' | 'sideways'
  atr: number
  rvol: number
  price: number
  position_tag: string
  computed_at?: string
  long_setup_score?: number
  short_setup_score?: number
}

export interface ZoneRankRow {
  rank: number
  symbol: string
  long_setup_score: number | null
  short_setup_score: number | null
  best_demand_score: number | null
  best_supply_score: number | null
  position_tag: string
  price: number
  atr: number
  rvol: number
  best_long_rr: number | null
  best_short_rr: number | null
  computed_at: string
}

export interface RecomputeStatus {
  done: number
  total: number
  finished: boolean
  is_running: boolean
  started_at: string | null
  error: string | null
}

export const analyzeZones = (symbol: string) =>
  apiFetch<ZoneResult>(`/zones/analyze/${symbol.toUpperCase()}`)

export const getZoneResult = (symbol: string) =>
  apiFetch<ZoneResult>(`/zones/results/${symbol.toUpperCase()}`)

export const getZoneRankings = (params?: { sort_by?: string; filter?: string; limit?: number }) => {
  const qs = new URLSearchParams()
  if (params?.sort_by) qs.set('sort_by', params.sort_by)
  if (params?.filter)  qs.set('filter',  params.filter)
  if (params?.limit)   qs.set('limit',   String(params.limit))
  const q = qs.toString()
  return apiFetch<ZoneRankRow[]>(`/zones/rankings${q ? '?' + q : ''}`)
}

export const recomputeAll = () =>
  apiFetch<{ status: string; symbol_count: number }>('/zones/recompute-all', { method: 'POST' })

export const getRecomputeStatus = () =>
  apiFetch<RecomputeStatus>('/zones/recompute-status')
```

- [ ] **Step 2: Create frontend/src/pages/ZonesPage.tsx**

```tsx
import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import {
  analyzeZones, getZoneRankings, recomputeAll, getRecomputeStatus,
  type ZoneCard, type ZoneRankRow, type ZoneResult,
} from '../api/zones'

// ── Helpers ──────────────────────────────────────────────────────────────────

const POSITION_BADGE: Record<string, { bg: string; text: string; label: string }> = {
  in_demand:   { bg: 'bg-green-100',  text: 'text-green-700',  label: '✦ IN DEMAND' },
  near_demand: { bg: 'bg-yellow-100', text: 'text-yellow-700', label: '⚡ NEAR DEMAND' },
  near_supply: { bg: 'bg-orange-100', text: 'text-orange-700', label: '⚠ NEAR SUPPLY' },
  in_supply:   { bg: 'bg-red-100',    text: 'text-red-700',    label: '✦ IN SUPPLY' },
  breakout:    { bg: 'bg-blue-100',   text: 'text-blue-700',   label: '🚀 BREAKOUT' },
  neutral:     { bg: 'bg-gray-100',   text: 'text-gray-600',   label: '− NEUTRAL' },
}

const TREND_BADGE: Record<string, { bg: string; text: string }> = {
  bullish:  { bg: 'bg-green-100',  text: 'text-green-700' },
  bearish:  { bg: 'bg-red-100',    text: 'text-red-700' },
  sideways: { bg: 'bg-gray-100',   text: 'text-gray-600' },
}

const FRESHNESS_STYLE: Record<string, string> = {
  fresh:    'text-green-600',
  tested:   'text-yellow-600',
  weakened: 'text-red-500',
}

function scoreColor(s: number | null): string {
  if (s == null) return 'text-gray-400'
  if (s >= 75) return 'text-green-600 font-bold'
  if (s >= 50) return 'text-yellow-600 font-semibold'
  return 'text-red-500'
}

function SourceTag({ tag }: { tag: string }) {
  return (
    <span className="inline-block px-1.5 py-0.5 rounded text-[10px] bg-blue-50 text-blue-700 border border-blue-100 mr-1 mb-0.5">
      {tag}
    </span>
  )
}

// ── Zone Card ─────────────────────────────────────────────────────────────────

function ZoneCardUI({ zone, type }: { zone: ZoneCard; type: 'demand' | 'supply' }) {
  const borderColor = type === 'demand' ? 'border-l-green-500' : 'border-l-red-500'
  const priceColor  = type === 'demand' ? 'text-green-700' : 'text-red-700'
  const badgeBg     = type === 'demand' ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'
  return (
    <div className={`bg-white rounded-md border border-gray-100 border-l-4 ${borderColor} p-3 mb-2`}>
      <div className="flex items-center justify-between mb-1">
        <span className={`font-bold text-sm ${priceColor}`}>
          ₹{zone.low.toLocaleString('en-IN', { maximumFractionDigits: 0 })} –{' '}
          ₹{zone.high.toLocaleString('en-IN', { maximumFractionDigits: 0 })}
        </span>
        <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${badgeBg}`}>
          {zone.score}/100
        </span>
      </div>
      <div className="text-xs text-gray-500 mb-1.5">
        <span className={FRESHNESS_STYLE[zone.freshness] || 'text-gray-500'}>
          {zone.freshness.charAt(0).toUpperCase() + zone.freshness.slice(1)}
        </span>
        {zone.touch_count > 0 && ` · ${zone.touch_count} touch${zone.touch_count > 1 ? 'es' : ''}`}
        {zone.last_reaction_pct > 0 && ` · Last ${zone.last_reaction_pct.toFixed(1)}%`}
      </div>
      <div className="flex flex-wrap">
        {zone.source_tags.map(t => <SourceTag key={t} tag={t} />)}
      </div>
    </div>
  )
}

// ── Analysis Panel ─────────────────────────────────────────────────────────────

function AnalysisPanel({ result }: { result: ZoneResult }) {
  const [showShort, setShowShort] = useState(false)
  const posTag   = POSITION_BADGE[result.position_tag] ?? POSITION_BADGE.neutral
  const trendTag = TREND_BADGE[result.market_structure] ?? TREND_BADGE.sideways

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4 mb-4">
      {/* Market structure strip */}
      <div className="flex flex-wrap items-center gap-3 px-3 py-2 bg-gray-50 rounded-md mb-4 text-sm">
        <span className="font-bold text-base">{result.symbol}</span>
        <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${trendTag.bg} ${trendTag.text}`}>
          {result.market_structure.toUpperCase()} TREND
        </span>
        <span>Price <b>₹{result.price.toLocaleString('en-IN', { maximumFractionDigits: 0 })}</b></span>
        <span>ATR <b>{result.atr.toFixed(1)}</b></span>
        <span>RVol <b className={result.rvol >= 1.5 ? 'text-green-600' : ''}>{result.rvol.toFixed(1)}×</b></span>
        <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${posTag.bg} ${posTag.text}`}>
          {posTag.label}
        </span>
      </div>

      {/* Three-column layout */}
      <div className="grid grid-cols-3 gap-3">
        {/* Demand zones */}
        <div className="bg-green-50 border border-green-100 rounded-md p-3">
          <div className="text-xs font-bold text-green-700 mb-2">⬇ DEMAND ZONES ({result.demand_zones.length})</div>
          {result.demand_zones.length === 0 && (
            <div className="text-xs text-gray-400">No demand zones detected</div>
          )}
          {result.demand_zones.map((z, i) => <ZoneCardUI key={i} zone={z} type="demand" />)}
        </div>

        {/* Supply zones */}
        <div className="bg-red-50 border border-red-100 rounded-md p-3">
          <div className="text-xs font-bold text-red-700 mb-2">⬆ SUPPLY ZONES ({result.supply_zones.length})</div>
          {result.supply_zones.length === 0 && (
            <div className="text-xs text-gray-400">No supply zones detected</div>
          )}
          {result.supply_zones.map((z, i) => <ZoneCardUI key={i} zone={z} type="supply" />)}
        </div>

        {/* Setup panel */}
        <div className="bg-blue-50 border border-blue-100 rounded-md p-3">
          {result.long_setup ? (
            <>
              <div className="text-xs font-bold text-blue-700 mb-3">
                🎯 LONG SETUP — {result.long_setup.score}/100
              </div>
              <div className="grid grid-cols-2 gap-x-2 gap-y-1 text-xs mb-3">
                <span className="text-gray-500">Ideal Entry</span>
                <span className="font-semibold">₹{result.long_setup.ideal_entry.toLocaleString('en-IN', { maximumFractionDigits: 0 })}</span>
                <span className="text-gray-500">Aggressive</span>
                <span>₹{result.long_setup.aggressive_entry.toLocaleString('en-IN', { maximumFractionDigits: 0 })}</span>
                <span className="text-gray-500">Conservative</span>
                <span>₹{result.long_setup.conservative_entry.toLocaleString('en-IN', { maximumFractionDigits: 0 })}</span>
                <span className="text-red-500">Stop Loss</span>
                <span className="text-red-600 font-semibold">₹{result.long_setup.stop_loss.toLocaleString('en-IN', { maximumFractionDigits: 0 })}</span>
                <span className="text-green-600">Target 1</span>
                <span className="text-green-700 font-semibold">₹{result.long_setup.t1.toLocaleString('en-IN', { maximumFractionDigits: 0 })} · 1:{result.long_setup.t1_rr}</span>
                <span className="text-green-600">Target 2</span>
                <span className="text-green-700">₹{result.long_setup.t2.toLocaleString('en-IN', { maximumFractionDigits: 0 })} · 1:{result.long_setup.t2_rr}</span>
                <span className="text-green-600">Target 3</span>
                <span className="text-green-700">₹{result.long_setup.t3.toLocaleString('en-IN', { maximumFractionDigits: 0 })} · 1:{result.long_setup.t3_rr}</span>
              </div>
              <div className="text-[10px] text-gray-600 bg-white border border-blue-100 rounded p-2 leading-relaxed mb-2">
                {result.long_setup.explanation}
              </div>
              <div className="text-[10px] text-red-600">{result.long_setup.invalidation}</div>
            </>
          ) : (
            <div className="text-xs text-gray-400">No demand zones — long setup unavailable</div>
          )}

          {result.short_setup && (
            <div className="border-t border-blue-100 mt-3 pt-3">
              <button
                onClick={() => setShowShort(v => !v)}
                className="text-xs font-bold text-purple-700 mb-2 w-full text-left"
              >
                ⬇ SHORT SETUP — {result.short_setup.score}/100 {showShort ? '▲' : '▼'}
              </button>
              {showShort && (
                <div className="text-xs text-gray-700">
                  Entry ₹{result.short_setup.ideal_entry.toLocaleString('en-IN', { maximumFractionDigits: 0 })} ·{' '}
                  SL ₹{result.short_setup.stop_loss.toLocaleString('en-IN', { maximumFractionDigits: 0 })} ·{' '}
                  T1 ₹{result.short_setup.t1.toLocaleString('en-IN', { maximumFractionDigits: 0 })} · R:R 1:{result.short_setup.t1_rr}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Ranking row ───────────────────────────────────────────────────────────────

function RankRow({
  row, onSelect, isSelected,
}: { row: ZoneRankRow; onSelect: (sym: string) => void; isSelected: boolean }) {
  const posStyle = POSITION_BADGE[row.position_tag] ?? POSITION_BADGE.neutral
  return (
    <div
      className={`border-b border-gray-100 cursor-pointer hover:bg-gray-50 ${isSelected ? 'bg-blue-50 border-l-2 border-l-blue-500' : ''}`}
    >
      <div
        className="grid gap-1 px-3 py-2 text-xs"
        style={{ gridTemplateColumns: '28px 80px 55px 100px 70px 55px 55px 50px 50px 70px' }}
        onClick={() => onSelect(row.symbol)}
      >
        <span className="text-gray-400">{row.rank}</span>
        <span className={`font-bold ${isSelected ? 'text-blue-600' : ''}`}>{row.symbol} {isSelected ? '▼' : '▶'}</span>
        <span className={scoreColor(row.long_setup_score)}>{row.long_setup_score ?? '—'}</span>
        <span className={`px-1.5 py-0.5 rounded-full text-[10px] font-medium ${posStyle.bg} ${posStyle.text}`}>
          {posStyle.label}
        </span>
        <span className={scoreColor(row.long_setup_score)}>
          {row.long_setup_score != null ? `Long ${row.long_setup_score}` : '—'}
        </span>
        <span className={scoreColor(row.best_demand_score)}>{row.best_demand_score ?? '—'}</span>
        <span className={scoreColor(row.best_supply_score)}>{row.best_supply_score ?? '—'}</span>
        <span>{row.atr?.toFixed(1) ?? '—'}</span>
        <span className={row.rvol >= 1.5 ? 'text-green-600 font-medium' : ''}>{row.rvol?.toFixed(1) ?? '—'}×</span>
        <span className="text-gray-400">{row.computed_at ? new Date(row.computed_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '—'}</span>
      </div>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

type SortKey = 'long_score' | 'short_score' | 'demand_score' | 'supply_score' | 'rvol' | 'atr'
type FilterKey = '' | 'long' | 'short' | 'in_demand' | 'breakout' | 'near_supply'

export function ZonesPage() {
  const [symbol, setSymbol]     = useState('')
  const [activeSymbol, setActiveSymbol] = useState<string | null>(null)
  const [sortBy, setSortBy]     = useState<SortKey>('long_score')
  const [filterBy, setFilterBy] = useState<FilterKey>('')
  const [expandedSym, setExpandedSym] = useState<string | null>(null)

  const analyzeQuery = useQuery({
    queryKey: ['zone-analyze', activeSymbol],
    queryFn: () => analyzeZones(activeSymbol!),
    enabled: !!activeSymbol,
  })

  const rankingsQuery = useQuery({
    queryKey: ['zone-rankings', sortBy, filterBy],
    queryFn: () => getZoneRankings({ sort_by: sortBy, filter: filterBy || undefined }),
    staleTime: 5 * 60 * 1000,
  })

  const statusQuery = useQuery({
    queryKey: ['zone-recompute-status'],
    queryFn: getRecomputeStatus,
    refetchInterval: (data: any) => data?.is_running ? 3000 : false,
  })

  const recomputeMut = useMutation({ mutationFn: recomputeAll })

  const handleAnalyze = () => {
    const sym = symbol.trim().toUpperCase()
    if (sym) { setActiveSymbol(sym); setExpandedSym(sym) }
  }

  const handleRowClick = (sym: string) => {
    if (expandedSym === sym) {
      setExpandedSym(null)
    } else {
      setExpandedSym(sym)
      setActiveSymbol(sym)
    }
  }

  const status = statusQuery.data
  const lastBatch = status?.finished
    ? `Last batch: just now · ${status.total} stocks`
    : status?.is_running
      ? `Recomputing… ${status.done}/${status.total}`
      : status?.started_at
        ? `Last batch: ${new Date(status.started_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`
        : 'No batch run yet'

  const FILTERS: { key: FilterKey; label: string }[] = [
    { key: 'long',        label: 'Long' },
    { key: 'short',       label: 'Short' },
    { key: 'in_demand',   label: 'In Demand' },
    { key: 'breakout',    label: 'Breakout' },
    { key: 'near_supply', label: 'Near Supply' },
  ]

  const SORTS: { key: SortKey; label: string }[] = [
    { key: 'long_score',   label: 'Long Score' },
    { key: 'short_score',  label: 'Short Score' },
    { key: 'demand_score', label: 'Demand' },
    { key: 'supply_score', label: 'Supply' },
    { key: 'rvol',         label: 'RVol' },
    { key: 'atr',          label: 'ATR' },
  ]

  return (
    <div>
      {/* Top bar */}
      <div className="flex items-center gap-3 bg-white rounded-lg border border-gray-200 px-4 py-3 mb-4 shadow-sm">
        <span className="font-bold text-base text-gray-800">Demand &amp; Supply Zones</span>
        <input
          className="flex-1 ml-4 border border-gray-300 rounded px-3 py-1.5 text-sm focus:outline-none focus:border-blue-400"
          placeholder="Symbol… RELIANCE"
          value={symbol}
          onChange={e => setSymbol(e.target.value.toUpperCase())}
          onKeyDown={e => e.key === 'Enter' && handleAnalyze()}
        />
        <button
          onClick={handleAnalyze}
          disabled={analyzeQuery.isFetching}
          className="px-4 py-1.5 bg-green-600 text-white text-sm rounded font-medium hover:bg-green-700 disabled:opacity-50"
        >
          {analyzeQuery.isFetching ? 'Analyzing…' : 'Analyze'}
        </button>
        <span className="text-xs text-gray-400 whitespace-nowrap">{lastBatch}</span>
        <button
          onClick={() => recomputeMut.mutate()}
          disabled={status?.is_running || recomputeMut.isPending}
          className="px-3 py-1.5 bg-indigo-600 text-white text-xs rounded font-medium hover:bg-indigo-700 disabled:opacity-50 whitespace-nowrap"
        >
          ⟳ Recompute All
        </button>
      </div>

      {/* Analysis panel */}
      {analyzeQuery.data && <AnalysisPanel result={analyzeQuery.data} />}
      {analyzeQuery.isError && (
        <div className="text-red-600 text-sm mb-4 bg-red-50 border border-red-200 rounded p-3">
          Failed to analyze {activeSymbol}: {(analyzeQuery.error as Error)?.message}
        </div>
      )}

      {/* Rankings table */}
      <div className="bg-white rounded-lg border border-gray-200 shadow-sm">
        <div className="flex items-center gap-2 px-4 py-3 border-b border-gray-100">
          <span className="font-bold text-sm">All Stocks Ranking</span>
          <span className="text-xs text-gray-400">
            {rankingsQuery.data?.length ?? 0} stocks
          </span>
          <div className="ml-auto flex items-center gap-2">
            {/* Filter chips */}
            {FILTERS.map(f => (
              <button
                key={f.key}
                onClick={() => setFilterBy(filterBy === f.key ? '' : f.key)}
                className={`px-2.5 py-1 rounded-full text-xs font-medium border transition-colors ${
                  filterBy === f.key
                    ? 'bg-blue-600 text-white border-blue-600'
                    : 'bg-white text-gray-600 border-gray-300 hover:border-blue-400'
                }`}
              >
                {f.label}
              </button>
            ))}
            {/* Sort select */}
            <select
              value={sortBy}
              onChange={e => setSortBy(e.target.value as SortKey)}
              className="border border-gray-300 rounded text-xs px-2 py-1 ml-2 focus:outline-none"
            >
              {SORTS.map(s => <option key={s.key} value={s.key}>{s.label}</option>)}
            </select>
          </div>
        </div>

        {/* Table header */}
        <div
          className="grid gap-1 px-3 py-2 bg-gray-50 text-xs font-bold text-gray-500 border-b border-gray-100"
          style={{ gridTemplateColumns: '28px 80px 55px 100px 70px 55px 55px 50px 50px 70px' }}
        >
          <span>#</span>
          <span>Symbol</span>
          <span>Score</span>
          <span>Position</span>
          <span>Setup</span>
          <span>Demand</span>
          <span>Supply</span>
          <span>ATR</span>
          <span>RVol</span>
          <span>Computed</span>
        </div>

        {rankingsQuery.isLoading && (
          <div className="text-center py-8 text-gray-400 text-sm">Loading rankings…</div>
        )}

        {rankingsQuery.data?.map(row => (
          <div key={row.symbol}>
            <RankRow
              row={row}
              onSelect={handleRowClick}
              isSelected={expandedSym === row.symbol}
            />
            {expandedSym === row.symbol && analyzeQuery.data?.symbol === row.symbol && (
              <div className="bg-blue-50 px-4 py-2.5 text-xs text-gray-700 border-b border-blue-100">
                <span className="font-semibold">Demand:</span>{' '}
                {analyzeQuery.data.demand_zones.slice(0, 2).map(
                  z => `₹${z.low.toLocaleString('en-IN', { maximumFractionDigits: 0 })}–₹${z.high.toLocaleString('en-IN', { maximumFractionDigits: 0 })} (${z.score})`
                ).join(' · ')}
                {' '}|{' '}
                <span className="font-semibold">Supply:</span>{' '}
                {analyzeQuery.data.supply_zones.slice(0, 2).map(
                  z => `₹${z.low.toLocaleString('en-IN', { maximumFractionDigits: 0 })}–₹${z.high.toLocaleString('en-IN', { maximumFractionDigits: 0 })} (${z.score})`
                ).join(' · ')}
                {analyzeQuery.data.long_setup && (
                  <>{' '}|{' '}<span className="font-semibold">Long:</span> Entry ₹{analyzeQuery.data.long_setup.ideal_entry.toLocaleString('en-IN', { maximumFractionDigits: 0 })} · SL ₹{analyzeQuery.data.long_setup.stop_loss.toLocaleString('en-IN', { maximumFractionDigits: 0 })} · T1 ₹{analyzeQuery.data.long_setup.t1.toLocaleString('en-IN', { maximumFractionDigits: 0 })} · R:R 1:{analyzeQuery.data.long_setup.t1_rr}</>
                )}
                {' '}
                <button
                  className="text-blue-600 underline hover:text-blue-800 ml-1"
                  onClick={() => { setActiveSymbol(row.symbol); window.scrollTo({ top: 0, behavior: 'smooth' }) }}
                >
                  View full analysis ↑
                </button>
              </div>
            )}
          </div>
        ))}

        {rankingsQuery.data?.length === 0 && !rankingsQuery.isLoading && (
          <div className="text-center py-8 text-gray-400 text-sm">
            No zone data for today. Click "Recompute All" to generate.
          </div>
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 3: Add route in App.tsx**

In `frontend/src/App.tsx`:

Add import:
```tsx
import { ZonesPage } from './pages/ZonesPage'
```

Add route inside `<Routes>`:
```tsx
              <Route path="/zones" element={<ZonesPage />} />
```

- [ ] **Step 4: Add nav link in NavBar.tsx**

In `frontend/src/components/NavBar.tsx`, add after `<NavLink to="/sector-rotation"...>Sectors</NavLink>`:

```tsx
      <NavLink to="/zones" className={link}>Zones</NavLink>
```

- [ ] **Step 5: TypeScript check**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -30
```
Expected: no errors (or only pre-existing errors unrelated to zones files).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/zones.ts frontend/src/pages/ZonesPage.tsx \
        frontend/src/components/NavBar.tsx frontend/src/App.tsx
git commit -m "feat(zones): frontend page — analysis panel, sortable ranking table, recompute status"
```

---

## Verification Checklist

After all tasks:

- [ ] `python -m pytest backend/tests/test_zone_detectors.py backend/tests/test_zone_clusterer.py backend/tests/test_zone_scorer.py backend/tests/test_zone_entry_engine.py -v` — all PASS
- [ ] `python -c "from main import app; print('OK')"` — no import errors
- [ ] `GET /api/v1/zones/analyze/RELIANCE` — returns demand/supply zones + long/short setups
- [ ] `GET /api/v1/zones/rankings` — returns list with `long_setup_score`, `position_tag`, etc.
- [ ] `POST /api/v1/zones/recompute-all` — returns `{"status": "started", ...}`
- [ ] `GET /api/v1/zones/recompute-status` — returns `{"done": N, "total": M, "finished": bool}`
- [ ] `GET /api/v1/intelligence/top-opportunities` — each item has `zone_summary` key
- [ ] Frontend `/zones` page loads, Analyze button fetches and displays zone cards + setup panel
- [ ] Clicking a rankings row expands inline summary + "View full analysis ↑" link works
- [ ] Recompute All button shows progress via status polling
