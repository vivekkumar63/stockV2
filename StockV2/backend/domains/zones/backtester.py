from __future__ import annotations
import logging
import math
from dataclasses import dataclass
from datetime import date
from typing import Optional

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from domains.data.indicators import IndicatorEngine
from .clusterer import ZoneClusterer
from .detectors import (
    FibonacciDetector, MADetector, MomentumDetector,
    PriceStructureDetector, VolatilityDetector, VolumeDetector,
)
from .models import Zone
from .scorer import ZoneScorer

logger = logging.getLogger(__name__)

_DETECTORS = [
    PriceStructureDetector(),
    MADetector(),
    VolumeDetector(),
    VolatilityDetector(),
    MomentumDetector(),
    FibonacciDetector(),
]


@dataclass
class ZoneTrade:
    symbol: str
    entry_date: date
    entry_price: float
    exit_date: date
    exit_price: float
    pnl_pct: float
    exit_reason: str   # "supply_zone" | "stop_loss" | "max_hold" | "end_of_period"
    hold_days: int


class ZoneBacktester:
    def run(self, symbol: str, from_date: date, to_date: date, db: Session) -> list[ZoneTrade]:
        """Load historical data from DB, build monthly zone snapshots, run simulation."""
        rows = db.execute(
            text("""
                SELECT date, open, high, low, close, volume FROM (
                    SELECT date, open, high, low, close, volume
                    FROM stock_prices_daily
                    WHERE symbol = :s
                    ORDER BY date DESC LIMIT 1000
                ) sub ORDER BY date ASC
            """),
            {"s": symbol},
        ).fetchall()
        if len(rows) < 30:
            return []

        df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"])
        for col in ("open", "high", "low", "close", "volume"):
            df[col] = df[col].astype(float)
        df_ind = IndicatorEngine.compute(df)
        df_ind["date"] = pd.to_datetime(df_ind["date"])

        snapshots = self._build_snapshots(df_ind, from_date, to_date)
        return self._simulate(symbol, df_ind, from_date, to_date, snapshots)

    def _build_snapshots(
        self,
        df_ind: pd.DataFrame,
        from_date: date,
        to_date: date,
    ) -> dict[tuple, tuple]:
        """Return {(year, month): (demand_zones, supply_zones, atr)} for each month in range.

        For each month, the snapshot uses only data strictly before the first observed
        trading day in that month (no look-ahead bias).
        """
        snapshots: dict[tuple, tuple] = {}
        all_dates = sorted(df_ind["date"].dt.date.tolist())
        sim_dates = [d for d in all_dates if from_date <= d <= to_date]
        seen: set[tuple] = set()

        for d in sim_dates:
            mk = (d.year, d.month)
            if mk in seen:
                continue
            seen.add(mk)

            # Use only data strictly before the first day of this month (no look-ahead)
            mask = df_ind["date"].dt.date < d
            df_hist = df_ind[mask]
            if len(df_hist) < 30:
                continue

            atr = float(df_hist["atr_14"].iloc[-1]) if "atr_14" in df_hist.columns else 0.0
            if not math.isfinite(atr) or atr <= 0:
                atr = float(df_hist["close"].iloc[-1]) * 0.01
            price_now = float(df_hist["close"].iloc[-1])

            levels = []
            for det in _DETECTORS:
                try:
                    levels.extend(det.detect(df_hist))
                except Exception as e:
                    logger.debug("[ZoneBacktester] detector %s failed: %s", type(det).__name__, e)

            all_zones = ZoneClusterer().cluster(levels, atr)
            scorer = ZoneScorer()
            n = len(df_hist)
            demand = scorer.score_all(
                [z for z in all_zones if z.zone_type == "demand"],
                atr=atr, n_bars=n, price=price_now,
            )
            supply = scorer.score_all(
                [z for z in all_zones if z.zone_type == "supply"],
                atr=atr, n_bars=n, price=price_now,
            )
            snapshots[mk] = (demand, supply, atr)

        return snapshots

    def _simulate(
        self,
        symbol: str,
        df_ind: pd.DataFrame,
        from_date: date,
        to_date: date,
        zone_snapshots: dict[tuple, tuple],
    ) -> list[ZoneTrade]:
        """Pure simulation — testable without DB."""
        all_dates = sorted(df_ind["date"].dt.date.tolist())
        sim_dates = [d for d in all_dates if from_date <= d <= to_date]
        if not sim_dates:
            return []

        trades: list[ZoneTrade] = []
        position: Optional[dict] = None   # {entry_date, entry_price, entry_zone, atr}
        pending_sell: Optional[str] = None
        pending_buy_zone: Optional[Zone] = None

        cur_demand: list[Zone] = []
        cur_supply: list[Zone] = []
        cur_atr: float = 0.0

        date_to_row = {d: df_ind[df_ind["date"].dt.date == d] for d in sim_dates}

        for d in sim_dates:
            mk = (d.year, d.month)
            if mk in zone_snapshots:
                cur_demand, cur_supply, cur_atr = zone_snapshots[mk]

            row = date_to_row[d]
            if row.empty:
                continue
            open_ = float(row["open"].iloc[0])
            close = float(row["close"].iloc[0])

            # Execute deferred actions at today's open
            if pending_sell and position:
                pnl_pct = (open_ - position["entry_price"]) / position["entry_price"] * 100
                hold = (d - position["entry_date"]).days
                trades.append(ZoneTrade(
                    symbol=symbol,
                    entry_date=position["entry_date"],
                    entry_price=position["entry_price"],
                    exit_date=d,
                    exit_price=open_,
                    pnl_pct=round(pnl_pct, 2),
                    exit_reason=pending_sell,
                    hold_days=hold,
                ))
                position = None
                pending_sell = None

            if pending_buy_zone is not None and position is None:
                position = {
                    "entry_date":  d,
                    "entry_price": open_,
                    "entry_zone":  pending_buy_zone,
                    "atr":         cur_atr,
                }
                pending_buy_zone = None

            # Detect conditions at today's close
            if position:
                hold = (d - position["entry_date"]).days
                if any(z.low <= close <= z.high for z in cur_supply):
                    pending_sell = "supply_zone"
                elif close < position["entry_zone"].low - 0.5 * position["atr"]:
                    pending_sell = "stop_loss"
                elif hold >= 20:
                    pending_sell = "max_hold"
            elif pending_buy_zone is None:
                for z in cur_demand:
                    if z.low <= close <= z.high:
                        pending_buy_zone = z
                        break

        # Force-close open position at end of period
        if position:
            last_row = date_to_row.get(sim_dates[-1], pd.DataFrame())
            if not last_row.empty:
                exit_price = float(last_row["close"].iloc[0])
                pnl_pct = (exit_price - position["entry_price"]) / position["entry_price"] * 100
                trades.append(ZoneTrade(
                    symbol=symbol,
                    entry_date=position["entry_date"],
                    entry_price=position["entry_price"],
                    exit_date=sim_dates[-1],
                    exit_price=exit_price,
                    pnl_pct=round(pnl_pct, 2),
                    exit_reason="end_of_period",
                    hold_days=(sim_dates[-1] - position["entry_date"]).days,
                ))

        return trades
