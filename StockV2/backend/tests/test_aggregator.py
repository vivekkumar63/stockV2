import pytest
from domains.strategies.aggregator import SignalAggregator
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe
import pandas as pd


class _MockStrategy(BaseStrategy):
    def __init__(self, name, stype=StrategyType.TECHNICAL):
        self.name = name
        self.strategy_type = stype
        self.weight = 0.20

    def generate_signal(self, df, fundamentals=None):
        return Signal("NONE")


def _buy(confidence=0.70):
    return Signal("BUY", confidence=confidence)


def _sell():
    return Signal("SELL", confidence=0.70)


def _none():
    return Signal("NONE")


def test_no_signals_returns_none():
    agg = SignalAggregator()
    result = agg.aggregate([(_MockStrategy("A"), _none()), (_MockStrategy("B"), _none())])
    assert result["signal_type"] == "NONE"
    assert result["consensus_score"] == 0.0
    assert result["buy_count"] == 0


def test_buy_signal_when_3_agree_above_threshold():
    agg = SignalAggregator()
    pairs = [(_MockStrategy(f"S{i}"), _buy(0.80)) for i in range(3)]
    result = agg.aggregate(pairs)
    assert result["signal_type"] == "BUY"
    assert result["consensus_score"] > 0.65
    assert result["buy_count"] == 3


def test_watch_when_2_agree_moderate_confidence():
    agg = SignalAggregator()
    pairs = [
        (_MockStrategy("A"), _buy(0.55)),
        (_MockStrategy("B"), _buy(0.55)),
    ]
    result = agg.aggregate(pairs)
    assert result["signal_type"] == "WATCH"
    assert result["consensus_score"] > 0.45


def test_none_when_only_1_buy():
    agg = SignalAggregator()
    result = agg.aggregate([(_MockStrategy("A"), _buy(0.90))])
    assert result["signal_type"] == "NONE"


def test_sell_count_tracked():
    agg = SignalAggregator()
    result = agg.aggregate([(_MockStrategy("A"), _sell()), (_MockStrategy("B"), _none())])
    assert result["sell_count"] == 1


def test_consensus_score_is_confidence_weighted():
    agg = SignalAggregator()
    pairs = [
        (_MockStrategy("A"), _buy(1.0)),
        (_MockStrategy("B"), _buy(1.0)),
        (_MockStrategy("C"), _buy(1.0)),
    ]
    result = agg.aggregate(pairs)
    assert result["consensus_score"] == pytest.approx(1.0, abs=0.01)
