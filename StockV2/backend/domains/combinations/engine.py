# backend/domains/combinations/engine.py
import json
import logging
import statistics
from dataclasses import dataclass, asdict, field
from datetime import date
from itertools import combinations as iter_combinations
from typing import Optional

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from domains.combinations.filter import StrategyFilter, FilterConfig
from domains.combinations.search import ComboSearch, SearchConfig
from domains.combinations.metrics import compute_extended_metrics, ExtendedMetrics
from domains.combinations.reliability import ReliabilityScorer, ReliabilityResult
from domains.combinations.sensitivity import SensitivityAnalyzer
from domains.combinations.explanations import ExplanationGenerator
from domains.backtest.simulator import BacktestSimulator
from domains.data.indicators import IndicatorEngine
from ist import ist_now

logger = logging.getLogger(__name__)


@dataclass
class EngineConfig:
    filter: FilterConfig = field(default_factory=FilterConfig)
    search: SearchConfig = field(default_factory=SearchConfig)
    symbols_limit: int = 200
    initial_capital: float = 500_000.0
    round_trip_cost_pct: float = 0.30
    train_ratio: float = 0.60
    val_ratio: float = 0.20
    sensitivity_top_n: int = 30
    explanation_top_n: int = 20


class CombinationEngine:
    def __init__(self, db: Session, config: EngineConfig | None = None):
        self.db = db
        self.config = config if config is not None else EngineConfig()
        self.scorer = ReliabilityScorer()
        self.sensitivity_analyzer = SensitivityAnalyzer()
        self.explainer = ExplanationGenerator()

    def run_full_analysis(self) -> int:
        """Run the complete pipeline. Returns run_id."""
        run_id = self._create_run_log()

        try:
            # Step 2: Filter candidates
            logger.info("[engine] Step 2: Filtering candidates")
            filter_result = StrategyFilter(self.db, self.config.filter).select_candidates()
            candidates = filter_result["overall"]
            logger.info("[engine] %d candidates selected, %d disqualified",
                        len(candidates), len(filter_result["disqualified"]))

            if len(candidates) < 2:
                self._fail_run(run_id, "Insufficient candidates after filtering")
                return run_id

            # Step 3: Generate combinations
            logger.info("[engine] Step 3: Generating combinations")
            combos = ComboSearch(candidates, self.config.search).generate_combinations()
            logger.info("[engine] %d combinations to evaluate", len(combos))

            # Step 4: Load price data for symbols
            logger.info("[engine] Step 4: Loading price data")
            symbols_data = self._load_symbols_data()
            if not symbols_data:
                self._fail_run(run_id, "No price data available")
                return run_id

            # Steps 5-6: Backtest + extended metrics per combo
            logger.info("[engine] Steps 5-6: Backtesting combinations")
            combo_results: list[dict] = []
            for idx, combo in enumerate(combos):
                if idx % max(1, len(combos) // 10) == 0:
                    logger.info("[engine] Progress: %d/%d combinations", idx, len(combos))
                result = self._evaluate_combo(combo, symbols_data, run_id)
                if result:
                    combo_results.append(result)

            if not combo_results:
                self._fail_run(run_id, "No combination results produced")
                return run_id

            # Step 7: Pass 1 reliability scoring
            logger.info("[engine] Step 7: Scoring reliability (Pass 1)")
            scored = []
            for cr in combo_results:
                r = self.scorer.score(
                    cr["train_metrics"], cr["val_metrics"], cr["oos_metrics"],
                    wf_consistency=cr["wf_consistency"]
                )
                cr["reliability_result"] = r
                scored.append(cr)

            # Step 8: Select top-N by reliability score
            scored.sort(key=lambda x: x["reliability_result"].score, reverse=True)
            top_n = scored[:self.config.sensitivity_top_n]

            # Step 9: Sensitivity analysis on top-N only
            logger.info("[engine] Step 9: Sensitivity analysis on top %d", len(top_n))
            for cr in top_n:
                sens_score = self.sensitivity_analyzer.test(
                    cr["combination"], symbols_data,
                    cr["oos_from"], cr["oos_to"]
                )
                cr["sensitivity_score"] = sens_score

            # Step 10: Apply sensitivity cap (Pass 2)
            logger.info("[engine] Step 10: Applying sensitivity cap (Pass 2)")
            for cr in top_n:
                cr["reliability_result"] = self.scorer.apply_sensitivity_cap(
                    cr["reliability_result"], cr.get("sensitivity_score", 50.0)
                )

            # Step 11: Generate explanations for top-explanation_top_n
            logger.info("[engine] Step 11: Generating explanations")
            corr_matrix = self._load_correlation_matrix()
            for cr in scored[:self.config.explanation_top_n]:
                explanation = self.explainer.explain(
                    cr["combination"], _RegimeAdapter(cr["oos_metrics"], cr.get("wf_consistency", 0.0)),
                    corr_matrix
                )
                cr["explanation"] = explanation

            # Step 12: Persist to DB
            logger.info("[engine] Step 12: Persisting results")
            top_combination_id = self._persist_results(scored, run_id)
            self._complete_run(run_id, len(symbols_data), len(candidates), len(combos), top_combination_id)
            logger.info("[engine] Analysis complete: run_id=%d", run_id)

        except Exception as e:
            logger.exception("[engine] Analysis failed")
            self._fail_run(run_id, str(e))

        return run_id

    def _evaluate_combo(self, combination: list, symbols_data: dict, run_id: int) -> Optional[dict]:
        """Run backtests for train/val/oos periods and walk-forward for a single combination."""
        all_train, all_val, all_oos = [], [], []
        train_from_date = val_from_date = oos_from_date = None
        train_to_date = val_to_date = oos_to_date = None

        simulator = BacktestSimulator()

        for symbol, prices_df in symbols_data.items():
            if len(prices_df) < 50:
                continue
            dates = prices_df["date"].values
            n = len(dates)
            train_end_idx = int(n * self.config.train_ratio)
            val_end_idx = int(n * (self.config.train_ratio + self.config.val_ratio))

            t_from = dates[0]
            t_to = dates[train_end_idx - 1]
            v_from = dates[train_end_idx]
            v_to = dates[val_end_idx - 1]
            o_from = dates[val_end_idx]
            o_to = dates[-1]

            if train_from_date is None:
                train_from_date, train_to_date = t_from, t_to
                val_from_date, val_to_date = v_from, v_to
                oos_from_date, oos_to_date = o_from, o_to

            try:
                df_ind = IndicatorEngine.compute(prices_df)
                train_trades = simulator.run(
                    symbol, prices_df, t_from, t_to, combination,
                    initial_capital=self.config.initial_capital,
                    round_trip_cost_pct=self.config.round_trip_cost_pct,
                    _df_ind_precomputed=df_ind,
                )
                val_trades = simulator.run(
                    symbol, prices_df, v_from, v_to, combination,
                    initial_capital=self.config.initial_capital,
                    round_trip_cost_pct=self.config.round_trip_cost_pct,
                    _df_ind_precomputed=df_ind,
                )
                oos_trades = simulator.run(
                    symbol, prices_df, o_from, o_to, combination,
                    initial_capital=self.config.initial_capital,
                    round_trip_cost_pct=self.config.round_trip_cost_pct,
                    _df_ind_precomputed=df_ind,
                )
            except Exception:
                logger.debug("[engine] backtest failed for %s, skipping", symbol)
                continue

            all_train.extend(train_trades)
            all_val.extend(val_trades)
            all_oos.extend(oos_trades)

        if not all_oos:
            return None

        benchmarks = self._compute_benchmarks(symbols_data, oos_from_date, oos_to_date)
        wf_consistency = self._compute_wf_consistency(
            combination, symbols_data, oos_from_date, oos_to_date
        )

        train_metrics = compute_extended_metrics(
            all_train, self.config.initial_capital, train_from_date, train_to_date, self.db, {}
        )
        val_metrics = compute_extended_metrics(
            all_val, self.config.initial_capital, val_from_date, val_to_date, self.db, {}
        )
        oos_metrics = compute_extended_metrics(
            all_oos, self.config.initial_capital, oos_from_date, oos_to_date, self.db, benchmarks
        )

        combo_name = "_".join(s.name[:6] for s in combination)
        strategy_ids = sorted([s.name for s in combination])

        return {
            "combination": combination,
            "combo_name": combo_name,
            "strategy_ids_json": json.dumps(strategy_ids),
            "strategy_names_json": json.dumps([s.name for s in combination]),
            "size": len(combination),
            "train_metrics": train_metrics,
            "val_metrics": val_metrics,
            "oos_metrics": oos_metrics,
            "wf_consistency": wf_consistency,
            "oos_from": oos_from_date,
            "oos_to": oos_to_date,
            "sensitivity_score": 50.0,  # default; overwritten in step 9 for top-N
            "reliability_result": None,
            "explanation": None,
        }

    def _load_symbols_data(self) -> dict[str, pd.DataFrame]:
        """Load price data for up to symbols_limit symbols."""
        rows = self.db.execute(text("""
            SELECT symbol FROM stock_prices_daily
            GROUP BY symbol
            HAVING COUNT(*) >= 200
            ORDER BY COUNT(*) DESC
            LIMIT :limit
        """), {"limit": self.config.symbols_limit}).fetchall()

        symbols = [r[0] for r in rows]
        result: dict[str, pd.DataFrame] = {}

        for symbol in symbols:
            price_rows = self.db.execute(text("""
                SELECT date, open, high, low, close, volume
                FROM stock_prices_daily
                WHERE symbol = :sym
                ORDER BY date ASC
            """), {"sym": symbol}).fetchall()

            if not price_rows:
                continue
            df = pd.DataFrame([dict(r._mapping) for r in price_rows])
            df["date"] = pd.to_datetime(df["date"]).dt.date
            result[symbol] = df

        logger.info("[engine] loaded %d symbols", len(result))
        return result

    def _compute_wf_consistency(
        self, combination: list, symbols_data: dict, oos_from: date, oos_to: date
    ) -> float:
        """Compute walk-forward consistency using existing WalkForwardRunner logic.

        Simplified: use average consistency_score from walk_forward_results for the
        strategies in this combination (as a proxy for the combination's consistency).
        """
        strategy_names = [s.name for s in combination]
        rows = self.db.execute(text("""
            SELECT AVG(wfr.consistency_score)
            FROM walk_forward_results wfr
            JOIN strategies s ON s.id = wfr.strategy_id
            WHERE s.name IN ({placeholders})
        """.format(
            placeholders=",".join(f":n{i}" for i in range(len(strategy_names)))
        )), {f"n{i}": n for i, n in enumerate(strategy_names)}).fetchone()

        return float(rows[0]) if rows and rows[0] is not None else 0.0

    def _compute_benchmarks(
        self, symbols_data: dict, from_date: date, to_date: date
    ) -> dict:
        """Compute benchmark CAGRs for the OOS period."""
        bah_cagrs = []
        days = max((to_date - from_date).days, 1)

        for symbol, df in symbols_data.items():
            start_row = df[df["date"] >= from_date]
            end_row = df[df["date"] <= to_date]
            if start_row.empty or end_row.empty:
                continue
            start_price = start_row.iloc[0]["close"]
            end_price = end_row.iloc[-1]["close"]
            if start_price > 0:
                cagr = ((end_price / start_price) ** (365.0 / days) - 1) * 100
                bah_cagrs.append(cagr)

        buy_and_hold = statistics.mean(bah_cagrs) if bah_cagrs else 0.0

        # Best single strategy from strategy_performance (approximation)
        best_single_row = self.db.execute(text(
            "SELECT MAX(cagr) FROM strategy_performance"
        )).fetchone()
        best_single = float(best_single_row[0]) if best_single_row and best_single_row[0] else 0.0

        return {
            "buy_and_hold": round(buy_and_hold, 4),
            "best_single": round(best_single, 4),
            "sma_crossover": 0.0,  # simplified — SMA crossover benchmark deferred
        }

    def _load_correlation_matrix(self) -> dict:
        """Load strategy correlation pairs from strategy_correlations table."""
        rows = self.db.execute(text("""
            SELECT sa.name, sb.name, sc.correlation
            FROM strategy_correlations sc
            JOIN strategies sa ON sa.id = sc.strategy_id_a
            JOIN strategies sb ON sb.id = sc.strategy_id_b
        """)).fetchall()
        return {tuple(sorted([r[0], r[1]])): r[2] for r in rows}

    def _persist_results(self, scored: list[dict], run_id: int) -> Optional[int]:
        """Persist all combination results to DB. Returns first (best) combination_id."""
        first_id = None
        for cr in scored:
            # Upsert into strategy_combinations
            rel = cr["reliability_result"]
            oos = cr["oos_metrics"]
            train = cr["train_metrics"]
            val = cr["val_metrics"]

            try:
                self.db.execute(text("""
                    INSERT OR IGNORE INTO strategy_combinations
                        (name, strategy_ids, strategy_names, size, search_method)
                    VALUES (:name, :ids, :names, :size, 'exhaustive')
                """), {
                    "name": cr["combo_name"],
                    "ids": cr["strategy_ids_json"],
                    "names": cr["strategy_names_json"],
                    "size": cr["size"],
                })
                combo_id_row = self.db.execute(text("""
                    SELECT id FROM strategy_combinations WHERE strategy_ids = :ids
                """), {"ids": cr["strategy_ids_json"]}).fetchone()
                if not combo_id_row:
                    continue
                combo_id = combo_id_row[0]
                if first_id is None:
                    first_id = combo_id

                exp_json = None
                if cr["explanation"]:
                    from dataclasses import asdict as dc_asdict
                    exp_json = json.dumps(dc_asdict(cr["explanation"]))

                self.db.execute(text("""
                    INSERT INTO combination_results (
                        combination_id, run_id,
                        train_cagr, train_sharpe, train_win_rate, train_max_drawdown,
                        train_profit_factor, train_total_trades, train_sortino,
                        val_cagr, val_sharpe, val_win_rate, val_max_drawdown, val_total_trades,
                        oos_cagr, oos_sharpe, oos_win_rate, oos_max_drawdown, oos_profit_factor,
                        oos_total_trades, oos_sortino, oos_median_return_pct,
                        wf_consistency_score, wf_avg_oos_cagr,
                        vs_buy_and_hold_cagr, vs_best_single_cagr, vs_sma_crossover_cagr,
                        reliability_score, reliability_label, sensitivity_score,
                        explanation_json
                    ) VALUES (
                        :cid, :rid,
                        :t_cagr, :t_sharpe, :t_wr, :t_dd, :t_pf, :t_trades, :t_sort,
                        :v_cagr, :v_sharpe, :v_wr, :v_dd, :v_trades,
                        :o_cagr, :o_sharpe, :o_wr, :o_dd, :o_pf, :o_trades, :o_sort, :o_med,
                        :wf, :wf_cagr,
                        :vs_bah, :vs_best, :vs_sma,
                        :rel_score, :rel_label, :sens_score,
                        :exp_json
                    )
                """), {
                    "cid": combo_id, "rid": run_id,
                    "t_cagr": train.cagr, "t_sharpe": train.sharpe_ratio,
                    "t_wr": train.win_rate, "t_dd": train.max_drawdown,
                    "t_pf": train.profit_factor, "t_trades": train.total_trades,
                    "t_sort": train.sortino_ratio,
                    "v_cagr": val.cagr, "v_sharpe": val.sharpe_ratio,
                    "v_wr": val.win_rate, "v_dd": val.max_drawdown,
                    "v_trades": val.total_trades,
                    "o_cagr": oos.cagr, "o_sharpe": oos.sharpe_ratio,
                    "o_wr": oos.win_rate, "o_dd": oos.max_drawdown,
                    "o_pf": oos.profit_factor, "o_trades": oos.total_trades,
                    "o_sort": oos.sortino_ratio, "o_med": oos.median_return_pct,
                    "wf": cr["wf_consistency"], "wf_cagr": None,
                    "vs_bah": oos.benchmark_deltas.get("bah"),
                    "vs_best": oos.benchmark_deltas.get("best_single"),
                    "vs_sma": oos.benchmark_deltas.get("sma_cross"),
                    "rel_score": rel.score, "rel_label": rel.label,
                    "sens_score": cr.get("sensitivity_score"),
                    "exp_json": exp_json,
                })
            except Exception:
                logger.exception("[engine] persist failed for %s", cr.get("combo_name"))
                continue

        self.db.commit()
        return first_id

    def _create_run_log(self) -> int:
        result = self.db.execute(text("""
            INSERT INTO combination_run_log (started_at, status, config_json)
            VALUES (:now, 'running', :cfg)
        """), {"now": ist_now(), "cfg": json.dumps(asdict(self.config))})
        self.db.commit()
        return result.lastrowid

    def _complete_run(
        self, run_id: int, symbols: int, candidates: int, combos: int,
        top_combo_id: Optional[int]
    ) -> None:
        self.db.execute(text("""
            UPDATE combination_run_log
            SET completed_at = :now, status = 'complete',
                symbols_analyzed = :sym, candidates_selected = :cand,
                combinations_tested = :combos, top_combination_id = :top
            WHERE id = :rid
        """), {
            "now": ist_now(), "sym": symbols, "cand": candidates,
            "combos": combos, "top": top_combo_id, "rid": run_id,
        })
        self.db.commit()

    def _fail_run(self, run_id: int, error: str) -> None:
        self.db.execute(text("""
            UPDATE combination_run_log
            SET completed_at = :now, status = 'failed', error_message = :err
            WHERE id = :rid
        """), {"now": ist_now(), "err": error, "rid": run_id})
        self.db.commit()

    def get_top_combinations(self, n: int = 50) -> list[dict]:
        """Return top combinations from most recent completed run."""
        rows = self.db.execute(text("""
            SELECT sc.name, sc.strategy_names, sc.size,
                   cr.oos_cagr, cr.oos_max_drawdown, cr.oos_sharpe, cr.oos_win_rate,
                   cr.oos_total_trades, cr.train_cagr, cr.wf_consistency_score,
                   cr.reliability_score, cr.reliability_label, cr.sensitivity_score,
                   cr.vs_buy_and_hold_cagr, cr.vs_best_single_cagr, sc.id AS combination_id
            FROM combination_results cr
            JOIN strategy_combinations sc ON sc.id = cr.combination_id
            JOIN combination_run_log rl ON rl.id = cr.run_id
            WHERE rl.status = 'complete'
            ORDER BY cr.reliability_score DESC
            LIMIT :n
        """), {"n": n}).fetchall()
        return [dict(r._mapping) for r in rows]


class _RegimeAdapter:
    """Adapter to pass oos metrics + wf_consistency to ExplanationGenerator."""
    def __init__(self, oos_metrics: ExtendedMetrics, wf_consistency: float):
        self.regime_win_rates = oos_metrics.regime_win_rates
        self.wf_consistency_score = wf_consistency
