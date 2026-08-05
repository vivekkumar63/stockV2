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
    db.execute(text("INSERT INTO stocks (symbol, name, sector, exchange, is_active, added_at) VALUES ('TCS', 'Tata Consultancy Services', 'IT', 'NSE', 1, datetime('now'))"))
    db.execute(text("INSERT INTO stock_prices_daily (symbol, date, open, high, low, close, volume, data_source) VALUES ('TCS', '2024-01-01', 3500, 3550, 3480, 3520, 1000000, 'yfinance')"))
    db.execute(text("INSERT INTO stock_prices_daily (symbol, date, open, high, low, close, volume, data_source) VALUES ('TCS', '2024-01-02', 3520, 3570, 3510, 3550, 1200000, 'yfinance')"))
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


def test_list_stocks_returns_list(client):
    response = client.get("/api/v1/stocks")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1


def test_list_stocks_includes_seeded_stock(client):
    response = client.get("/api/v1/stocks")
    symbols = [s["symbol"] for s in response.json()]
    assert "TCS" in symbols


def test_get_stock_detail(client):
    response = client.get("/api/v1/stocks/TCS")
    assert response.status_code == 200
    data = response.json()
    assert data["symbol"] == "TCS"
    assert "name" in data


def test_get_unknown_stock_returns_404(client):
    response = client.get("/api/v1/stocks/FAKESTOCK")
    assert response.status_code == 404


def test_get_stock_prices(client):
    response = client.get("/api/v1/stocks/TCS/prices")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 2
    assert data[0]["symbol"] == "TCS"
    assert "close" in data[0]


def test_get_stock_prices_date_filter(client):
    response = client.get("/api/v1/stocks/TCS/prices?from_date=2024-01-02")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["date"] == "2024-01-02"
