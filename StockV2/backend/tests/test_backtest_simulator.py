from datetime import date
import pandas as pd


def _make_prices(n: int = 250, start_close: float = 1000.0) -> pd.DataFrame:
    """Steadily rising prices: +2/day. Reliable for deterministic test entry/exit."""
    dates = pd.bdate_range("2023-01-01", periods=n).date
    closes = [start_close + i * 2.0 for i in range(n)]
    return pd.DataFrame({
        "date":   dates,
        "open":   [c * 0.995 for c in closes],
        "high":   [c * 1.010 for c in closes],
        "low":    [c * 0.990 for c in closes],
        "close":  closes,
        "volume": [1_000_000] * n,
    })


class _AlwaysBuyStrategy:
    """Test double: always BUY after 30-bar warmup. No ABC inheritance needed."""
    name = "always_buy"
    weight = 0.20
    strategy_type = "technical"

    def generate_signal(self, df, fundamentals=None):
        from domains.strategies.base import Signal
        if len(df) < 30:
            return Signal(signal_type="NONE")
        return Signal(signal_type="BUY", confidence=0.80)


def test_simulator_returns_trades_for_buy_signal():
    from domains.backtest.simulator import BacktestSimulator
    df = _make_prices(250)
    from_date, to_date = df["date"][50], df["date"].iloc[-1]
    trades = BacktestSimulator().run(
        symbol="TCS",
        prices_df=df,
        from_date=from_date,
        to_date=to_date,
        strategies=[_AlwaysBuyStrategy()],
        use_aggregator=False,
        initial_capital=500_000.0,
    )
    assert len(trades) >= 1


def test_simulator_trade_fields_are_populated():
    from domains.backtest.simulator import BacktestSimulator, SimTrade
    df = _make_prices(250)
    from_date, to_date = df["date"][50], df["date"].iloc[-1]
    trades = BacktestSimulator().run(
        symbol="TCS", prices_df=df,
        from_date=from_date, to_date=to_date,
        strategies=[_AlwaysBuyStrategy()],
        use_aggregator=False, initial_capital=500_000.0,
    )
    t = trades[0]
    assert isinstance(t, SimTrade)
    assert t.symbol == "TCS"
    assert t.entry_price > 0
    assert t.exit_price > 0
    assert t.quantity > 0
    assert t.exit_reason in ("stop_loss", "target_hit", "max_holding_days", "end_of_period")


def test_simulator_exit_on_target():
    """Rapidly rising prices → target_hit exit."""
    from domains.backtest.simulator import BacktestSimulator   # ADD THIS LINE
    n = 120
    # Flat for 50 bars, then +15/bar so target (+15%) hits quickly
    closes = [1000.0] * 50 + [1001.0 + i * 15 for i in range(70)]
    dates = pd.bdate_range("2023-01-01", periods=n).date
    df = pd.DataFrame({
        "date":   dates,
        "open":   [c * 0.99 for c in closes],
        "high":   [c * 1.02 for c in closes],
        "low":    [c * 0.98 for c in closes],
        "close":  closes,
        "volume": [1_000_000] * n,
    })
    trades = BacktestSimulator().run(
        symbol="TCS", prices_df=df,
        from_date=dates[50], to_date=dates[-1],
        strategies=[_AlwaysBuyStrategy()],
        use_aggregator=False, initial_capital=500_000.0,
    )
    assert any(t.exit_reason == "target_hit" for t in trades)


def test_simulator_no_double_entry():
    """Entries must not overlap — exit_date[i] <= entry_date[i+1]."""
    from domains.backtest.simulator import BacktestSimulator
    df = _make_prices(250)
    from_date, to_date = df["date"][50], df["date"].iloc[-1]
    trades = BacktestSimulator().run(
        symbol="TCS", prices_df=df,
        from_date=from_date, to_date=to_date,
        strategies=[_AlwaysBuyStrategy()],
        use_aggregator=False, initial_capital=500_000.0,
    )
    for i in range(len(trades) - 1):
        assert trades[i].exit_date <= trades[i + 1].entry_date


def test_simulator_aggregator_requires_three_buy_signals():
    """SignalAggregator only fires BUY with consensus_score > 0.65 AND buy_count >= 3."""
    from domains.backtest.simulator import BacktestSimulator
    df = _make_prices(250)
    from_date, to_date = df["date"][50], df["date"].iloc[-1]
    # One strategy cannot satisfy buy_count >= 3 — expect zero trades
    trades = BacktestSimulator().run(
        symbol="TCS", prices_df=df,
        from_date=from_date, to_date=to_date,
        strategies=[_AlwaysBuyStrategy()],
        use_aggregator=True,
        initial_capital=500_000.0,
    )
    assert trades == []


def test_round_trip_cost_reduces_pnl():
    """Verify round-trip cost deducts from raw PnL."""
    from domains.backtest.simulator import BacktestSimulator
    df = _make_prices(250)
    from_date, to_date = df["date"][50], df["date"].iloc[-1]

    trades_no_cost = BacktestSimulator().run(
        symbol="TCS", prices_df=df,
        from_date=from_date, to_date=to_date,
        strategies=[_AlwaysBuyStrategy()],
        use_aggregator=False, initial_capital=500_000.0,
        round_trip_cost_pct=0.0,
    )

    trades_with_cost = BacktestSimulator().run(
        symbol="TCS", prices_df=df,
        from_date=from_date, to_date=to_date,
        strategies=[_AlwaysBuyStrategy()],
        use_aggregator=False, initial_capital=500_000.0,
        round_trip_cost_pct=0.30,
    )

    assert len(trades_no_cost) == len(trades_with_cost)
    for t_no, t_yes in zip(trades_no_cost, trades_with_cost):
        assert t_yes.pnl < t_no.pnl
        assert t_yes.commission > 0
        entry_value = t_yes.entry_price * t_yes.quantity
        expected_commission = round(entry_value * 0.30 / 100, 2)
        assert abs(t_yes.commission - expected_commission) < 0.01


def test_zero_cost_pnl_unchanged():
    """Verify 0% cost produces same PnL as default (backward compat check)."""
    from domains.backtest.simulator import BacktestSimulator
    df = _make_prices(250)
    from_date, to_date = df["date"][50], df["date"].iloc[-1]

    trades_default = BacktestSimulator().run(
        symbol="TCS", prices_df=df,
        from_date=from_date, to_date=to_date,
        strategies=[_AlwaysBuyStrategy()],
        use_aggregator=False, initial_capital=500_000.0,
    )

    trades_explicit_zero = BacktestSimulator().run(
        symbol="TCS", prices_df=df,
        from_date=from_date, to_date=to_date,
        strategies=[_AlwaysBuyStrategy()],
        use_aggregator=False, initial_capital=500_000.0,
        round_trip_cost_pct=0.0,
    )

    assert len(trades_default) == len(trades_explicit_zero)
    for t1, t2 in zip(trades_default, trades_explicit_zero):
        assert t1.pnl == t2.pnl
        assert t1.commission == 0.0
        assert t2.commission == 0.0
