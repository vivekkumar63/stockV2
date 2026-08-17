import logging
import statistics
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from domains.backtest.metrics import compute_metrics
from domains.backtest.simulator import BacktestSimulator
from domains.data.indicators import IndicatorEngine
from domains.strategies.engine import ALL_STRATEGIES

logger = logging.getLogger(__name__)


@dataclass
class WalkForwardWindow:
    window_index: int
    train_from: date
    train_to: date
    test_from: date
    test_to: date
    oos_metrics: dict


@dataclass
class WalkForwardResult:
    symbol: str
    strategy_id: int
    n_windows: int
    windows: list[WalkForwardWindow]
    oos_win_rate_mean: Optional[float]
    oos_win_rate_std: Optional[float]
    consistency_score: float
    in_sample_win_rate: Optional[float]


class WalkForwardRunner:
    def run(
        self,
        symbol: str,
        strategy_id: int,
        db: Session,
        train_months: int = 12,
        test_months: int = 3,
        round_trip_cost_pct: float = 0.30,
    ) -> WalkForwardResult:
        row = db.execute(
            text("SELECT name FROM strategies WHERE id = :id"), {"id": strategy_id}
        ).fetchone()
        if not row:
            raise ValueError(f"Strategy id={strategy_id} not found")
        strat_name = row[0]
        strat = next((s for s in ALL_STRATEGIES if s.name == strat_name), None)
        if not strat:
            raise ValueError(f"Strategy '{strat_name}' not in ALL_STRATEGIES")

        rows = db.execute(
            text("""
                SELECT date, open, high, low, close, volume
                FROM stock_prices_daily
                WHERE symbol = :sym
                ORDER BY date ASC
            """),
            {"sym": symbol},
        ).fetchall()

        if len(rows) < 50:
            raise ValueError(f"Insufficient price data for {symbol}: {len(rows)} bars")

        df = pd.DataFrame([dict(r._mapping) for r in rows])
        df["date"] = pd.to_datetime(df["date"]).dt.date

        min_date, max_date = df["date"].min(), df["date"].max()

        windows: list[WalkForwardWindow] = []
        window_idx = 0
        simulator = BacktestSimulator()

        test_start = min_date + timedelta(days=train_months * 30)
        while test_start <= max_date:
            test_end = test_start + timedelta(days=test_months * 30)
            if test_end > max_date:
                test_end = max_date

            train_start = test_start - timedelta(days=train_months * 30)

            df_window = df[(df["date"] >= train_start) & (df["date"] <= test_end)]
            if df_window.empty or len(df_window) < 50:
                test_start += timedelta(days=test_months * 30)
                continue

            df_ind = IndicatorEngine.compute(df_window)
            trades = simulator.run(
                symbol=symbol,
                prices_df=df_window,
                from_date=test_start,
                to_date=test_end,
                strategies=[strat],
                use_aggregator=False,
                initial_capital=500_000.0,
                _df_ind_precomputed=df_ind,
                round_trip_cost_pct=round_trip_cost_pct,
            )

            oos_metrics = compute_metrics(trades, 500_000.0, test_start, test_end)
            windows.append(WalkForwardWindow(
                window_index=window_idx,
                train_from=train_start,
                train_to=test_start - timedelta(days=1),
                test_from=test_start,
                test_to=test_end,
                oos_metrics=oos_metrics,
            ))

            window_idx += 1
            test_start += timedelta(days=test_months * 30)

        if not windows:
            return WalkForwardResult(
                symbol=symbol, strategy_id=strategy_id, n_windows=0, windows=[],
                oos_win_rate_mean=None, oos_win_rate_std=None,
                consistency_score=0.0, in_sample_win_rate=None,
            )

        oos_win_rates = [w.oos_metrics["win_rate"] for w in windows if w.oos_metrics["win_rate"] is not None]
        oos_win_rate_mean = round(statistics.mean(oos_win_rates), 4) if oos_win_rates else None
        oos_win_rate_std = round(statistics.stdev(oos_win_rates), 4) if len(oos_win_rates) > 1 else None

        winning_windows = sum(1 for wr in oos_win_rates if wr >= 0.45)
        consistency_score = round(winning_windows / len(oos_win_rates), 4) if oos_win_rates else 0.0

        df_ind_full = IndicatorEngine.compute(df)
        is_trades = simulator.run(
            symbol=symbol, prices_df=df,
            from_date=min_date, to_date=max_date,
            strategies=[strat], use_aggregator=False,
            initial_capital=500_000.0, _df_ind_precomputed=df_ind_full,
            round_trip_cost_pct=round_trip_cost_pct,
        )
        is_metrics = compute_metrics(is_trades, 500_000.0, min_date, max_date)

        return WalkForwardResult(
            symbol=symbol,
            strategy_id=strategy_id,
            n_windows=len(windows),
            windows=windows,
            oos_win_rate_mean=oos_win_rate_mean,
            oos_win_rate_std=oos_win_rate_std,
            consistency_score=consistency_score,
            in_sample_win_rate=is_metrics["win_rate"],
        )
