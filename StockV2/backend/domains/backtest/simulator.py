import logging
from dataclasses import dataclass
from datetime import date, timedelta
from types import SimpleNamespace
from typing import Optional

import pandas as pd

from domains.data.indicators import IndicatorEngine
from domains.strategies.aggregator import SignalAggregator
from domains.portfolio.position_sizer import PositionSizer

logger = logging.getLogger(__name__)


@dataclass
class SimTrade:
    symbol: str
    entry_date: date
    entry_price: float
    exit_date: date
    exit_price: float
    quantity: int
    stop_loss_price: float
    target_price: float
    exit_reason: str  # "stop_loss" | "target_hit" | "max_holding_days" | "end_of_period"
    pnl: float
    pnl_pct: float
    holding_days: int
    commission: float = 0.0


@dataclass
class _OpenPosition:
    entry_date: date
    entry_price: float
    quantity: int
    stop_loss_price: float
    target_price: float
    max_exit_date: date


class BacktestSimulator:
    def run(
        self,
        symbol: str,
        prices_df: pd.DataFrame,
        from_date: date,
        to_date: date,
        strategies: list,
        initial_capital: float = 500_000.0,
        risk_per_trade_pct: float = 2.0,
        max_single_stock_pct: float = 20.0,
        use_aggregator: bool = True,
        _df_ind_precomputed: Optional[pd.DataFrame] = None,
        stop_loss_pct_override: Optional[float] = None,
        target_pct_override: Optional[float] = None,
        round_trip_cost_pct: float = 0.0,
    ) -> list[SimTrade]:
        cfg = SimpleNamespace(
            total_capital=initial_capital,
            paper_capital=initial_capital,
            risk_per_trade_pct=risk_per_trade_pct,
            max_open_positions=8,
            max_single_stock_pct=max_single_stock_pct,
        )
        aggregator = SignalAggregator()
        sizer = PositionSizer()

        df = prices_df.copy()
        # Normalize date column to Python date objects
        if not df.empty and not isinstance(df["date"].iloc[0], date):
            df["date"] = pd.to_datetime(df["date"]).dt.date
        df = df.sort_values("date").reset_index(drop=True)

        mask = (df["date"] >= from_date) & (df["date"] <= to_date)
        trading_dates = df.loc[mask, "date"].tolist()

        # Pre-build date→position lookup once (O(n)) before the loop
        date_to_idx = {d: i for i, d in enumerate(df["date"])}

        # Pre-compute indicators once on the full df — indicators are all rolling/cumulative
        # so df_ind_full.iloc[:idx+1] equals IndicatorEngine.compute(df.iloc[:idx+1]).
        # This reduces indicator overhead from O(n²) to O(n).
        # _df_ind_precomputed lets callers (e.g. scan_all) skip recomputation across strategies.
        df_ind_full = _df_ind_precomputed if _df_ind_precomputed is not None else IndicatorEngine.compute(df)

        trades: list[SimTrade] = []
        open_pos: Optional[_OpenPosition] = None

        for current_date in trading_dates:
            idx = date_to_idx[current_date]
            if idx < 30:
                continue

            current_price = float(df["close"].iat[idx])

            # Check exits before entries
            if open_pos:
                reason = self._check_exit(open_pos, current_price, current_date)
                if reason:
                    trades.append(self._close(symbol, open_pos, current_price, current_date, reason, round_trip_cost_pct))
                    open_pos = None

            if open_pos is None:
                df_ind = df_ind_full.iloc[: idx + 1]

                if use_aggregator:
                    pairs = [(s, s.generate_signal(df_ind)) for s in strategies]
                    consensus = aggregator.aggregate(pairs)
                    should_enter = consensus["signal_type"] == "BUY"
                    buy_sigs = [sig for _, sig in pairs if sig.signal_type == "BUY"]
                    stop_pct = stop_loss_pct_override if stop_loss_pct_override is not None else (
                        (sum(s.stop_loss_pct for s in buy_sigs) / len(buy_sigs)) if buy_sigs else 7.0
                    )
                    tgt_pct = target_pct_override if target_pct_override is not None else (
                        (sum(s.target_pct for s in buy_sigs) / len(buy_sigs)) if buy_sigs else 15.0
                    )
                    h_days = int(sum(s.holding_days for s in buy_sigs) / len(buy_sigs)) if buy_sigs else 15
                else:
                    sig = strategies[0].generate_signal(df_ind)
                    should_enter = sig.signal_type == "BUY"
                    stop_pct = stop_loss_pct_override if stop_loss_pct_override is not None else sig.stop_loss_pct
                    tgt_pct = target_pct_override if target_pct_override is not None else sig.target_pct
                    h_days = sig.holding_days

                if should_enter:
                    sl = round(current_price * (1 - stop_pct / 100), 2)
                    tgt = round(current_price * (1 + tgt_pct / 100), 2)
                    # open_positions=0 and invested_capital=0.0 are correct here:
                    # exits are evaluated before entries, so open_pos is always None at this point.
                    pos = sizer.compute(
                        entry_price=current_price,
                        stop_loss_price=sl,
                        target_price=tgt,
                        open_positions=0,
                        invested_capital=0.0,
                        _cfg=cfg,
                    )
                    if pos.is_valid:
                        open_pos = _OpenPosition(
                            entry_date=current_date,
                            entry_price=current_price,
                            quantity=pos.quantity,
                            stop_loss_price=pos.stop_loss_price,
                            target_price=pos.target_price,
                            max_exit_date=current_date + timedelta(days=h_days),
                        )

        # Force-close any open position at end of period.
        # Use the actual last trading date (not to_date, which may be a weekend/holiday).
        if open_pos and trading_dates:
            last_row = df[df["date"] <= to_date].iloc[-1]
            last_price = float(last_row["close"])
            actual_last_date = last_row["date"]
            trades.append(self._close(symbol, open_pos, last_price, actual_last_date, "end_of_period", round_trip_cost_pct))

        return trades

    def _check_exit(self, pos: _OpenPosition, price: float, current_date: date) -> Optional[str]:
        if price <= pos.stop_loss_price:
            return "stop_loss"
        if price >= pos.target_price:
            return "target_hit"
        if current_date >= pos.max_exit_date:
            return "max_holding_days"
        return None

    def _close(self, symbol: str, pos: _OpenPosition, price: float,
               exit_date: date, reason: str, round_trip_cost_pct: float = 0.0) -> SimTrade:
        raw_pnl = round((price - pos.entry_price) * pos.quantity, 2)
        entry_value = pos.entry_price * pos.quantity
        commission = round(entry_value * round_trip_cost_pct / 100, 2)
        net_pnl = round(raw_pnl - commission, 2)
        pnl_pct = round((price - pos.entry_price) / pos.entry_price * 100, 2)
        return SimTrade(
            symbol=symbol,
            entry_date=pos.entry_date,
            entry_price=pos.entry_price,
            exit_date=exit_date,
            exit_price=price,
            quantity=pos.quantity,
            stop_loss_price=pos.stop_loss_price,
            target_price=pos.target_price,
            exit_reason=reason,
            pnl=net_pnl,
            pnl_pct=pnl_pct,
            holding_days=(exit_date - pos.entry_date).days,
            commission=commission,
        )
