import statistics
from dataclasses import dataclass
from datetime import date
from typing import Optional

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from domains.backtest.metrics import compute_metrics


@dataclass
class ExtendedMetrics:
    # All fields from compute_metrics() dict
    total_trades: int
    win_rate: Optional[float]
    total_pnl: float
    total_return_pct: float
    cagr: Optional[float]
    sharpe_ratio: Optional[float]
    max_drawdown: Optional[float]
    profit_factor: Optional[float]
    avg_return_pct: Optional[float]
    # New fields
    sortino_ratio: Optional[float]       # uses only downside deviation
    median_return_pct: Optional[float]   # median trade return
    regime_win_rates: dict               # {regime_label: win_rate}
    benchmark_deltas: dict               # {bah: float, best_single: float, sma_cross: float}


def compute_extended_metrics(
    trades: list,
    initial_capital: float,
    from_date: date,
    to_date: date,
    db: Session,
    benchmarks: dict,
) -> ExtendedMetrics:
    """Compute extended metrics from a list of SimTrade objects.

    trades: list of SimTrade (from BacktestSimulator)
    benchmarks: dict with keys buy_and_hold, best_single, sma_crossover (CAGR values)
    """
    base = compute_metrics(trades, initial_capital, from_date, to_date)

    # Sortino ratio — downside deviation only
    # When there are >= 2 downside samples use population stdev; when exactly 1,
    # use abs(single loss) as the downside deviation (avoids a zero-division on pstdev).
    sortino = None
    if trades:
        returns = [t.pnl_pct / 100.0 for t in trades]
        downside = [r for r in returns if r < 0]
        if len(downside) >= 1:
            mean_r = statistics.mean(returns)
            downside_std = statistics.pstdev(downside) if len(downside) > 1 else abs(downside[0])
            if downside_std > 0:
                sortino = round(mean_r / downside_std * (252 ** 0.5), 4)

    # Median trade return
    median_return_pct = None
    if trades:
        median_return_pct = round(statistics.median([t.pnl_pct for t in trades]), 4)

    # Regime win rates from market_regime table
    regime_win_rates: dict[str, Optional[float]] = {}
    if trades:
        for regime_label in ["BULL", "SIDEWAYS", "BEAR", "STRONG_BULL", "STRONG_BEAR"]:
            regime_trades = [
                t for t in trades
                if _get_regime_for_date(db, t.exit_date) == regime_label
            ]
            if regime_trades:
                wins = sum(1 for t in regime_trades if t.pnl > 0)
                regime_win_rates[regime_label] = round(wins / len(regime_trades), 4)
            else:
                regime_win_rates[regime_label] = None

    # Benchmark deltas
    oos_cagr = base["cagr"] or 0.0
    benchmark_deltas = {
        "bah": round(oos_cagr - benchmarks.get("buy_and_hold", 0.0), 4),
        "best_single": round(oos_cagr - benchmarks.get("best_single", 0.0), 4),
        "sma_cross": round(oos_cagr - benchmarks.get("sma_crossover", 0.0), 4),
    }

    return ExtendedMetrics(
        total_trades=base["total_trades"],
        win_rate=base["win_rate"],
        total_pnl=base["total_pnl"],
        total_return_pct=base["total_return_pct"],
        cagr=base["cagr"],
        sharpe_ratio=base["sharpe_ratio"],
        max_drawdown=base["max_drawdown"],
        profit_factor=base["profit_factor"],
        avg_return_pct=base["avg_return_pct"],
        sortino_ratio=sortino,
        median_return_pct=median_return_pct,
        regime_win_rates=regime_win_rates,
        benchmark_deltas=benchmark_deltas,
    )


def _get_regime_for_date(db: Session, d: date) -> Optional[str]:
    row = db.execute(
        text("SELECT regime FROM market_regime WHERE date = :d"),
        {"d": d}
    ).fetchone()
    return row[0] if row else None
