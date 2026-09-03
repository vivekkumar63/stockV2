import pytest
from domains.zones.scorer import ZoneScorer
from domains.zones.models import Zone


def _zone(tags: list[str], reaction: float = 5.0, vol: float = 2.0,
          touch: int = 0, bar_index: int = 400, n_bars: int = 500) -> Zone:
    return Zone(
        low=950.0, high=960.0, zone_type="demand",
        source_tags=tags, touch_count=touch,
        last_reaction_pct=reaction, freshness="fresh",
        volume_at_zone=vol, bar_index=bar_index,
        strength_hint=0.6,
    )


def test_score_is_0_to_100():
    zone = _zone(["swing_low"])
    scored = ZoneScorer().score(zone, atr=20.0, n_bars=500, price=970.0)
    assert 0 <= scored.score <= 100


def test_more_unique_sources_scores_higher():
    few = _zone(["swing_low"])
    many = _zone(["swing_low", "ema_50", "vol_node", "fib_0.618"])
    s_few  = ZoneScorer().score(few,  atr=20.0, n_bars=500, price=970.0)
    s_many = ZoneScorer().score(many, atr=20.0, n_bars=500, price=970.0)
    assert s_many.score > s_few.score


def test_correlated_ema9_ema21_count_as_one():
    corr  = _zone(["ema_9", "ema_21"])       # correlated — counts as 1
    uncorr = _zone(["ema_9", "vol_node"])    # independent — counts as 2
    s_corr  = ZoneScorer().score(corr,  atr=20.0, n_bars=500, price=970.0)
    s_uncorr = ZoneScorer().score(uncorr, atr=20.0, n_bars=500, price=970.0)
    assert s_uncorr.score > s_corr.score


def test_closer_zone_scores_higher():
    close_zone = _zone(["swing_low"])  # bar_index=400, price=970 (zone midpoint 955)
    far_zone   = _zone(["swing_low"], bar_index=10)
    s_close = ZoneScorer().score(close_zone, atr=20.0, n_bars=500, price=970.0)
    s_far   = ZoneScorer().score(far_zone,   atr=20.0, n_bars=500, price=970.0)
    # More recent bar_index = higher recency score
    assert s_close.score >= s_far.score


def test_score_returns_zone_with_score_field():
    zone = _zone(["swing_low", "ema_50"])
    result = ZoneScorer().score(zone, atr=20.0, n_bars=500, price=960.0)
    assert isinstance(result, Zone)
    assert result.score > 0


def test_correlated_ema50_sma200_count_as_one():
    corr  = _zone(["ema_50", "sma_200"])     # correlated — counts as 1
    uncorr = _zone(["ema_50", "vol_node"])   # independent — counts as 2
    s_corr  = ZoneScorer().score(corr,  atr=20.0, n_bars=500, price=970.0)
    s_uncorr = ZoneScorer().score(uncorr, atr=20.0, n_bars=500, price=970.0)
    assert s_uncorr.score > s_corr.score
