import importlib
import inspect
import json
import logging
import pkgutil
from datetime import date
from pathlib import Path

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from domains.data.indicators import IndicatorEngine
from domains.strategies.aggregator import SignalAggregator
from domains.strategies.base import BaseStrategy, Signal

logger = logging.getLogger(__name__)


def _discover_strategies() -> list[BaseStrategy]:
    """Auto-discover every BaseStrategy subclass in the strategies/ sub-package.

    To add a new strategy:
      1. Drop a .py file into domains/strategies/strategies/
         (copy _template.py as a starting point)
      2. Define a class that inherits BaseStrategy and sets a unique `name`
      3. Restart the backend — it is auto-imported, instantiated, added to
         ALL_STRATEGIES, and seeded into the DB via seed_strategies()

    Files starting with '_' (e.g. _template.py, __init__.py) are skipped.
    """
    found: dict[str, BaseStrategy] = {}
    package_dir = Path(__file__).parent / "strategies"

    for module_info in pkgutil.iter_modules([str(package_dir)]):
        if module_info.name.startswith("_"):
            continue
        try:
            module = importlib.import_module(
                f"domains.strategies.strategies.{module_info.name}"
            )
        except Exception as e:
            logger.warning("[discover_strategies] import failed — %s: %s", module_info.name, e)
            continue

        for _, cls in inspect.getmembers(module, inspect.isclass):
            if (
                cls.__module__ == module.__name__  # defined in this file, not just imported
                and issubclass(cls, BaseStrategy)
                and cls is not BaseStrategy
                and getattr(cls, "name", "")       # name must be a non-empty string
                and cls.name not in found          # deduplicate across files
            ):
                try:
                    found[cls.name] = cls()
                except Exception as e:
                    logger.warning(
                        "[discover_strategies] instantiation failed — %s: %s", cls.__name__, e
                    )

    strategies = sorted(found.values(), key=lambda s: s.name)
    logger.info(
        "[discover_strategies] %d strategies loaded: %s",
        len(strategies),
        [s.name for s in strategies],
    )
    return strategies


ALL_STRATEGIES: list[BaseStrategy] = _discover_strategies()


class StrategyEngine:
    def __init__(self, db: Session):
        self.db = db
        self.aggregator = SignalAggregator()
        self._strategy_id_map: dict[str, int] = self._load_strategy_ids()

    def _load_strategy_ids(self) -> dict[str, int]:
        rows = self.db.execute(text("SELECT id, name FROM strategies")).fetchall()
        return {row[1]: row[0] for row in rows}

    def scan_all(self, symbols: list[str], scan_date: date) -> dict[str, dict]:
        results: dict[str, dict] = {}
        for symbol in symbols:
            df = self._load_prices(symbol)
            if df.empty or len(df) < 30:
                continue
            df = IndicatorEngine.compute(df)
            from domains.data.fundamentals import FundamentalsService
            fundamentals = FundamentalsService(self.db).get_latest(symbol)
            symbol_signals: list[tuple[BaseStrategy, Signal]] = []
            for strategy in ALL_STRATEGIES:
                signal = strategy.generate_signal(df, fundamentals=fundamentals)
                symbol_signals.append((strategy, signal))
                if signal.signal_type != "NONE":
                    self._save_signal(symbol, strategy, signal, float(df["close"].iloc[-1]), scan_date)
            agg = self.aggregator.aggregate(symbol_signals)
            if agg["signal_type"] != "NONE":
                results[symbol] = agg
        self.db.commit()
        logger.info("[StrategyEngine] scan_all: %d/%d symbols with signals", len(results), len(symbols))
        return results

    def _load_prices(self, symbol: str, limit: int = 200) -> pd.DataFrame:
        rows = self.db.execute(
            text("""
                SELECT date, open, high, low, close, volume FROM (
                    SELECT date, open, high, low, close, volume
                    FROM stock_prices_daily
                    WHERE symbol = :s
                    ORDER BY date DESC
                    LIMIT :lim
                ) ORDER BY date ASC
            """),
            {"s": symbol, "lim": limit},
        ).fetchall()
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"])
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].astype(float)
        return df

    def _save_signal(self, symbol: str, strategy: BaseStrategy, signal: Signal, price: float, scan_date: date):
        strategy_id = self._strategy_id_map.get(strategy.name)
        if strategy_id is None:
            logger.warning("[StrategyEngine] Strategy not in DB: %s", strategy.name)
            return
        stop_loss = price * (1 - signal.stop_loss_pct / 100) if signal.stop_loss_pct > 0 else None
        target = price * (1 + signal.target_pct / 100) if signal.target_pct > 0 else None
        self.db.execute(
            text("""
                INSERT OR REPLACE INTO strategy_signals
                (symbol, strategy_id, signal_date, signal_type, price_at_signal,
                 confidence_score, risk_score, expected_upside_pct,
                 suggested_stop_loss, suggested_target, holding_period_days,
                 reasoning_json, indicators_json, created_at)
                VALUES (:sym, :sid, :sdate, :stype, :price, :conf, :risk, :upside,
                        :sl, :tgt, :hdays, :reasoning, :indicators, datetime('now'))
            """),
            {
                "sym": symbol,
                "sid": strategy_id,
                "sdate": str(scan_date),
                "stype": signal.signal_type,
                "price": price,
                "conf": signal.confidence,
                "risk": signal.risk_score,
                "upside": signal.expected_upside_pct,
                "sl": stop_loss,
                "tgt": target,
                "hdays": signal.holding_days,
                "reasoning": json.dumps({
                    "conditions_met": signal.conditions_met,
                    "conditions_failed": signal.conditions_failed,
                }),
                "indicators": json.dumps(strategy.get_required_indicators()),
            },
        )
