import math
import numpy as np
import pandas as pd
import pytest
from datetime import date, timedelta
from domains.zones.backtester import ZoneBacktester, ZoneTrade
from domains.zones.models import Zone


def _make_zone(low: float, high: float, zone_type: str = "demand") -> Zone:
    return Zone(
        low=low, high=high, zone_type=zone_type,
        source_tags=["swing_low"], score=70,
        freshness="fresh", bar_index=100, strength_hint=0.6,
    )


def _make_df(n_rows: int = 40, close: float = 100.0) -> pd.DataFrame:
    """Synthetic price DataFrame with required columns for _simulate()."""
    start = date(2023, 1, 1)
    dates = [start + timedelta(days=i) for i in range(n_rows)]
    closes = np.full(n_rows, close)
    return pd.DataFrame({
        "date":         pd.to_datetime(dates),
        "open":         closes,
        "high":         closes + 2,
        "low":          closes - 2,
        "close":        closes,
        "volume":       np.full(n_rows, 1_000_000.0),
        "atr_14":       np.full(n_rows, 5.0),
        "volume_ratio": np.ones(n_rows),
        "ema_50":       closes,
    })


def _snapshot(demand_zones, supply_zones=None, atr=5.0):
    return (demand_zones, supply_zones or [], atr)


def test_entry_and_supply_exit():
    """Price enters demand zone on day 5, enters supply zone on day 10 → supply_zone exit."""
    bt = ZoneBacktester()
    closes = np.full(40, 110.0)
    closes[5] = 100.0   # day 5: price enters demand zone [98, 102]
    closes[10] = 200.0  # day 10: price enters supply zone [195, 205]

    start = date(2023, 1, 1)
    dates = pd.to_datetime([start + timedelta(days=i) for i in range(40)])
    df = pd.DataFrame({
        "date": dates, "open": closes, "high": closes + 2,
        "low": closes - 2, "close": closes,
        "volume": np.full(40, 1e6), "atr_14": np.full(40, 5.0),
        "volume_ratio": np.ones(40), "ema_50": closes,
    })

    demand = [_make_zone(98.0, 102.0, "demand")]
    supply = [_make_zone(195.0, 205.0, "supply")]
    snapshots = {(2023, 1): (demand, supply, 5.0)}

    from_d = date(2023, 1, 1)
    to_d = date(2023, 2, 9)
    trades = bt._simulate("TEST", df, from_d, to_d, snapshots)

    assert len(trades) == 1
    assert trades[0].exit_reason == "supply_zone"
    assert trades[0].symbol == "TEST"


def test_stop_loss_exit():
    """Price falls below zone.low - 0.5*ATR → stop_loss exit."""
    bt = ZoneBacktester()
    closes = np.full(40, 110.0)
    closes[5] = 100.0   # enter demand zone [98, 102]
    closes[8] = 94.0    # below 98 - 0.5*5 = 95.5 → stop loss

    start = date(2023, 1, 1)
    dates = pd.to_datetime([start + timedelta(days=i) for i in range(40)])
    df = pd.DataFrame({
        "date": dates, "open": closes, "high": closes + 2,
        "low": closes - 2, "close": closes,
        "volume": np.full(40, 1e6), "atr_14": np.full(40, 5.0),
        "volume_ratio": np.ones(40), "ema_50": closes,
    })

    demand = [_make_zone(98.0, 102.0, "demand")]
    snapshots = {(2023, 1): (demand, [], 5.0)}

    trades = bt._simulate("TEST", df, date(2023, 1, 1), date(2023, 2, 9), snapshots)
    assert len(trades) == 1
    assert trades[0].exit_reason == "stop_loss"


def test_max_hold_exit():
    """Position held 20 days without hitting other exits → max_hold."""
    bt = ZoneBacktester()
    closes = np.full(60, 110.0)
    closes[5] = 100.0   # enter demand zone [98, 102]

    start = date(2023, 1, 1)
    dates = pd.to_datetime([start + timedelta(days=i) for i in range(60)])
    df = pd.DataFrame({
        "date": dates, "open": closes, "high": closes + 2,
        "low": closes - 2, "close": closes,
        "volume": np.full(60, 1e6), "atr_14": np.full(60, 5.0),
        "volume_ratio": np.ones(60), "ema_50": closes,
    })

    demand = [_make_zone(98.0, 102.0, "demand")]
    snapshots = {(2023, 1): (demand, [], 5.0), (2023, 2): (demand, [], 5.0)}

    trades = bt._simulate("TEST", df, date(2023, 1, 1), date(2023, 3, 1), snapshots)
    assert any(t.exit_reason == "max_hold" for t in trades)


def test_no_entry_when_no_demand_zones():
    bt = ZoneBacktester()
    df = _make_df()
    snapshots = {(2023, 1): ([], [], 5.0)}
    trades = bt._simulate("TEST", df, date(2023, 1, 1), date(2023, 1, 31), snapshots)
    assert trades == []
