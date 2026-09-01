import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock
from datetime import date
import domains.intelligence.ml_scorer as m
from domains.intelligence.ml_scorer import MLSignalScorer, regime_to_code


def test_regime_to_code_known():
    assert regime_to_code("BULL") == 4
    assert regime_to_code("STRONG_BULL") == 5


def test_regime_to_code_unknown_defaults_to_sideways():
    assert regime_to_code("UNKNOWN") == 3


def test_predict_returns_none_when_no_model(tmp_path):
    m._model_cache.clear()
    # strategy_id=999 has no model file → should return None
    scorer = MLSignalScorer()
    result = scorer.predict({
        "confidence_score": 0.7, "regime_code": 4, "strategy_id": 999,
        "month": 6, "day_of_week": 2,
    })
    assert result is None


def test_train_returns_dict_with_samples_zero_when_insufficient():
    db = MagicMock()
    db.execute.return_value.fetchall.return_value = []
    scorer = MLSignalScorer()
    result = scorer.train(db, strategy_id=1)
    assert isinstance(result, dict)
    assert result["samples"] == 0


def test_train_returns_dict_with_samples_zero_when_single_class(tmp_path):
    db = MagicMock()
    # 60 rows, all profitable — only one class
    fake_rows = [
        (0.8, "BULL", 1, date(2023, i % 12 + 1, 1), True,
         0.6, 60, 0.55, None, None, None, None)
        for i in range(60)
    ]
    db.execute.return_value.fetchall.return_value = fake_rows
    m._model_cache.clear()
    scorer = MLSignalScorer()
    result = scorer.train(db, strategy_id=1)
    assert result["samples"] == 0
