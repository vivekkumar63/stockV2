import numpy as np
import pandas as pd
import pytest
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


def test_signal_defaults():
    s = Signal(signal_type="NONE")
    assert s.confidence == 0.0
    assert s.stop_loss_pct == 7.0
    assert s.target_pct == 15.0
    assert s.holding_days == 15
    assert s.conditions_met == []
    assert s.conditions_failed == []


def test_signal_buy():
    s = Signal(signal_type="BUY", confidence=0.75, conditions_met=["RSI < 30"])
    assert s.signal_type == "BUY"
    assert s.confidence == 0.75
    assert "RSI < 30" in s.conditions_met


def test_base_strategy_is_abstract():
    with pytest.raises(TypeError):
        BaseStrategy()  # cannot instantiate abstract class


def test_strategy_type_values():
    assert StrategyType.TECHNICAL == "technical"
    assert StrategyType.FUNDAMENTAL == "fundamental"
    assert StrategyType.ML == "ml"
    assert StrategyType.CUSTOM == "custom"


def test_timeframe_values():
    assert Timeframe.DAILY == "daily"
    assert Timeframe.INTRADAY_15M == "intraday_15m"


def _make_df(n=60, rsi_trigger=None, macd_cross=None, ema_cross=None, sma_cross=None, st_flip=None):
    close = pd.Series([100.0 + i * 0.5 for i in range(n)], dtype=float)
    df = pd.DataFrame({
        "open": close - 0.5,
        "high": close + 1.0,
        "low": close - 1.0,
        "close": close,
        "volume": [1_000_000.0] * n,
        "rsi_14": [50.0] * n,
        "macd_hist": [0.1] * n,
        "ema_9": close,
        "ema_21": close - 2,
        "sma_20": close,
        "sma_50": close - 5,
        "supertrend_direction": [1.0] * n,
        "supertrend": close - 3,
        "bb_upper": close + 10,
        "bb_middle": close,
        "bb_lower": close - 10,
        "atr_14": [2.0] * n,
        "adx_14": [30.0] * n,
        "volume_sma_20": [1_000_000.0] * n,
        "volume_ratio": [1.0] * n,
        "macd": [0.5] * n,
        "macd_signal": [0.4] * n,
        "roc_10": [1.0] * n,
    })
    return df


# ── RSI ────────────────────────────────────────────────────────────────────────

def test_rsi_buy_when_oversold():
    from domains.strategies.strategies.rsi_oversold import RSIOversoldStrategy
    df = _make_df()
    df["rsi_14"] = 25.0
    signal = RSIOversoldStrategy().generate_signal(df)
    assert signal.signal_type == "BUY"
    assert signal.confidence > 0.5


def test_rsi_sell_when_overbought():
    from domains.strategies.strategies.rsi_oversold import RSIOversoldStrategy
    df = _make_df()
    df["rsi_14"] = 75.0
    signal = RSIOversoldStrategy().generate_signal(df)
    assert signal.signal_type == "SELL"


def test_rsi_none_when_neutral():
    from domains.strategies.strategies.rsi_oversold import RSIOversoldStrategy
    df = _make_df()
    df["rsi_14"] = 50.0
    signal = RSIOversoldStrategy().generate_signal(df)
    assert signal.signal_type == "NONE"


def test_rsi_none_when_nan():
    from domains.strategies.strategies.rsi_oversold import RSIOversoldStrategy
    df = _make_df(n=5)
    df["rsi_14"] = float("nan")
    signal = RSIOversoldStrategy().generate_signal(df)
    assert signal.signal_type == "NONE"


# ── MACD ───────────────────────────────────────────────────────────────────────

def test_macd_buy_on_bullish_crossover():
    from domains.strategies.strategies.macd_crossover import MACDCrossoverStrategy
    df = _make_df()
    df["macd_hist"] = 0.1
    df.at[df.index[-2], "macd_hist"] = -0.1
    signal = MACDCrossoverStrategy().generate_signal(df)
    assert signal.signal_type == "BUY"


def test_macd_sell_on_bearish_crossover():
    from domains.strategies.strategies.macd_crossover import MACDCrossoverStrategy
    df = _make_df()
    df["macd_hist"] = -0.1
    df.at[df.index[-2], "macd_hist"] = 0.1
    signal = MACDCrossoverStrategy().generate_signal(df)
    assert signal.signal_type == "SELL"


def test_macd_none_when_no_cross():
    from domains.strategies.strategies.macd_crossover import MACDCrossoverStrategy
    df = _make_df()
    df["macd_hist"] = 0.2
    signal = MACDCrossoverStrategy().generate_signal(df)
    assert signal.signal_type == "NONE"


# ── EMA Crossover ──────────────────────────────────────────────────────────────

def test_ema_buy_on_upward_cross():
    from domains.strategies.strategies.ema_crossover import EMACrossoverStrategy
    df = _make_df()
    df["ema_9"] = 102.0
    df["ema_21"] = 103.0
    df.at[df.index[-1], "ema_9"] = 104.0
    df.at[df.index[-1], "ema_21"] = 103.0
    signal = EMACrossoverStrategy().generate_signal(df)
    assert signal.signal_type == "BUY"


def test_ema_none_when_already_above():
    from domains.strategies.strategies.ema_crossover import EMACrossoverStrategy
    df = _make_df()
    df["ema_9"] = 105.0
    df["ema_21"] = 100.0
    signal = EMACrossoverStrategy().generate_signal(df)
    assert signal.signal_type == "NONE"


# ── SMA Crossover ──────────────────────────────────────────────────────────────

def test_sma_buy_golden_cross():
    from domains.strategies.strategies.sma_crossover import SMACrossoverStrategy
    df = _make_df()
    df["sma_20"] = 98.0
    df["sma_50"] = 100.0
    df.at[df.index[-1], "sma_20"] = 101.0
    df.at[df.index[-1], "sma_50"] = 100.0
    signal = SMACrossoverStrategy().generate_signal(df)
    assert signal.signal_type == "BUY"
    assert signal.confidence >= 0.70


def test_sma_sell_death_cross():
    from domains.strategies.strategies.sma_crossover import SMACrossoverStrategy
    df = _make_df()
    df["sma_20"] = 102.0
    df["sma_50"] = 100.0
    df.at[df.index[-1], "sma_20"] = 99.0
    df.at[df.index[-1], "sma_50"] = 100.0
    signal = SMACrossoverStrategy().generate_signal(df)
    assert signal.signal_type == "SELL"


# ── SuperTrend ─────────────────────────────────────────────────────────────────

def test_supertrend_buy_on_bullish_flip():
    from domains.strategies.strategies.supertrend_strategy import SuperTrendStrategy
    df = _make_df()
    df["supertrend_direction"] = 1.0
    df.at[df.index[-2], "supertrend_direction"] = -1.0
    signal = SuperTrendStrategy().generate_signal(df)
    assert signal.signal_type == "BUY"
    assert signal.confidence >= 0.70


def test_supertrend_sell_on_bearish_flip():
    from domains.strategies.strategies.supertrend_strategy import SuperTrendStrategy
    df = _make_df()
    df["supertrend_direction"] = -1.0
    df.at[df.index[-2], "supertrend_direction"] = 1.0
    signal = SuperTrendStrategy().generate_signal(df)
    assert signal.signal_type == "SELL"


def test_supertrend_none_when_no_flip():
    from domains.strategies.strategies.supertrend_strategy import SuperTrendStrategy
    df = _make_df()
    df["supertrend_direction"] = 1.0
    signal = SuperTrendStrategy().generate_signal(df)
    assert signal.signal_type == "NONE"


# ── BB Squeeze ─────────────────────────────────────────────────────────────────

def test_bb_squeeze_buy_on_breakout_with_volume():
    from domains.strategies.strategies.bb_squeeze import BBSqueezeStrategy
    df = _make_df()
    df["close"] = 115.0
    df["bb_upper"] = 110.0
    df["volume_ratio"] = 2.0
    signal = BBSqueezeStrategy().generate_signal(df)
    assert signal.signal_type == "BUY"
    assert signal.confidence > 0.55


def test_bb_squeeze_none_without_volume():
    from domains.strategies.strategies.bb_squeeze import BBSqueezeStrategy
    df = _make_df()
    df["close"] = 115.0
    df["bb_upper"] = 110.0
    df["volume_ratio"] = 1.0
    signal = BBSqueezeStrategy().generate_signal(df)
    assert signal.signal_type == "NONE"


def test_bb_squeeze_none_below_band():
    from domains.strategies.strategies.bb_squeeze import BBSqueezeStrategy
    df = _make_df()
    df["close"] = 100.0
    df["bb_upper"] = 110.0
    df["volume_ratio"] = 3.0
    signal = BBSqueezeStrategy().generate_signal(df)
    assert signal.signal_type == "NONE"


# ── Volume Breakout ────────────────────────────────────────────────────────────

def test_volume_breakout_buy_on_surge_up():
    from domains.strategies.strategies.volume_breakout import VolumeBreakoutStrategy
    df = _make_df()
    df["volume_ratio"] = 3.0
    df["close"] = 102.0
    df.at[df.index[-2], "close"] = 100.0
    signal = VolumeBreakoutStrategy().generate_signal(df)
    assert signal.signal_type == "BUY"


def test_volume_breakout_none_if_price_down():
    from domains.strategies.strategies.volume_breakout import VolumeBreakoutStrategy
    df = _make_df()
    df["volume_ratio"] = 3.0
    df["close"] = 98.0
    df.at[df.index[-2], "close"] = 100.0
    signal = VolumeBreakoutStrategy().generate_signal(df)
    assert signal.signal_type == "NONE"


def test_volume_breakout_none_low_volume():
    from domains.strategies.strategies.volume_breakout import VolumeBreakoutStrategy
    df = _make_df()
    df["volume_ratio"] = 1.5
    signal = VolumeBreakoutStrategy().generate_signal(df)
    assert signal.signal_type == "NONE"


# ── Mean Reversion ─────────────────────────────────────────────────────────────

def test_mean_reversion_buy_oversold_non_trending():
    from domains.strategies.strategies.mean_reversion import MeanReversionStrategy
    df = _make_df()
    df["close"] = 85.0
    df["bb_lower"] = 90.0
    df["bb_upper"] = 115.0
    df["rsi_14"] = 32.0
    df["adx_14"] = 18.0
    signal = MeanReversionStrategy().generate_signal(df)
    assert signal.signal_type == "BUY"


def test_mean_reversion_none_if_trending():
    from domains.strategies.strategies.mean_reversion import MeanReversionStrategy
    df = _make_df()
    df["close"] = 85.0
    df["bb_lower"] = 90.0
    df["rsi_14"] = 32.0
    df["adx_14"] = 35.0
    signal = MeanReversionStrategy().generate_signal(df)
    assert signal.signal_type == "NONE"


def test_mean_reversion_sell_overbought():
    from domains.strategies.strategies.mean_reversion import MeanReversionStrategy
    df = _make_df()
    df["close"] = 125.0
    df["bb_upper"] = 110.0
    df["bb_lower"] = 90.0
    df["rsi_14"] = 75.0
    df["adx_14"] = 15.0
    signal = MeanReversionStrategy().generate_signal(df)
    assert signal.signal_type == "SELL"


# ── Volatility Breakout ────────────────────────────────────────────────────────

def test_volatility_breakout_buy_on_20d_high_break():
    from domains.strategies.strategies.volatility_breakout import VolatilityBreakoutStrategy
    df = _make_df(n=60)
    df["close"] = 100.0
    df["volume_ratio"] = 2.0
    df.at[df.index[-1], "close"] = 105.0
    df.at[df.index[-2], "close"] = 99.0
    signal = VolatilityBreakoutStrategy().generate_signal(df)
    assert signal.signal_type == "BUY"


def test_volatility_breakout_none_without_volume():
    from domains.strategies.strategies.volatility_breakout import VolatilityBreakoutStrategy
    df = _make_df(n=60)
    df["close"] = 100.0
    df["volume_ratio"] = 1.0
    df.at[df.index[-1], "close"] = 105.0
    signal = VolatilityBreakoutStrategy().generate_signal(df)
    assert signal.signal_type == "NONE"


def test_volatility_breakout_none_too_few_rows():
    from domains.strategies.strategies.volatility_breakout import VolatilityBreakoutStrategy
    df = _make_df(n=15)
    signal = VolatilityBreakoutStrategy().generate_signal(df)
    assert signal.signal_type == "NONE"


# ── Swing Trend Rider ──────────────────────────────────────────────────────────

def test_swing_trend_rider_buy_all_conditions():
    from domains.strategies.strategies.swing_trend_rider import SwingTrendRiderStrategy
    df = _make_df()
    df["close"] = 110.0
    df["sma_50"] = 100.0
    df["rsi_14"] = 58.0
    df["adx_14"] = 28.0
    df["macd_hist"] = 0.5
    df["supertrend_direction"] = 1.0
    signal = SwingTrendRiderStrategy().generate_signal(df)
    assert signal.signal_type == "BUY"
    assert signal.confidence >= 0.90


def test_swing_trend_rider_buy_4_of_5():
    from domains.strategies.strategies.swing_trend_rider import SwingTrendRiderStrategy
    df = _make_df()
    df["close"] = 110.0
    df["sma_50"] = 100.0
    df["rsi_14"] = 58.0
    df["adx_14"] = 28.0
    df["macd_hist"] = 0.5
    df["supertrend_direction"] = -1.0
    signal = SwingTrendRiderStrategy().generate_signal(df)
    assert signal.signal_type == "BUY"
    assert signal.confidence >= 0.80


def test_swing_trend_rider_none_only_3_conditions():
    from domains.strategies.strategies.swing_trend_rider import SwingTrendRiderStrategy
    df = _make_df()
    df["close"] = 110.0
    df["sma_50"] = 100.0
    df["rsi_14"] = 58.0
    df["adx_14"] = 15.0
    df["macd_hist"] = -0.1
    df["supertrend_direction"] = 1.0
    signal = SwingTrendRiderStrategy().generate_signal(df)
    assert signal.signal_type == "NONE"
