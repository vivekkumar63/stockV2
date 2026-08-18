from datetime import date
from unittest.mock import MagicMock
from domains.backtest.simulator import SimTrade
from domains.combinations.metrics import compute_extended_metrics, ExtendedMetrics


def _make_trade(pnl: float, pnl_pct: float, exit_date: date = date(2024, 3, 1)) -> SimTrade:
    return SimTrade(
        symbol="TEST", entry_date=date(2024, 1, 1), entry_price=100.0,
        exit_date=exit_date, exit_price=100.0 + pnl,
        quantity=10, stop_loss_price=90.0, target_price=115.0,
        exit_reason="target_hit", pnl=pnl, pnl_pct=pnl_pct, holding_days=14
    )


def test_extended_metrics_includes_sortino():
    db = MagicMock()
    db.execute.return_value.fetchone.return_value = None  # no regime data

    # Give trades separate exit dates so each loss lands on its own day,
    # ensuring at least 2 downside returns in the daily equity curve.
    trades = [
        _make_trade(2000.0, 4.0, exit_date=date(2024, 1, 15)),
        _make_trade(-800.0, -1.6, exit_date=date(2024, 2, 1)),
        _make_trade(-600.0, -1.2, exit_date=date(2024, 2, 15)),
    ]

    result = compute_extended_metrics(
        trades, 500_000.0, date(2024, 1, 1), date(2024, 3, 31), db, {}
    )

    assert isinstance(result, ExtendedMetrics)
    assert result.sortino_ratio is not None
    assert result.median_return_pct is not None
    assert isinstance(result.regime_win_rates, dict)


def test_extended_metrics_empty_trades():
    db = MagicMock()
    result = compute_extended_metrics([], 500_000.0, date(2024, 1, 1), date(2024, 3, 31), db, {})
    assert result.total_trades == 0
    assert result.sortino_ratio is None
    assert result.median_return_pct is None


def test_benchmark_deltas_correct():
    db = MagicMock()
    db.execute.return_value.fetchone.return_value = None

    trades = [_make_trade(50000.0, 10.0)]  # ~large gain to get positive CAGR
    benchmarks = {"buy_and_hold": 12.5, "best_single": 18.0, "sma_crossover": 8.5}

    result = compute_extended_metrics(
        trades, 500_000.0, date(2024, 1, 1), date(2024, 3, 31), db, benchmarks
    )

    # Deltas should be oos_cagr - benchmark
    assert "bah" in result.benchmark_deltas
    assert "best_single" in result.benchmark_deltas
    assert "sma_cross" in result.benchmark_deltas
