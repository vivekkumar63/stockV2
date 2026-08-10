import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base
import models  # noqa


@pytest.fixture(scope="module")
def db():
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    Session = sessionmaker(bind=eng)
    session = Session()

    session.execute(text(
        "INSERT INTO strategies (name, type, description, is_active, created_at) "
        "VALUES ('RSI', 'technical', '', 1, datetime('now'))"
    ))
    session.execute(text(
        "INSERT INTO stocks (symbol, name, exchange, is_active, added_at) "
        "VALUES ('TCS', 'TCS', 'NSE', 1, datetime('now'))"
    ))
    # Signal 1: BUY with stop_loss and target
    session.execute(text("""
        INSERT INTO strategy_signals
            (symbol, strategy_id, signal_date, signal_type, price_at_signal,
             confidence_score, suggested_stop_loss, suggested_target,
             holding_period_days, created_at)
        VALUES ('TCS', 1, date('now'), 'BUY', 1000.0, 0.80, 900.0, 1150.0, 15, datetime('now'))
    """))
    # Signal 2: SELL — should be rejected by enter()
    session.execute(text("""
        INSERT INTO strategy_signals
            (symbol, strategy_id, signal_date, signal_type, price_at_signal,
             confidence_score, created_at)
        VALUES ('TCS', 1, date('now'), 'SELL', 1000.0, 0.70, datetime('now'))
    """))
    session.commit()
    yield session
    session.close()


def test_enter_creates_buy_trade(db):
    from domains.portfolio.paper_trader import PaperTrader
    result = PaperTrader(db).enter(signal_id=1, price=1000.0)
    assert result is not None
    assert result["trade_type"] == "BUY"
    assert result["symbol"] == "TCS"
    assert result["quantity"] > 0
    assert result["mode"] == "paper"


def test_enter_creates_portfolio_holding(db):
    count = db.execute(
        text("SELECT COUNT(*) FROM portfolio_holdings WHERE symbol='TCS' AND is_active=1")
    ).fetchone()[0]
    assert count == 1


def test_enter_creates_exit_rule(db):
    count = db.execute(
        text("SELECT COUNT(*) FROM exit_rules WHERE symbol='TCS'")
    ).fetchone()[0]
    assert count >= 1


def test_enter_rejects_sell_signal(db):
    from domains.portfolio.paper_trader import PaperTrader
    result = PaperTrader(db).enter(signal_id=2, price=1000.0)
    assert result is None


def test_exit_creates_sell_trade_and_closes_holding(db):
    from domains.portfolio.paper_trader import PaperTrader
    result = PaperTrader(db).exit("TCS", 1100.0, "target_hit")
    assert result is not None
    assert result["trade_type"] == "SELL"
    assert result["price"] == 1100.0
    holding = db.execute(
        text("SELECT is_active FROM portfolio_holdings WHERE symbol='TCS'")
    ).fetchone()
    assert holding[0] == 0


def test_exit_returns_none_for_missing_holding(db):
    from domains.portfolio.paper_trader import PaperTrader
    result = PaperTrader(db).exit("NONEXISTENT", 500.0, "manual")
    assert result is None
