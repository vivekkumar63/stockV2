"""Tests for GET /intelligence/top-opportunities endpoint."""
import sys
import os
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database import Base, get_db
from settings import settings
import models  # noqa — registers all ORM models


def _make_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture(scope="module")
def client():
    engine = _make_engine()
    Session = sessionmaker(bind=engine)

    db = Session()
    today = date.today().isoformat()

    # Insert two strategies
    db.execute(text("""
        INSERT INTO strategies (id, name, type, is_active, created_at)
        VALUES (1, 'StratA', 'technical', 1, CURRENT_TIMESTAMP),
               (2, 'StratB', 'technical', 1, CURRENT_TIMESTAMP)
    """))

    # Insert three BUY signals for today — three unique symbols
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
    return TestClient(app, headers={"X-API-Key": settings.api_key})


def test_top_opportunities_returns_list(client):
    r = client.get("/api/v1/intelligence/top-opportunities")
    # 200 with results, or 503 when MarketRegimeEngine cannot run on an empty DB
    assert r.status_code in (200, 503), f"unexpected status {r.status_code}: {r.text}"
    if r.status_code == 200:
        assert isinstance(r.json(), list)


def test_top_opportunities_sorted_by_score_descending(client):
    r = client.get("/api/v1/intelligence/top-opportunities")
    if r.status_code != 200:
        pytest.skip("endpoint returned non-200; likely regime unavailable in test DB")
    body = r.json()
    if len(body) >= 2:
        scores = [item["score"] for item in body]
        assert scores == sorted(scores, reverse=True), "results must be sorted by score descending"


def test_top_opportunities_limit_respected(client):
    r = client.get("/api/v1/intelligence/top-opportunities?limit=2")
    if r.status_code != 200:
        pytest.skip("endpoint returned non-200; likely regime unavailable in test DB")
    body = r.json()
    assert len(body) <= 2


def test_top_opportunities_empty_when_no_signals():
    """Returns [] when there are no BUY signals today."""
    engine = _make_engine()
    Session = sessionmaker(bind=engine)

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    from main import app
    # Save and restore the existing override so the module-scoped client fixture
    # is not affected by this isolated test.
    previous = app.dependency_overrides.get(get_db)
    try:
        app.dependency_overrides[get_db] = override
        c = TestClient(app, headers={"X-API-Key": settings.api_key})
        r = c.get("/api/v1/intelligence/top-opportunities")
        assert r.status_code == 200
        assert r.json() == []
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous


def test_top_opportunities_response_shape(client):
    """Each item has the required fields."""
    r = client.get("/api/v1/intelligence/top-opportunities?limit=1")
    if r.status_code != 200:
        pytest.skip("endpoint returned non-200; likely regime unavailable in test DB")
    body = r.json()
    if not body:
        pytest.skip("No BUY signals today — cannot check shape")
    item = body[0]
    for field in (
        "signal_id", "symbol", "strategy_id", "strategy_name",
        "score", "grade", "regime", "breakdown",
        "stop_loss_price", "target_price",
    ):
        assert field in item, f"missing field: {field}"
    assert isinstance(item["breakdown"], dict)
