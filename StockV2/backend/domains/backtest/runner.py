import json
import logging
from datetime import date
from typing import Optional

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from domains.backtest.metrics import compute_metrics
from domains.backtest.simulator import BacktestSimulator, SimTrade
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
        rows = self.db.execute(
            text("""
                SELECT date, open, high, low, close, volume
                FROM stock_prices_daily
                WHERE symbol = :sym
                ORDER BY date ASC
            """),
            {"sym": symbol.upper()},
        ).fetchall()

        if len(rows) < 50:
            return {"error": f"Insufficient price data for {symbol}: {len(rows)} bars (need ≥ 50)"}

        df = pd.DataFrame([dict(r._mapping) for r in rows])

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
            use_aggregator = False
        else:
            strategies = list(ALL_STRATEGIES)
            use_aggregator = True

        trades = self.simulator.run(
            symbol=symbol.upper(),
            prices_df=df,
            from_date=from_date,
            to_date=to_date,
            strategies=strategies,
            use_aggregator=use_aggregator,
            initial_capital=initial_capital,
        )

        metrics = compute_metrics(trades, initial_capital, from_date, to_date)
        # strategy_id=0 is the sentinel for "all strategies / aggregator run"
        # because backtest_results.strategy_id is NOT NULL
        db_strategy_id = strategy_id if strategy_id is not None else 0
        result_id = self._save_result(symbol.upper(), from_date, to_date, db_strategy_id, metrics, trades)

        logger.info("[BacktestRunner] %s %s→%s: %d trades, result_id=%d",
                    symbol, from_date, to_date, len(trades), result_id)
        return {
            "result_id": result_id,
            "symbol": symbol.upper(),
            "from_date": str(from_date),
            "to_date": str(to_date),
            **metrics,
        }

    def _save_result(
        self, symbol: str, from_date: date, to_date: date,
        strategy_id: int, metrics: dict, trades: list[SimTrade],
    ) -> int:
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
