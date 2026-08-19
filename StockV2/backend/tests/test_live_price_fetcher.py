"""Tests for live_price_fetcher."""
import pandas as pd
from unittest.mock import patch


def test_fetch_live_prices_empty_symbols():
    from domains.data.live_price_fetcher import fetch_live_prices
    assert fetch_live_prices([]) == {}


def test_fetch_live_prices_single_symbol():
    from domains.data.live_price_fetcher import fetch_live_prices
    mock_df = pd.DataFrame({"Close": [100.0, 101.0, 102.5]})
    with patch("domains.data.live_price_fetcher.yf.download", return_value=mock_df) as mock_dl:
        result = fetch_live_prices(["RELIANCE"])
    mock_dl.assert_called_once()
    assert result == {"RELIANCE": 102.5}


def test_fetch_live_prices_handles_download_exception():
    from domains.data.live_price_fetcher import fetch_live_prices
    with patch("domains.data.live_price_fetcher.yf.download", side_effect=Exception("network")):
        result = fetch_live_prices(["RELIANCE"])
    assert result == {}


def test_fetch_live_prices_handles_empty_dataframe():
    from domains.data.live_price_fetcher import fetch_live_prices
    with patch("domains.data.live_price_fetcher.yf.download", return_value=pd.DataFrame()):
        result = fetch_live_prices(["RELIANCE"])
    assert result == {}


def test_fetch_live_prices_multi_symbol():
    from domains.data.live_price_fetcher import fetch_live_prices
    import pandas as pd
    arrays = [["RELIANCE.NS", "RELIANCE.NS", "SBIN.NS", "SBIN.NS"],
              ["Close", "Open", "Close", "Open"]]
    mi = pd.MultiIndex.from_arrays(arrays)
    mock_df = pd.DataFrame([[500.0, 495.0, 800.0, 795.0]], columns=mi)
    with patch("domains.data.live_price_fetcher.yf.download", return_value=mock_df):
        result = fetch_live_prices(["RELIANCE", "SBIN"])
    assert result["RELIANCE"] == 500.0
    assert result["SBIN"] == 800.0
