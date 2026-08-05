import pytest
from unittest.mock import MagicMock
from domains.data.feeds.angel_one_feed import AngelOneFeed


def test_feed_initialises_without_credentials():
    feed = AngelOneFeed(api_key="", client_id="", password="", totp_secret="")
    assert feed is not None
    assert feed.connected is False


def test_get_quote_returns_none_when_not_connected():
    feed = AngelOneFeed(api_key="", client_id="", password="", totp_secret="")
    result = feed.get_quote("RELIANCE")
    assert result is None


def test_get_quote_returns_price_when_connected():
    feed = AngelOneFeed(api_key="key", client_id="cid", password="pass", totp_secret="secret")
    mock_api = MagicMock()
    mock_api.getMarketData.return_value = {
        "status": True,
        "data": {"fetched": [{"ltp": 2850.50, "tradingSymbol": "RELIANCE-EQ"}]},
    }
    feed._api = mock_api
    feed._connected = True
    feed._get_token = lambda sym: "2885"  # stub token map (full map implemented in Plan 2)

    result = feed.get_quote("RELIANCE")
    assert result is not None
    assert result["ltp"] == 2850.50
    assert result["symbol"] == "RELIANCE"


def test_get_quote_returns_none_on_api_error():
    feed = AngelOneFeed(api_key="key", client_id="cid", password="pass", totp_secret="secret")
    mock_api = MagicMock()
    mock_api.getMarketData.side_effect = Exception("API error")
    feed._api = mock_api
    feed._connected = True

    result = feed.get_quote("RELIANCE")
    assert result is None


def test_is_market_hours_returns_bool():
    feed = AngelOneFeed(api_key="", client_id="", password="", totp_secret="")
    result = feed.is_market_hours()
    assert isinstance(result, bool)
