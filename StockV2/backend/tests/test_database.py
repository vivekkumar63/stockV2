from sqlalchemy import text
from database import engine, SessionLocal, get_db


def test_engine_connects():
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1"))
        assert result.scalar() == 1


def test_wal_mode_enabled():
    with engine.connect() as conn:
        result = conn.execute(text("PRAGMA journal_mode"))
        mode = result.scalar()
        assert mode == "wal"


def test_session_local_creates_session():
    db = SessionLocal()
    try:
        result = db.execute(text("SELECT 1"))
        assert result.scalar() == 1
    finally:
        db.close()


def test_get_db_yields_and_closes():
    gen = get_db()
    db = next(gen)
    assert db is not None
    try:
        next(gen)
    except StopIteration:
        pass
