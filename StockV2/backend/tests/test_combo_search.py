# backend/tests/test_combo_search.py
from domains.combinations.search import ComboSearch, SearchConfig
from domains.strategies.base import BaseStrategy, Signal, StrategyType
import pandas as pd


class MockStrategy(BaseStrategy):
    def __init__(self, name: str):
        self.name = name
        self.description = "mock"
        self.strategy_type = StrategyType.TECHNICAL

    def generate_signal(self, df: pd.DataFrame, fundamentals=None) -> Signal:
        return Signal("NONE")


def test_search_generates_all_pairs():
    """C(5,2) = 10 pairs from 5 candidates."""
    candidates = [MockStrategy(f"S{i}") for i in range(5)]
    combos = ComboSearch(candidates).generate_combinations()
    assert len(combos) == 10
    assert all(len(c) == 2 for c in combos)


def test_search_deduplicates_reversed_pairs():
    """(A, B) and (B, A) are the same combination — only one should appear."""
    a = MockStrategy("A")
    b = MockStrategy("B")
    combos = ComboSearch([a, b]).generate_combinations()
    assert len(combos) == 1
    assert {s.name for s in combos[0]} == {"A", "B"}


def test_greedy_extend_picks_best_marginal():
    """greedy_extend adds the strategy that maximises the score function."""
    base = [MockStrategy("X")]
    remaining = [MockStrategy("Good"), MockStrategy("Bad")]

    # score_fn returns 2.0 if "Good" is in combo, else 1.0
    def score_fn(combo: list) -> float:
        return 2.0 if any(s.name == "Good" for s in combo) else 1.0

    result = ComboSearch([]).greedy_extend(base, remaining, score_fn)
    assert len(result) == 2
    assert result[-1].name == "Good"


def test_greedy_extend_returns_base_when_no_improvement():
    """If no candidate improves the score, base is returned unchanged."""
    base = [MockStrategy("X")]
    remaining = [MockStrategy("Worse")]

    def score_fn(combo: list) -> float:
        return 1.0  # constant — adding anything doesn't help

    result = ComboSearch([]).greedy_extend(base, remaining, score_fn)
    assert len(result) == 1
    assert result[0].name == "X"
