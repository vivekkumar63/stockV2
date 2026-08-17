"""
Unit tests for Phase B intelligence engines.

Tests are pure Python — no database required.
MarketRegimeEngine.compute_bulk() is tested with an in-memory SQLite database.
"""

import sys
import os
from datetime import date, timedelta

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ── OpportunityScorer ─────────────────────────────────────────────────────────

class TestOpportunityScorer:
    from domains.intelligence.opportunity_scorer import OpportunityScorer

    def _scorer(self):
        from domains.intelligence.opportunity_scorer import OpportunityScorer
        return OpportunityScorer()

    def test_full_bullish_all_components(self):
        opp = self._scorer().full_score(
            symbol="RELIANCE",
            strategy_id=1,
            confidence=1.0,
            historical_win_rate=1.0,
            regime="STRONG_BULL",
            regime_strategy_win_rate=1.0,
            mtf_alignment=1.0,
            volume_score=1.0,
            sr_score=1.0,
        )
        assert opp.score == 100
        assert opp.grade == "A+"

    def test_full_bearish_all_components(self):
        opp = self._scorer().full_score(
            symbol="RELIANCE",
            strategy_id=1,
            confidence=0.0,
            historical_win_rate=0.0,
            regime="STRONG_BEAR",
            regime_strategy_win_rate=0.0,
            mtf_alignment=0.0,
            volume_score=0.0,
            sr_score=0.0,
        )
        assert opp.score == 0
        assert opp.grade == "D"

    def test_quick_score_no_win_rate(self):
        """Missing win rate → component omitted, score normalised from remaining components."""
        opp = self._scorer().quick_score(
            symbol="TCS",
            strategy_id=2,
            confidence=1.0,
            historical_win_rate=None,
            regime="STRONG_BULL",  # STRONG_BULL = 1.0, so both active components = 1.0
            regime_strategy_win_rate=None,
        )
        # Only confidence (20) and regime_alignment (18) contribute; both = 1.0 → 100
        assert opp.score == 100
        assert opp.strategy_id == 2

    def test_partial_components_normalise_correctly(self):
        """Score is normalised by available weight, not total weight."""
        opp = self._scorer().quick_score(
            symbol="INFY",
            strategy_id=3,
            confidence=0.5,
            historical_win_rate=0.5,
            regime="SIDEWAYS",
            regime_strategy_win_rate=0.5,
        )
        # All provided values = 0.5 → raw = 0.5 → score = 50
        assert opp.score == 50
        assert opp.grade == "B"

    def test_regime_alignment_values(self):
        from domains.intelligence.opportunity_scorer import _REGIME_BUY_SCORE
        assert _REGIME_BUY_SCORE["STRONG_BULL"] == 1.00
        assert _REGIME_BUY_SCORE["STRONG_BEAR"] == 0.00
        assert _REGIME_BUY_SCORE["SIDEWAYS"] == 0.50

    def test_grade_boundaries(self):
        scorer = self._scorer()

        def _score_with_raw(raw: float):
            import math
            return round(raw * 100)

        assert scorer._compute("X", 1, {"strategy_confidence": 0.80}).grade == "A+"
        assert scorer._compute("X", 1, {"strategy_confidence": 0.65}).grade == "A"
        assert scorer._compute("X", 1, {"strategy_confidence": 0.50}).grade == "B"
        assert scorer._compute("X", 1, {"strategy_confidence": 0.35}).grade == "C"
        assert scorer._compute("X", 1, {"strategy_confidence": 0.20}).grade == "D"

    def test_clamps_values_to_0_1(self):
        opp = self._scorer().quick_score(
            symbol="X",
            strategy_id=1,
            confidence=2.0,   # >1 — should be clamped
            historical_win_rate=1.5,  # >1 — should be clamped
            regime="STRONG_BULL",
            regime_strategy_win_rate=-0.1,  # <0 — should be clamped
        )
        # All clamped to 1.0 / 1.0 / 1.0 / 0.0 → weighted
        # STRONG_BULL regime = 1.0
        # hist_wr = 1.0 (clamped from 1.5) × 25 = 25
        # confidence = 1.0 (clamped from 2.0) × 20 = 20
        # regime_alignment = 1.0 × 18 = 18
        # regime_strategy = 0.0 (clamped from -0.1) × 4 = 0
        # total_weight = 67, weighted_sum = 63 → 63/67 ≈ 0.94 → 94
        assert opp.score >= 90

    def test_empty_parts_returns_neutral(self):
        opp = self._scorer()._compute("X", None, {})
        assert opp.score == 50
        assert opp.grade == "B"


# ── RegimePerformanceEngine ───────────────────────────────────────────────────

class TestRegimePerformanceEngine:
    def _engine(self):
        from domains.intelligence.regime_performance import RegimePerformanceEngine
        return RegimePerformanceEngine()

    def _make_db(self):
        """In-memory SQLite DB with the tables needed for regime performance."""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session
        from database import Base
        import models  # ensure all models are registered

        eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=eng)
        return Session(bind=eng)

    def test_compute_all_empty_tables_returns_empty(self):
        db = self._make_db()
        result = self._engine().compute_all(db)
        assert result == []

    def test_get_for_regime_empty_returns_empty(self):
        db = self._make_db()
        result = self._engine().get_for_regime(db, "BULL")
        assert result == {}

    def test_save_and_retrieve(self):
        from domains.intelligence.regime_performance import RegimePerf
        db = self._make_db()
        engine = self._engine()

        perfs = [
            RegimePerf(strategy_id=1, regime="BULL", total_trades=20, win_rate=0.65, avg_pnl_pct=3.2),
            RegimePerf(strategy_id=1, regime="BEAR", total_trades=10, win_rate=0.30, avg_pnl_pct=-1.5),
            RegimePerf(strategy_id=2, regime="BULL", total_trades=15, win_rate=0.55, avg_pnl_pct=2.0),
        ]
        engine.save(db, perfs)

        bull_map = engine.get_for_regime(db, "BULL")
        assert 1 in bull_map
        assert 2 in bull_map
        assert abs(bull_map[1].win_rate - 0.65) < 0.001
        assert bull_map[1].total_trades == 20

        bear_map = engine.get_for_regime(db, "BEAR")
        assert 1 in bear_map
        assert 2 not in bear_map
        assert abs(bear_map[1].win_rate - 0.30) < 0.001

    def test_upsert_replaces_existing(self):
        from domains.intelligence.regime_performance import RegimePerf
        db = self._make_db()
        engine = self._engine()

        engine.save(db, [RegimePerf(strategy_id=1, regime="BULL", total_trades=10, win_rate=0.50, avg_pnl_pct=1.0)])
        engine.save(db, [RegimePerf(strategy_id=1, regime="BULL", total_trades=20, win_rate=0.70, avg_pnl_pct=2.0)])

        result = engine.get_for_regime(db, "BULL")
        assert result[1].win_rate == 0.70
        assert result[1].total_trades == 20


# ── StrategySelectionEngine ───────────────────────────────────────────────────

class TestStrategySelectionEngine:
    def _make_db_with_strategies(self):
        """In-memory DB with strategies and regime performance data."""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session
        from database import Base
        import models
        from sqlalchemy import text

        eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=eng)
        db = Session(bind=eng)

        db.execute(text("INSERT INTO strategies (id, name, type, is_active, created_at) VALUES (1, 'StratA', 'technical', 1, CURRENT_TIMESTAMP)"))
        db.execute(text("INSERT INTO strategies (id, name, type, is_active, created_at) VALUES (2, 'StratB', 'technical', 1, CURRENT_TIMESTAMP)"))
        db.execute(text("INSERT INTO strategies (id, name, type, is_active, created_at) VALUES (3, 'StratC', 'technical', 1, CURRENT_TIMESTAMP)"))
        db.execute(text("""
            INSERT INTO strategy_regime_performance (strategy_id, regime, total_trades, win_rate, avg_pnl_pct, computed_at)
            VALUES (1, 'BULL', 30, 0.70, 3.0, CURRENT_TIMESTAMP),
                   (2, 'BULL', 20, 0.55, 1.5, CURRENT_TIMESTAMP),
                   (3, 'BULL', 10, 0.40, 0.5, CURRENT_TIMESTAMP)
        """))
        db.commit()
        return db

    def test_rank_for_regime_order(self):
        from domains.intelligence.strategy_selector import StrategySelectionEngine
        db = self._make_db_with_strategies()
        ranks = StrategySelectionEngine().rank_for_regime(db, "BULL")
        assert len(ranks) == 3
        assert ranks[0].strategy_name == "StratA"
        assert ranks[0].rank == 1
        assert ranks[1].strategy_name == "StratB"
        assert ranks[2].strategy_name == "StratC"

    def test_rank_returns_regime_win_rate(self):
        from domains.intelligence.strategy_selector import StrategySelectionEngine
        db = self._make_db_with_strategies()
        ranks = StrategySelectionEngine().rank_for_regime(db, "BULL")
        assert abs(ranks[0].regime_win_rate - 0.70) < 0.001
        assert ranks[0].regime_total_trades == 30

    def test_rank_no_regime_data_returns_all_strategies(self):
        """Strategies with no regime data should still appear in the ranking."""
        from domains.intelligence.strategy_selector import StrategySelectionEngine
        db = self._make_db_with_strategies()
        ranks = StrategySelectionEngine().rank_for_regime(db, "STRONG_BEAR")
        assert len(ranks) == 3
        for r in ranks:
            assert r.regime_win_rate is None


# ── MarketRegimeEngine.compute_bulk ──────────────────────────────────────────

class TestMarketRegimeEngineBulk:
    def _make_db_with_prices(self, num_symbols: int = 80, num_days: int = 400):
        """In-memory DB filled with synthetic price data."""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session
        from database import Base
        import models
        from sqlalchemy import text

        eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=eng)
        db = Session(bind=eng)

        base = date(2023, 1, 1)
        rows = []
        for sym_idx in range(num_symbols):
            sym = f"SYM{sym_idx:03d}"
            for day_idx in range(num_days):
                d = base + timedelta(days=day_idx)
                close = 100.0 * (1.001 ** day_idx)   # steady uptrend
                rows.append({
                    "sym": sym, "d": str(d),
                    "o": close, "h": close + 1, "l": close - 1, "c": close,
                    "v": 100000,
                })

        db.execute(
            text("""
                INSERT INTO stock_prices_daily
                (symbol, date, open, high, low, close, volume, data_source)
                VALUES (:sym, :d, :o, :h, :l, :c, :v, 'yfinance')
            """),
            rows,
        )
        db.commit()
        return db

    def test_compute_bulk_returns_dates_in_range(self):
        from domains.market.regime import MarketRegimeEngine
        db = self._make_db_with_prices()

        start = date(2023, 8, 1)
        end   = date(2023, 9, 30)
        results = MarketRegimeEngine().compute_bulk(db, start, end)

        assert len(results) > 0
        for d in results:
            assert start <= d <= end

    def test_compute_bulk_steady_uptrend_is_bullish(self):
        from domains.market.regime import MarketRegimeEngine
        db = self._make_db_with_prices()

        start = date(2023, 10, 1)
        end   = date(2023, 10, 31)
        results = MarketRegimeEngine().compute_bulk(db, start, end)

        # All stocks in steady uptrend → most/all should be BULL or STRONG_BULL
        for r in results.values():
            assert r.regime in ("BULL", "STRONG_BULL", "SIDEWAYS")
            assert r.pct_above_sma50 >= 0.5

    def test_save_bulk_inserts_and_skips_existing(self):
        from domains.market.regime import MarketRegimeEngine
        db = self._make_db_with_prices()
        engine = MarketRegimeEngine()

        start = date(2023, 10, 1)
        end   = date(2023, 10, 15)

        results = engine.compute_bulk(db, start, end)
        first_run = engine.save_bulk(db, results)
        assert first_run > 0

        second_run = engine.save_bulk(db, results)
        assert second_run == 0   # all already present

    def test_compute_bulk_empty_db_returns_empty(self):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session
        from database import Base
        import models

        eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=eng)
        db = Session(bind=eng)

        from domains.market.regime import MarketRegimeEngine
        results = MarketRegimeEngine().compute_bulk(db, date(2020, 1, 1), date(2020, 12, 31))
        assert results == {}
