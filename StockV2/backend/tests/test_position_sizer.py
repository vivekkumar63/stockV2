from types import SimpleNamespace

CFG = SimpleNamespace(
    total_capital=500_000.0,
    paper_capital=500_000.0,
    risk_per_trade_pct=2.0,
    max_open_positions=8,
    max_single_stock_pct=20.0,
)


def test_basic_valid_position():
    from domains.portfolio.position_sizer import PositionSizer
    sizer = PositionSizer()
    # risk=10_000, risk_per_share=100 (1000-900), qty=100, pos_value=100_000 (20% cap exact)
    result = sizer.compute(
        entry_price=1000.0, stop_loss_price=900.0, target_price=1150.0,
        open_positions=0, invested_capital=0.0, _cfg=CFG,
    )
    assert result.is_valid
    assert result.quantity == 100
    assert result.position_value == 100_000.0
    assert result.stop_loss_price == 900.0
    assert result.target_price == 1150.0


def test_caps_at_max_single_stock_pct():
    from domains.portfolio.position_sizer import PositionSizer
    sizer = PositionSizer()
    # Tight stop → qty would be huge; capped at 20% of capital
    result = sizer.compute(
        entry_price=1000.0, stop_loss_price=990.0, target_price=1100.0,
        open_positions=0, invested_capital=0.0, _cfg=CFG,
    )
    assert result.is_valid
    assert result.position_value <= 100_000.0 + 1000.0


def test_rejects_when_max_positions_reached():
    from domains.portfolio.position_sizer import PositionSizer
    result = PositionSizer().compute(
        entry_price=1000.0, stop_loss_price=900.0, target_price=1150.0,
        open_positions=8, invested_capital=0.0, _cfg=CFG,
    )
    assert not result.is_valid
    assert "Max open positions" in result.reject_reason


def test_rejects_when_insufficient_capital():
    from domains.portfolio.position_sizer import PositionSizer
    result = PositionSizer().compute(
        entry_price=1000.0, stop_loss_price=900.0, target_price=1150.0,
        open_positions=0, invested_capital=490_000.0, _cfg=CFG,
    )
    assert not result.is_valid
    assert "Insufficient capital" in result.reject_reason


def test_rejects_when_stop_loss_above_entry():
    from domains.portfolio.position_sizer import PositionSizer
    result = PositionSizer().compute(
        entry_price=1000.0, stop_loss_price=1050.0, target_price=1200.0,
        open_positions=0, invested_capital=0.0, _cfg=CFG,
    )
    assert not result.is_valid
    assert "Invalid stop loss" in result.reject_reason
