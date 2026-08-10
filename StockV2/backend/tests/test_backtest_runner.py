import pytest
from datetime import date
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import pandas as pd
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

    # Seed 300 days of steadily rising prices for TCS starting 2020-01-01.
    # from_date=2021-01-04 is bar ~262 → >200 bars of warmup history.
    dates = pd.bdate_range("2020-01-01", periods=300)
    for i, d in enumerate(dates):
        close = 1000.0 + i * 2.0
        session.execute(text("""
            INSERT INTO stock_prices_daily
                (symbol, date, open, high, low, close, volume, data_source)
            VALUES (:sym, :d, :o, :h, :l, :c, :v, 'test')
        """), {
            "sym": "TCS",
            "d": d.date().isoformat(),
            "o": round(close * 0.995, 2),
            "h": round(close * 1.010, 2),
            "l": round(close * 0.990, 2),
            "c": close,
            "v": 1_000_000,
        })
    session.commit()
    yield session
    session.close()


def test_runner_returns_result_id(db):
    from domains.backtest.runner import BacktestRunner
    result = BacktestRunner(db).run(
        symbol="TCS",
        from_date=date(2021, 1, 4),
        to_date=date(2021, 3, 31),
    )
    assert "error" not in result
    assert "result_id" in result
    assert result["result_id"] > 0
    assert result["symbol"] == "TCS"


def test_runner_saves_result_to_db(db):
    from domains.backtest.runner import BacktestRunner
    result = BacktestRunner(db).run(
        symbol="TCS",
        from_date=date(2021, 1, 4),
        to_date=date(2021, 3, 31),
    )
    row = db.execute(
        text("SELECT id FROM backtest_results WHERE id = :id"), {"id": result["result_id"]}
    ).fetchone()
    assert row is not None


def test_runner_result_has_metrics(db):
    from domains.backtest.runner import BacktestRunner
    result = BacktestRunner(db).run(
        symbol="TCS",
        from_date=date(2021, 1, 4),
        to_date=date(2021, 3, 31),
    )
    assert "total_trades" in result
    assert "win_rate" in result
    assert "cagr" in result
    assert "total_pnl" in result


def test_runner_insufficient_data_returns_error(db):
    from domains.backtest.runner import BacktestRunner
    result = BacktestRunner(db).run(
        symbol="NONEXISTENT",
        from_date=date(2021, 1, 4),
        to_date=date(2021, 3, 31),
    )
    assert "error" in result


def test_runner_invalid_strategy_id_returns_error(db):
    from domains.backtest.runner import BacktestRunner
    result = BacktestRunner(db).run(
        symbol="TCS",
        from_date=date(2021, 1, 4),
        to_date=date(2021, 3, 31),
        strategy_id=99999,
    )
    assert "error" in result
