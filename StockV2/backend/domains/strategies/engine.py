import json
import logging
from datetime import date

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from domains.data.indicators import IndicatorEngine
from domains.strategies.aggregator import SignalAggregator
from domains.strategies.base import BaseStrategy, Signal
from domains.strategies.strategies.rsi_oversold import RSIOversoldStrategy
from domains.strategies.strategies.macd_crossover import MACDCrossoverStrategy
from domains.strategies.strategies.ema_crossover import EMACrossoverStrategy
from domains.strategies.strategies.sma_crossover import SMACrossoverStrategy
from domains.strategies.strategies.supertrend_strategy import SuperTrendStrategy
from domains.strategies.strategies.bb_squeeze import BBSqueezeStrategy
from domains.strategies.strategies.volume_breakout import VolumeBreakoutStrategy
from domains.strategies.strategies.mean_reversion import MeanReversionStrategy
from domains.strategies.strategies.volatility_breakout import VolatilityBreakoutStrategy
from domains.strategies.strategies.swing_trend_rider import SwingTrendRiderStrategy

logger = logging.getLogger(__name__)

ALL_STRATEGIES: list[BaseStrategy] = [
    RSIOversoldStrategy(),
    MACDCrossoverStrategy(),
    EMACrossoverStrategy(),
    SMACrossoverStrategy(),
    SuperTrendStrategy(),
    BBSqueezeStrategy(),
    VolumeBreakoutStrategy(),
    MeanReversionStrategy(),
    VolatilityBreakoutStrategy(),
    SwingTrendRiderStrategy(),
]


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
            symbol_signals: list[tuple[BaseStrategy, Signal]] = []
            for strategy in ALL_STRATEGIES:
                signal = strategy.generate_signal(df)
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
                SELECT date, open, high, low, close, volume
                FROM stock_prices_daily
                WHERE symbol = :s
                ORDER BY date ASC
                LIMIT :lim
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
