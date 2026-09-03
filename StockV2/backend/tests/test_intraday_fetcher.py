import pandas as pd
import pytest
from unittest.mock import MagicMock, patch
from domains.data.intraday_fetcher import IntradayFetcher


def _make_yf_df(n_rows: int = 12) -> pd.DataFrame:
    """Minimal fake yfinance 5-min response: Datetime index + OHLCV columns."""
    import numpy as np
    idx = pd.date_range(start="2024-01-02 09:30", periods=n_rows, freq="5min", tz="Asia/Kolkata")
    data = {
        "Open":   np.full(n_rows, 100.0),
        "High":   np.full(n_rows, 102.0),
        "Low":    np.full(n_rows, 98.0),
        "Close":  np.full(n_rows, 101.0),
        "Volume": np.full(n_rows, 50000),
    }
    return pd.DataFrame(data, index=idx)


def test_fetch_one_normalizes_columns():
    fetcher = IntradayFetcher()
    fake_df = _make_yf_df()

    with patch("domains.data.intraday_fetcher.yf.Ticker") as mock_ticker:
        mock_ticker.return_value.history.return_value = fake_df
        df = fetcher.fetch_one("RELIANCE")

    assert list(df.columns) == ["datetime", "open", "high", "low", "close", "volume"]
    assert len(df) == 12
    assert df["close"].iloc[0] == 101.0


def test_fetch_one_returns_empty_on_yf_error():
    fetcher = IntradayFetcher()
    with patch("domains.data.intraday_fetcher.yf.Ticker") as mock_ticker:
        mock_ticker.return_value.history.side_effect = Exception("network error")
        df = fetcher.fetch_one("BADSTOCK")
    assert df.empty


def test_fetch_and_store_upserts_rows():
    fetcher = IntradayFetcher()
    db = MagicMock()

    with patch.object(fetcher, "fetch_one", return_value=pd.DataFrame({
        "datetime": pd.date_range("2024-01-02 09:30", periods=3, freq="5min"),
        "open": [100.0, 100.0, 100.0],
        "high": [102.0, 102.0, 102.0],
        "low":  [98.0,  98.0,  98.0],
        "close":[101.0, 101.0, 101.0],
        "volume":[50000, 50000, 50000],
    })):
        fetcher.fetch_and_store(["RELIANCE"], db)

    assert db.execute.called
    assert db.commit.called
