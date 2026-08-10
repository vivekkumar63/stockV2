from datetime import date
from domains.backtest.simulator import SimTrade


def _trade(pnl: float, pnl_pct: float, entry: date, exit_: date) -> SimTrade:
    return SimTrade(
        symbol="TCS",
        entry_date=entry,
        entry_price=1000.0,
        exit_date=exit_,
        exit_price=1000.0 + pnl / 100,
        quantity=100,
        stop_loss_price=930.0,
        target_price=1150.0,
        exit_reason="target_hit",
        pnl=pnl,
        pnl_pct=pnl_pct,
        holding_days=(exit_ - entry).days,
    )


def test_empty_trades():
    from domains.backtest.metrics import compute_metrics
    result = compute_metrics([], 500_000.0, date(2023, 1, 1), date(2023, 12, 31))
    assert result["total_trades"] == 0
    assert result["total_pnl"] == 0.0
    assert result["win_rate"] is None


def test_all_wins():
    from domains.backtest.metrics import compute_metrics
    trades = [
        _trade(1000.0, 1.0, date(2023, 1, 2), date(2023, 1, 20)),
        _trade(2000.0, 2.0, date(2023, 2, 1), date(2023, 2, 20)),
    ]
    r = compute_metrics(trades, 500_000.0, date(2023, 1, 1), date(2023, 12, 31))
    assert r["win_rate"] == 1.0
    assert r["total_pnl"] == 3000.0
    assert r["total_trades"] == 2


def test_mixed_win_loss():
    from domains.backtest.metrics import compute_metrics
    trades = [
        _trade(1000.0, 1.0, date(2023, 1, 2), date(2023, 1, 20)),
        _trade(-500.0, -0.5, date(2023, 2, 1), date(2023, 2, 20)),
    ]
    r = compute_metrics(trades, 500_000.0, date(2023, 1, 1), date(2023, 12, 31))
    assert r["win_rate"] == 0.5
    assert r["total_pnl"] == 500.0


def test_profit_factor():
    from domains.backtest.metrics import compute_metrics
    trades = [
        _trade(2000.0, 2.0, date(2023, 1, 2), date(2023, 1, 20)),
        _trade(-1000.0, -1.0, date(2023, 2, 1), date(2023, 2, 20)),
    ]
    r = compute_metrics(trades, 500_000.0, date(2023, 1, 1), date(2023, 12, 31))
    assert r["profit_factor"] == 2.0


def test_cagr_positive():
    from domains.backtest.metrics import compute_metrics
    # 10% gain in ~1 year → CAGR ≈ 10%
    trades = [
        _trade(50_000.0, 10.0, date(2023, 1, 2), date(2023, 6, 30)),
    ]
    r = compute_metrics(trades, 500_000.0, date(2023, 1, 1), date(2023, 12, 31))
    assert r["cagr"] is not None
    assert r["cagr"] > 0


def test_max_drawdown_negative():
    from domains.backtest.metrics import compute_metrics
    # Loss followed by a gain — there should be a drawdown
    trades = [
        _trade(-10_000.0, -2.0, date(2023, 1, 2), date(2023, 1, 20)),
        _trade(5_000.0, 1.0, date(2023, 2, 1), date(2023, 2, 20)),
    ]
    r = compute_metrics(trades, 500_000.0, date(2023, 1, 1), date(2023, 12, 31))
    assert r["max_drawdown"] is not None
    assert r["max_drawdown"] < 0
