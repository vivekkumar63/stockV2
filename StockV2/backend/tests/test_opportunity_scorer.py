"""Tests for OpportunityScorer — sector_health and confluence components."""


def test_weights_sum_to_100():
    from domains.intelligence.opportunity_scorer import _WEIGHTS
    assert sum(_WEIGHTS.values()) == 100, f"Weights sum to {sum(_WEIGHTS.values())}, expected 100"


def test_sector_health_in_weights():
    from domains.intelligence.opportunity_scorer import _WEIGHTS
    assert "sector_health" in _WEIGHTS
    assert _WEIGHTS["sector_health"] == 10


def test_full_score_with_strong_sector_health_raises_score():
    from domains.intelligence.opportunity_scorer import OpportunityScorer
    scorer = OpportunityScorer()
    base = scorer.full_score(
        symbol="SBIN", strategy_id=1, confidence=0.6,
        historical_win_rate=0.55, regime="BULL",
        regime_strategy_win_rate=0.60,
        mtf_alignment=0.7, volume_score=0.8, sr_score=0.6,
        sector_health_score=0.5,
    )
    boosted = scorer.full_score(
        symbol="SBIN", strategy_id=1, confidence=0.6,
        historical_win_rate=0.55, regime="BULL",
        regime_strategy_win_rate=0.60,
        mtf_alignment=0.7, volume_score=0.8, sr_score=0.6,
        sector_health_score=1.0,
    )
    assert boosted.score > base.score


def test_full_score_with_weak_sector_health_lowers_score():
    from domains.intelligence.opportunity_scorer import OpportunityScorer
    scorer = OpportunityScorer()
    neutral = scorer.full_score(
        symbol="SBIN", strategy_id=1, confidence=0.6,
        historical_win_rate=0.55, regime="BULL",
        regime_strategy_win_rate=0.60,
        mtf_alignment=0.7, volume_score=0.8, sr_score=0.6,
        sector_health_score=0.5,
    )
    penalised = scorer.full_score(
        symbol="SBIN", strategy_id=1, confidence=0.6,
        historical_win_rate=0.55, regime="BULL",
        regime_strategy_win_rate=0.60,
        mtf_alignment=0.7, volume_score=0.8, sr_score=0.6,
        sector_health_score=0.1,
    )
    assert penalised.score < neutral.score


def test_full_score_none_sector_health_uses_neutral_default():
    from domains.intelligence.opportunity_scorer import OpportunityScorer
    scorer = OpportunityScorer()
    no_sector = scorer.full_score(
        symbol="KRBL", strategy_id=2, confidence=0.6,
        historical_win_rate=0.55, regime="BULL",
        regime_strategy_win_rate=None,
        mtf_alignment=None, volume_score=None, sr_score=None,
        sector_health_score=None,
    )
    neutral_sector = scorer.full_score(
        symbol="KRBL", strategy_id=2, confidence=0.6,
        historical_win_rate=0.55, regime="BULL",
        regime_strategy_win_rate=None,
        mtf_alignment=None, volume_score=None, sr_score=None,
        sector_health_score=0.5,
    )
    assert no_sector.score == neutral_sector.score


def test_confluence_bonus_increases_score():
    from domains.intelligence.opportunity_scorer import OpportunityScorer
    scorer = OpportunityScorer()
    single = scorer.full_score(
        symbol="TCS", strategy_id=1, confidence=0.6,
        historical_win_rate=0.55, regime="BULL",
        regime_strategy_win_rate=0.60,
        mtf_alignment=0.7, volume_score=0.8, sr_score=0.6,
        confluence_count=1,
    )
    multi = scorer.full_score(
        symbol="TCS", strategy_id=1, confidence=0.6,
        historical_win_rate=0.55, regime="BULL",
        regime_strategy_win_rate=0.60,
        mtf_alignment=0.7, volume_score=0.8, sr_score=0.6,
        confluence_count=3,
    )
    assert multi.score > single.score
    assert multi.breakdown.get("confluence_count") == 3


def test_confluence_count_stored_in_breakdown():
    from domains.intelligence.opportunity_scorer import OpportunityScorer
    scorer = OpportunityScorer()
    opp = scorer.full_score(
        symbol="INFY", strategy_id=2, confidence=0.5,
        historical_win_rate=0.50, regime="SIDEWAYS",
        regime_strategy_win_rate=None,
        mtf_alignment=None, volume_score=None, sr_score=None,
        confluence_count=2,
    )
    assert opp.breakdown.get("confluence_count") == 2


def test_score_capped_at_100():
    from domains.intelligence.opportunity_scorer import OpportunityScorer
    scorer = OpportunityScorer()
    opp = scorer.full_score(
        symbol="RELIANCE", strategy_id=1, confidence=1.0,
        historical_win_rate=1.0, regime="STRONG_BULL",
        regime_strategy_win_rate=1.0,
        mtf_alignment=1.0, volume_score=1.0, sr_score=1.0,
        sector_health_score=1.0,
        confluence_count=4,
    )
    assert opp.score <= 100
