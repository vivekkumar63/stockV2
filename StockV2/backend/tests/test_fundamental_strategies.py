import pandas as pd
import pytest


def _make_df(n=100, close=100.0, volume=1_500_000.0, vol_sma=1_000_000.0,
             rsi=55.0, sma_50=95.0):
    """Minimal DataFrame with indicator columns needed by fundamental strategies."""
    closes = [close] * n
    return pd.DataFrame({
        "open":         [close - 1] * n,
        "high":         [close + 2] * n,
        "low":          [close - 2] * n,
        "close":        closes,
        "volume":       [volume] * n,
        "rsi_14":       [rsi] * n,
        "sma_20":       [close] * n,
        "sma_50":       [sma_50] * n,
        "volume_sma_20":[vol_sma] * n,
        "volume_ratio": [volume / vol_sma] * n,
        "bb_upper":     [close + 10] * n,
        "bb_lower":     [close - 10] * n,
        "bb_middle":    [close] * n,
        "adx_14":       [25.0] * n,
        "atr_14":       [2.0] * n,
        "macd":         [0.5] * n,
        "macd_signal":  [0.4] * n,
        "macd_hist":    [0.1] * n,
    })


def _good_fundamentals():
    """Fundamentals dict that passes all criteria for all fundamental strategies."""
    return {
        "pe_ratio":       15.0,   # was 20.0 — changed to pass Magic Formula PE < 20
        "pb_ratio":       2.0,
        "eps":            50.0,
        "revenue":        1e10,
        "net_profit":     1e9,
        "debt_equity":    0.4,
        "roe":            0.20,
        "dividend_yield": 0.025,
        "data_as_of":     "2026-08-01",
    }


# ── CANSLIM ──────────────────────────────────────────────────────────────────

def test_canslim_buy_when_all_criteria_met():
    from domains.strategies.strategies.canslim import CANSLIMStrategy
    df = _make_df(close=100.0, sma_50=95.0, volume=1_500_000.0, vol_sma=1_000_000.0)
    f = _good_fundamentals()  # eps>0, roe>0.15, pe<30
    signal = CANSLIMStrategy().generate_signal(df, f)
    assert signal.signal_type == "BUY"
    assert signal.confidence > 0.5


def test_canslim_none_when_fundamentals_empty():
    from domains.strategies.strategies.canslim import CANSLIMStrategy
    df = _make_df()
    signal = CANSLIMStrategy().generate_signal(df, {})
    assert signal.signal_type == "NONE"


def test_canslim_none_when_only_2_criteria_met():
    from domains.strategies.strategies.canslim import CANSLIMStrategy
    df = _make_df(close=100.0, sma_50=110.0)  # close < sma_50 (M fails)
    f = {**_good_fundamentals(), "eps": -5.0, "roe": 0.05}  # C, A also fail
    signal = CANSLIMStrategy().generate_signal(df, f)
    assert signal.signal_type == "NONE"


def test_canslim_none_when_fundamentals_is_none():
    from domains.strategies.strategies.canslim import CANSLIMStrategy
    df = _make_df()
    signal = CANSLIMStrategy().generate_signal(df, None)
    assert signal.signal_type == "NONE"


def test_canslim_none_when_exactly_4_criteria_met():
    from domains.strategies.strategies.canslim import CANSLIMStrategy
    # Fail M (sma_50 > close) and C (eps < 0): only 4 of 6 met
    df = _make_df(close=100.0, sma_50=110.0)
    f = {**_good_fundamentals(), "eps": -1.0}
    signal = CANSLIMStrategy().generate_signal(df, f)
    assert signal.signal_type == "NONE"


def test_canslim_buy_confidence_is_five_sixths_when_5_of_6_met():
    from domains.strategies.strategies.canslim import CANSLIMStrategy
    # M fails (close < sma_50), 5/6 criteria met
    df = _make_df(close=100.0, sma_50=110.0)
    f = _good_fundamentals()  # eps>0, roe>0.15, pe<30 all good
    signal = CANSLIMStrategy().generate_signal(df, f)
    assert signal.signal_type == "BUY"
    assert abs(signal.confidence - round(5 / 6, 4)) < 1e-4


# ── Magic Formula ─────────────────────────────────────────────────────────────

def test_magic_formula_buy_when_all_criteria_met():
    from domains.strategies.strategies.magic_formula import MagicFormulaStrategy
    df = _make_df(close=500.0)  # EPS=50, price=500 → earnings yield=10% > 6%
    f = {**_good_fundamentals(), "pe_ratio": 15.0}
    signal = MagicFormulaStrategy().generate_signal(df, f)
    assert signal.signal_type == "BUY"
    assert signal.confidence == pytest.approx(0.75)


def test_magic_formula_none_when_fundamentals_empty():
    from domains.strategies.strategies.magic_formula import MagicFormulaStrategy
    signal = MagicFormulaStrategy().generate_signal(_make_df(), {})
    assert signal.signal_type == "NONE"


def test_magic_formula_none_when_earnings_yield_too_low():
    from domains.strategies.strategies.magic_formula import MagicFormulaStrategy
    # EPS=50, close=2000 → earnings yield = 50/2000 = 2.5% < 6%
    df = _make_df(close=2000.0)
    f = {**_good_fundamentals(), "pe_ratio": 15.0}
    signal = MagicFormulaStrategy().generate_signal(df, f)
    assert signal.signal_type == "NONE"


def test_magic_formula_none_when_fundamentals_is_none():
    from domains.strategies.strategies.magic_formula import MagicFormulaStrategy
    signal = MagicFormulaStrategy().generate_signal(_make_df(), None)
    assert signal.signal_type == "NONE"


def test_magic_formula_none_when_pe_at_boundary():
    from domains.strategies.strategies.magic_formula import MagicFormulaStrategy
    df = _make_df(close=500.0)
    f = {**_good_fundamentals(), "pe_ratio": 20.0}  # exactly at threshold — strict < means NONE
    signal = MagicFormulaStrategy().generate_signal(df, f)
    assert signal.signal_type == "NONE"


# ── Graham Value ──────────────────────────────────────────────────────────────

def test_graham_value_buy_when_undervalued():
    from domains.strategies.strategies.graham_value import GrahamValueStrategy
    # EPS=50, PB=1.2, close=400
    # BookValue = 400/1.2 = 333.3
    # Graham = sqrt(22.5 * 50 * 333.3) = sqrt(374962) ≈ 612
    # 1.3 * 612 = 796 → close=400 < 796 ✓
    # PE = 400/50 = 8 < 15 ✓ (we override pe_ratio below), PB = 1.2 < 1.5 ✓
    df = _make_df(close=400.0)
    f = {**_good_fundamentals(), "eps": 50.0, "pb_ratio": 1.2, "pe_ratio": 8.0}
    signal = GrahamValueStrategy().generate_signal(df, f)
    assert signal.signal_type == "BUY"
    assert 0.4 <= signal.confidence <= 1.0


def test_graham_value_none_when_fundamentals_empty():
    from domains.strategies.strategies.graham_value import GrahamValueStrategy
    signal = GrahamValueStrategy().generate_signal(_make_df(), {})
    assert signal.signal_type == "NONE"


def test_graham_value_none_when_overvalued():
    from domains.strategies.strategies.graham_value import GrahamValueStrategy
    # High PE = 30 (>15), PB = 3 (>1.5) — both fail
    df = _make_df(close=1500.0)
    f = {**_good_fundamentals(), "eps": 50.0, "pb_ratio": 3.0, "pe_ratio": 30.0}
    signal = GrahamValueStrategy().generate_signal(df, f)
    assert signal.signal_type == "NONE"


def test_graham_value_none_when_fundamentals_is_none():
    from domains.strategies.strategies.graham_value import GrahamValueStrategy
    signal = GrahamValueStrategy().generate_signal(_make_df(), None)
    assert signal.signal_type == "NONE"


# ── Growth Investing ──────────────────────────────────────────────────────────

def test_growth_buy_when_all_criteria_met():
    from domains.strategies.strategies.growth_investing import GrowthInvestingStrategy
    signal = GrowthInvestingStrategy().generate_signal(_make_df(), _good_fundamentals())
    assert signal.signal_type == "BUY"
    assert signal.confidence == pytest.approx(1.0)  # 5/5 met


def test_growth_none_when_fundamentals_empty():
    from domains.strategies.strategies.growth_investing import GrowthInvestingStrategy
    signal = GrowthInvestingStrategy().generate_signal(_make_df(), {})
    assert signal.signal_type == "NONE"


def test_growth_none_when_fundamentals_is_none():
    from domains.strategies.strategies.growth_investing import GrowthInvestingStrategy
    signal = GrowthInvestingStrategy().generate_signal(_make_df(), None)
    assert signal.signal_type == "NONE"


def test_growth_none_when_3_criteria_fail():
    from domains.strategies.strategies.growth_investing import GrowthInvestingStrategy
    # roe=0.05 (<15%), eps=-10 (<0), net_profit=-1e9 (<0) — 3 fail, only 2 pass
    f = {**_good_fundamentals(), "roe": 0.05, "eps": -10.0, "net_profit": -1e9}
    signal = GrowthInvestingStrategy().generate_signal(_make_df(), f)
    assert signal.signal_type == "NONE"


def test_growth_buy_when_exactly_4_criteria_met():
    from domains.strategies.strategies.growth_investing import GrowthInvestingStrategy
    # Fail only ROE; 4 of 5 pass
    f = {**_good_fundamentals(), "roe": 0.10}  # 10% < 15% fails ROE
    signal = GrowthInvestingStrategy().generate_signal(_make_df(), f)
    assert signal.signal_type == "BUY"
    assert signal.confidence == pytest.approx(4 / 5)


# ── Dividend Investing ────────────────────────────────────────────────────────

def test_dividend_buy_when_all_criteria_met():
    from domains.strategies.strategies.dividend_investing import DividendInvestingStrategy
    signal = DividendInvestingStrategy().generate_signal(_make_df(), _good_fundamentals())
    assert signal.signal_type == "BUY"
    assert signal.confidence == pytest.approx(0.70)


def test_dividend_none_when_fundamentals_empty():
    from domains.strategies.strategies.dividend_investing import DividendInvestingStrategy
    signal = DividendInvestingStrategy().generate_signal(_make_df(), {})
    assert signal.signal_type == "NONE"


def test_dividend_none_when_fundamentals_is_none():
    from domains.strategies.strategies.dividend_investing import DividendInvestingStrategy
    signal = DividendInvestingStrategy().generate_signal(_make_df(), None)
    assert signal.signal_type == "NONE"


def test_dividend_none_when_low_yield():
    from domains.strategies.strategies.dividend_investing import DividendInvestingStrategy
    f = {**_good_fundamentals(), "dividend_yield": 0.005}  # 0.5% < 2%
    signal = DividendInvestingStrategy().generate_signal(_make_df(), f)
    assert signal.signal_type == "NONE"


def test_dividend_none_when_high_debt():
    from domains.strategies.strategies.dividend_investing import DividendInvestingStrategy
    f = {**_good_fundamentals(), "debt_equity": 0.8}  # D/E > 0.5
    signal = DividendInvestingStrategy().generate_signal(_make_df(), f)
    assert signal.signal_type == "NONE"
