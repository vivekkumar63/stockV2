import sys
import os
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Remove any existing model file before tests run to ensure isolation
_MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "ml_models", "signal_scorer.pkl")


def _remove_model():
    if os.path.exists(_MODEL_PATH):
        os.remove(_MODEL_PATH)


def _make_db_with_outcomes(n_outcomes: int = 60):
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session
    from database import Base
    import models

    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=eng)
    db = Session(bind=eng)

    db.execute(text(
        "INSERT INTO strategies (id, name, type, is_active, created_at) "
        "VALUES (1, 'TestStrat', 'technical', 1, CURRENT_TIMESTAMP)"
    ))

    base = date(2024, 1, 1)
    rows_signals = []
    rows_outcomes = []
    rows_regime = []
    for i in range(n_outcomes):
        sig_date = base + timedelta(days=i)
        is_prof = 1 if i % 2 == 0 else 0
        rows_signals.append({
            "sid": i + 1, "sym": "TCS", "strat": 1, "sdate": str(sig_date),
            "stype": "BUY", "conf": 0.75, "price": 100.0,
        })
        rows_outcomes.append({
            "sig_id": i + 1, "sym": "TCS", "strat": 1, "sdate": str(sig_date),
            "stype": "BUY", "price": 100.0, "oprice": 110.0 if is_prof else 90.0,
            "odate": str(sig_date + timedelta(days=15)), "pnl": 10.0 if is_prof else -10.0,
            "prof": is_prof, "hdays": 15,
        })
        rows_regime.append({
            "d": str(sig_date), "regime": "BULL", "conf": 0.8,
            "pct50": 0.6, "pct200": 0.5, "adr": 1.2, "atr": 0.02, "stocks": 200,
        })

    db.execute(text("""
        INSERT INTO strategy_signals
            (id, symbol, strategy_id, signal_date, signal_type, confidence_score,
             price_at_signal, created_at)
        VALUES (:sid, :sym, :strat, :sdate, :stype, :conf, :price, CURRENT_TIMESTAMP)
    """), rows_signals)

    db.execute(text("""
        INSERT INTO signal_outcomes
            (signal_id, symbol, strategy_id, signal_date, signal_type,
             price_at_signal, outcome_price, outcome_date, pnl_pct,
             is_profitable, holding_days_actual, computed_at)
        VALUES (:sig_id, :sym, :strat, :sdate, :stype,
                :price, :oprice, :odate, :pnl, :prof, :hdays, CURRENT_TIMESTAMP)
    """), rows_outcomes)

    db.execute(text("""
        INSERT INTO market_regime
            (date, regime, confidence, pct_above_sma50, pct_above_sma200,
             advance_decline_ratio, avg_atr_ratio, stocks_counted, computed_at)
        VALUES (:d, :regime, :conf, :pct50, :pct200, :adr, :atr, :stocks, CURRENT_TIMESTAMP)
    """), rows_regime)

    db.commit()
    return db


def test_train_returns_zero_below_min_samples():
    """Fewer than 50 outcomes → train returns 0, no model file written."""
    from domains.intelligence.ml_scorer import MLSignalScorer
    _remove_model()
    db = _make_db_with_outcomes(n_outcomes=40)
    n = MLSignalScorer().train(db)
    assert n == 0
    assert not os.path.exists(_MODEL_PATH)
    db.close()


def test_predict_returns_none_when_no_model():
    """No .pkl file → predict returns None."""
    from domains.intelligence.ml_scorer import MLSignalScorer
    _remove_model()
    prob = MLSignalScorer().predict({
        "confidence_score": 0.75,
        "regime_code": 4,
        "strategy_id": 1,
        "month": 1,
        "day_of_week": 0,
    })
    assert prob is None


def test_train_and_predict():
    """Insert 60 outcomes, train, predict → returns float in [0,1]."""
    from domains.intelligence.ml_scorer import MLSignalScorer
    _remove_model()
    db = _make_db_with_outcomes(n_outcomes=60)
    scorer = MLSignalScorer()
    n = scorer.train(db)
    assert n == 60
    assert os.path.exists(_MODEL_PATH)

    prob = scorer.predict({
        "confidence_score": 0.80,
        "regime_code": 4,
        "strategy_id": 1,
        "month": 2,
        "day_of_week": 1,
    })
    assert prob is not None
    assert 0.0 <= prob <= 1.0
    db.close()


def test_probability_in_breakdown():
    """full_score with ml_probability → ml_signal_probability in breakdown."""
    from domains.intelligence.opportunity_scorer import OpportunityScorer
    from domains.intelligence.ml_scorer import MLSignalScorer

    # Train model first
    db = _make_db_with_outcomes(n_outcomes=60)
    _remove_model()
    MLSignalScorer().train(db)
    db.close()

    scorer = OpportunityScorer()
    opp = scorer.full_score(
        symbol="TCS",
        strategy_id=1,
        confidence=0.75,
        historical_win_rate=0.60,
        regime="BULL",
        regime_strategy_win_rate=0.55,
        mtf_alignment=0.8,
        volume_score=0.7,
        sr_score=0.6,
        false_signal_rate=0.30,
        ml_probability=0.65,
    )

    assert "ml_signal_probability" in opp.breakdown
    assert opp.breakdown["ml_signal_probability"] == 0.65
    assert opp.score > 0
