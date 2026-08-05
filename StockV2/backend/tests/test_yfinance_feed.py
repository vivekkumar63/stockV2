import pandas as pd
import pytest
from unittest.mock import patch, MagicMock
from domains.data.feeds.yfinance_feed import YFinanceFeed


@pytest.fixture
def mock_ohlcv():
    """Minimal valid OHLCV DataFrame that yfinance returns."""
    dates = pd.date_range("2024-01-01", periods=5, freq="B")
    return pd.DataFrame({
        "Open":   [100.0, 101.0, 102.0, 101.5, 103.0],
        "High":   [101.0, 102.0, 103.0, 102.5, 104.0],
        "Low":    [99.0,  100.0, 101.0, 100.5, 102.0],
        "Close":  [100.5, 101.5, 102.5, 102.0, 103.5],
        "Volume": [1_000_000, 1_200_000, 900_000, 1_100_000, 950_000],
    }, index=dates)


def test_download_returns_dataframe(mock_ohlcv):
    with patch("yfinance.Ticker") as mock_ticker:
        mock_ticker.return_value.history.return_value = mock_ohlcv
        feed = YFinanceFeed()
        df = feed.download("RELIANCE", years=1)
    assert isinstance(df, pd.DataFrame)
    assert not df.empty


def test_download_normalises_column_names(mock_ohlcv):
    with patch("yfinance.Ticker") as mock_ticker:
        mock_ticker.return_value.history.return_value = mock_ohlcv
        feed = YFinanceFeed()
        df = feed.download("RELIANCE", years=1)
    assert all(c == c.lower() for c in df.columns)
    assert "close" in df.columns


def test_download_adds_ns_suffix(mock_ohlcv):
    with patch("yfinance.Ticker") as mock_ticker:
        mock_ticker.return_value.history.return_value = mock_ohlcv
        feed = YFinanceFeed()
        feed.download("RELIANCE", years=1)
    mock_ticker.assert_called_once_with("RELIANCE.NS")


def test_download_returns_empty_on_yfinance_failure():
    with patch("yfinance.Ticker") as mock_ticker:
        mock_ticker.return_value.history.side_effect = Exception("network error")
        feed = YFinanceFeed()
        df = feed.download("BADSYMBOL", years=1)
    assert isinstance(df, pd.DataFrame)
    assert df.empty


def test_validate_row_rejects_zero_volume():
    feed = YFinanceFeed()
    assert feed.validate_row(high=101.0, low=99.0, close=100.0, volume=0) is False


def test_validate_row_rejects_price_spike():
    feed = YFinanceFeed()
    assert feed.validate_row(high=200.0, low=99.0, close=100.0, volume=1_000_000) is False


def test_validate_row_accepts_good_data():
    feed = YFinanceFeed()
    assert feed.validate_row(high=101.0, low=99.0, close=100.0, volume=1_000_000) is True


def test_get_last_date_returns_none_for_unknown_symbol():
    mock_db = MagicMock()
    mock_db.execute.return_value.scalar.return_value = None
    feed = YFinanceFeed()
    result = feed.get_last_date(mock_db, "UNKNOWN")
    assert result is None
