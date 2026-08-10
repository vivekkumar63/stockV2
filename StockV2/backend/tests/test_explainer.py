import json
import pytest
from unittest.mock import MagicMock, patch
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base
import models  # noqa


@pytest.fixture(scope="module")
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    session.execute(text(
        "INSERT INTO strategies (name, type, description, is_active, created_at) VALUES ('RSI Oversold/Overbought', 'technical', '', 1, datetime('now'))"
    ))
    session.execute(text(
        "INSERT INTO stocks (symbol, name, sector, exchange, is_active, added_at) VALUES ('TCS', 'Tata Consultancy Services', 'IT', 'NSE', 1, datetime('now'))"
    ))
    session.execute(text(
        "INSERT INTO strategy_signals "
        "(symbol, strategy_id, signal_date, signal_type, price_at_signal, confidence_score, "
        "risk_score, suggested_stop_loss, suggested_target, holding_period_days, reasoning_json, created_at) "
        "VALUES ('TCS', 1, date('now'), 'BUY', 3500.0, 0.80, 0.40, 3255.0, 4025.0, 10, "
        "'{\"conditions_met\": [\"RSI=25.0 < 30\"], \"conditions_failed\": []}', datetime('now'))"
    ))
    session.execute(text(
        "INSERT INTO strategy_signals "
        "(symbol, strategy_id, signal_date, signal_type, price_at_signal, confidence_score, "
        "risk_score, reasoning_json, created_at) "
        "VALUES ('TCS', 1, date('now'), 'SELL', 3500.0, 0.70, 0.55, "
        "'{\"conditions_met\": [\"RSI=75.0 > 70\"], \"conditions_failed\": []}', datetime('now'))"
    ))
    session.commit()
    yield session
    session.close()


_FAKE_EXPLANATION = {
    "summary": "TCS showing strong RSI oversold bounce opportunity.",
    "bull_case": ["RSI at 25 indicates extreme oversold", "Strong support at 3255"],
    "bear_case": ["Broader market weakness", "IT sector rotation risk"],
    "confidence_reasoning": "RSI below 30 with volume confirmation",
    "suggested_entry": 3500.0,
    "stop_loss": 3255.0,
    "target_1": 3850.0,
    "target_2": 4025.0,
    "holding_period": "10-15 days",
    "risk_rating": "MEDIUM",
}


def test_explainer_returns_none_when_no_api_key(db):
    from domains.ai.explainer import SignalExplainer
    explainer = SignalExplainer(db)
    explainer._client = None
    result = explainer.explain(1)
    assert result is None


def test_explainer_calls_claude_and_returns_dict(db):
    from domains.ai.explainer import SignalExplainer

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=json.dumps(_FAKE_EXPLANATION))]

    explainer = SignalExplainer(db)
    explainer._client = MagicMock()
    explainer._client.messages.create.return_value = mock_response

    result = explainer.explain(1)
    assert result is not None
    assert result["summary"] == _FAKE_EXPLANATION["summary"]
    assert "bull_case" in result


def test_explainer_caches_result(db):
    from domains.ai.explainer import SignalExplainer

    # Clear any existing cache for signal 1 so this test starts with a cold cache
    db.execute(text(
        "DELETE FROM ai_analyses WHERE subject_type = 'signal' AND subject_id = '1'"
    ))
    db.commit()

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=json.dumps(_FAKE_EXPLANATION))]

    explainer = SignalExplainer(db)
    explainer._client = MagicMock()
    explainer._client.messages.create.return_value = mock_response

    explainer.explain(1)
    explainer.explain(1)

    assert explainer._client.messages.create.call_count == 1


def test_explainer_returns_none_for_sell_signal(db):
    from domains.ai.explainer import SignalExplainer
    explainer = SignalExplainer(db)
    explainer._client = MagicMock()
    result = explainer.explain(2)
    assert result is None
    explainer._client.messages.create.assert_not_called()


def test_explainer_returns_none_for_missing_signal(db):
    from domains.ai.explainer import SignalExplainer
    explainer = SignalExplainer(db)
    explainer._client = MagicMock()
    result = explainer.explain(99999)
    assert result is None
