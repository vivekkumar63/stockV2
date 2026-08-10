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

    from domains.strategies.seed import seed_strategies
    seed_strategies(session)

    strat_id = session.execute(text("SELECT id FROM strategies WHERE name='RSI Oversold/Overbought'")).fetchone()[0]
    session.execute(text(
        "INSERT INTO strategy_signals (symbol, strategy_id, signal_date, signal_type, price_at_signal, confidence_score, created_at) "
        "VALUES ('TCS', :sid, date('now'), 'BUY', 3500.0, 0.75, datetime('now'))"
    ), {"sid": strat_id})
    session.commit()
    yield session
    session.close()


def test_seed_inserts_10_strategies(db):
    count = db.execute(text("SELECT COUNT(*) FROM strategies")).fetchone()[0]
    assert count == 10


def test_seed_is_idempotent(db):
    from domains.strategies.seed import seed_strategies
    seed_strategies(db)
    count = db.execute(text("SELECT COUNT(*) FROM strategies")).fetchone()[0]
    assert count == 10


def test_get_all_strategies_returns_10(db):
    from domains.strategies.service import StrategyService
    strategies = StrategyService(db).get_all_strategies()
    assert len(strategies) == 10
    assert all("name" in s for s in strategies)


def test_get_today_signals_returns_list(db):
    from domains.strategies.service import StrategyService
    signals = StrategyService(db).get_today_signals()
    assert isinstance(signals, list)
    assert len(signals) >= 1


def test_get_today_signals_include_strategy_name(db):
    from domains.strategies.service import StrategyService
    signals = StrategyService(db).get_today_signals()
    assert "strategy_name" in signals[0]
    assert signals[0]["strategy_name"] == "RSI Oversold/Overbought"


def test_get_signal_by_id(db):
    from domains.strategies.service import StrategyService
    signals = StrategyService(db).get_today_signals()
    signal_id = signals[0]["id"]
    signal = StrategyService(db).get_signal_by_id(signal_id)
    assert signal is not None
    assert signal["symbol"] == "TCS"


def test_get_signal_by_id_returns_none_for_missing(db):
    from domains.strategies.service import StrategyService
    assert StrategyService(db).get_signal_by_id(99999) is None


def test_get_signals_filter_by_symbol(db):
    from domains.strategies.service import StrategyService
    signals = StrategyService(db).get_signals(symbol="TCS")
    assert all(s["symbol"] == "TCS" for s in signals)


def test_get_signals_filter_by_type(db):
    from domains.strategies.service import StrategyService
    signals = StrategyService(db).get_signals(signal_type="BUY")
    assert all(s["signal_type"] == "BUY" for s in signals)
