import pandas as pd
import numpy as np
import pytest
from unittest.mock import MagicMock
from datetime import datetime
from domains.zones.detectors import VWAPZoneDetector


def _make_intraday_rows(n: int = 12, vwap_price: float = 100.0):
    """Returns rows that db.execute().fetchall() would return.
    Sets high=vwap_price+0.5, low=vwap_price-0.5, close=vwap_price so
    typical_price == vwap_price and VWAP == vwap_price exactly."""
    rows = []
    base = datetime(2024, 1, 2, 9, 15)
    for i in range(n):
        h = vwap_price + 0.5
        l = vwap_price - 0.5
        c = vwap_price
        # Use timedelta to avoid minute overflow (5-min bars spread across the day)
        from datetime import timedelta
        ts = base + timedelta(minutes=i * 5)
        rows.append((ts, h, l, c, 10000))
    return rows


def test_vwap_demand_when_price_above_vwap():
    db = MagicMock()
    db.execute.return_value.fetchall.return_value = _make_intraday_rows(12, vwap_price=95.0)
    detector = VWAPZoneDetector()
    zones = detector.detect("RELIANCE", db, atr=5.0, current_price=100.0)
    assert len(zones) == 1
    assert zones[0].zone_type == "demand"
    assert zones[0].source == "vwap"
    assert "vwap" in zones[0].source_tags


def test_vwap_supply_when_price_below_vwap():
    db = MagicMock()
    db.execute.return_value.fetchall.return_value = _make_intraday_rows(12, vwap_price=105.0)
    detector = VWAPZoneDetector()
    zones = detector.detect("RELIANCE", db, atr=5.0, current_price=100.0)
    assert len(zones) == 1
    assert zones[0].zone_type == "supply"


def test_vwap_returns_empty_with_too_few_bars():
    db = MagicMock()
    db.execute.return_value.fetchall.return_value = _make_intraday_rows(3)
    detector = VWAPZoneDetector()
    zones = detector.detect("RELIANCE", db, atr=5.0, current_price=100.0)
    assert zones == []


def test_vwap_band_width_is_0_3_atr():
    db = MagicMock()
    db.execute.return_value.fetchall.return_value = _make_intraday_rows(12, vwap_price=100.0)
    detector = VWAPZoneDetector()
    atr = 10.0
    zones = detector.detect("RELIANCE", db, atr=atr, current_price=105.0)
    assert len(zones) == 1
    z = zones[0]
    expected_low  = 100.0 - 0.3 * atr  # 97.0
    expected_high = 100.0 + 0.3 * atr  # 103.0
    assert abs(z.low - expected_low) < 0.01
    assert abs(z.high - expected_high) < 0.01
