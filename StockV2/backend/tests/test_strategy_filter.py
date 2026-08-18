# backend/tests/test_strategy_filter.py
from unittest.mock import MagicMock, patch
from domains.combinations.filter import StrategyFilter, FilterConfig
from domains.strategies.base import BaseStrategy, Signal, StrategyType
import pandas as pd


class MockStrategy(BaseStrategy):
    def __init__(self, name: str):
        self.name = name
        self.description = "mock strategy"
        self.strategy_type = StrategyType.TECHNICAL

    def generate_signal(self, df: pd.DataFrame, fundamentals=None) -> Signal:
        return Signal("NONE")


def _make_mock_db(perf_row, wf_row=None, strategy_ids=None):
    """Return a MagicMock DB with execute().fetchone() returning perf_row and wf_row."""
    db = MagicMock()
    strategies_rows = [(1, "StratA"), (2, "StratB")]
    if strategy_ids:
        # strategy_ids is {name: id}; DB rows are (id, name)
        strategies_rows = [(v, k) for k, v in strategy_ids.items()]

    def mock_execute(query, params=None):
        mock_result = MagicMock()
        q = str(query) if not isinstance(query, str) else query
        if "SELECT id, name FROM strategies" in q:
            mock_result.fetchall.return_value = strategies_rows
        elif "strategy_performance" in q:
            mock_result.fetchone.return_value = perf_row
        elif "walk_forward_results" in q:
            mock_result.fetchone.return_value = wf_row or (0.7,)
        else:
            mock_result.fetchone.return_value = None
            mock_result.fetchall.return_value = []
        return mock_result

    db.execute.side_effect = mock_execute
    return db


def test_filter_returns_top_n_overall():
    """select_candidates returns at most top_n_overall strategies."""
    strats = [MockStrategy(f"S{i}") for i in range(5)]
    with patch("domains.combinations.filter.ALL_STRATEGIES", strats):
        db = _make_mock_db(
            perf_row=(50, 0.55, 1.2, -18.0, 2.1),
            strategy_ids={s.name: i + 1 for i, s in enumerate(strats)},
        )
        result = StrategyFilter(db, FilterConfig(top_n_overall=3)).select_candidates()

    assert len(result["overall"]) <= 3
    assert "scores" in result
    assert "disqualified" in result
    assert "by_regime" in result


def test_filter_disqualifies_below_min_trades():
    """Strategies with total_trades < min_trades are moved to disqualified."""
    strats = [MockStrategy("LowVolume")]
    with patch("domains.combinations.filter.ALL_STRATEGIES", strats):
        db = _make_mock_db(
            perf_row=(5, 0.60, 1.5, -10.0, 2.5),   # only 5 trades
            strategy_ids={"LowVolume": 1},
        )
        result = StrategyFilter(db, FilterConfig(min_trades=30)).select_candidates()

    assert "LowVolume" not in result["scores"]
    assert any("LowVolume" in d for d in result["disqualified"])


def test_filter_computes_multifactor_score():
    """Multi-factor score uses correct weighted formula."""
    strats = [MockStrategy("TestStrat")]
    with patch("domains.combinations.filter.ALL_STRATEGIES", strats):
        db = _make_mock_db(
            perf_row=(100, 0.60, 2.0, -20.0, 3.0),  # sharpe=2.0, wr=0.60, pf=3.0
            wf_row=(0.8,),
            strategy_ids={"TestStrat": 1},
        )
        result = StrategyFilter(db, FilterConfig()).select_candidates()

    assert "TestStrat" in result["scores"]
    score = result["scores"]["TestStrat"]
    # sharpe_norm=1.0 (2.0/2.0), wf=0.8, wr=0.60, pf_norm=1.0 ((3.0-1)/2)
    expected = 0.30 * 1.0 + 0.30 * 0.8 + 0.20 * 0.60 + 0.20 * 1.0
    assert abs(score - expected) < 0.001
