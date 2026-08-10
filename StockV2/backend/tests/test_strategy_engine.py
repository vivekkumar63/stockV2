import pytest
from datetime import date
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base
import models  # noqa


@pytest.fixture(scope="module")
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    session.execute(text(
        "INSERT INTO strategies (name, type, description, is_active, created_at) VALUES "
        "('RSI Oversold/Overbought', 'technical', '', 1, datetime('now')),"
        "('MACD Crossover', 'technical', '', 1, datetime('now')),"
        "('EMA Crossover (9/21)', 'technical', '', 1, datetime('now')),"
        "('SMA Crossover (20/50)', 'technical', '', 1, datetime('now')),"
        "('SuperTrend', 'technical', '', 1, datetime('now')),"
        "('Bollinger Band Squeeze', 'technical', '', 1, datetime('now')),"
        "('Volume Breakout', 'technical', '', 1, datetime('now')),"
        "('Mean Reversion', 'technical', '', 1, datetime('now')),"
        "('Volatility Breakout', 'technical', '', 1, datetime('now')),"
        "('Swing Trade Trend Rider', 'technical', '', 1, datetime('now'))"
    ))

    session.execute(text(
        "INSERT INTO stocks (symbol, name, exchange, is_active, added_at) VALUES ('TCS', 'Tata Consultancy Services', 'NSE', 1, datetime('now'))"
    ))

    for i in range(60):
        close = 3500.0 - i * 2
        session.execute(text(
            "INSERT INTO stock_prices_daily (symbol, date, open, high, low, close, volume, data_source) "
            "VALUES ('TCS', date('2024-01-01', :offset), :open, :high, :low, :close, 1000000, 'yfinance')"
        ), {"offset": f"+{i} days", "open": close + 5, "high": close + 10, "low": close - 10, "close": close})

    session.commit()
    yield session
    session.close()


def test_engine_loads_strategy_ids(db):
    from domains.strategies.engine import StrategyEngine
    engine = StrategyEngine(db)
    assert len(engine._strategy_id_map) == 10
    assert "RSI Oversold/Overbought" in engine._strategy_id_map


def test_engine_scan_all_returns_dict(db):
    from domains.strategies.engine import StrategyEngine
    engine = StrategyEngine(db)
    results = engine.scan_all(["TCS"], date(2024, 3, 1))
    assert isinstance(results, dict)


def test_engine_scan_all_saves_signals_to_db(db):
    from domains.strategies.engine import StrategyEngine
    engine = StrategyEngine(db)
    engine.scan_all(["TCS"], date(2024, 3, 1))
    count = db.execute(text("SELECT COUNT(*) FROM strategy_signals WHERE symbol='TCS'")).fetchone()[0]
    assert count >= 1


def test_engine_skips_symbol_with_no_prices(db):
    from domains.strategies.engine import StrategyEngine
    engine = StrategyEngine(db)
    results = engine.scan_all(["FAKESTOCK"], date(2024, 3, 1))
    assert "FAKESTOCK" not in results


def test_engine_skips_symbol_with_too_few_prices(db):
    from domains.strategies.engine import StrategyEngine
    db.execute(text("INSERT INTO stocks (symbol, name, exchange, is_active, added_at) VALUES ('TINYSTOCK', '', 'NSE', 1, datetime('now'))"))
    for i in range(5):
        db.execute(text(
            "INSERT INTO stock_prices_daily (symbol, date, open, high, low, close, volume, data_source) "
            "VALUES ('TINYSTOCK', date('2024-01-01', :offset), 100, 105, 95, 100, 100000, 'yfinance')"
        ), {"offset": f"+{i} days"})
    db.commit()
    from domains.strategies.engine import StrategyEngine
    results = StrategyEngine(db).scan_all(["TINYSTOCK"], date(2024, 3, 1))
    assert "TINYSTOCK" not in results
