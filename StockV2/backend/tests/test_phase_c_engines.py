"""
Unit tests for Phase C intelligence engines.

Covers:
  - FalseSignalDetector  (outcome tracking, false rate computation)
  - StrategyCorrelationEngine (pairwise overlap matrix)
  - RiskGuard (position checks)
  - OpportunityScorer false_signal_rate multiplier
"""

import sys
import os
from datetime import date, timedelta

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ─── helpers ──────────────────────────────────────────────────────────────────

def _make_db(with_strategies: bool = False, with_prices: bool = False):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from database import Base
    import models
    from sqlalchemy import text

    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=eng)
    db = Session(bind=eng)

    if with_strategies:
        for sid, name in [(1, "StratA"), (2, "StratB"), (3, "StratC")]:
            db.execute(text(
                "INSERT INTO strategies (id, name, type, is_active, created_at) "
                f"VALUES ({sid}, '{name}', 'technical', 1, CURRENT_TIMESTAMP)"
            ))
        db.commit()

    if with_prices:
        rows = []
        base = date(2024, 1, 1)
        for i in range(100):
            d = base + timedelta(days=i)
            rows.append({"sym": "RELIANCE", "d": str(d), "c": 100.0 + i * 0.5})
        db.execute(text(
            "INSERT INTO stock_prices_daily (symbol, date, open, high, low, close, volume, data_source) "
            "VALUES (:sym, :d, :c, :c, :c, :c, 100000, 'yfinance')"
        ), rows)
        db.commit()

    return db


# ── FalseSignalDetector ───────────────────────────────────────────────────────

class TestFalseSignalDetector:
    def _engine(self):
        from domains.intelligence.false_signal_detector import FalseSignalDetector
        return FalseSignalDetector()

    def test_compute_outcomes_empty_returns_zero(self):
        db = _make_db()
        n = self._engine().compute_outcomes(db)
        assert n == 0

    def test_get_false_signal_rates_empty_returns_empty(self):
        db = _make_db()
        rates = self._engine().get_false_signal_rates(db)
        assert rates == {}

    def test_get_rate_for_strategy_none_when_no_data(self):
        db = _make_db()
        rate = self._engine().get_rate_for_strategy(db, 1)
        assert rate is None

    def _insert_outcomes(self, db, strategy_id: int, n_profitable: int, n_false: int):
        from sqlalchemy import text
        # Insert dummy strategy if not present
        db.execute(text(
            f"INSERT OR IGNORE INTO strategies (id, name, type, is_active, created_at) "
            f"VALUES ({strategy_id}, 'Strat{strategy_id}', 'technical', 1, CURRENT_TIMESTAMP)"
        ))
        base = date(2024, 1, 1)
        rows = []
        for i in range(n_profitable + n_false):
            sig_date = base + timedelta(days=i)
            is_prof = 1 if i < n_profitable else 0
            rows.append({
                "sid": i + 100 + strategy_id * 1000,
                "sym": "RELIANCE",
                "strat": strategy_id,
                "sdate": str(sig_date),
                "price": 100.0,
                "oprice": 110.0 if is_prof else 90.0,
                "odate": str(sig_date + timedelta(days=15)),
                "pnl": 10.0 if is_prof else -10.0,
                "prof": is_prof,
                "hdays": 15,
            })
        db.execute(text("""
            INSERT INTO signal_outcomes
            (signal_id, symbol, strategy_id, signal_date, signal_type,
             price_at_signal, outcome_price, outcome_date, pnl_pct,
             is_profitable, holding_days_actual, computed_at)
            VALUES (:sid, :sym, :strat, :sdate, 'BUY',
                    :price, :oprice, :odate, :pnl, :prof, :hdays, CURRENT_TIMESTAMP)
        """), rows)
        db.commit()

    def test_false_signal_rate_50_percent(self):
        db = _make_db()
        self._insert_outcomes(db, strategy_id=1, n_profitable=10, n_false=10)
        rate = self._engine().get_rate_for_strategy(db, 1)
        assert rate is not None
        assert abs(rate - 0.50) < 0.01

    def test_false_signal_rate_zero_when_all_profitable(self):
        db = _make_db()
        self._insert_outcomes(db, strategy_id=2, n_profitable=10, n_false=0)
        rate = self._engine().get_rate_for_strategy(db, 2)
        assert rate == 0.0

    def test_false_signal_rate_one_when_all_false(self):
        db = _make_db()
        self._insert_outcomes(db, strategy_id=3, n_profitable=0, n_false=10)
        rate = self._engine().get_rate_for_strategy(db, 3)
        assert rate == 1.0

    def test_below_min_signals_threshold_not_reported(self):
        """Strategies with < MIN_SIGNALS outcomes are excluded from get_false_signal_rates."""
        from domains.intelligence.false_signal_detector import MIN_SIGNALS
        db = _make_db()
        # Insert fewer outcomes than MIN_SIGNALS
        self._insert_outcomes(db, strategy_id=4, n_profitable=MIN_SIGNALS - 1, n_false=0)
        rate = self._engine().get_rate_for_strategy(db, 4)
        assert rate is None

    def test_get_stats_returns_list(self):
        db = _make_db()
        self._insert_outcomes(db, strategy_id=5, n_profitable=8, n_false=4)
        stats = self._engine().get_stats(db)
        assert isinstance(stats, list)
        if stats:
            s = stats[0]
            assert "strategy_id" in s
            assert "win_rate" in s
            assert "false_signal_rate" in s


# ── StrategyCorrelationEngine ─────────────────────────────────────────────────

class TestStrategyCorrelationEngine:
    def _engine(self):
        from domains.intelligence.strategy_correlation import StrategyCorrelationEngine
        return StrategyCorrelationEngine()

    def _make_db_with_signals(self):
        db = _make_db(with_strategies=True)
        from sqlalchemy import text
        base = date(2024, 1, 2)
        rows = []
        # Strategy 1 and 2 fire together on the same 25 stocks → high correlation
        # Strategy 3 fires on different stocks → low correlation with 1 and 2
        for i in range(25):
            sym = f"SYM{i:03d}"
            rows.append({"strat": 1, "sym": sym, "d": str(base + timedelta(days=i))})
            rows.append({"strat": 2, "sym": sym, "d": str(base + timedelta(days=i))})
            # Strategy 3 fires on different symbols
            rows.append({"strat": 3, "sym": f"OTH{i:03d}", "d": str(base + timedelta(days=i))})
        db.execute(text("""
            INSERT INTO strategy_signals (symbol, strategy_id, signal_date, signal_type, created_at)
            VALUES (:sym, :strat, :d, 'BUY', CURRENT_TIMESTAMP)
        """), rows)
        db.commit()
        return db

    def test_compute_returns_pairs(self):
        db = self._make_db_with_signals()
        pairs = self._engine().compute(db)
        assert len(pairs) > 0

    def test_high_correlation_between_overlapping_strategies(self):
        db = self._make_db_with_signals()
        pairs = self._engine().compute(db)
        # Strategies 1 and 2 fire on all 25 same stocks → correlation = 1.0
        pair_12 = next((p for p in pairs if {p.strategy_id_a, p.strategy_id_b} == {1, 2}), None)
        assert pair_12 is not None
        assert pair_12.correlation == 1.0
        assert pair_12.shared_signals == 25

    def test_no_correlation_between_non_overlapping_strategies(self):
        db = self._make_db_with_signals()
        pairs = self._engine().compute(db)
        # Strategies 1 and 3 never fire on the same symbol
        pair_13 = next((p for p in pairs if {p.strategy_id_a, p.strategy_id_b} == {1, 3}), None)
        if pair_13:
            assert pair_13.correlation == 0.0
        else:
            # No overlap at all → not included in pairs (COUNT(*) = 0)
            pass  # OK either way

    def test_save_and_get_matrix(self):
        db = self._make_db_with_signals()
        engine = self._engine()
        pairs = engine.compute(db)
        engine.save(db, pairs)
        matrix = engine.get_matrix(db)
        assert isinstance(matrix, list)
        assert len(matrix) == len(pairs)
        if matrix:
            assert "correlation" in matrix[0]
            assert "strategy_name_a" in matrix[0]

    def test_get_correlation_returns_stored_value(self):
        db = self._make_db_with_signals()
        engine = self._engine()
        pairs = engine.compute(db)
        engine.save(db, pairs)
        corr = engine.get_correlation(db, 1, 2)
        assert corr == 1.0

    def test_get_correlation_returns_zero_when_not_stored(self):
        db = _make_db()
        assert self._engine().get_correlation(db, 99, 100) == 0.0


# ── RiskGuard ─────────────────────────────────────────────────────────────────

class TestRiskGuard:
    def _guard(self):
        from domains.portfolio.risk_guard import RiskGuard
        return RiskGuard()

    def test_allowed_on_empty_portfolio(self):
        db = _make_db()
        result = self._guard().check_entry(db, symbol="RELIANCE")
        assert result.allowed is True

    def test_blocked_when_score_below_threshold(self):
        from domains.portfolio.risk_guard import MIN_OPPORTUNITY_SCORE
        db = _make_db()
        result = self._guard().check_entry(db, symbol="RELIANCE", opportunity_score=MIN_OPPORTUNITY_SCORE - 1)
        assert result.allowed is False
        assert any(c.name == "opportunity_score" for c in result.blockers())

    def test_allowed_when_score_at_threshold(self):
        from domains.portfolio.risk_guard import MIN_OPPORTUNITY_SCORE
        db = _make_db()
        result = self._guard().check_entry(db, symbol="RELIANCE", opportunity_score=MIN_OPPORTUNITY_SCORE)
        assert result.allowed is True

    def test_blocked_when_max_positions_reached(self):
        from domains.portfolio.risk_guard import MAX_POSITIONS
        db = _make_db()
        from sqlalchemy import text
        for i in range(MAX_POSITIONS):
            db.execute(text(
                f"INSERT INTO portfolio_holdings (symbol, quantity, avg_buy_price, "
                f"first_buy_date, last_buy_date, is_active) "
                f"VALUES ('SYM{i:03d}', 10, 100.0, '2024-01-01', '2024-01-01', 1)"
            ))
        db.commit()
        result = self._guard().check_entry(db, symbol="RELIANCE")
        assert result.allowed is False
        assert any(c.name == "max_positions" for c in result.blockers())

    def test_sector_concentration_is_advisory_not_blocking(self):
        from domains.portfolio.risk_guard import MAX_SECTOR_PCT
        db = _make_db()
        from sqlalchemy import text
        # Add stock with sector
        db.execute(text(
            "INSERT OR IGNORE INTO stocks (symbol, name, sector, exchange) "
            "VALUES ('RELIANCE', 'Reliance Industries', 'Energy', 'NSE')"
        ))
        # Fill portfolio with Energy stocks beyond MAX_SECTOR_PCT
        for i in range(5):
            sym = f"ENRG{i:03d}"
            db.execute(text(
                f"INSERT OR IGNORE INTO stocks (symbol, name, sector, exchange) "
                f"VALUES ('{sym}', 'Energy {i}', 'Energy', 'NSE')"
            ))
            db.execute(text(
                f"INSERT INTO portfolio_holdings (symbol, quantity, avg_buy_price, "
                f"first_buy_date, last_buy_date, is_active) "
                f"VALUES ('{sym}', 10, 100.0, '2024-01-01', '2024-01-01', 1)"
            ))
        db.commit()
        result = self._guard().check_entry(db, symbol="RELIANCE")
        # Sector check failing is advisory — overall entry may still be allowed
        sector_check = next((c for c in result.checks if c.name == "sector_concentration"), None)
        if sector_check and not sector_check.passed:
            assert sector_check.blocking is False

    def test_all_checks_present_in_result(self):
        db = _make_db()
        result = self._guard().check_entry(db, symbol="RELIANCE", strategy_id=1, opportunity_score=50)
        check_names = {c.name for c in result.checks}
        assert "max_positions" in check_names
        assert "opportunity_score" in check_names


# ── OpportunityScorer false_signal_rate multiplier ────────────────────────────

class TestOpportunityScorerFalseSignalPenalty:
    def _scorer(self):
        from domains.intelligence.opportunity_scorer import OpportunityScorer
        return OpportunityScorer()

    def test_no_penalty_when_false_rate_low(self):
        base = self._scorer().full_score(
            "X", 1, 1.0, 1.0, "STRONG_BULL", 1.0, 1.0, 1.0, 1.0, false_signal_rate=0.30
        )
        assert base.score == 100   # no penalty

    def test_moderate_penalty_when_false_rate_above_50(self):
        high = self._scorer().full_score(
            "X", 1, 1.0, 1.0, "STRONG_BULL", 1.0, 1.0, 1.0, 1.0, false_signal_rate=None
        )
        penalised = self._scorer().full_score(
            "X", 1, 1.0, 1.0, "STRONG_BULL", 1.0, 1.0, 1.0, 1.0, false_signal_rate=0.60
        )
        assert penalised.score < high.score
        assert penalised.score == round(high.score * 0.80)

    def test_heavy_penalty_when_false_rate_above_70(self):
        high = self._scorer().full_score(
            "X", 1, 1.0, 1.0, "STRONG_BULL", 1.0, 1.0, 1.0, 1.0, false_signal_rate=None
        )
        penalised = self._scorer().full_score(
            "X", 1, 1.0, 1.0, "STRONG_BULL", 1.0, 1.0, 1.0, 1.0, false_signal_rate=0.80
        )
        assert penalised.score == round(high.score * 0.60)

    def test_false_signal_rate_in_breakdown(self):
        opp = self._scorer().full_score(
            "X", 1, 0.5, 0.5, "BULL", 0.5, 0.5, 0.5, 0.5, false_signal_rate=0.65
        )
        assert "false_signal_rate" in opp.breakdown
        assert opp.breakdown["false_signal_rate"] == 0.65
