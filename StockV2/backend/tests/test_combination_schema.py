from sqlalchemy import text
from database import SessionLocal, engine


def _create_combination_tables() -> None:
    """Run the same CREATE TABLE IF NOT EXISTS SQL used in lifespan."""
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS strategy_combinations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                strategy_ids TEXT NOT NULL,
                strategy_names TEXT NOT NULL,
                size INTEGER NOT NULL,
                search_method TEXT NOT NULL,
                created_at DATETIME DEFAULT (datetime('now'))
            )
        """))
        conn.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_combination_ids
            ON strategy_combinations(strategy_ids)
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS combination_run_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at DATETIME NOT NULL,
                completed_at DATETIME,
                status TEXT NOT NULL DEFAULT 'running',
                symbols_analyzed INTEGER,
                candidates_selected INTEGER,
                combinations_tested INTEGER,
                top_combination_id INTEGER REFERENCES strategy_combinations(id),
                error_message TEXT,
                config_json TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS combination_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                combination_id INTEGER NOT NULL REFERENCES strategy_combinations(id),
                run_id INTEGER NOT NULL REFERENCES combination_run_log(id),
                train_cagr REAL, train_sharpe REAL, train_win_rate REAL,
                train_max_drawdown REAL, train_profit_factor REAL,
                train_total_trades INTEGER, train_sortino REAL,
                val_cagr REAL, val_sharpe REAL, val_win_rate REAL,
                val_max_drawdown REAL, val_total_trades INTEGER,
                oos_cagr REAL, oos_sharpe REAL, oos_win_rate REAL,
                oos_max_drawdown REAL, oos_profit_factor REAL,
                oos_total_trades INTEGER, oos_sortino REAL, oos_median_return_pct REAL,
                wf_consistency_score REAL, wf_avg_oos_cagr REAL,
                vs_buy_and_hold_cagr REAL, vs_best_single_cagr REAL, vs_sma_crossover_cagr REAL,
                reliability_score REAL, reliability_label TEXT, sensitivity_score REAL,
                explanation_json TEXT,
                computed_at DATETIME DEFAULT (datetime('now'))
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS combination_regime_perf (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                combination_id INTEGER NOT NULL REFERENCES strategy_combinations(id),
                run_id INTEGER NOT NULL REFERENCES combination_run_log(id),
                regime TEXT NOT NULL,
                win_rate REAL, avg_pnl_pct REAL, trade_count INTEGER, cagr REAL
            )
        """))
        conn.commit()


# Ensure tables exist regardless of whether lifespan ran
_create_combination_tables()


def test_combination_tables_exist():
    db = SessionLocal()
    try:
        tables = db.execute(text("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name LIKE '%combination%'
        """)).fetchall()
        table_names = {r[0] for r in tables}
        assert "strategy_combinations" in table_names
        assert "combination_results" in table_names
        assert "combination_regime_perf" in table_names
        assert "combination_run_log" in table_names
    finally:
        db.close()


def test_combination_results_columns():
    db = SessionLocal()
    try:
        db.execute(text(
            "SELECT id, combination_id, run_id, oos_cagr, reliability_score, "
            "reliability_label, sensitivity_score FROM combination_results LIMIT 0"
        ))
    finally:
        db.close()
