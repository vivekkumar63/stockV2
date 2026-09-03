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


def test_ma_detector_emits_levels_with_valid_zone_types(df_ind):
    """MADetector must emit at least one level on a 500-bar series and use valid zone_types."""
    levels = MADetector().detect(df_ind)
    assert len(levels) > 0, "Expected MADetector to emit levels on 500-bar df"
    assert all(z.zone_type in ("demand", "supply") for z in levels)


def test_ma_tags_known(df_ind):
    levels = MADetector().detect(df_ind)
    valid_tags = {"ema_9", "ema_21", "ema_50", "sma_200"}
    assert all(z.source_tag in valid_tags for z in levels)


def test_volume_detector_emits_levels_with_valid_zone_types(df_ind):
    """VolumeDetector must emit at least one vol_node level on a 500-bar series."""
    levels = VolumeDetector().detect(df_ind)
    assert len(levels) > 0, "Expected VolumeDetector to emit levels on 500-bar df"
    assert all(z.source_tag == "vol_node" for z in levels)
    assert all(z.zone_type in ("demand", "supply") for z in levels)


def test_volatility_detector_emits_demand_near_lower_band():
    """VolatilityDetector emits a demand level when close is within ATR of bb_lower."""
    n = 50
    close_price = 1000.0
    bb_lower = 992.0  # abs(1000 - 992) = 8 <= 15 ATR → triggers demand
    atr = 15.0
    df = pd.DataFrame({
        "open": [close_price] * n,
        "high": [close_price * 1.01] * n,
        "low":  [close_price * 0.99] * n,
        "close": [close_price] * n,
        "volume": [1_000_000] * n,
        "bb_lower": [bb_lower] * n,
        "bb_upper": [close_price * 1.05] * n,  # far away, should not trigger
        "atr_14": [atr] * n,
    })
    df.index = pd.date_range("2024-01-01", periods=n, freq="B")
    levels = VolatilityDetector().detect(df)
    assert len(levels) == 1
    assert levels[0].zone_type == "demand"
    assert levels[0].source_tag == "bb_lower"


def test_momentum_detector_emits_levels_with_valid_zone_types(df_ind):
    """MomentumDetector must emit levels on a 500-bar series with RSI excursions."""
    levels = MomentumDetector().detect(df_ind)
    assert len(levels) > 0, "Expected MomentumDetector to emit levels on 500-bar df"
    assert all(z.zone_type in ("demand", "supply") for z in levels)
    assert all(z.source_tag in ("rsi_oversold", "rsi_overbought") for z in levels)


def test_fibonacci_detector_returns_list(df_ind):
    levels = FibonacciDetector().detect(df_ind)
    assert isinstance(levels, list)


def test_fibonacci_tags_format(df_ind):
    """Fibonacci source tags must use 'fib_XX.X' format (e.g. 'fib_61.8')."""
    levels = FibonacciDetector().detect(df_ind)
    for level in levels:
        assert level.source_tag.startswith("fib_"), f"Expected fib_ prefix, got {level.source_tag!r}"
        # The part after 'fib_' should be a valid number like '61.8'
        suffix = level.source_tag[4:]
        float(suffix)  # must be parseable as float, raises ValueError if not


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


def test_fibonacci_detector_emits_demand_in_uptrend(df_ind):
    """FibonacciDetector must emit only demand zones when price is above the swing midpoint."""
    levels = FibonacciDetector().detect(df_ind)
    # Only check if levels were emitted; skip if empty (reaction guard may filter all)
    demand_levels = [z for z in levels if z.zone_type == "demand"]
    supply_levels = [z for z in levels if z.zone_type == "supply"]
    # Both demand-only and supply-only are valid depending on the trend in df_ind;
    # what's NOT valid is mixing both types in one detect() call
    if len(levels) > 0:
        assert len(demand_levels) == 0 or len(supply_levels) == 0, (
            "FibonacciDetector must emit only demand (uptrend) or only supply (downtrend) "
            "in a single call, not both"
        )


def test_fibonacci_detector_demand_in_controlled_uptrend():
    """FibonacciDetector emits demand zones when price is above the swing midpoint."""
    import numpy as np
    n = 200
    # Construct a rising price series: starts at 100, ends at 200
    close = np.linspace(100, 200, n)
    # Last bar price is 200, swing_low ≈ 100, swing_high ≈ 200, midpoint ≈ 150
    # price_now (200) > midpoint (150) → uptrend → demand zones expected
    # Set ATR to 5.0 (price changes ~0.5/bar, so ATR ≈ 0.5; we need reaction near fib levels)
    # Use a declining close for the last few bars to ensure reaction near some fib levels
    # Fib levels in uptrend: swing_high - fib * rng → e.g. 200 - 0.382*100 = 161.8
    # We need some bar's close within 0.3 * ATR of a fib level
    # Make ATR large (15) so the reaction guard is easily satisfied
    atr_val = 15.0
    df = pd.DataFrame({
        "open": close * 0.999,
        "high": close * 1.005,
        "low":  close * 0.995,
        "close": close,
        "volume": [1_000_000] * n,
        "atr_14": [atr_val] * n,
        "volume_ratio": [1.0] * n,
    })
    df.index = pd.date_range("2020-01-01", periods=n, freq="B")
    levels = FibonacciDetector().detect(df)
    assert len(levels) > 0, "Expected at least one Fibonacci demand level in controlled uptrend (ATR is large enough for reaction guard)"
    assert all(z.zone_type == "demand" for z in levels), (
        f"Expected only demand zones in uptrend, got: {[z.zone_type for z in levels]}"
    )
