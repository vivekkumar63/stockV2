import sys
import os
import math
from datetime import date, timedelta
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _make_db_with_prices(symbol: str, n_days: int = 730):
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session
    from database import Base
    import models

    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=eng)
    db = Session(bind=eng)

    # Use "EMA Crossover (9/21)" — fires whenever EMA9 crosses EMA21.
    # Oscillating prices guarantee crossovers in every OOS window.
    db.execute(text(
        "INSERT INTO strategies (id, name, type, is_active, created_at) "
        "VALUES (1, 'EMA Crossover (9/21)', 'technical', 1, CURRENT_TIMESTAMP)"
    ))

    start_date = date(2022, 1, 1)
    rows = []
    base = 1000.0
    # Oscillate with a 20-day cycle so EMA9/EMA21 cross repeatedly across windows
    for i in range(n_days):
        d = start_date + timedelta(days=i)
        c = base + 100.0 * math.sin(2 * math.pi * i / 20)
        rows.append({
            "sym": symbol, "d": str(d),
            "o": c * 0.995, "h": c * 1.01, "l": c * 0.99, "c": c, "v": 1000000,
        })

    db.execute(text("""
        INSERT INTO stock_prices_daily (symbol, date, open, high, low, close, volume, data_source)
        VALUES (:sym, :d, :o, :h, :l, :c, :v, 'yfinance')
    """), rows)
    db.commit()
    return db


def test_walk_forward_returns_result():
    from domains.backtest.walk_forward import WalkForwardRunner, WalkForwardResult
    db = _make_db_with_prices("TCS", n_days=730)
    runner = WalkForwardRunner()
    result = runner.run(symbol="TCS", strategy_id=1, db=db, train_months=12, test_months=3)

    assert isinstance(result, WalkForwardResult)
    assert result.symbol == "TCS"
    assert result.strategy_id == 1
    assert result.n_windows > 0
    assert result.oos_win_rate_mean is not None or result.n_windows == 0
    assert 0.0 <= result.consistency_score <= 1.0
    db.close()


def test_walk_forward_window_count():
    from domains.backtest.walk_forward import WalkForwardRunner
    db = _make_db_with_prices("INFY", n_days=730)
    runner = WalkForwardRunner()
    result = runner.run(symbol="INFY", strategy_id=1, db=db, train_months=12, test_months=3)

    assert result.n_windows >= 2
    db.close()


def test_consistency_score_bounded():
    from domains.backtest.walk_forward import WalkForwardRunner
    db = _make_db_with_prices("RELIANCE", n_days=730)
    runner = WalkForwardRunner()
    result = runner.run(symbol="RELIANCE", strategy_id=1, db=db, train_months=12, test_months=3)

    assert 0.0 <= result.consistency_score <= 1.0
    if result.n_windows > 0:
        assert result.oos_win_rate_mean is not None
    db.close()
