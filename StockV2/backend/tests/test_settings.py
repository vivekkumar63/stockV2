from settings import settings


def test_settings_has_required_fields():
    assert hasattr(settings, "anthropic_api_key")
    assert hasattr(settings, "trading_mode")
    assert hasattr(settings, "total_capital")
    assert hasattr(settings, "api_key")


def test_settings_defaults():
    assert settings.trading_mode == "paper"
    assert settings.total_capital == 500_000
    assert settings.max_open_positions == 8
    assert settings.max_single_stock_pct == 20.0
    assert settings.host == "127.0.0.1"
    assert settings.port == 8000
