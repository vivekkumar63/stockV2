"""Tests for fii_dii_fetcher parse logic."""


def test_parse_fii_dii_response_flat():
    from domains.data.fii_dii_fetcher import _parse_fii_dii_response
    rows = [
        {"category": "FII/FPI", "buyValue": "8420.10", "sellValue": "7179.60", "netValue": "1240.50", "date": "19-Aug-2026"},
        {"category": "DII",     "buyValue": "4210.30", "sellValue": "3530.10", "netValue":  "680.20", "date": "19-Aug-2026"},
        {"category": "PRO",     "buyValue":  "100.00", "sellValue":  "120.00", "netValue":  "-20.00", "date": "19-Aug-2026"},
    ]
    result = _parse_fii_dii_response(rows)
    assert result is not None
    assert result["fii_net_equity"] == 1240.50
    assert result["fii_buy"] == 8420.10
    assert result["fii_sell"] == 7179.60
    assert result["dii_net_equity"] == 680.20
    assert result["dii_buy"] == 4210.30
    assert result["dii_sell"] == 3530.10


def test_parse_fii_dii_response_clienttype_key():
    """NSE sometimes returns 'clientType' instead of 'category'."""
    from domains.data.fii_dii_fetcher import _parse_fii_dii_response
    rows = [
        {"clientType": "FII/FPI", "buyValue": "5000.00", "sellValue": "4000.00", "netValue": "1000.00"},
        {"clientType": "DII",     "buyValue": "2000.00", "sellValue": "1500.00", "netValue":  "500.00"},
    ]
    result = _parse_fii_dii_response(rows)
    assert result is not None
    assert result["fii_net_equity"] == 1000.00
    assert result["dii_net_equity"] == 500.00


def test_parse_fii_dii_response_no_relevant_rows():
    from domains.data.fii_dii_fetcher import _parse_fii_dii_response
    rows = [{"category": "CLIENT", "buyValue": "100.00", "sellValue": "90.00", "netValue": "10.00"}]
    result = _parse_fii_dii_response(rows)
    assert result is None


def test_parse_fii_dii_response_empty():
    from domains.data.fii_dii_fetcher import _parse_fii_dii_response
    assert _parse_fii_dii_response([]) is None


def test_parse_fii_dii_response_comma_values():
    """Values like '8,420.10' must be parsed correctly."""
    from domains.data.fii_dii_fetcher import _parse_fii_dii_response
    rows = [
        {"category": "FII/FPI", "buyValue": "8,420.10", "sellValue": "7,179.60", "netValue": "1,240.50"},
        {"category": "DII",     "buyValue": "4,210.30", "sellValue": "3,530.10", "netValue":   "680.20"},
    ]
    result = _parse_fii_dii_response(rows)
    assert result is not None
    assert abs(result["fii_net_equity"] - 1240.50) < 0.01
