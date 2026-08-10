import statistics
from datetime import date
from typing import Optional

import pandas as pd


def compute_metrics(
    trades: list,
    initial_capital: float,
    from_date: date,
    to_date: date,
) -> dict:
    if not trades:
        return {
            "total_trades": 0,
            "win_rate": None,
            "total_pnl": 0.0,
            "total_return_pct": 0.0,
            "cagr": None,
            "sharpe_ratio": None,
            "max_drawdown": None,
            "profit_factor": None,
            "avg_return_pct": None,
        }

    total_trades = len(trades)
    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl <= 0]
    win_rate = round(len(wins) / total_trades, 4)

    total_pnl = round(sum(t.pnl for t in trades), 2)
    total_return_pct = round(total_pnl / initial_capital * 100, 4)

    days = max((to_date - from_date).days, 1)
    final_capital = initial_capital + total_pnl
    cagr = None
    if final_capital > 0:
        cagr = round(((final_capital / initial_capital) ** (365.0 / days) - 1) * 100, 4)

    gross_profit = sum(t.pnl for t in wins) if wins else 0.0
    gross_loss = abs(sum(t.pnl for t in losses)) if losses else 0.0
    profit_factor = round(gross_profit / gross_loss, 4) if gross_loss > 0 else None

    avg_return_pct = round(sum(t.pnl_pct for t in trades) / total_trades, 4)

    equity_curve = _build_equity_curve(trades, initial_capital, from_date, to_date)
    sharpe = _compute_sharpe(equity_curve)
    max_dd = _compute_max_drawdown(equity_curve)

    return {
        "total_trades": total_trades,
        "win_rate": win_rate,
        "total_pnl": total_pnl,
        "total_return_pct": total_return_pct,
        "cagr": cagr,
        "sharpe_ratio": sharpe,
        "max_drawdown": max_dd,
        "profit_factor": profit_factor,
        "avg_return_pct": avg_return_pct,
    }


def _build_equity_curve(trades: list, initial_capital: float,
                         from_date: date, to_date: date) -> list[float]:
    pnl_by_date: dict[date, float] = {}
    for t in trades:
        pnl_by_date[t.exit_date] = pnl_by_date.get(t.exit_date, 0.0) + t.pnl

    bdays = pd.bdate_range(from_date, to_date)
    equity = initial_capital
    curve: list[float] = []
    for d in bdays:
        equity += pnl_by_date.get(d.date(), 0.0)
        curve.append(equity)
    return curve


def _compute_sharpe(curve: list[float]) -> Optional[float]:
    if len(curve) < 3:
        return None
    returns = [(curve[i] - curve[i - 1]) / curve[i - 1] for i in range(1, len(curve))]
    if len(returns) < 2:
        return None
    mean_r = statistics.mean(returns)
    std_r = statistics.stdev(returns)
    if std_r == 0:
        return None
    return round(mean_r / std_r * (252 ** 0.5), 4)


def _compute_max_drawdown(curve: list[float]) -> Optional[float]:
    if not curve:
        return None
    peak = curve[0]
    max_dd = 0.0
    for v in curve:
        peak = max(peak, v)
        dd = (v - peak) / peak * 100
        if dd < max_dd:
            max_dd = dd
    return round(max_dd, 4)
