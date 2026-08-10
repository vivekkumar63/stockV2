import json
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base, get_db
from settings import settings
import models  # noqa


@pytest.fixture(scope="module")
def client():
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(test_engine)
    TestSession = sessionmaker(bind=test_engine)

    db = TestSession()
    # Seed strategy + stock + BUY signal
    db.execute(text(
        "INSERT INTO strategies (name, type, description, is_active, created_at) "
        "VALUES ('RSI', 'technical', '', 1, datetime('now'))"
    ))
    db.execute(text(
        "INSERT INTO stocks (symbol, name, exchange, is_active, added_at) "
        "VALUES ('INFY', 'Infosys', 'NSE', 1, datetime('now'))"
    ))
    db.execute(text("""
        INSERT INTO strategy_signals
            (symbol, strategy_id, signal_date, signal_type, price_at_signal,
             confidence_score, suggested_stop_loss, suggested_target,
             holding_period_days, created_at)
        VALUES ('INFY', 1, date('now'), 'BUY', 1500.0, 0.78, 1395.0, 1725.0, 15, datetime('now'))
    """))
    # Seed holding for exit test
    db.execute(text("""
        INSERT INTO portfolio_holdings
            (symbol, quantity, avg_buy_price, first_buy_date, last_buy_date, is_active)
        VALUES ('WIPRO', 50, 400.0, date('now'), date('now'), 1)
    """))
    pnl_notes = json.dumps({"reason": "target_hit", "buy_avg": 400.0, "pnl": 2500.0, "pnl_pct": 12.5})
    db.execute(text("""
        INSERT INTO trades
            (symbol, trade_type, quantity, price, total_value, brokerage, mode, notes, trade_date)
        VALUES ('TCS', 'SELL', 100, 1150.0, 115000.0, 0, 'paper', :notes, datetime('now'))
    """), {"notes": pnl_notes})
    db.commit()
    db.close()

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    from main import app
    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app, headers={"X-API-Key": settings.api_key})


def test_get_portfolio_summary(client):
    r = client.get("/api/v1/portfolio/summary")
    assert r.status_code == 200
    data = r.json()
    assert "paper_capital" in data
    assert "cash_available" in data
    assert "open_positions" in data


def test_get_portfolio_holdings(client):
    r = client.get("/api/v1/portfolio/holdings")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_get_portfolio_trades(client):
    r = client.get("/api/v1/portfolio/trades")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_get_portfolio_pnl(client):
    r = client.get("/api/v1/portfolio/pnl")
    assert r.status_code == 200
    data = r.json()
    assert "total_pnl" in data
    assert data["total_pnl"] == 2500.0


def test_paper_enter_from_signal(client):
    r = client.post("/api/v1/portfolio/enter/1", json={"price": 1500.0})
    assert r.status_code == 200
    data = r.json()
    assert data["trade_type"] == "BUY"
    assert data["symbol"] == "INFY"


def test_paper_exit_symbol(client):
    r = client.post("/api/v1/portfolio/exit/WIPRO", json={"price": 450.0, "reason": "manual"})
    assert r.status_code == 200
    assert r.json()["trade_type"] == "SELL"


def test_paper_exit_missing_holding(client):
    r = client.post("/api/v1/portfolio/exit/NONSTOCK", json={"price": 100.0})
    assert r.status_code == 404


def test_get_watchlist(client):
    r = client.get("/api/v1/watchlist")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_add_to_watchlist(client):
    r = client.post("/api/v1/watchlist/HDFC", json={"reason": "breakout watch"})
    assert r.status_code == 200
    assert r.json()["symbol"] == "HDFC"


def test_remove_from_watchlist(client):
    client.post("/api/v1/watchlist/AXISBANK", json={})
    r = client.delete("/api/v1/watchlist/AXISBANK")
    assert r.status_code == 200


def test_unauthorized_without_key():
    from main import app
    c = TestClient(app)
    r = c.get("/api/v1/portfolio/summary")
    assert r.status_code == 401
