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
    """Two demand levels 20 points apart with ATR=10 (0.5×ATR=5) stay separate."""
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
