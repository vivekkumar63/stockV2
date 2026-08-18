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
        "pe_ratio":       20.0,
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
