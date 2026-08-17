"""
Tests for Phase A market intelligence engines.

Covers:
- MarketRegimeEngine: classification logic, fallback, caching
- SupportResistanceEngine: swing pivots, static levels, clustering
- MultiTimeframeEngine: resampling, alignment scoring
- VolumeAnalysisEngine: divergence, breakout confirmation, spike detection
"""

import pytest
import pandas as pd
import numpy as np
from datetime import date, timedelta
from unittest.mock import MagicMock


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_df(n=200, trend="flat", base=100.0) -> pd.DataFrame:
    """Synthetic OHLCV DataFrame for testing."""
    dates   = [date(2022, 1, 1) + timedelta(days=i) for i in range(n)]
    closes  = []
    c = base
    for i in range(n):
        if trend == "up":
            c *= 1.002
        elif trend == "down":
            c *= 0.998
        elif trend == "spike":
            c = base * (1 + 0.5 * np.sin(i / 5))
        closes.append(c)
    closes = np.array(closes)
    highs   = closes * 1.01
    lows    = closes * 0.99
    opens   = closes * 0.999
    volumes = np.random.randint(100_000, 500_000, size=n).astype(float)
    return pd.DataFrame({
        "date":   dates,
        "open":   opens,
        "high":   highs,
        "low":    lows,
        "close":  closes,
        "volume": volumes,
    })


# ═══════════════════════════════════════════════════════════════════════════════
# MarketRegimeEngine
# ═══════════════════════════════════════════════════════════════════════════════

class TestMarketRegimeClassify:
    from domains.market.regime import MarketRegimeEngine
    engine = MarketRegimeEngine()

    def test_strong_bull(self):
        from domains.market.regime import MarketRegimeEngine
        regime, conf = MarketRegimeEngine()._classify(
            pct50=0.80, pct200=0.70, adv_dec=0.65, avg_atr=1.5
        )
        assert regime == "STRONG_BULL"
        assert conf > 0.75

    def test_bull(self):
        from domains.market.regime import MarketRegimeEngine
        regime, conf = MarketRegimeEngine()._classify(
            pct50=0.60, pct200=0.55, adv_dec=0.55, avg_atr=1.5
        )
        assert regime == "BULL"
        assert 0.55 <= conf <= 0.90

    def test_sideways(self):
        from domains.market.regime import MarketRegimeEngine
        regime, conf = MarketRegimeEngine()._classify(
            pct50=0.50, pct200=0.48, adv_dec=0.50, avg_atr=1.8
        )
        assert regime == "SIDEWAYS"

    def test_bear(self):
        from domains.market.regime import MarketRegimeEngine
        regime, conf = MarketRegimeEngine()._classify(
            pct50=0.35, pct200=0.38, adv_dec=0.40, avg_atr=2.0
        )
        assert regime == "BEAR"

    def test_strong_bear(self):
        from domains.market.regime import MarketRegimeEngine
        regime, conf = MarketRegimeEngine()._classify(
            pct50=0.20, pct200=0.22, adv_dec=0.30, avg_atr=2.5
        )
        assert regime == "STRONG_BEAR"
        assert conf > 0.70

    def test_high_volatility_overrides_bull(self):
        """Even if breadth is bullish, extreme ATR forces HIGH_VOLATILITY."""
        from domains.market.regime import MarketRegimeEngine
        regime, conf = MarketRegimeEngine()._classify(
            pct50=0.75, pct200=0.70, adv_dec=0.65, avg_atr=5.0
        )
        assert regime == "HIGH_VOLATILITY"

    def test_confidence_bounded_0_to_1(self):
        from domains.market.regime import MarketRegimeEngine
        engine = MarketRegimeEngine()
        for pct50 in [0.0, 0.25, 0.50, 0.75, 1.0]:
            for pct200 in [0.0, 0.50, 1.0]:
                for atr in [1.0, 4.0]:
                    _, conf = engine._classify(pct50, pct200, 0.5, atr)
                    assert 0.0 <= conf <= 1.0, f"conf={conf} out of bounds for pct50={pct50}"


# ═══════════════════════════════════════════════════════════════════════════════
# SupportResistanceEngine
# ═══════════════════════════════════════════════════════════════════════════════

class TestSupportResistanceEngine:
    from domains.market.support_resistance import SupportResistanceEngine
    engine = SupportResistanceEngine()

    def _make_sr_df(self) -> pd.DataFrame:
        """Price series with clear swing highs and lows."""
        # 120 bars with a wave pattern to create obvious pivots
        n = 120
        dates  = [date(2023, 1, 1) + timedelta(days=i) for i in range(n)]
        closes = 100.0 + 20 * np.sin(np.linspace(0, 4 * np.pi, n))
        highs  = closes + 2.0
        lows   = closes - 2.0
        opens  = closes - 0.5
        vols   = np.ones(n) * 200_000
        return pd.DataFrame({
            "date": dates, "open": opens, "high": highs,
            "low": lows, "close": closes, "volume": vols,
        })

    def test_has_support_and_resistance(self):
        from domains.market.support_resistance import SupportResistanceEngine
        engine = SupportResistanceEngine()
        df = self._make_sr_df()
        current_price = float(df["close"].iloc[-1])
        levels = engine._static_levels(df, current_price)
        levels += engine._sma_levels(df, current_price)
        supports    = [l for l in levels if l.level_type == "SUPPORT"]
        resistances = [l for l in levels if l.level_type == "RESISTANCE"]
        assert len(supports) > 0
        assert len(resistances) > 0

    def test_swing_high_detection(self):
        """Verify swing highs are detected in a wave-pattern series."""
        from domains.market.support_resistance import SupportResistanceEngine
        engine = SupportResistanceEngine()
        df = self._make_sr_df()
        current_price = float(df["close"].iloc[-1])
        levels = engine._swing_levels(df, current_price)
        swing_highs = [l for l in levels if l.level_source == "SWING_HIGH"]
        assert len(swing_highs) > 0, "Should detect at least one swing high in wave pattern"

    def test_clustering_removes_near_duplicates(self):
        """Two levels within CLUSTER_BAND_PCT% should merge into one."""
        from domains.market.support_resistance import SupportResistanceEngine, SRLevel
        engine = SupportResistanceEngine()
        levels = [
            SRLevel(price=100.0, level_type="RESISTANCE", level_source="SWING_HIGH",
                    strength=0.5, distance_pct=5.0),
            SRLevel(price=100.3, level_type="RESISTANCE", level_source="52W_HIGH",
                    strength=0.8, distance_pct=5.3),  # within 0.8% → should merge
        ]
        merged = engine._cluster(levels, 95.0)
        assert len(merged) == 1
        assert merged[0].strength == 0.8   # stronger one survives

    def test_insufficient_data_returns_empty(self):
        from domains.market.support_resistance import SupportResistanceEngine
        db_mock = MagicMock()
        db_mock.execute.return_value.fetchall.return_value = []  # no rows
        result = SupportResistanceEngine().compute(db_mock, "TEST")
        assert result.current_price == 0.0
        assert result.levels == []

    def test_distance_sign_convention(self):
        """Support must be below price (negative distance), resistance above (positive)."""
        from domains.market.support_resistance import SupportResistanceEngine
        engine = SupportResistanceEngine()
        df = self._make_sr_df()
        current_price = float(df["close"].iloc[-1])
        all_levels = engine._static_levels(df, current_price) + engine._sma_levels(df, current_price)
        for l in all_levels:
            if l.level_type == "SUPPORT":
                assert l.distance_pct < 0, f"{l.level_source} labelled SUPPORT but above price"
            else:
                assert l.distance_pct >= 0, f"{l.level_source} labelled RESISTANCE but below price"


# ═══════════════════════════════════════════════════════════════════════════════
# MultiTimeframeEngine
# ═══════════════════════════════════════════════════════════════════════════════

class TestMultiTimeframeEngine:

    def test_analyze_bullish_uptrend(self):
        """Strongly uptrending data should produce BULLISH timeframe view."""
        from domains.market.multi_timeframe import MultiTimeframeEngine, MIN_BARS_DAILY
        import pandas as pd
        engine = MultiTimeframeEngine()
        # Use 0.8%/day growth — strong enough to push RSI well above 52
        n      = 200
        dates  = [date(2022, 1, 1) + timedelta(days=i) for i in range(n)]
        closes = [100.0 * (1.008 ** i) for i in range(n)]
        df = pd.DataFrame({
            "date": dates, "open": [c * 0.999 for c in closes],
            "high": [c * 1.01 for c in closes], "low": [c * 0.99 for c in closes],
            "close": closes, "volume": [200_000.0] * n,
        })
        df = df.set_index(pd.to_datetime(df["date"])).drop(columns=["date"])
        view = engine._analyze(df, "DAILY", MIN_BARS_DAILY)
        assert view is not None
        assert view.trend == "BULLISH"
        assert view.ema_fast_above_slow is True

    def test_analyze_bearish_downtrend(self):
        """Downtrending data should produce BEARISH timeframe view."""
        from domains.market.multi_timeframe import MultiTimeframeEngine, MIN_BARS_DAILY
        engine = MultiTimeframeEngine()
        df = _make_df(n=200, trend="down")
        df = df.set_index(pd.to_datetime(df["date"])).drop(columns=["date"])
        view = engine._analyze(df, "DAILY", MIN_BARS_DAILY)
        assert view is not None
        assert view.trend == "BEARISH"

    def test_alignment_all_bullish(self):
        """Three bullish views should give STRONGLY_BULLISH label and score >= 0.80."""
        from domains.market.multi_timeframe import MultiTimeframeEngine, TimeframeView
        engine = MultiTimeframeEngine()
        bullish_view = lambda tf: TimeframeView(
            timeframe=tf, trend="BULLISH", ema20=110, ema50=105, last_close=115,
            ema_fast_above_slow=True, price_above_ema20=True,
            rsi=62.0, macd_bullish=True, bars_available=100,
        )
        score, label = engine._alignment_score([
            bullish_view("DAILY"), bullish_view("WEEKLY"), bullish_view("MONTHLY")
        ])
        assert label == "STRONGLY_BULLISH"
        assert score >= 0.80

    def test_alignment_all_bearish(self):
        from domains.market.multi_timeframe import MultiTimeframeEngine, TimeframeView
        engine = MultiTimeframeEngine()
        bearish_view = lambda tf: TimeframeView(
            timeframe=tf, trend="BEARISH", ema20=90, ema50=100, last_close=85,
            ema_fast_above_slow=False, price_above_ema20=False,
            rsi=38.0, macd_bullish=False, bars_available=100,
        )
        score, label = engine._alignment_score([
            bearish_view("DAILY"), bearish_view("WEEKLY"), bearish_view("MONTHLY")
        ])
        assert label == "STRONGLY_BEARISH"
        assert score <= 0.20

    def test_alignment_mixed(self):
        from domains.market.multi_timeframe import MultiTimeframeEngine, TimeframeView
        engine = MultiTimeframeEngine()
        views = [
            TimeframeView("DAILY",   "BULLISH", 110, 105, 115, True,  True,  62, True,  100),
            TimeframeView("WEEKLY",  "BEARISH", 90,  100, 85,  False, False, 38, False, 50),
            TimeframeView("MONTHLY", "NEUTRAL", 100, 100, 100, False, True,  50, False, 20),
        ]
        score, label = engine._alignment_score(views)
        assert label in ("MIXED", "BULLISH", "BEARISH")

    def test_resample_weekly_reduces_bars(self):
        """Weekly resampled data must have fewer bars than daily."""
        from domains.market.multi_timeframe import MultiTimeframeEngine
        engine = MultiTimeframeEngine()
        df = _make_df(n=200)
        df = df.set_index(pd.to_datetime(df["date"])).drop(columns=["date"])
        weekly = engine._resample(df, "W")
        assert len(weekly) < len(df)
        assert len(weekly) >= 20   # at least 20 weeks from 200 days

    def test_rsi_within_bounds(self):
        from domains.market.multi_timeframe import MultiTimeframeEngine
        engine = MultiTimeframeEngine()
        for trend in ["up", "down", "flat"]:
            df = _make_df(n=100, trend=trend)
            closes = df["close"]
            rsi = engine._rsi(closes)
            assert 0.0 <= rsi <= 100.0, f"RSI={rsi} out of bounds for trend={trend}"


# ═══════════════════════════════════════════════════════════════════════════════
# VolumeAnalysisEngine
# ═══════════════════════════════════════════════════════════════════════════════

class TestVolumeAnalysisEngine:

    def _df_with_spike(self, n=60) -> pd.DataFrame:
        df = _make_df(n=n, trend="up")
        df["volume_sma_20"] = df["volume"].rolling(20).mean()
        # Last bar: volume spike
        df.loc[df.index[-1], "volume"] = float(df["volume"].mean() * 4)
        return df

    def _df_with_bearish_divergence(self, n=60) -> pd.DataFrame:
        """Price going up but OBV going down."""
        df = _make_df(n=n, trend="up")
        # Simulate OBV falling while price rises (construct manually)
        return df

    def test_volume_spike_detected(self):
        from domains.market.volume_analysis import VolumeAnalysisEngine
        engine = VolumeAnalysisEngine()
        df = self._df_with_spike()
        result = engine.analyze(df)
        assert result.volume_spike is True

    def test_no_spike_on_normal_volume(self):
        from domains.market.volume_analysis import VolumeAnalysisEngine
        engine = VolumeAnalysisEngine()
        df = _make_df(n=60, trend="flat")
        df["volume_sma_20"] = df["volume"].rolling(20).mean()
        result = engine.analyze(df)
        assert result.volume_spike is False

    def test_breakout_confirmed_at_range_high_with_high_volume(self):
        from domains.market.volume_analysis import VolumeAnalysisEngine
        engine = VolumeAnalysisEngine()
        df = _make_df(n=60, trend="up")
        df["volume_sma_20"] = df["volume"].rolling(20).mean()
        # Force last bar to be at range high with 2× volume
        max_close = float(df["close"].max())
        df.loc[df.index[-1], "close"] = max_close
        df.loc[df.index[-1], "volume"] = float(df["volume_sma_20"].iloc[-1]) * 2.0
        result = engine.analyze(df)
        assert result.breakout_volume_confirmed is True

    def test_bearish_divergence(self):
        """Price up significantly but OBV falling → bearish divergence."""
        from domains.market.volume_analysis import VolumeAnalysisEngine
        engine = VolumeAnalysisEngine()
        n = 50
        closes = np.linspace(100, 120, n)   # price rising
        obv    = np.linspace(1_000_000, 800_000, n)  # OBV falling
        result_str = engine._detect_divergence(closes, obv)
        assert result_str == "BEARISH_DIVERGENCE"

    def test_bullish_divergence(self):
        """Price falling but OBV rising → bullish divergence (accumulation)."""
        from domains.market.volume_analysis import VolumeAnalysisEngine
        engine = VolumeAnalysisEngine()
        n = 50
        closes = np.linspace(120, 100, n)   # price falling
        obv    = np.linspace(800_000, 1_000_000, n)  # OBV rising
        result_str = engine._detect_divergence(closes, obv)
        assert result_str == "BULLISH_DIVERGENCE"

    def test_no_divergence_when_price_and_obv_aligned(self):
        from domains.market.volume_analysis import VolumeAnalysisEngine
        engine = VolumeAnalysisEngine()
        n = 50
        closes = np.linspace(100, 120, n)
        obv    = np.linspace(800_000, 1_000_000, n)  # both rising
        assert engine._detect_divergence(closes, obv) == "NONE"

    def test_empty_profile_on_insufficient_data(self):
        from domains.market.volume_analysis import VolumeAnalysisEngine
        engine = VolumeAnalysisEngine()
        df = _make_df(n=10)  # too few bars
        result = engine.analyze(df)
        assert result.volume_spike is False
        assert result.price_volume_divergence == "NONE"

    def test_obv_trend_rising(self):
        from domains.market.volume_analysis import VolumeAnalysisEngine
        engine = VolumeAnalysisEngine()
        # OBV steadily rising over 11 bars (>5% change)
        obv = np.linspace(1_000_000, 1_200_000, 11)
        trend = engine._trend_direction(obv, pct_threshold=5.0)
        assert trend == "RISING"

    def test_obv_trend_flat(self):
        from domains.market.volume_analysis import VolumeAnalysisEngine
        engine = VolumeAnalysisEngine()
        obv = np.ones(11) * 1_000_000
        trend = engine._trend_direction(obv, pct_threshold=5.0)
        assert trend == "FLAT"
