import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from typing import Optional

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from domains.backtest.metrics import compute_metrics
from domains.backtest.simulator import BacktestSimulator, SimTrade
from domains.data.indicator_cache import IndicatorCache
from domains.data.indicators import IndicatorEngine
from domains.strategies.engine import ALL_STRATEGIES
from settings import settings

logger = logging.getLogger(__name__)

_SCAN_METRICS = ["total_trades", "win_rate", "cagr", "sharpe_ratio", "max_drawdown", "profit_factor", "total_pnl"]


class BacktestRunner:
    def __init__(self, db: Session):
        self.db = db
        self.simulator = BacktestSimulator()

    def run(
        self,
        symbol: str,
        from_date: date,
        to_date: date,
        strategy_id: Optional[int] = None,
        initial_capital: float = 500_000.0,
        stop_loss_pct: Optional[float] = None,
        target_pct: Optional[float] = None,
    ) -> dict:
        symbol = symbol.upper()
        # Fetch full history — no LIMIT because IndicatorEngine needs warmup bars
        # before from_date, and the simulator filters to the requested window.
        rows = self.db.execute(
            text("""
                SELECT date, open, high, low, close, volume
                FROM stock_prices_daily
                WHERE symbol = :sym
                ORDER BY date ASC
            """),
            {"sym": symbol},
        ).fetchall()

        if len(rows) < 50:
            return {"error": f"Insufficient price data for {symbol}: {len(rows)} bars (need >= 50)"}

        df = pd.DataFrame([dict(r._mapping) for r in rows])
        df["date"] = pd.to_datetime(df["date"]).dt.date

        if df[(df["date"] >= from_date) & (df["date"] <= to_date)].empty:
            return {"error": f"No price data for {symbol} in range {from_date} to {to_date}"}

        if strategy_id is not None:
            row = self.db.execute(
                text("SELECT name FROM strategies WHERE id = :id"), {"id": strategy_id}
            ).fetchone()
            if not row:
                return {"error": f"Strategy id={strategy_id} not found"}
            strat_name = row[0]
            strategies = [s for s in ALL_STRATEGIES if s.name == strat_name]
            if not strategies:
                return {"error": f"Strategy '{strat_name}' not in ALL_STRATEGIES"}
            use_aggregator = False  # single strategy; no consensus threshold needed
        else:
            strategies = list(ALL_STRATEGIES)
            use_aggregator = True

        trades = self.simulator.run(
            symbol=symbol,
            prices_df=df,
            from_date=from_date,
            to_date=to_date,
            strategies=strategies,
            use_aggregator=use_aggregator,
            initial_capital=initial_capital,
            stop_loss_pct_override=stop_loss_pct,
            target_pct_override=target_pct,
            round_trip_cost_pct=0.30,
        )

        metrics = compute_metrics(trades, initial_capital, from_date, to_date)
        result_id = self._save_result(symbol, from_date, to_date, strategy_id, metrics, trades)

        logger.info("[BacktestRunner] %s %s->%s: %d trades, result_id=%d",
                    symbol, from_date, to_date, len(trades), result_id)
        return {
            "result_id": result_id,
            "symbol": symbol,
            "from_date": str(from_date),
            "to_date": str(to_date),
            **metrics,
        }

    def scan_all(
        self,
        from_date: date,
        to_date: date,
        strategy_ids: Optional[list[int]] = None,
        initial_capital: float = 500_000.0,
        limit: int = 200,
        stop_loss_pct: Optional[float] = None,
        target_pct: Optional[float] = None,
    ) -> list[dict]:
        # Sentinel -1.0 = "use the strategy's own default" in the cache key.
        # Using a real float (not NULL) keeps the UNIQUE constraint deterministic.
        sl_key = stop_loss_pct if stop_loss_pct is not None else -1.0
        tgt_key = target_pct if target_pct is not None else -1.0

        if strategy_ids:
            placeholders = ",".join(str(int(i)) for i in strategy_ids)
            strats_rows = self.db.execute(
                text(f"SELECT id, name FROM strategies WHERE id IN ({placeholders}) AND is_active = true")
            ).fetchall()
        else:
            strats_rows = self.db.execute(
                text("SELECT id, name FROM strategies WHERE is_active = true")
            ).fetchall()

        strats_to_run: list[tuple[int, str, object]] = []
        for sid, sname in strats_rows:
            instances = [s for s in ALL_STRATEGIES if s.name == sname]
            if instances:
                strats_to_run.append((sid, sname, instances[0]))

        if not strats_to_run:
            return []

        strat_ids_set = {sid for sid, _, _ in strats_to_run}

        symbols = [
            r[0] for r in self.db.execute(
                text("""
                    SELECT symbol FROM stock_prices_daily
                    WHERE date >= :fd AND date <= :td
                    GROUP BY symbol HAVING COUNT(*) >= 10
                    ORDER BY symbol LIMIT :lim
                """),
                {"fd": str(from_date), "td": str(to_date), "lim": limit},
            ).fetchall()
        ]
        if not symbols:
            return []

        symbols_set = set(symbols)

        # Bulk cache lookup — single query for the entire (date_range, capital, sl, tgt) set
        cached_rows = self.db.execute(
            text("""
                SELECT symbol, strategy_id, total_trades, win_rate, cagr,
                       sharpe_ratio, max_drawdown, profit_factor, total_pnl
                FROM scan_result_cache
                WHERE from_date = :fd AND to_date = :td
                  AND initial_capital = :cap
                  AND stop_loss_pct = :sl AND target_pct = :tgt
            """),
            {"fd": str(from_date), "td": str(to_date),
             "cap": initial_capital, "sl": sl_key, "tgt": tgt_key},
        ).fetchall()

        cached_map: dict[tuple[str, int], dict] = {
            (r[0], r[1]): dict(zip(_SCAN_METRICS, r[2:]))
            for r in cached_rows
            if r[0] in symbols_set and r[1] in strat_ids_set
        }

        # Only load prices for symbols that still need at least one strategy computed
        symbols_needing_compute = [
            sym for sym in symbols
            if any((sym, sid) not in cached_map for sid, _, _ in strats_to_run)
        ]

        computed_map: dict[tuple[str, int], dict] = {}

        for symbol in symbols_needing_compute:
            rows = self.db.execute(
                text("SELECT date, open, high, low, close, volume FROM stock_prices_daily WHERE symbol = :sym ORDER BY date ASC"),
                {"sym": symbol},
            ).fetchall()
            if len(rows) < 50:
                continue

            df = pd.DataFrame([dict(r._mapping) for r in rows])
            df["date"] = pd.to_datetime(df["date"]).dt.date
            try:
                # Use cache — reads from DB if precomputed (instant), else computes+stores.
                df_ind = IndicatorCache(self.db).get(symbol, df)
            except Exception as e:
                logger.warning("[scan] %s: indicator compute failed: %s", symbol, e)
                continue

            new_entries: list[tuple[str, int, dict]] = []
            for sid, sname, strat in strats_to_run:
                if (symbol, sid) in cached_map:
                    continue
                try:
                    trades = self.simulator.run(
                        symbol=symbol,
                        prices_df=df,
                        from_date=from_date,
                        to_date=to_date,
                        strategies=[strat],
                        use_aggregator=False,
                        initial_capital=initial_capital,
                        _df_ind_precomputed=df_ind,
                        stop_loss_pct_override=stop_loss_pct,
                        target_pct_override=target_pct,
                        round_trip_cost_pct=0.30,
                    )
                    m = compute_metrics(trades, initial_capital, from_date, to_date)
                    computed_map[(symbol, sid)] = m
                    new_entries.append((symbol, sid, m))
                except Exception as e:
                    logger.warning("[scan] %s/%s: %s", symbol, sname, e)

            # Batch-persist cache entries for this symbol
            for sym, sid, m in new_entries:
                self.db.execute(
                    text("""
                        INSERT INTO scan_result_cache
                            (symbol, strategy_id, from_date, to_date, initial_capital,
                             stop_loss_pct, target_pct, total_trades, win_rate, cagr,
                             sharpe_ratio, max_drawdown, profit_factor, total_pnl, cached_at)
                        VALUES (:sym, :sid, :fd, :td, :cap, :sl, :tgt,
                                :tt, :wr, :cagr, :sharpe, :dd, :pf, :tpnl, CURRENT_TIMESTAMP)
                        ON CONFLICT (symbol, strategy_id, from_date, to_date, initial_capital, stop_loss_pct, target_pct)
                        DO UPDATE SET
                            total_trades=EXCLUDED.total_trades, win_rate=EXCLUDED.win_rate,
                            cagr=EXCLUDED.cagr, sharpe_ratio=EXCLUDED.sharpe_ratio,
                            max_drawdown=EXCLUDED.max_drawdown, profit_factor=EXCLUDED.profit_factor,
                            total_pnl=EXCLUDED.total_pnl, cached_at=CURRENT_TIMESTAMP
                    """),
                    {
                        "sym": sym, "sid": sid,
                        "fd": str(from_date), "td": str(to_date),
                        "cap": initial_capital, "sl": sl_key, "tgt": tgt_key,
                        "tt": m["total_trades"], "wr": m["win_rate"], "cagr": m["cagr"],
                        "sharpe": m["sharpe_ratio"], "dd": m["max_drawdown"],
                        "pf": m["profit_factor"], "tpnl": m["total_pnl"],
                    },
                )
            if new_entries:
                self.db.commit()

        n_cached = sum(1 for sym in symbols for sid, _, _ in strats_to_run if (sym, sid) in cached_map)
        logger.info("[scan_all] %s→%s: %d cached hits, %d computed, sl=%s tgt=%s",
                    from_date, to_date, n_cached, len(computed_map), sl_key, tgt_key)

        # Assemble final results preserving symbols order
        results = []
        for symbol in symbols:
            for sid, sname, _ in strats_to_run:
                m = cached_map.get((symbol, sid)) or computed_map.get((symbol, sid))
                if m is None:
                    continue
                results.append({
                    "symbol": symbol,
                    "strategy_id": sid,
                    "strategy_name": sname,
                    **{k: m[k] for k in _SCAN_METRICS},
                })

        return results

    def precompute_all_strategies(
        self,
        strategy_ids: Optional[list[int]] = None,
        _state: Optional[dict] = None,
    ) -> int:
        """Compute strategy_performance for every active (strategy, symbol) pair.

        Optimisations vs the old per-strategy loop:
          1. IndicatorCache — indicators computed once per symbol, stored in DB,
             reused for all strategies (eliminates 115× redundant recomputation).
          2. Symbol-first loop — all strategies run on the same indicator DataFrame.
          3. ThreadPoolExecutor — symbols processed in parallel; threads share
             pre-loaded DataFrames (read-only) so there is no SQLite contention.
          4. Incremental skip — symbols already current (to_date == last_price_date)
             are skipped with a single metadata check.
        """
        t_total = time.time()

        def _upd(done: int, total: int, phase: str, message: str = "") -> None:
            if _state is not None:
                _state.update({"done": done, "total": max(total, 1), "phase": phase, "message": message})

        _upd(0, 1, "starting", "Loading strategy metadata…")

        # ── 1. Metadata ──────────────────────────────────────────────────────
        if strategy_ids:
            placeholders = ",".join(str(int(i)) for i in strategy_ids)
            strats_rows = self.db.execute(
                text(f"SELECT id, name FROM strategies WHERE id IN ({placeholders}) AND is_active = true")
            ).fetchall()
        else:
            strats_rows = self.db.execute(
                text("SELECT id, name FROM strategies WHERE is_active = true")
            ).fetchall()

        strats_to_run: list[tuple[int, str, object]] = [
            (sid, sname, strat)
            for sid, sname in strats_rows
            for strat in [next((s for s in ALL_STRATEGIES if s.name == sname), None)]
            if strat is not None
        ]
        if not strats_to_run:
            logger.info("[precompute_all] no matching active strategies found — nothing to do")
            return 0

        logger.info("[precompute_all] starting — %d strategies: %s",
                    len(strats_to_run), ", ".join(sname for _, sname, _ in strats_to_run))

        existing: dict[tuple[str, int], str] = {
            (r[0], r[1]): str(r[2])
            for r in self.db.execute(
                text("SELECT symbol, strategy_id, to_date FROM strategy_performance WHERE to_date IS NOT NULL")
            ).fetchall()
        }
        last_price_date: dict[str, str] = {
            r[0]: str(r[1])
            for r in self.db.execute(
                text("SELECT symbol, MAX(date) FROM stock_prices_daily GROUP BY symbol")
            ).fetchall()
        }
        symbols = [
            r[0] for r in self.db.execute(
                text("SELECT DISTINCT symbol FROM stock_prices_daily ORDER BY symbol")
            ).fetchall()
        ]
        if settings.dev_symbol_limit > 0:
            symbols = symbols[:settings.dev_symbol_limit]
            logger.warning("[precompute_all] DEV MODE: capped to %d symbols", settings.dev_symbol_limit)

        # ── 2. Build indicator cache ──────────────────────────────────────────
        # Strategy: split into parallel compute/load then sequential DB write.
        #   • Each worker thread opens its own Session (WAL mode allows concurrent reads).
        #   • Symbols already cached → worker just _load()s from stock_indicators_daily.
        #   • Symbols needing recompute → worker loads prices + runs IndicatorEngine.
        #   • Main thread writes newly computed rows to DB (no lock contention).
        t_cache = time.time()
        # Leave at least half the cores free for FastAPI request handlers.
        n_workers = max(2, (os.cpu_count() or 4) // 2)

        symbols_to_process = [
            s for s in symbols
            if last_price_date.get(s) and not all(
                existing.get((s, sid)) == last_price_date[s]
                for sid, _, _ in strats_to_run
            )
        ]
        n_syms = len(symbols_to_process)
        logger.info("[precompute_all] phase 2 — %d symbols to process (%d workers)", n_syms, n_workers)
        _upd(0, n_syms, "cache", f"Building indicator cache (0/{n_syms} symbols)…")

        def _prepare_symbol(symbol: str) -> tuple[str, Optional[pd.DataFrame], bool]:
            """Returns (symbol, df_ind, needs_write). Each call uses its own Session."""
            from database import SessionLocal as _SL  # noqa: PLC0415
            _db = _SL()
            try:
                lpd = last_price_date[symbol]
                cached_max = _db.execute(
                    text("SELECT MAX(date) FROM stock_indicators_daily WHERE symbol = :s"),
                    {"s": symbol},
                ).scalar()

                if cached_max is not None and str(cached_max) >= lpd:
                    # Already current — load from cache (read-only, thread-safe)
                    df_ind = IndicatorCache(_db)._load(symbol)
                    return symbol, df_ind, False

                # Needs fresh computation
                rows = _db.execute(
                    text("SELECT date, open, high, low, close, volume FROM stock_prices_daily "
                         "WHERE symbol = :s ORDER BY date ASC"),
                    {"s": symbol},
                ).fetchall()
                if len(rows) < 50:
                    return symbol, None, False
                df = pd.DataFrame([dict(r._mapping) for r in rows])
                df["date"] = pd.to_datetime(df["date"]).dt.date
                return symbol, IndicatorEngine.compute(df), True
            except Exception as e:
                logger.warning("[precompute_all] %s: prepare failed: %s", symbol, e)
                return symbol, None, False
            finally:
                _db.close()

        # Parallel phase: load or compute
        prepared: list[tuple[str, pd.DataFrame, bool]] = []
        with ThreadPoolExecutor(max_workers=n_workers) as executor:
            futures = {executor.submit(_prepare_symbol, sym): sym for sym in symbols_to_process}
            done_count = 0
            for future in as_completed(futures):
                sym, df_ind, needs_write = future.result()
                done_count += 1
                if df_ind is not None:
                    prepared.append((sym, df_ind, needs_write))
                if done_count % 25 == 0 or done_count == n_syms:
                    logger.info("[precompute_all] cache build: %d/%d (%.0f%%)",
                                done_count, n_syms, done_count / n_syms * 100)
                    _upd(done_count, n_syms, "cache",
                         f"Building indicator cache ({done_count}/{n_syms} symbols)…")

        # Sequential phase: write newly computed rows to DB
        write_count = sum(1 for _, _, nw in prepared if nw)
        if write_count:
            logger.info("[precompute_all] writing %d new indicator datasets to DB…", write_count)
            _cache = IndicatorCache(self.db)
            for sym, df_ind, needs_write in prepared:
                if needs_write:
                    try:
                        cached_max = self.db.execute(
                            text("SELECT MAX(date) FROM stock_indicators_daily WHERE symbol = :s"),
                            {"s": sym},
                        ).scalar()
                        _cache._store(sym, df_ind, cached_max)
                    except Exception as e:
                        logger.warning("[precompute_all] %s: cache write failed: %s", sym, e)

        all_indicators: dict[str, pd.DataFrame] = {sym: df for sym, df, _ in prepared}

        logger.info("[precompute_all] %d symbols ready — indicator cache built in %.1fs",
                    len(all_indicators), time.time() - t_cache)

        if not all_indicators:
            logger.info("[precompute_all] all strategies current — nothing to do")
            return 0

        # ── 3. Parallel strategy computation ─────────────────────────────────
        # Threads share pre-loaded DataFrames (read-only) — no SQLite inside workers.
        # n_workers already set above (Phase 2 used same pool size)
        results: list[tuple[str, int, dict, str]] = []

        def _process_symbol(symbol: str, df_ind: pd.DataFrame) -> list:
            lpd = last_price_date.get(symbol)
            from_date = df_ind["date"].min()
            to_date_val = df_ind["date"].max()

            strats_needed = [
                (sid, strat)
                for sid, sname, strat in strats_to_run
                if not (lpd and existing.get((symbol, sid)) == lpd)
            ]
            if not strats_needed:
                return []

            try:
                trades_map = BacktestSimulator().run_multi(
                    symbol=symbol,
                    df_ind=df_ind,
                    strategies_with_ids=strats_needed,
                    from_date=from_date,
                    to_date=to_date_val,
                    round_trip_cost_pct=0.30,
                )
            except Exception as e:
                logger.warning("[precompute_all] %s: run_multi failed: %s", symbol, e)
                return []

            return [
                (symbol, sid, compute_metrics(trades, 500_000.0, from_date, to_date_val), str(to_date_val))
                for sid, trades in trades_map.items()
            ]

        t_compute = time.time()
        n_symbols = len(all_indicators)
        logger.info("[precompute_all] phase 3 — parallel computation: %d symbols × %d strategies (%d workers)",
                    n_symbols, len(strats_to_run), n_workers)
        _upd(0, n_symbols, "compute", f"Computing strategies (0/{n_symbols} symbols)…")
        with ThreadPoolExecutor(max_workers=n_workers) as executor:
            futures = {
                executor.submit(_process_symbol, sym, df): sym
                for sym, df in all_indicators.items()
            }
            done = 0
            for future in as_completed(futures):
                sym = futures[future]
                try:
                    results.extend(future.result())
                except Exception as e:
                    logger.warning("[precompute_all] %s: worker error: %s", sym, e)
                done += 1
                if done % 10 == 0 or done == n_symbols:
                    logger.info("[precompute_all] compute: %d/%d symbols (%.0f%%) — %d pairs so far",
                                done, n_symbols, done / n_symbols * 100, len(results))
                    _upd(done, n_symbols, "compute",
                         f"Computing strategies ({done}/{n_symbols} symbols, {len(results)} pairs)…")

        logger.info("[precompute_all] phase 3 done — %d pairs computed in %.1fs",
                    len(results), time.time() - t_compute)
        logger.info("[precompute_all] phase 4 — writing %d rows to DB", len(results))

        # ── 4. Write all results — small batches so UI requests can slip in ────
        # Commit every 50 rows + sleep 10ms between commits. This releases the
        # SQLite write lock frequently so scan/backtest from the UI never waits
        # longer than a single 50-row transaction (~50ms).
        _INS_PERF = text("""
            INSERT INTO strategy_performance
                (strategy_id, symbol, total_trades, win_rate, cagr,
                 sharpe_ratio, max_drawdown, profit_factor, total_pnl,
                 computed_at, to_date)
            VALUES (:sid, :sym, :tt, :wr, :cagr, :sharpe, :dd, :pf, :tpnl,
                    CURRENT_TIMESTAMP, :to_date)
            ON CONFLICT (strategy_id, symbol) DO UPDATE SET
                total_trades=EXCLUDED.total_trades, win_rate=EXCLUDED.win_rate,
                cagr=EXCLUDED.cagr, sharpe_ratio=EXCLUDED.sharpe_ratio,
                max_drawdown=EXCLUDED.max_drawdown, profit_factor=EXCLUDED.profit_factor,
                total_pnl=EXCLUDED.total_pnl, computed_at=CURRENT_TIMESTAMP,
                to_date=EXCLUDED.to_date
        """)
        count = 0
        for symbol, sid, m, to_date_str in results:
            self.db.execute(
                _INS_PERF,
                {
                    "sid": sid, "sym": symbol,
                    "tt": m["total_trades"], "wr": m["win_rate"],
                    "cagr": m["cagr"], "sharpe": m["sharpe_ratio"],
                    "dd": m["max_drawdown"], "pf": m["profit_factor"],
                    "tpnl": m["total_pnl"], "to_date": to_date_str,
                },
            )
            count += 1
            if count % 50 == 0:
                self.db.commit()
                time.sleep(0.01)  # 10ms yield — let UI writes through

        self.db.commit()
        logger.info("[precompute_all] done — %d pairs written in %.1fs total",
                    count, time.time() - t_total)
        return count

    def precompute_all_for_strategy(self, strategy_id: int) -> int:
        """Run backtest for every stock using its full price history and persist
        results to strategy_performance.

        Skips any (strategy, symbol) pair whose stored to_date already matches
        the symbol's latest price date — so re-runs within the same trading day
        are instant no-ops, and only genuinely new data triggers recomputation.
        """
        row = self.db.execute(
            text("SELECT name FROM strategies WHERE id = :id"), {"id": strategy_id}
        ).fetchone()
        if not row:
            return 0
        strat = next((s for s in ALL_STRATEGIES if s.name == row[0]), None)
        if not strat:
            logger.warning("[precompute] strategy '%s' not in ALL_STRATEGIES", row[0])
            return 0

        # Bulk-load what's already stored for this strategy (symbol → to_date)
        existing = {
            r[0]: r[1] for r in self.db.execute(
                text("SELECT symbol, to_date FROM strategy_performance WHERE strategy_id = :sid"),
                {"sid": strategy_id},
            ).fetchall()
        }

        # Bulk-load last available price date per symbol
        last_price_date = {
            r[0]: r[1] for r in self.db.execute(
                text("SELECT symbol, MAX(date) FROM stock_prices_daily GROUP BY symbol")
            ).fetchall()
        }

        symbols = [
            r[0] for r in self.db.execute(
                text("SELECT DISTINCT symbol FROM stock_prices_daily ORDER BY symbol")
            ).fetchall()
        ]

        count = 0
        skipped = 0
        for symbol in symbols:
            last_date = last_price_date.get(symbol)
            if last_date and existing.get(symbol) == str(last_date):
                skipped += 1
                continue  # already computed through today's price data

            rows = self.db.execute(
                text("""
                    SELECT date, open, high, low, close, volume
                    FROM stock_prices_daily WHERE symbol = :s ORDER BY date ASC
                """),
                {"s": symbol},
            ).fetchall()
            if len(rows) < 50:
                continue

            df = pd.DataFrame([dict(r._mapping) for r in rows])
            df["date"] = pd.to_datetime(df["date"]).dt.date
            from_date = df["date"].min()
            to_date = df["date"].max()

            try:
                trades = self.simulator.run(
                    symbol=symbol, prices_df=df,
                    from_date=from_date, to_date=to_date,
                    strategies=[strat], use_aggregator=False,
                    initial_capital=500_000.0,
                    round_trip_cost_pct=0.30,
                )
                m = compute_metrics(trades, 500_000.0, from_date, to_date)
                self.db.execute(
                    text("""
                        INSERT INTO strategy_performance
                            (strategy_id, symbol, total_trades, win_rate, cagr,
                             sharpe_ratio, max_drawdown, profit_factor, total_pnl,
                             computed_at, to_date)
                        VALUES (:sid, :sym, :tt, :wr, :cagr, :sharpe, :dd, :pf, :tpnl,
                                CURRENT_TIMESTAMP, :to_date)
                        ON CONFLICT (strategy_id, symbol) DO UPDATE SET
                            total_trades=EXCLUDED.total_trades, win_rate=EXCLUDED.win_rate,
                            cagr=EXCLUDED.cagr, sharpe_ratio=EXCLUDED.sharpe_ratio,
                            max_drawdown=EXCLUDED.max_drawdown, profit_factor=EXCLUDED.profit_factor,
                            total_pnl=EXCLUDED.total_pnl, computed_at=CURRENT_TIMESTAMP,
                            to_date=EXCLUDED.to_date
                    """),
                    {
                        "sid": strategy_id, "sym": symbol,
                        "tt": m["total_trades"], "wr": m["win_rate"],
                        "cagr": m["cagr"], "sharpe": m["sharpe_ratio"],
                        "dd": m["max_drawdown"], "pf": m["profit_factor"],
                        "tpnl": m["total_pnl"],
                        "to_date": str(to_date),
                    },
                )
                count += 1
                if count % 10 == 0:
                    self.db.commit()
                    logger.info("[precompute] %s: %d/%d symbols done", row[0], count, len(symbols))
            except Exception as e:
                logger.warning("[precompute] %s/%s: %s", row[0], symbol, e)

        self.db.commit()
        if skipped:
            logger.info("[precompute] %s: %d symbols skipped (already current), %d updated",
                        row[0], skipped, count)
        else:
            logger.info("[precompute] %s complete: %d symbols", row[0], count)
        return count

    def _save_result(
        self, symbol: str, from_date: date, to_date: date,
        strategy_id: Optional[int], metrics: dict, trades: list[SimTrade],
    ) -> int:
        # sortino_ratio stored as NULL — compute_metrics does not compute it yet
        result = self.db.execute(
            text("""
                INSERT INTO backtest_results
                    (strategy_id, symbol, from_date, to_date,
                     total_trades, win_rate, cagr, sharpe_ratio,
                     sortino_ratio, max_drawdown, profit_factor,
                     avg_return_pct, full_metrics_json, ran_at)
                VALUES (:sid, :sym, :fd, :td,
                        :tt, :wr, :cagr, :sharpe,
                        NULL, :dd, :pf, :ar, :fmj, CURRENT_TIMESTAMP)
            """),
            {
                "sid": strategy_id,
                "sym": symbol,
                "fd": str(from_date),
                "td": str(to_date),
                "tt": metrics["total_trades"],
                "wr": metrics["win_rate"],
                "cagr": metrics["cagr"],
                "sharpe": metrics["sharpe_ratio"],
                "dd": metrics["max_drawdown"],
                "pf": metrics["profit_factor"],
                "ar": metrics["avg_return_pct"],
                "fmj": json.dumps(metrics),
            },
        )
        result_id = result.lastrowid

        for t in trades:
            self.db.execute(
                text("""
                    INSERT INTO backtest_trades
                        (backtest_result_id, symbol, entry_date, entry_price,
                         exit_date, exit_price, quantity, pnl, pnl_pct,
                         exit_reason, holding_days)
                    VALUES (:rid, :sym, :ed, :ep, :xd, :xp, :qty, :pnl, :ppct, :er, :hd)
                """),
                {
                    "rid": result_id, "sym": t.symbol,
                    "ed": str(t.entry_date), "ep": t.entry_price,
                    "xd": str(t.exit_date), "xp": t.exit_price,
                    "qty": t.quantity, "pnl": t.pnl, "ppct": t.pnl_pct,
                    "er": t.exit_reason, "hd": t.holding_days,
                },
            )

        self.db.commit()
        return result_id
