"""Tests for index_fetcher compute logic."""


def test_compute_trend_label_strong_bull():
    from domains.data.index_fetcher import _compute_trend_label
    assert _compute_trend_label(above_sma20=True, above_sma50=True) == "STRONG_BULL"


def test_compute_trend_label_bull():
    from domains.data.index_fetcher import _compute_trend_label
    assert _compute_trend_label(above_sma20=True, above_sma50=False) == "BULL"


def test_compute_trend_label_neutral():
    from domains.data.index_fetcher import _compute_trend_label
    assert _compute_trend_label(above_sma20=False, above_sma50=True) == "NEUTRAL"


def test_compute_trend_label_bear():
    from domains.data.index_fetcher import _compute_trend_label
    assert _compute_trend_label(above_sma20=False, above_sma50=False) == "BEAR"


def test_index_alignment_score_unmapped():
    from domains.data.index_fetcher import compute_index_alignment_score
    assert compute_index_alignment_score(index_trend_row=None) == 50


def test_index_alignment_score_strong_bull():
    from domains.data.index_fetcher import compute_index_alignment_score
    row = {"above_sma20": 1, "above_sma50": 1, "trend_label": "STRONG_BULL"}
    assert compute_index_alignment_score(row) == 100


def test_index_alignment_score_bull():
    from domains.data.index_fetcher import compute_index_alignment_score
    row = {"above_sma20": 1, "above_sma50": 0, "trend_label": "BULL"}
    assert compute_index_alignment_score(row) == 70


def test_index_alignment_score_neutral():
    from domains.data.index_fetcher import compute_index_alignment_score
    row = {"above_sma20": 0, "above_sma50": 1, "trend_label": "NEUTRAL"}
    assert compute_index_alignment_score(row) == 40


def test_index_alignment_score_bear():
    from domains.data.index_fetcher import compute_index_alignment_score
    row = {"above_sma20": 0, "above_sma50": 0, "trend_label": "BEAR"}
    assert compute_index_alignment_score(row) == 15
