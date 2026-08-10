# backend/tests/test_backtest_router.py
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import pandas as pd

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
    # Seed 300 days for RELIANCE — same pattern as runner test
    dates = pd.bdate_range("2020-01-01", periods=300)
    for i, d in enumerate(dates):
        close = 2000.0 + i * 3.0
        db.execute(text("""
            INSERT INTO stock_prices_daily
                (symbol, date, open, high, low, close, volume, data_source)
            VALUES (:sym, :d, :o, :h, :l, :c, :v, 'test')
        """), {
            "sym": "RELIANCE",
            "d": d.date().isoformat(),
            "o": round(close * 0.995, 2),
            "h": round(close * 1.010, 2),
            "l": round(close * 0.990, 2),
            "c": close,
            "v": 1_000_000,
        })
    db.commit()
    db.close()

    def override_get_db():
        session = TestSession()
        try:
            yield session
        finally:
            session.close()

    from main import app
    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app, headers={"X-API-Key": settings.api_key})


def test_run_backtest_returns_metrics(client):
    r = client.post("/api/v1/backtest/run", json={
        "symbol": "RELIANCE",
        "from_date": "2021-01-04",
        "to_date": "2021-03-31",
    })
    assert r.status_code == 200
    data = r.json()
    assert "result_id" in data
    assert "total_trades" in data
    assert "win_rate" in data
    assert "cagr" in data


def test_run_backtest_bad_symbol(client):
    r = client.post("/api/v1/backtest/run", json={
        "symbol": "FAKESTK",
        "from_date": "2021-01-04",
        "to_date": "2021-03-31",
    })
    assert r.status_code == 400


def test_list_results(client):
    r = client.get("/api/v1/backtest/results")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
    assert len(r.json()) >= 1


def test_list_results_filtered_by_symbol(client):
    r = client.get("/api/v1/backtest/results?symbol=RELIANCE")
    assert r.status_code == 200
    for item in r.json():
        assert item["symbol"] == "RELIANCE"


def test_get_result_by_id(client):
    run_r = client.post("/api/v1/backtest/run", json={
        "symbol": "RELIANCE",
        "from_date": "2021-01-04",
        "to_date": "2021-03-31",
    })
    result_id = run_r.json()["result_id"]
    r = client.get(f"/api/v1/backtest/results/{result_id}")
    assert r.status_code == 200
    assert r.json()["id"] == result_id


def test_get_result_trades(client):
    run_r = client.post("/api/v1/backtest/run", json={
        "symbol": "RELIANCE",
        "from_date": "2021-01-04",
        "to_date": "2021-03-31",
    })
    result_id = run_r.json()["result_id"]
    r = client.get(f"/api/v1/backtest/results/{result_id}/trades")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_get_result_404(client):
    r = client.get("/api/v1/backtest/results/99999")
    assert r.status_code == 404


def test_unauthorized(client):
    from main import app
    c = TestClient(app)
    r = c.post("/api/v1/backtest/run", json={
        "symbol": "RELIANCE", "from_date": "2021-01-04", "to_date": "2021-03-31"
    })
    assert r.status_code == 401
