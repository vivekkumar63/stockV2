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
