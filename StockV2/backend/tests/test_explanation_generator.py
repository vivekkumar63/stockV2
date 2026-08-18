# backend/tests/test_explanation_generator.py
import pandas as pd
from domains.combinations.explanations import ExplanationGenerator, CombinationExplanation
from domains.strategies.base import BaseStrategy, Signal, StrategyType


class MockTechnical(BaseStrategy):
    def __init__(self, name: str = "RSI", description: str = "RSI momentum"):
        self.name = name
        self.description = description
        self.strategy_type = StrategyType.TECHNICAL

    def generate_signal(self, df: pd.DataFrame, fundamentals=None) -> Signal:
        return Signal("NONE")


class MockFundamental(BaseStrategy):
    def __init__(self):
        self.name = "Graham"
        self.description = "Benjamin Graham value criteria"
        self.strategy_type = StrategyType.FUNDAMENTAL

    def generate_signal(self, df: pd.DataFrame, fundamentals=None) -> Signal:
        return Signal("NONE")


class MockResult:
    def __init__(self, regime_win_rates=None, wf_consistency_score=0.75):
        self.regime_win_rates = regime_win_rates or {"BULL": 0.65, "BEAR": 0.35}
        self.wf_consistency_score = wf_consistency_score


def test_explanation_produces_all_fields():
    """explain() returns CombinationExplanation with all 6 fields populated."""
    gen = ExplanationGenerator()
    combination = [MockTechnical("RSI"), MockTechnical("MACD", "MACD trend")]
    result = MockResult()
    corr_matrix = {("MACD", "RSI"): 0.25}

    explanation = gen.explain(combination, result, corr_matrix)

    assert isinstance(explanation, CombinationExplanation)
    assert len(explanation.what_each_captures) == 2
    assert "RSI" in explanation.what_each_captures[0]
    assert len(explanation.why_complementary) > 0
    assert len(explanation.typical_stocks) > 0
    assert len(explanation.works_well_in) > 0
    assert len(explanation.struggles_in) > 0
    assert len(explanation.risks_and_weaknesses) > 0


def test_explanation_low_correlation_says_complementary():
    """Low correlation → explains as independent signal sources."""
    gen = ExplanationGenerator()
    combination = [MockTechnical("A"), MockTechnical("B")]
    result = MockResult()
    corr_matrix = {("A", "B"): 0.15}  # low correlation

    explanation = gen.explain(combination, result, corr_matrix)

    assert "0.15" in explanation.why_complementary


def test_explanation_tech_fundamental_mix():
    """Technical + fundamental mix → describes quality stocks at breakout."""
    gen = ExplanationGenerator()
    combination = [MockTechnical(), MockFundamental()]
    result = MockResult()

    explanation = gen.explain(combination, result, {})

    assert "technical" in explanation.typical_stocks.lower() or "quality" in explanation.typical_stocks.lower()


def test_explanation_regime_fit_identifies_best_worst():
    """Regime win rates → best regime in works_well_in, worst in struggles_in."""
    gen = ExplanationGenerator()
    combination = [MockTechnical()]
    result = MockResult(regime_win_rates={"BULL": 0.70, "BEAR": 0.30, "SIDEWAYS": 0.50})

    explanation = gen.explain(combination, result, {})

    assert "Bull" in explanation.works_well_in or "BULL" in explanation.works_well_in
    assert "Bear" in explanation.struggles_in or "BEAR" in explanation.struggles_in
