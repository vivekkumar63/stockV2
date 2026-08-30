# backend/domains/combinations/engine.py
import json
import logging
import statistics
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, asdict, field
from datetime import date
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
from domains.data.indicator_cache import IndicatorCache
from ist import ist_now

logger = logging.getLogger(__name__)

# ── Module-level state for ProcessPoolExecutor workers ───────────────────────
# Each worker process gets its own copy via the 'initializer' argument.
# Using globals means we serialize the large data once per worker, not per task.
_W_SYMBOLS: dict = {}
_W_INDICATORS: dict = {}
_W_REGIME: dict = {}
_W_WF: dict = {}
_W_BENCHMARKS: dict = {}
_W_CFG: tuple = (0.60, 0.20, 500_000.0, 0.30)


def _combo_worker_init(symbols_data, indicators_data, regime_map, wf_map, benchmarks, cfg):
    global _W_SYMBOLS, _W_INDICATORS, _W_REGIME, _W_WF, _W_BENCHMARKS, _W_CFG
    _W_SYMBOLS = symbols_data
    _W_INDICATORS = indicators_data
    _W_REGIME = regime_map
    _W_WF = wf_map
    _W_BENCHMARKS = benchmarks
    _W_CFG = cfg


def _combo_worker_eval(combination: list) -> Optional[dict]:
    """Evaluate one combination in a worker process. No DB calls."""
    from domains.backtest.simulator import BacktestSimulator
    from domains.combinations.metrics import compute_extended_metrics

    train_ratio, val_ratio, initial_capital, round_trip_cost_pct = _W_CFG
    simulator = BacktestSimulator()
    all_train, all_val, all_oos = [], [], []
    train_from = val_from = oos_from = None
    train_to = val_to = oos_to = None

    for symbol, prices_df in _W_SYMBOLS.items():
        if len(prices_df) < 50:
            continue
        df_ind = _W_INDICATORS.get(symbol)
        if df_ind is None:
            continue
        dates = prices_df["date"].values
        n = len(dates)
        train_end = int(n * train_ratio)
        val_end = int(n * (train_ratio + val_ratio))
        t_from, t_to = dates[0], dates[train_end - 1]
        v_from, v_to = dates[train_end], dates[val_end - 1]
        o_from, o_to = dates[val_end], dates[-1]
        if train_from is None:
            train_from, train_to = t_from, t_to
            val_from, val_to = v_from, v_to
            oos_from, oos_to = o_from, o_to
        try:
            all_train.extend(simulator.run(symbol, prices_df, t_from, t_to, combination,
                initial_capital=initial_capital, round_trip_cost_pct=round_trip_cost_pct,
                _df_ind_precomputed=df_ind))
            all_val.extend(simulator.run(symbol, prices_df, v_from, v_to, combination,
                initial_capital=initial_capital, round_trip_cost_pct=round_trip_cost_pct,
                _df_ind_precomputed=df_ind))
            all_oos.extend(simulator.run(symbol, prices_df, o_from, o_to, combination,
                initial_capital=initial_capital, round_trip_cost_pct=round_trip_cost_pct,
                _df_ind_precomputed=df_ind))
        except Exception:
            continue

    if not all_oos or oos_from is None:
        return None

    wf = sum(_W_WF.get(s.name, 0.0) for s in combination) / len(combination)
    train_m = compute_extended_metrics(all_train, initial_capital, train_from, train_to,
                                       None, {}, regime_map=_W_REGIME)
    val_m   = compute_extended_metrics(all_val,   initial_capital, val_from,   val_to,
                                       None, {}, regime_map=_W_REGIME)
    oos_m   = compute_extended_metrics(all_oos,   initial_capital, oos_from,   oos_to,
                                       None, _W_BENCHMARKS, regime_map=_W_REGIME)

    return {
        "combination": combination,
        "combo_name": "_".join(s.name[:6] for s in combination),
        "strategy_ids_json": json.dumps(sorted(s.name for s in combination)),
        "strategy_names_json": json.dumps([s.name for s in combination]),
        "size": len(combination),
        "train_metrics": train_m,
        "val_metrics": val_m,
        "oos_metrics": oos_m,
        "wf_consistency": wf,
        "oos_from": oos_from,
        "oos_to": oos_to,
        "sensitivity_score": None,
        "reliability_result": None,
        "explanation": None,
    }


@dataclass
class EngineConfig:
    filter: FilterConfig = field(default_factory=FilterConfig)
    search: SearchConfig = field(default_factory=SearchConfig)
    symbols_limit: int = 30
    initial_capital: float = 500_000.0
    round_trip_cost_pct: float = 0.30
    train_ratio: float = 0.60
    val_ratio: float = 0.20
    sensitivity_top_n: int = 30
    explanation_top_n: int = 20
    max_workers: int = 4


class CombinationEngine:
    def __init__(self, db: Session, config: EngineConfig | None = None):
        self.db = db
        self.config = config if config is not None else EngineConfig()
        self.scorer = ReliabilityScorer()
        self.sensitivity_analyzer = SensitivityAnalyzer()
        self.explainer = ExplanationGenerator()
        self.simulator = BacktestSimulator()

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

            # Step 4: Load price data + indicators for symbols (indicators loaded once,
            # reused for every combo — avoids N_combos × N_symbols recomputes)
            logger.info("[engine] Step 4: Loading price data")
            symbols_data = self._load_symbols_data()
            if not symbols_data:
                self._fail_run(run_id, "No price data available")
                return run_id

            logger.info("[engine] Step 4b: Loading indicator cache for %d symbols", len(symbols_data))
            indicators_data = self._load_indicators_data(symbols_data)

            # Steps 5-6: Backtest + extended metrics per combo (parallelized)
            logger.info("[engine] Steps 5-6: Backtesting combinations (workers=%d, symbols=%d)",
                        self.config.max_workers, len(symbols_data))
            regime_map = self._load_regime_map()
            wf_map = self._load_wf_map()
            benchmarks = self._compute_benchmarks_once(symbols_data, indicators_data)
            combo_results: list[dict] = []
            completed = 0
            total = len(combos)
            log_interval = max(1, total // 20)
            cfg_tuple = (self.config.train_ratio, self.config.val_ratio,
                         self.config.initial_capital, self.config.round_trip_cost_pct)

            with ProcessPoolExecutor(
                max_workers=self.config.max_workers,
                initializer=_combo_worker_init,
                initargs=(symbols_data, indicators_data, regime_map, wf_map, benchmarks, cfg_tuple),
            ) as executor:
                futures = {executor.submit(_combo_worker_eval, combo): combo for combo in combos}
                for future in as_completed(futures):
                    completed += 1
                    if completed % log_interval == 0 or completed == total:
                        logger.info("[engine] Progress: %d/%d combinations", completed, total)
                    try:
                        result = future.result()
                        if result:
                            combo_results.append(result)
                    except Exception:
                        logger.exception("[engine] combo evaluation raised exception")

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
                try:
                    sens_score = self.sensitivity_analyzer.test(
                        cr["combination"], symbols_data,
                        cr["oos_from"], cr["oos_to"],
                        df_ind_map=indicators_data,
                    )
                    cr["sensitivity_score"] = sens_score
                except Exception:
                    logger.warning("[engine] sensitivity test failed for %s, defaulting to 50", cr.get("combo_name"))
                    cr["sensitivity_score"] = 50.0

            # Step 10: Apply sensitivity cap (Pass 2)
            logger.info("[engine] Step 10: Applying sensitivity cap (Pass 2)")
            for cr in top_n:
                cr["reliability_result"] = self.scorer.apply_sensitivity_cap(
                    cr["reliability_result"], cr["sensitivity_score"]
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

    def _load_indicators_data(self, symbols_data: dict) -> dict[str, pd.DataFrame]:
        """Use IndicatorCache to load precomputed indicators for all symbols.
        Reads from stock_indicators_daily if current; computes+stores if stale.
        Called ONCE before the combo loop so indicators are not recomputed per combo."""
        cache = IndicatorCache(self.db)
        result: dict[str, pd.DataFrame] = {}
        for symbol, prices_df in symbols_data.items():
            try:
                result[symbol] = cache.get(symbol, prices_df)
            except Exception:
                logger.warning("[engine] indicator load failed for %s, skipping", symbol)
        logger.info("[engine] indicators ready for %d/%d symbols", len(result), len(symbols_data))
        return result

    def _load_regime_map(self) -> dict:
        """Pre-load all market regime rows into a date→label dict (eliminates N+1 per trade)."""
        rows = self.db.execute(text("SELECT date, regime FROM market_regime")).fetchall()
        result = {}
        for r in rows:
            d = r[0].date() if hasattr(r[0], "date") else r[0]
            result[d] = r[1]
        logger.info("[engine] loaded %d regime rows", len(result))
        return result

    def _load_wf_map(self) -> dict:
        """Pre-load walk-forward consistency per strategy name into a dict."""
        rows = self.db.execute(text("""
            SELECT s.name, AVG(wfr.consistency_score)
            FROM walk_forward_results wfr
            JOIN strategies s ON s.id = wfr.strategy_id
            GROUP BY s.name
        """)).fetchall()
        return {str(r[0]): float(r[1]) for r in rows if r[1] is not None}

    def _compute_benchmarks_once(self, symbols_data: dict, _indicators_data: dict) -> dict:
        """Compute benchmarks using OOS window from first available symbol."""
        for symbol, prices_df in symbols_data.items():
            if len(prices_df) < 50:
                continue
            dates = prices_df["date"].values
            n = len(dates)
            val_end_idx = int(n * (self.config.train_ratio + self.config.val_ratio))
            oos_from = dates[val_end_idx]
            oos_to = dates[-1]
            return self._compute_benchmarks(symbols_data, oos_from, oos_to)
        return {"buy_and_hold": 0.0, "best_single": 0.0, "sma_crossover": 0.0}

    def _load_symbols_data(self) -> dict[str, pd.DataFrame]:
        """Load price data for up to symbols_limit symbols in a single bulk query."""
        # Get top symbols by row count
        sym_rows = self.db.execute(text("""
            SELECT symbol FROM stock_prices_daily
            GROUP BY symbol
            HAVING COUNT(*) >= 200
            ORDER BY COUNT(*) DESC
            LIMIT :limit
        """), {"limit": self.config.symbols_limit}).fetchall()

        if not sym_rows:
            return {}

        symbols = [r[0] for r in sym_rows]
        placeholders = ",".join(f":s{i}" for i in range(len(symbols)))
        params = {f"s{i}": s for i, s in enumerate(symbols)}

        price_rows = self.db.execute(text(f"""
            SELECT symbol, date, open, high, low, close, volume
            FROM stock_prices_daily
            WHERE symbol IN ({placeholders})
            ORDER BY symbol, date ASC
        """), params).fetchall()

        result: dict[str, pd.DataFrame] = {}
        if price_rows:
            df_all = pd.DataFrame([dict(r._mapping) for r in price_rows])
            df_all["date"] = pd.to_datetime(df_all["date"]).dt.date
            for symbol, group in df_all.groupby("symbol"):
                result[symbol] = group.drop(columns=["symbol"]).reset_index(drop=True)

        logger.info("[engine] loaded %d symbols", len(result))
        return result

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

        best_single_row = self.db.execute(text(
            "SELECT MAX(cagr) FROM strategy_performance"
        )).fetchone()
        best_single = float(best_single_row[0]) if best_single_row and best_single_row[0] else 0.0

        return {
            "buy_and_hold": round(buy_and_hold, 4),
            "best_single": round(best_single, 4),
            "sma_crossover": 0.0,
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
            rel = cr["reliability_result"]
            oos = cr["oos_metrics"]
            train = cr["train_metrics"]
            val = cr["val_metrics"]

            try:
                self.db.execute(text("""
                    INSERT INTO strategy_combinations
                        (name, strategy_ids, strategy_names, size, search_method)
                    VALUES (:name, :ids, :names, :size, 'exhaustive')
                    ON CONFLICT (strategy_ids) DO NOTHING
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
                    exp_json = json.dumps(asdict(cr["explanation"]))

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

                # Write per-regime performance (win_rate available; trade_count/avg_pnl_pct/cagr are NULL)
                for regime_label, win_rate in oos.regime_win_rates.items():
                    if win_rate is not None:
                        self.db.execute(text("""
                            INSERT INTO combination_regime_perf
                                (combination_id, run_id, regime, win_rate)
                            VALUES (:cid, :rid, :regime, :wr)
                        """), {
                            "cid": combo_id, "rid": run_id,
                            "regime": regime_label, "wr": win_rate,
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
        """Return top combinations from the most recent completed run."""
        rows = self.db.execute(text("""
            SELECT sc.name, sc.strategy_names, sc.size,
                   cr.oos_cagr, cr.oos_max_drawdown, cr.oos_sharpe, cr.oos_win_rate,
                   cr.oos_total_trades, cr.train_cagr, cr.wf_consistency_score,
                   cr.reliability_score, cr.reliability_label, cr.sensitivity_score,
                   cr.vs_buy_and_hold_cagr, cr.vs_best_single_cagr, sc.id AS combination_id
            FROM combination_results cr
            JOIN strategy_combinations sc ON sc.id = cr.combination_id
            JOIN combination_run_log rl ON rl.id = cr.run_id
            WHERE rl.id = (SELECT MAX(id) FROM combination_run_log WHERE status = 'complete')
            ORDER BY cr.reliability_score DESC
            LIMIT :n
        """), {"n": n}).fetchall()
        return [dict(r._mapping) for r in rows]


class _RegimeAdapter:
    """Adapter to pass oos metrics + wf_consistency to ExplanationGenerator."""
    def __init__(self, oos_metrics: ExtendedMetrics, wf_consistency: float):
        self.regime_win_rates = oos_metrics.regime_win_rates
        self.wf_consistency_score = wf_consistency
