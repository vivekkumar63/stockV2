# backend/tests/test_combination_router.py
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base, get_db
from settings import settings
import models  # noqa


def _create_combination_tables(engine) -> None:
    """Create the combination tables (raw SQL, not ORM models)."""
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS strategy_combinations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                strategy_ids TEXT NOT NULL,
                strategy_names TEXT NOT NULL,
                size INTEGER NOT NULL,
                search_method TEXT NOT NULL,
                created_at DATETIME DEFAULT (datetime('now'))
            )
        """))
        conn.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_combination_ids
            ON strategy_combinations(strategy_ids)
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS combination_run_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at DATETIME NOT NULL,
                completed_at DATETIME,
                status TEXT NOT NULL DEFAULT 'running',
                symbols_analyzed INTEGER,
                candidates_selected INTEGER,
                combinations_tested INTEGER,
                top_combination_id INTEGER REFERENCES strategy_combinations(id),
                error_message TEXT,
                config_json TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS combination_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                combination_id INTEGER NOT NULL REFERENCES strategy_combinations(id),
                run_id INTEGER NOT NULL REFERENCES combination_run_log(id),
                train_cagr REAL, train_sharpe REAL, train_win_rate REAL,
                train_max_drawdown REAL, train_profit_factor REAL,
                train_total_trades INTEGER, train_sortino REAL,
                val_cagr REAL, val_sharpe REAL, val_win_rate REAL,
                val_max_drawdown REAL, val_total_trades INTEGER,
                oos_cagr REAL, oos_sharpe REAL, oos_win_rate REAL,
                oos_max_drawdown REAL, oos_profit_factor REAL,
                oos_total_trades INTEGER, oos_sortino REAL, oos_median_return_pct REAL,
                wf_consistency_score REAL, wf_avg_oos_cagr REAL,
                vs_buy_and_hold_cagr REAL, vs_best_single_cagr REAL, vs_sma_crossover_cagr REAL,
                reliability_score REAL, reliability_label TEXT, sensitivity_score REAL,
                explanation_json TEXT,
                computed_at DATETIME DEFAULT (datetime('now'))
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS combination_regime_perf (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                combination_id INTEGER NOT NULL REFERENCES strategy_combinations(id),
                run_id INTEGER NOT NULL REFERENCES combination_run_log(id),
                regime TEXT NOT NULL,
                win_rate REAL, avg_pnl_pct REAL, trade_count INTEGER, cagr REAL
            )
        """))
        conn.commit()


@pytest.fixture(scope="module")
def client():
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(test_engine)
    _create_combination_tables(test_engine)
    TestSession = sessionmaker(bind=test_engine)

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    from main import app
    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app, headers={"X-API-Key": settings.api_key})


def test_get_run_status_endpoint(client):
    response = client.get("/api/v1/combinations/run-status")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert data["status"] in ["never_run", "running", "complete", "failed"]
    assert "last_run_id" in data
    assert "combinations_tested" in data


def test_get_rankings_endpoint(client):
    response = client.get("/api/v1/combinations/rankings")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_get_best_endpoint(client):
    response = client.get("/api/v1/combinations/best")
    assert response.status_code == 200
    data = response.json()
    assert set(data.keys()) == {"overall", "low_risk", "high_growth", "most_consistent"}


def test_get_avoid_endpoint(client):
    response = client.get("/api/v1/combinations/avoid")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_trigger_analysis_endpoint(client):
    response = client.post("/api/v1/combinations/analyze")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data


def test_get_combination_detail_not_found(client):
    response = client.get("/api/v1/combinations/999999")
    assert response.status_code == 404


def test_unauthorized_without_key():
    from main import app
    c = TestClient(app)
    response = c.get("/api/v1/combinations/run-status")
    assert response.status_code == 401
