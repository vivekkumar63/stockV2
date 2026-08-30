import logging
import math
from dataclasses import dataclass
from datetime import date, timedelta
from types import SimpleNamespace
from typing import Optional

import pandas as pd

from domains.data.indicators import IndicatorEngine
from domains.portfolio.position_sizer import PositionSizer
from domains.special_strategies.base import SpecialBaseStrategy

logger = logging.getLogger(__name__)

_SIZING_STOP_PCT = 7.0   # used only for position sizing, NOT as an exit trigger


@dataclass
class SpecialTrade:
    symbol: str
    entry_date: date
    entry_price: float
    exit_date: date
    exit_price: float
    quantity: int
    exit_reason: str  # "sell_signal" | "end_of_period"
    pnl: float
    pnl_pct: float
    holding_days: int


@dataclass
class _OpenPos:
    entry_date: date
    entry_price: float
    quantity: int


class SpecialSimulator:
    def run(
        self,
        symbol: str,
        prices_df: pd.DataFrame,
        from_date: date,
        to_date: date,
        strategy: SpecialBaseStrategy,
        initial_capital: float = 500_000.0,
        _df_ind_precomputed: Optional[pd.DataFrame] = None,
    ) -> list[SpecialTrade]:
        cfg = SimpleNamespace(
            total_capital=initial_capital,
            paper_capital=initial_capital,
            risk_per_trade_pct=2.0,
            max_open_positions=8,
            max_single_stock_pct=20.0,
        )
        sizer = PositionSizer()

        df = prices_df.copy()
        if not df.empty and not isinstance(df["date"].iloc[0], date):
            df["date"] = pd.to_datetime(df["date"]).dt.date
        df = df.sort_values("date").reset_index(drop=True)

        df_ind = _df_ind_precomputed if _df_ind_precomputed is not None else IndicatorEngine.compute(df)
        if not isinstance(df_ind["date"].iloc[0], date):
            df_ind = df_ind.copy()
            df_ind["date"] = pd.to_datetime(df_ind["date"]).dt.date

        dates = df_ind["date"].tolist()
        date_to_idx = {d: i for i, d in enumerate(dates)}
        trading_dates = [d for d in dates if from_date <= d <= to_date]

        trades: list[SpecialTrade] = []
        open_pos: Optional[_OpenPos] = None

        for current_date in trading_dates:
            idx = date_to_idx[current_date]
            if idx < 30:
                continue
            current_price = float(df_ind["close"].iat[idx])
            if not math.isfinite(current_price):
                continue

            _start = max(0, idx - 499)
            df_slice = df_ind.iloc[_start:idx + 1]

            if open_pos is not None:
                try:
                    should_sell = strategy.sell_signal(df_slice, entry_price=open_pos.entry_price)
                except Exception:
                    should_sell = False
                if should_sell:
                    trades.append(self._close(symbol, open_pos, current_price, current_date, "sell_signal"))
                    open_pos = None
                    continue

            if open_pos is None:
                try:
                    sig = strategy.buy_signal(df_slice)
                except Exception:
                    continue
                if sig.signal_type == "BUY":
                    sl = round(current_price * (1 - _SIZING_STOP_PCT / 100), 2)
                    tgt = round(current_price * (1 + 15.0 / 100), 2)
                    sized = sizer.compute(
                        entry_price=current_price,
                        stop_loss_price=sl,
                        target_price=tgt,
                        open_positions=0,
                        invested_capital=0.0,
                        _cfg=cfg,
                    )
                    if sized.is_valid:
                        open_pos = _OpenPos(
                            entry_date=current_date,
                            entry_price=current_price,
                            quantity=sized.quantity,
                        )

        if open_pos is not None and trading_dates:
            last_row = df_ind[df_ind["date"] <= to_date].iloc[-1]
            last_price = float(last_row["close"])
            actual_last_date = last_row["date"]
            trades.append(self._close(symbol, open_pos, last_price, actual_last_date, "end_of_period"))

        return trades

    def _close(
        self, symbol: str, pos: _OpenPos, price: float, exit_date: date, reason: str
    ) -> SpecialTrade:
        raw_pnl = round((price - pos.entry_price) * pos.quantity, 2)
        entry_value = pos.entry_price * pos.quantity
        pnl_pct = round(raw_pnl / entry_value * 100, 2) if entry_value else 0.0
        return SpecialTrade(
            symbol=symbol,
            entry_date=pos.entry_date,
            entry_price=pos.entry_price,
            exit_date=exit_date,
            exit_price=price,
            quantity=pos.quantity,
            exit_reason=reason,
            pnl=raw_pnl,
            pnl_pct=pnl_pct,
            holding_days=(exit_date - pos.entry_date).days,
        )
