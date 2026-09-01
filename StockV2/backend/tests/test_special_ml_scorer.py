import pytest
from unittest.mock import MagicMock, patch
from datetime import date
from domains.special_strategies.ml_scorer import SpecialMLScorer, special_regime_to_code


def test_regime_to_code_known():
    assert special_regime_to_code("BULL") == 4
    assert special_regime_to_code("STRONG_BULL") == 5
    assert special_regime_to_code("BEAR") == 2


def test_regime_to_code_unknown_defaults_to_sideways():
    assert special_regime_to_code("UNKNOWN") == 3


def test_predict_returns_none_when_no_model(tmp_path):
    with patch("domains.special_strategies.ml_scorer.MODEL_PATH", str(tmp_path / "missing.pkl")):
        import domains.special_strategies.ml_scorer as m
        m._cached_model = None
        scorer = SpecialMLScorer()
        result = scorer.predict({
            "strategy_id": 1, "entry_month": 6, "entry_dow": 2,
            "regime_code": 4, "strategy_avg_win_rate": 0.6,
            "strategy_profit_factor": 1.5, "strategy_avg_pnl_pct": 3.2,
        })
        assert result is None


def test_train_returns_dict_with_samples_zero_when_insufficient():
    db = MagicMock()
    db.execute.return_value.fetchall.return_value = []
    scorer = SpecialMLScorer()
    result = scorer.train(db)
    assert isinstance(result, dict)
    assert result["samples"] == 0


def test_train_returns_dict_with_samples_zero_when_single_class(tmp_path):
    """All trades profitable → only one class → skipped."""
    db = MagicMock()
    fake_rows = [
        (1, date(2023, i % 12 + 1, 1), "BULL", 500.0, 0.65, 1.8, 4.2)
        for i in range(60)
    ]
    db.execute.return_value.fetchall.return_value = fake_rows
    with patch("domains.special_strategies.ml_scorer.MODEL_PATH", str(tmp_path / "model.pkl")):
        import domains.special_strategies.ml_scorer as m
        m._cached_model = None
        scorer = SpecialMLScorer()
        result = scorer.train(db)
        assert result["samples"] == 0
