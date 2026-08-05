from sqlalchemy import inspect
from database import engine, Base
import models  # noqa: F401


def _table_columns(table_name: str) -> set[str]:
    inspector = inspect(engine)
    return {col["name"] for col in inspector.get_columns(table_name)}


def setup_module():
    Base.metadata.create_all(bind=engine)


def test_stocks_table_exists():
    Base.metadata.create_all(bind=engine)
    inspector = inspect(engine)
    assert "stocks" in inspector.get_table_names()


def test_stocks_columns():
    cols = _table_columns("stocks")
    assert {"id", "symbol", "name", "sector", "exchange", "is_active"}.issubset(cols)


def test_stock_prices_daily_columns():
    cols = _table_columns("stock_prices_daily")
    assert {"id", "symbol", "date", "open", "high", "low", "close", "volume"}.issubset(cols)


def test_stock_prices_intraday_columns():
    cols = _table_columns("stock_prices_intraday")
    assert {"id", "symbol", "timestamp", "open", "high", "low", "close", "volume", "interval"}.issubset(cols)


def test_all_20_tables_exist():
    Base.metadata.create_all(bind=engine)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    expected = {
        "stocks", "stock_prices_daily", "stock_prices_intraday",
        "fundamentals", "corporate_actions", "news",
        "strategies", "strategy_signals", "backtest_results", "backtest_trades",
        "portfolio_holdings", "trades", "orders", "exit_rules", "watchlist",
        "ai_analyses", "ai_conversations",
        "alerts", "alert_history", "data_quality_log",
    }
    assert expected.issubset(tables), f"Missing tables: {expected - tables}"
