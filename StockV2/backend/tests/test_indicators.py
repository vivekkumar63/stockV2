import pandas as pd
import numpy as np
import pytest
from domains.data.indicators import IndicatorEngine


@pytest.fixture
def sample_df():
    """200 days of synthetic OHLCV data — enough for all indicators."""
    np.random.seed(42)
    n = 200
    close = 1000 + np.cumsum(np.random.randn(n) * 10)
    df = pd.DataFrame({
        "open":   close * (1 + np.random.uniform(-0.01, 0.01, n)),
        "high":   close * (1 + np.random.uniform(0.0, 0.02, n)),
        "low":    close * (1 - np.random.uniform(0.0, 0.02, n)),
        "close":  close,
        "volume": np.random.randint(100_000, 5_000_000, n),
    })
    df.index = pd.date_range("2024-01-01", periods=n, freq="B")
    return df


def test_compute_returns_dataframe(sample_df):
    result = IndicatorEngine.compute(sample_df)
    assert isinstance(result, pd.DataFrame)


def test_sma_columns_present(sample_df):
    result = IndicatorEngine.compute(sample_df)
    assert "sma_20" in result.columns
    assert "sma_50" in result.columns


def test_ema_columns_present(sample_df):
    result = IndicatorEngine.compute(sample_df)
    assert "ema_9" in result.columns
    assert "ema_21" in result.columns


def test_rsi_present_and_in_range(sample_df):
    result = IndicatorEngine.compute(sample_df)
    assert "rsi_14" in result.columns
    rsi_values = result["rsi_14"].dropna()
    assert (rsi_values >= 0).all() and (rsi_values <= 100).all()


def test_macd_columns_present(sample_df):
    result = IndicatorEngine.compute(sample_df)
    assert "macd" in result.columns
    assert "macd_signal" in result.columns
    assert "macd_hist" in result.columns


def test_bollinger_bands_present(sample_df):
    result = IndicatorEngine.compute(sample_df)
    assert "bb_upper" in result.columns
    assert "bb_middle" in result.columns
    assert "bb_lower" in result.columns


def test_atr_present(sample_df):
    result = IndicatorEngine.compute(sample_df)
    assert "atr_14" in result.columns
    assert (result["atr_14"].dropna() > 0).all()


def test_volume_ratio_present(sample_df):
    result = IndicatorEngine.compute(sample_df)
    assert "volume_sma_20" in result.columns
    assert "volume_ratio" in result.columns


def test_adx_present(sample_df):
    result = IndicatorEngine.compute(sample_df)
    assert "adx_14" in result.columns


def test_roc_present(sample_df):
    result = IndicatorEngine.compute(sample_df)
    assert "roc_10" in result.columns


def test_supertrend_present(sample_df):
    result = IndicatorEngine.compute(sample_df)
    assert "supertrend" in result.columns
    assert "supertrend_direction" in result.columns


def test_does_not_modify_input(sample_df):
    original_cols = list(sample_df.columns)
    IndicatorEngine.compute(sample_df)
    assert list(sample_df.columns) == original_cols


def test_short_df_returns_nan_gracefully():
    """Less than 50 rows — indicators that need 50-period history return NaN, not crash."""
    df = pd.DataFrame({
        "open": [100.0] * 10,
        "high": [101.0] * 10,
        "low": [99.0] * 10,
        "close": [100.0] * 10,
        "volume": [1_000_000] * 10,
    })
    result = IndicatorEngine.compute(df)
    assert "sma_20" in result.columns
    assert result["sma_20"].isna().all()
