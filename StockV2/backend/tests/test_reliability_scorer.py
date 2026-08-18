# backend/tests/test_reliability_scorer.py
from domains.combinations.reliability import ReliabilityScorer
from domains.combinations.metrics import ExtendedMetrics


def _make_metrics(
    total_trades: int = 50,
    win_rate: float = 0.55,
    cagr: float = 20.0,
    sharpe_ratio: float = 1.5,
    max_drawdown: float = -15.0,
    profit_factor: float = 2.0,
) -> ExtendedMetrics:
    return ExtendedMetrics(
        total_trades=total_trades,
        win_rate=win_rate,
        total_pnl=10000.0,
        total_return_pct=2.0,
        cagr=cagr,
        sharpe_ratio=sharpe_ratio,
        max_drawdown=max_drawdown,
        profit_factor=profit_factor,
        avg_return_pct=0.5,
        sortino_ratio=1.8,
        median_return_pct=0.4,
        regime_win_rates={"BULL": 0.65, "SIDEWAYS": 0.48, "BEAR": 0.35},
        benchmark_deltas={"bah": 8.0, "best_single": 2.0, "sma_cross": 11.0},
    )


def test_scorer_labels_strong_when_all_high():
    """High OOS, high WF consistency → Strong evidence."""
    train = _make_metrics(cagr=28.0, total_trades=150)
    val = _make_metrics(cagr=25.0, total_trades=50)
    oos = _make_metrics(cagr=24.0, total_trades=60, max_drawdown=-14.0)

    result = ReliabilityScorer().score(train, val, oos, wf_consistency=0.85)

    assert result.score >= 75.0
    assert result.label == "Strong evidence"
    assert len(result.component_scores) == 6


def test_scorer_labels_overfitted_when_train_oos_gap_large():
    """train CAGR=45%, OOS CAGR=4% → degradation=0.91 (>60%), score ~29 → Likely Overfitted."""
    train = _make_metrics(cagr=45.0, total_trades=200)
    val = _make_metrics(cagr=20.0, total_trades=60)
    oos = _make_metrics(cagr=4.0, total_trades=30, max_drawdown=-30.0)

    result = ReliabilityScorer().score(train, val, oos, wf_consistency=0.25)

    assert result.label == "Likely Overfitted"


def test_scorer_labels_insufficient_when_oos_trades_low():
    """Fewer than 20 OOS trades → Insufficient Data regardless of CAGR."""
    train = _make_metrics(cagr=30.0, total_trades=100)
    val = _make_metrics(cagr=25.0, total_trades=30)
    oos = _make_metrics(cagr=25.0, total_trades=10)  # only 10 trades

    result = ReliabilityScorer().score(train, val, oos, wf_consistency=0.80)

    assert result.label == "Insufficient Data"


def test_scorer_components_sum_to_score():
    """Sum of 6 component scores equals the total score (within float rounding)."""
    train = _make_metrics(cagr=25.0, total_trades=100)
    val = _make_metrics(cagr=22.0, total_trades=40)
    oos = _make_metrics(cagr=20.0, total_trades=45)

    result = ReliabilityScorer().score(train, val, oos, wf_consistency=0.70)

    total = sum(result.component_scores.values())
    assert abs(total - result.score) < 0.1


def test_apply_sensitivity_cap_downgrades_strong():
    """sensitivity_score < 40 downgrades "Strong evidence" to "Moderate evidence"."""
    train = _make_metrics(cagr=28.0, total_trades=150)
    val = _make_metrics(cagr=25.0, total_trades=50)
    oos = _make_metrics(cagr=24.0, total_trades=60)

    scorer = ReliabilityScorer()
    result = scorer.score(train, val, oos, wf_consistency=0.85)
    # Ensure we start with Strong evidence
    assert result.label == "Strong evidence"

    capped = scorer.apply_sensitivity_cap(result, sensitivity_score=35.0)
    assert capped.label == "Moderate evidence"
    assert capped.score == result.score  # score unchanged


def test_apply_sensitivity_cap_severe_downgrades_to_weak():
    """sensitivity_score < 20 downgrades Moderate evidence to Weak evidence."""
    train = _make_metrics(cagr=25.0, total_trades=100)
    val = _make_metrics(cagr=22.0, total_trades=40)
    # OOS CAGR=14%, wf=0.50, 45 trades → score ~64.7 = Moderate evidence
    oos = _make_metrics(cagr=14.0, total_trades=45)

    scorer = ReliabilityScorer()
    result = scorer.score(train, val, oos, wf_consistency=0.50)
    # Ensure we start with Moderate evidence
    assert result.label == "Moderate evidence"

    capped = scorer.apply_sensitivity_cap(result, sensitivity_score=15.0)
    assert capped.label == "Weak evidence"
    assert capped.score == result.score
