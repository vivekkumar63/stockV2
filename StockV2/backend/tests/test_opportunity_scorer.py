"""Tests for OpportunityScorer — index_alignment component."""


def test_weights_sum_to_100():
    from domains.intelligence.opportunity_scorer import _WEIGHTS
    assert sum(_WEIGHTS.values()) == 100, f"Weights sum to {sum(_WEIGHTS.values())}, expected 100"


def test_index_alignment_in_weights():
    from domains.intelligence.opportunity_scorer import _WEIGHTS
    assert "index_alignment" in _WEIGHTS
    assert _WEIGHTS["index_alignment"] == 10


def test_full_score_with_strong_bull_index_raises_score():
    from domains.intelligence.opportunity_scorer import OpportunityScorer
    scorer = OpportunityScorer()
    base = scorer.full_score(
        symbol="SBIN", strategy_id=1, confidence=0.6,
        historical_win_rate=0.55, regime="BULL",
        regime_strategy_win_rate=0.60,
        mtf_alignment=0.7, volume_score=0.8, sr_score=0.6,
        index_alignment_score=50,
    )
    boosted = scorer.full_score(
        symbol="SBIN", strategy_id=1, confidence=0.6,
        historical_win_rate=0.55, regime="BULL",
        regime_strategy_win_rate=0.60,
        mtf_alignment=0.7, volume_score=0.8, sr_score=0.6,
        index_alignment_score=100,
    )
    assert boosted.score > base.score


def test_full_score_with_bear_index_lowers_score():
    from domains.intelligence.opportunity_scorer import OpportunityScorer
    scorer = OpportunityScorer()
    neutral = scorer.full_score(
        symbol="SBIN", strategy_id=1, confidence=0.6,
        historical_win_rate=0.55, regime="BULL",
        regime_strategy_win_rate=0.60,
        mtf_alignment=0.7, volume_score=0.8, sr_score=0.6,
        index_alignment_score=50,
    )
    penalised = scorer.full_score(
        symbol="SBIN", strategy_id=1, confidence=0.6,
        historical_win_rate=0.55, regime="BULL",
        regime_strategy_win_rate=0.60,
        mtf_alignment=0.7, volume_score=0.8, sr_score=0.6,
        index_alignment_score=15,
    )
    assert penalised.score < neutral.score


def test_full_score_none_index_alignment_is_neutral():
    from domains.intelligence.opportunity_scorer import OpportunityScorer
    scorer = OpportunityScorer()
    no_index = scorer.full_score(
        symbol="KRBL", strategy_id=2, confidence=0.6,
        historical_win_rate=0.55, regime="BULL",
        regime_strategy_win_rate=None,
        mtf_alignment=None, volume_score=None, sr_score=None,
        index_alignment_score=None,
    )
    neutral_index = scorer.full_score(
        symbol="KRBL", strategy_id=2, confidence=0.6,
        historical_win_rate=0.55, regime="BULL",
        regime_strategy_win_rate=None,
        mtf_alignment=None, volume_score=None, sr_score=None,
        index_alignment_score=50,
    )
    assert no_index.score == neutral_index.score
