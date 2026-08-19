"""Tests for entry_window module."""


def test_is_in_entry_window_exact_match():
    from domains.alerts.entry_window import is_in_entry_window
    assert is_in_entry_window(current_price=100.0, entry_price=100.0) is True


def test_is_in_entry_window_within_2pct_above():
    from domains.alerts.entry_window import is_in_entry_window
    assert is_in_entry_window(current_price=101.9, entry_price=100.0) is True


def test_is_in_entry_window_within_2pct_below():
    from domains.alerts.entry_window import is_in_entry_window
    assert is_in_entry_window(current_price=98.1, entry_price=100.0) is True


def test_is_in_entry_window_outside_above():
    from domains.alerts.entry_window import is_in_entry_window
    assert is_in_entry_window(current_price=102.1, entry_price=100.0) is False


def test_is_in_entry_window_outside_below():
    from domains.alerts.entry_window import is_in_entry_window
    assert is_in_entry_window(current_price=97.9, entry_price=100.0) is False


def test_get_signals_in_entry_window_filters_non_buy():
    from unittest.mock import MagicMock
    from domains.alerts.entry_window import get_signals_in_entry_window

    db = MagicMock()
    db.execute.return_value.fetchone.return_value = None  # not already alerted

    signals = [
        {"symbol": "SBIN", "strategy_id": 1, "signal_type": "SELL",
         "price_at_signal": 820.0, "signal_date": "2026-08-19"},
    ]
    live_prices = {"SBIN": 821.0}
    result = get_signals_in_entry_window(db, signals, live_prices)
    assert result == []


def test_get_signals_in_entry_window_passes_valid_signal():
    from unittest.mock import MagicMock
    from domains.alerts.entry_window import get_signals_in_entry_window

    db = MagicMock()
    db.execute.return_value.fetchone.return_value = None  # not already alerted

    signals = [
        {"symbol": "SBIN", "strategy_id": 1, "signal_type": "BUY",
         "price_at_signal": 820.0, "signal_date": "2026-08-19"},
    ]
    live_prices = {"SBIN": 821.0}  # within 2%
    result = get_signals_in_entry_window(db, signals, live_prices)
    assert len(result) == 1
    assert result[0]["symbol"] == "SBIN"


def test_get_signals_in_entry_window_skips_already_alerted():
    from unittest.mock import MagicMock
    from domains.alerts.entry_window import get_signals_in_entry_window

    db = MagicMock()
    db.execute.return_value.fetchone.return_value = (1,)  # already alerted

    signals = [
        {"symbol": "SBIN", "strategy_id": 1, "signal_type": "BUY",
         "price_at_signal": 820.0, "signal_date": "2026-08-19"},
    ]
    live_prices = {"SBIN": 821.0}
    result = get_signals_in_entry_window(db, signals, live_prices)
    assert result == []


def test_get_signals_in_entry_window_skips_missing_live_price():
    from unittest.mock import MagicMock
    from domains.alerts.entry_window import get_signals_in_entry_window

    db = MagicMock()
    signals = [
        {"symbol": "SBIN", "strategy_id": 1, "signal_type": "BUY",
         "price_at_signal": 820.0, "signal_date": "2026-08-19"},
    ]
    live_prices = {}  # SBIN missing
    result = get_signals_in_entry_window(db, signals, live_prices)
    assert result == []
