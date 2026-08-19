"""Tests for GET /intelligence/top-opportunities endpoint."""
import sys, os
from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database import Base, get_db
from settings import settings
import models  # noqa


def _make_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    # index_trend is created via raw DDL in main.py lifespan, not via ORM
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS index_trend (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                index_name  TEXT NOT NULL,
                date        DATE NOT NULL,
                close       REAL NOT NULL,
                sma20       REAL,
                sma50       REAL,
                above_sma20 INTEGER NOT NULL DEFAULT 0,
                above_sma50 INTEGER NOT NULL DEFAULT 0,
                trend_label TEXT NOT NULL,
                computed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(index_name, date)
            )
        """))
        conn.commit()
    return engine


def _make_regime_mock():
    """Return a mock that satisfies MarketRegimeEngine.get_or_compute(db)."""
    mock = MagicMock()
    mock.regime = "BULL"
    mock.confidence = 0.75
    return mock


@pytest.fixture(scope="module")
def client():
    engine = _make_engine()
    Session = sessionmaker(bind=engine)

    db = Session()
    today = date.today().isoformat()

    db.execute(text("""
        INSERT INTO strategies (id, name, type, is_active, created_at)
        VALUES (1, 'StratA', 'technical', 1, CURRENT_TIMESTAMP),
               (2, 'StratB', 'technical', 1, CURRENT_TIMESTAMP)
    """))
    db.execute(text("""
        INSERT INTO strategy_signals
            (symbol, strategy_id, signal_date, signal_type,
             confidence_score, price_at_signal, suggested_stop_loss, suggested_target,
             holding_period_days, created_at)
        VALUES
            ('RELIANCE', 1, :today, 'BUY', 0.80, 2400.0, 5.0, 10.0, 15, CURRENT_TIMESTAMP),
            ('TCS',      2, :today, 'BUY', 0.60, 3500.0, 5.0, 10.0, 15, CURRENT_TIMESTAMP),
            ('INFY',     1, :today, 'BUY', 0.70, 1800.0, 5.0, 10.0, 15, CURRENT_TIMESTAMP)
    """), {"today": today})
    db.commit()
    db.close()

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    from main import app
    app.dependency_overrides[get_db] = override
    # Patch MarketRegimeEngine so the endpoint returns 200 on a bare SQLite DB
    with patch(
        "domains.intelligence.router.MarketRegimeEngine.get_or_compute",
        return_value=_make_regime_mock(),
    ):
        yield TestClient(app, headers={"X-API-Key": settings.api_key})


def test_top_opportunities_returns_list(client):
    r = client.get("/api/v1/intelligence/top-opportunities")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_top_opportunities_sorted_by_score_descending(client):
    r = client.get("/api/v1/intelligence/top-opportunities")
    assert r.status_code == 200
    body = r.json()
    assert len(body) >= 1, "expected at least 1 result from 3 inserted signals"
    scores = [item["score"] for item in body]
    assert scores == sorted(scores, reverse=True)


def test_top_opportunities_limit_respected(client):
    r = client.get("/api/v1/intelligence/top-opportunities?limit=2")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 2, f"expected exactly 2 results with limit=2, got {len(body)}"


def test_top_opportunities_empty_when_no_signals():
    """Returns [] immediately when there are no BUY signals today."""
    engine = _make_engine()
    Session = sessionmaker(bind=engine)

    saved = {}
    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    from main import app
    saved["orig"] = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override
    try:
        c = TestClient(app, headers={"X-API-Key": settings.api_key})
        r = c.get("/api/v1/intelligence/top-opportunities")
        assert r.status_code == 200
        assert r.json() == []
    finally:
        if saved["orig"] is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = saved["orig"]


def test_top_opportunities_response_shape(client):
    r = client.get("/api/v1/intelligence/top-opportunities?limit=1")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    item = body[0]
    for field in ("signal_id", "symbol", "strategy_id", "strategy_name",
                  "score", "grade", "regime", "breakdown",
                  "stop_loss_price", "target_price"):
        assert field in item, f"missing field: {field}"
    assert isinstance(item["breakdown"], dict)
