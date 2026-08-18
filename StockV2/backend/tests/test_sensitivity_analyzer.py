# backend/tests/test_sensitivity_analyzer.py
from datetime import date
from unittest.mock import patch, MagicMock
import pandas as pd

from domains.combinations.sensitivity import SensitivityAnalyzer
from domains.strategies.base import BaseStrategy, Signal, StrategyType


class AlwaysBuyStrategy(BaseStrategy):
    def __init__(self, confidence: float = 0.9):
        self.name = "always_buy"
        self.description = "always BUY"
        self.strategy_type = StrategyType.TECHNICAL
        self._confidence = confidence

    def generate_signal(self, df: pd.DataFrame, fundamentals=None) -> Signal:
        return Signal("BUY", confidence=self._confidence)


class NeverBuyStrategy(BaseStrategy):
    def __init__(self):
        self.name = "never_buy"
        self.description = "never BUY"
        self.strategy_type = StrategyType.TECHNICAL

    def generate_signal(self, df: pd.DataFrame, fundamentals=None) -> Signal:
        return Signal("NONE")


def _make_prices_df(n: int = 60) -> pd.DataFrame:
    dates = pd.date_range("2024-01-02", periods=n, freq="B").date
    return pd.DataFrame({
        "date": list(dates),
        "open": 100.0, "high": 105.0, "low": 95.0, "close": 102.0, "volume": 1_000_000
    })


def test_sensitivity_returns_float_in_range():
    """test() returns a float in [0, 100]."""
    with patch("domains.combinations.sensitivity.IndicatorEngine") as mock_ie:
        mock_df = _make_prices_df()
        mock_ie.compute.return_value = mock_df

        analyzer = SensitivityAnalyzer()
        strategies = [AlwaysBuyStrategy()]
        prices_map = {"TEST": mock_df}

        score = analyzer.test(
            strategies, prices_map,
            date(2024, 2, 1), date(2024, 3, 31)
        )

    assert isinstance(score, float)
    assert 0.0 <= score <= 100.0


def test_sensitivity_all_zeros_returns_zero():
    """If no BUY signals at any threshold, returns 0."""
    with patch("domains.combinations.sensitivity.IndicatorEngine") as mock_ie:
        mock_df = _make_prices_df()
        mock_ie.compute.return_value = mock_df

        analyzer = SensitivityAnalyzer()
        strategies = [NeverBuyStrategy()]
        prices_map = {"TEST": mock_df}

        score = analyzer.test(
            strategies, prices_map,
            date(2024, 2, 1), date(2024, 3, 31)
        )

    assert score == 0.0
