# backend/tests/test_combination_engine.py
from domains.combinations.engine import CombinationEngine, EngineConfig
from domains.combinations.filter import FilterConfig
from database import SessionLocal
from sqlalchemy import text


def test_combination_engine_run_smoke():
    """Smoke test: engine runs without crashing, run log created."""
    db = SessionLocal()
    try:
        config = EngineConfig(
            symbols_limit=5,
            sensitivity_top_n=2,
            explanation_top_n=1,
        )
        config.filter.min_trades = 5   # relaxed for test data
        config.filter.top_n_overall = 3

        engine = CombinationEngine(db, config)
        run_id = engine.run_full_analysis()

        assert run_id > 0

        row = db.execute(
            text("SELECT status FROM combination_run_log WHERE id = :rid"),
            {"rid": run_id}
        ).fetchone()
        assert row is not None
        assert row[0] in ("complete", "failed")
    finally:
        db.close()
