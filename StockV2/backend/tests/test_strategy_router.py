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
    from domains.strategies.seed import seed_strategies
    seed_strategies(db)
    strat_id = db.execute(text("SELECT id FROM strategies WHERE name='RSI Oversold/Overbought'")).fetchone()[0]
    db.execute(text(
        "INSERT INTO stocks (symbol, name, exchange, is_active, added_at) VALUES ('TCS', 'TCS', 'NSE', 1, datetime('now'))"
    ))
    db.execute(text(
        "INSERT INTO strategy_signals (symbol, strategy_id, signal_date, signal_type, price_at_signal, confidence_score, created_at) "
        "VALUES ('TCS', :sid, date('now'), 'BUY', 3500.0, 0.80, datetime('now'))"
    ), {"sid": strat_id})
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


def test_get_strategies_returns_10(client):
    response = client.get("/api/v1/strategies")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 10


def test_get_signals_today_returns_list(client):
    response = client.get("/api/v1/signals/today")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1


def test_get_signals_today_has_strategy_name(client):
    response = client.get("/api/v1/signals/today")
    assert "strategy_name" in response.json()[0]


def test_get_signals_with_symbol_filter(client):
    response = client.get("/api/v1/signals?symbol=TCS")
    assert response.status_code == 200
    data = response.json()
    assert all(s["symbol"] == "TCS" for s in data)


def test_get_signal_by_id(client):
    signals = client.get("/api/v1/signals/today").json()
    signal_id = signals[0]["id"]
    response = client.get(f"/api/v1/signals/{signal_id}")
    assert response.status_code == 200
    assert response.json()["id"] == signal_id


def test_get_signal_not_found(client):
    response = client.get("/api/v1/signals/99999")
    assert response.status_code == 404


def test_unauthorized_without_key():
    from main import app
    c = TestClient(app)
    response = c.get("/api/v1/strategies")
    assert response.status_code == 401
