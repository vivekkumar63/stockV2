import json
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

    # Active holding
    session.execute(text("""
        INSERT INTO portfolio_holdings
            (symbol, quantity, avg_buy_price, first_buy_date, last_buy_date, is_active)
        VALUES ('TCS', 100, 1000.0, date('now'), date('now'), 1)
    """))
    session.execute(text("""
        INSERT INTO exit_rules
            (order_id, symbol, entry_price, stop_loss_price,
             target_1_price, target_2_price, partial_exit_at_t1)
        VALUES (1, 'TCS', 1000.0, 930.0, 1150.0, 1200.0, 0)
    """))
    # BUY trade
    session.execute(text("""
        INSERT INTO trades
            (symbol, trade_type, quantity, price, total_value, brokerage, mode, trade_date)
        VALUES ('TCS', 'BUY', 100, 1000.0, 100000.0, 0, 'paper', datetime('now'))
    """))
    # SELL trade with P&L in notes
    pnl_notes = json.dumps({"reason": "target_hit", "buy_avg": 1000.0, "pnl": 15000.0, "pnl_pct": 15.0})
    session.execute(text("""
        INSERT INTO trades
            (symbol, trade_type, quantity, price, total_value, brokerage, mode, notes, trade_date)
        VALUES ('INFY', 'SELL', 100, 1150.0, 115000.0, 0, 'paper', :notes, datetime('now'))
    """), {"notes": pnl_notes})
    session.commit()
    yield session
    session.close()


def test_get_holdings_returns_active_position(db):
    from domains.portfolio.service import PortfolioService
    holdings = PortfolioService(db).get_holdings()
    assert any(h["symbol"] == "TCS" for h in holdings)


def test_get_holdings_includes_exit_rule_data(db):
    from domains.portfolio.service import PortfolioService
    holdings = PortfolioService(db).get_holdings()
    tcs = next(h for h in holdings if h["symbol"] == "TCS")
    assert tcs["stop_loss_price"] == 930.0
    assert tcs["target_1_price"] == 1150.0


def test_get_portfolio_summary_structure(db):
    from domains.portfolio.service import PortfolioService
    summary = PortfolioService(db).get_portfolio_summary()
    assert "paper_capital" in summary
    assert "cash_available" in summary
    assert "open_positions" in summary
    assert summary["open_positions"] >= 1
    assert summary["cash_available"] < summary["paper_capital"]


def test_get_trade_history_returns_all_paper_trades(db):
    from domains.portfolio.service import PortfolioService
    trades = PortfolioService(db).get_trade_history()
    assert len(trades) >= 2


def test_get_closed_pnl_parses_notes(db):
    from domains.portfolio.service import PortfolioService
    result = PortfolioService(db).get_closed_pnl()
    assert result["total_pnl"] == 15000.0
    assert len(result["closed_trades"]) >= 1
    assert result["closed_trades"][0]["pnl"] == 15000.0


@pytest.fixture(scope="module")
def wl_db():
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    Session = sessionmaker(bind=eng)
    session = Session()
    yield session
    session.close()


def test_watchlist_add_and_get(wl_db):
    from domains.portfolio.watchlist_service import WatchlistService
    svc = WatchlistService(wl_db)
    item = svc.add("TCS", reason="RSI oversold")
    assert item["symbol"] == "TCS"
    items = svc.get_all()
    assert any(i["symbol"] == "TCS" for i in items)


def test_watchlist_add_is_idempotent(wl_db):
    from domains.portfolio.watchlist_service import WatchlistService
    svc = WatchlistService(wl_db)
    svc.add("TCS")
    svc.add("TCS")  # duplicate
    items = svc.get_all()
    assert sum(1 for i in items if i["symbol"] == "TCS") == 1


def test_watchlist_remove(wl_db):
    from domains.portfolio.watchlist_service import WatchlistService
    svc = WatchlistService(wl_db)
    svc.add("INFY")
    removed = svc.remove("INFY")
    assert removed is True
    assert not any(i["symbol"] == "INFY" for i in svc.get_all())


def test_watchlist_remove_missing_returns_false(wl_db):
    from domains.portfolio.watchlist_service import WatchlistService
    result = WatchlistService(wl_db).remove("NONEXISTENT")
    assert result is False
