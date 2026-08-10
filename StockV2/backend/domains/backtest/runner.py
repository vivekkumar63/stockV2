import json
import logging
from datetime import date
from typing import Optional

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from domains.backtest.metrics import compute_metrics
from domains.backtest.simulator import BacktestSimulator, SimTrade
from domains.data.indicators import IndicatorEngine
from domains.strategies.engine import ALL_STRATEGIES

logger = logging.getLogger(__name__)


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
    ) -> list[dict]:
        if strategy_ids:
            placeholders = ",".join(str(int(i)) for i in strategy_ids)
            strats_rows = self.db.execute(
                text(f"SELECT id, name FROM strategies WHERE id IN ({placeholders}) AND is_active = 1")
            ).fetchall()
        else:
            strats_rows = self.db.execute(
                text("SELECT id, name FROM strategies WHERE is_active = 1")
            ).fetchall()

        strats_to_run = []
        for sid, sname in strats_rows:
            instances = [s for s in ALL_STRATEGIES if s.name == sname]
            if instances:
                strats_to_run.append((sid, sname, instances[0]))

        if not strats_to_run:
            return []

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

        results = []
        for symbol in symbols:
            rows = self.db.execute(
                text("SELECT date, open, high, low, close, volume FROM stock_prices_daily WHERE symbol = :sym ORDER BY date ASC"),
                {"sym": symbol},
            ).fetchall()
            if len(rows) < 50:
                continue

            df = pd.DataFrame([dict(r._mapping) for r in rows])
            df["date"] = pd.to_datetime(df["date"]).dt.date

            # Compute indicators once; reuse across all strategies for this stock
            df_ind = IndicatorEngine.compute(df)

            for sid, sname, strat in strats_to_run:
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
                    )
                    m = compute_metrics(trades, initial_capital, from_date, to_date)
                    results.append({
                        "symbol": symbol,
                        "strategy_id": sid,
                        "strategy_name": sname,
                        "total_trades": m["total_trades"],
                        "win_rate": m["win_rate"],
                        "cagr": m["cagr"],
                        "sharpe_ratio": m["sharpe_ratio"],
                        "max_drawdown": m["max_drawdown"],
                        "profit_factor": m["profit_factor"],
                        "total_pnl": m["total_pnl"],
                    })
                except Exception as e:
                    logger.warning("[scan] %s/%s: %s", symbol, sname, e)

        logger.info("[scan_all] %s→%s: %d results across %d symbols × %d strategies",
                    from_date, to_date, len(results), len(symbols), len(strats_to_run))
        return results

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
                        NULL, :dd, :pf, :ar, :fmj, datetime('now'))
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
