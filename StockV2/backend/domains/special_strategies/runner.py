import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from typing import Optional

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from database import SessionLocal
from domains.backtest.metrics import compute_metrics
from domains.data.indicator_cache import IndicatorCache
from domains.special_strategies import ALL_SPECIAL_STRATEGIES
from domains.special_strategies.simulator import SpecialSimulator

logger = logging.getLogger(__name__)

_FROM_DATE = date(2015, 1, 1)
_INITIAL_CAPITAL = 500_000.0


class SpecialBacktestRunner:
    def __init__(self, db: Session):
        self.db = db

    def precompute_all(self, force: bool = False, _state: Optional[dict] = None) -> int:
        def _upd(done, total, phase, message):
            if _state is not None:
                _state.update(done=done, total=total, phase=phase, message=message)

        _upd(0, 1, "starting", "Initializing…")

        # ── Phase 1: Load metadata ────────────────────────────────────────────
        id_map: dict[str, int] = {
            r[0]: r[1]
            for r in self.db.execute(text("SELECT name, id FROM special_strategies")).fetchall()
        }
        strategies = [(id_map[s.name], s) for s in ALL_SPECIAL_STRATEGIES if s.name in id_map]
        if not strategies:
            _upd(0, 0, "done", "No special strategies seeded")
            return 0

        sym_rows = self.db.execute(
            text("SELECT DISTINCT symbol FROM stock_prices_daily ORDER BY symbol")
        ).fetchall()
        symbols = [r[0] for r in sym_rows]

        if not symbols:
            _upd(0, 0, "done", "No symbols in price data")
            return 0

        # Build set of pairs to skip (already current) unless force
        existing: dict[tuple, str] = {}  # (symbol, sid) -> to_date str
        if not force:
            rows = self.db.execute(
                text("SELECT symbol, special_strategy_id, to_date FROM special_strategy_performance")
            ).fetchall()
            existing = {(r[0], r[1]): str(r[2]) for r in rows}

        last_price_date: dict[str, str] = {
            r[0]: str(r[1])
            for r in self.db.execute(
                text("SELECT symbol, MAX(date) FROM stock_prices_daily GROUP BY symbol")
            ).fetchall()
        }

        pairs_needed: list[tuple] = []
        for sym in symbols:
            lpd = last_price_date.get(sym)
            if not lpd:
                continue
            for sid, strat in strategies:
                key = (sym, sid)
                if not force and key in existing and existing[key] >= lpd:
                    continue
                pairs_needed.append((sym, sid, strat, lpd))

        if not pairs_needed:
            _upd(0, 0, "done", "All pairs already current")
            return 0

        logger.info("[SpecialRunner] %d pairs to compute across %d symbols × %d strategies",
                    len(pairs_needed), len(symbols), len(strategies))

        total = len(pairs_needed)
        _upd(0, total, "phase2", f"Computing {total} symbol×strategy pairs…")

        # ── Phase 2: Parallel computation ─────────────────────────────────────
        n_workers = max(2, (os.cpu_count() or 4) // 2)
        # Group pairs by symbol so we compute indicators once per symbol
        by_symbol: dict[str, list[tuple]] = {}
        for item in pairs_needed:
            sym = item[0]
            by_symbol.setdefault(sym, []).append(item)

        results: list[tuple] = []  # (symbol, sid, metrics, to_date_str)
        done_count = 0

        def _process_symbol(sym: str, sym_pairs: list[tuple]) -> list[tuple]:
            thread_db = SessionLocal()
            try:
                # Load full price history
                price_rows = thread_db.execute(
                    text("""
                        SELECT date, open, high, low, close, volume
                        FROM stock_prices_daily WHERE symbol = :s ORDER BY date ASC
                    """),
                    {"s": sym},
                ).fetchall()
                if len(price_rows) < 50:
                    return []
                prices_df = pd.DataFrame([dict(r._mapping) for r in price_rows])
                prices_df["date"] = pd.to_datetime(prices_df["date"]).dt.date

                # Load or compute indicators via cache
                df_ind = IndicatorCache(thread_db).get(sym, prices_df)
                if df_ind.empty:
                    return []
                if not isinstance(df_ind["date"].iloc[0], date):
                    df_ind = df_ind.copy()
                    df_ind["date"] = pd.to_datetime(df_ind["date"]).dt.date

                symbol_results = []
                sim = SpecialSimulator()
                to_date_val = df_ind["date"].max()

                for _sym, sid, strat, lpd in sym_pairs:
                    try:
                        trades = sim.run(
                            symbol=sym,
                            prices_df=prices_df,
                            from_date=_FROM_DATE,
                            to_date=to_date_val,
                            strategy=strat,
                            initial_capital=_INITIAL_CAPITAL,
                            _df_ind_precomputed=df_ind,
                        )
                        metrics = compute_metrics(trades, _INITIAL_CAPITAL, _FROM_DATE, to_date_val)
                        symbol_results.append((sym, sid, metrics, str(to_date_val)))
                    except Exception as e:
                        logger.warning("[SpecialRunner] %s/%s failed: %s", sym, strat.name, e)
                return symbol_results
            except Exception as e:
                logger.warning("[SpecialRunner] symbol %s worker error: %s", sym, e)
                return []
            finally:
                thread_db.close()

        with ThreadPoolExecutor(max_workers=n_workers) as pool:
            futures = {
                pool.submit(_process_symbol, sym, sym_pairs): sym
                for sym, sym_pairs in by_symbol.items()
            }
            for fut in as_completed(futures):
                sym = futures[fut]
                try:
                    sym_results = fut.result()
                    results.extend(sym_results)
                    done_count += len(sym_results)
                except Exception as e:
                    logger.warning("[SpecialRunner] future error for %s: %s", sym, e)
                _upd(done_count, total, "phase2",
                     f"Computed {done_count}/{total} pairs ({sym})")

        # ── Phase 3: Sequential DB write ──────────────────────────────────────
        _upd(done_count, total, "phase3", f"Writing {len(results)} results to DB…")
        _CHUNK = 50
        written = 0
        for i in range(0, len(results), _CHUNK):
            batch = results[i: i + _CHUNK]
            for sym, sid, m, to_date_str in batch:
                self.db.execute(
                    text("""
                        INSERT INTO special_strategy_performance
                            (special_strategy_id, symbol, total_trades, win_rate, cagr,
                             sharpe_ratio, max_drawdown, profit_factor, total_pnl, avg_pnl_pct, to_date, computed_at)
                        VALUES (:sid, :sym, :tt, :wr, :cagr, :sh, :dd, :pf, :pnl, :apct, :td, CURRENT_TIMESTAMP)
                        ON CONFLICT (special_strategy_id, symbol) DO UPDATE SET
                            total_trades = EXCLUDED.total_trades,
                            win_rate     = EXCLUDED.win_rate,
                            cagr         = EXCLUDED.cagr,
                            sharpe_ratio = EXCLUDED.sharpe_ratio,
                            max_drawdown = EXCLUDED.max_drawdown,
                            profit_factor= EXCLUDED.profit_factor,
                            total_pnl    = EXCLUDED.total_pnl,
                            avg_pnl_pct  = EXCLUDED.avg_pnl_pct,
                            to_date      = EXCLUDED.to_date,
                            computed_at  = EXCLUDED.computed_at
                    """),
                    {
                        "sid": sid, "sym": sym,
                        "tt": m["total_trades"],
                        "wr": m.get("win_rate"),
                        "cagr": m.get("cagr"),
                        "sh": m.get("sharpe_ratio"),
                        "dd": m.get("max_drawdown"),
                        "pf": m.get("profit_factor"),
                        "pnl": m.get("total_pnl", 0.0),
                        "apct": m.get("avg_return_pct"),
                        "td": to_date_str,
                    },
                )
                written += 1
            self.db.commit()
            time.sleep(0.01)

        _upd(written, total, "done", f"Done — {written} pairs updated")
        logger.info("[SpecialRunner] precompute complete: %d pairs written", written)
        return written
