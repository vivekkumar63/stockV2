import pandas as pd
import pytest
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


def test_signal_defaults():
    s = Signal(signal_type="NONE")
    assert s.confidence == 0.0
    assert s.stop_loss_pct == 7.0
    assert s.target_pct == 15.0
    assert s.holding_days == 15
    assert s.conditions_met == []
    assert s.conditions_failed == []


def test_signal_buy():
    s = Signal(signal_type="BUY", confidence=0.75, conditions_met=["RSI < 30"])
    assert s.signal_type == "BUY"
    assert s.confidence == 0.75
    assert "RSI < 30" in s.conditions_met


def test_base_strategy_is_abstract():
    with pytest.raises(TypeError):
        BaseStrategy()  # cannot instantiate abstract class


def test_strategy_type_values():
    assert StrategyType.TECHNICAL == "technical"
    assert StrategyType.FUNDAMENTAL == "fundamental"
    assert StrategyType.ML == "ml"
    assert StrategyType.CUSTOM == "custom"


def test_timeframe_values():
    assert Timeframe.DAILY == "daily"
    assert Timeframe.INTRADAY_15M == "intraday_15m"
