import logging
import math

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from domains.data.indicators import IndicatorEngine
from domains.special_strategies import ALL_SPECIAL_STRATEGIES
from domains.special_strategies.base import SpecialBaseStrategy

logger = logging.getLogger(__name__)


class SpecialScanner:
    def __init__(self, db: Session):
        self.db = db
        self._id_map: dict[str, int] = self._load_id_map()

    def _load_id_map(self) -> dict[str, int]:
        rows = self.db.execute(text("SELECT name, id FROM special_strategies")).fetchall()
        return {r[0]: r[1] for r in rows}

    def scan(self, strategy_id: int | None = None) -> list[dict]:
        strategies: list[SpecialBaseStrategy] = ALL_SPECIAL_STRATEGIES
        if strategy_id is not None:
            strategies = [s for s in ALL_SPECIAL_STRATEGIES if self._id_map.get(s.name) == strategy_id]
            if not strategies:
                return []

        symbols = self._get_symbols()
        logger.info("[SpecialScanner] scanning %d symbols with %d strategies", len(symbols), len(strategies))
        results: list[dict] = []

        for symbol in symbols:
            df = self._load_prices(symbol)
            if df.empty or len(df) < 30:
                continue
            try:
                df_ind = IndicatorEngine.compute(df)
            except Exception as e:
                logger.warning("[SpecialScanner] indicator compute failed for %s: %s", symbol, e)
                continue

            price = float(df_ind["close"].iloc[-1])
            if not math.isfinite(price):
                continue

            for strategy in strategies:
                try:
                    sig = strategy.buy_signal(df_ind)
                except Exception as e:
                    logger.warning("[SpecialScanner] %s on %s failed: %s", strategy.name, symbol, e)
                    continue
                if sig.signal_type != "BUY":
                    continue
                confidence = sig.confidence if math.isfinite(sig.confidence) else 0.0
                sid = self._id_map.get(strategy.name)
                results.append({
                    "symbol": symbol,
                    "strategy_id": sid,
                    "strategy_name": strategy.name,
                    "signal_type": sig.signal_type,
                    "confidence": round(confidence, 4),
                    "price": price,
                    "conditions_met": sig.conditions_met,
                })

        results.sort(key=lambda r: r["confidence"], reverse=True)
        logger.info("[SpecialScanner] %d buy signals found", len(results))
        return results

    def _get_symbols(self) -> list[str]:
        rows = self.db.execute(
            text("""
                SELECT DISTINCT symbol FROM stock_prices_daily
                WHERE date >= CURRENT_DATE - INTERVAL '10 days'
                ORDER BY symbol
            """)
        ).fetchall()
        return [r[0] for r in rows]

    def _load_prices(self, symbol: str) -> pd.DataFrame:
        rows = self.db.execute(
            text("""
                SELECT date, open, high, low, close, volume FROM (
                    SELECT date, open, high, low, close, volume
                    FROM stock_prices_daily
                    WHERE symbol = :s
                    ORDER BY date DESC
                    LIMIT 200
                ) ORDER BY date ASC
            """),
            {"s": symbol},
        ).fetchall()
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"])
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].astype(float)
        return df
