from domains.data.nse_universe import NSE_SYMBOLS, get_yfinance_symbol


def test_universe_has_sufficient_stocks():
    assert len(NSE_SYMBOLS) >= 200


def test_symbols_are_uppercase():
    for sym in NSE_SYMBOLS:
        assert sym == sym.upper(), f"{sym} is not uppercase"


def test_symbols_have_no_ns_suffix():
    for sym in NSE_SYMBOLS:
        assert not sym.endswith(".NS"), f"{sym} should not include .NS suffix"


def test_get_yfinance_symbol():
    assert get_yfinance_symbol("RELIANCE") == "RELIANCE.NS"
    assert get_yfinance_symbol("TCS") == "TCS.NS"


def test_known_symbols_present():
    assert "RELIANCE" in NSE_SYMBOLS
    assert "TCS" in NSE_SYMBOLS
    assert "INFY" in NSE_SYMBOLS
    assert "HDFCBANK" in NSE_SYMBOLS
