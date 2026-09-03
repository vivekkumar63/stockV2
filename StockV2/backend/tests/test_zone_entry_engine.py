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
