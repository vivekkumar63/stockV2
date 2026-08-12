import logging

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from domains.data.indicators import IndicatorEngine
from domains.strategies.engine import ALL_STRATEGIES

logger = logging.getLogger(__name__)


class LiveScanner:
    """Run strategies against all stocks using current price data and return
    only the stocks where a strategy fires a BUY or SELL signal."""

    def __init__(self, db: Session):
        self.db = db
        self._id_map: dict[str, int] = self._load_id_map()

    def _load_id_map(self) -> dict[str, int]:
        rows = self.db.execute(text("SELECT name, id FROM strategies")).fetchall()
        return {r[0]: r[1] for r in rows}

    def scan(
        self,
        strategy_id: int | None = None,
        signal_type: str | None = None,
        limit: int = 200,
    ) -> list[dict]:
        strategies = ALL_STRATEGIES
        if strategy_id is not None:
            strategies = [s for s in ALL_STRATEGIES if self._id_map.get(s.name) == strategy_id]
            if not strategies:
                return []

        filter_type = signal_type.upper() if signal_type else None
        symbols = self._get_symbols(limit)
        logger.info("[LiveScanner] scanning %d symbols with %d strategies", len(symbols), len(strategies))

        results: list[dict] = []
        for symbol in symbols:
            df = self._load_prices(symbol)
            if df.empty or len(df) < 30:
                continue
            df = IndicatorEngine.compute(df)
            price = float(df["close"].iloc[-1])

            for strategy in strategies:
                try:
                    signal = strategy.generate_signal(df)
                except Exception as e:
                    logger.warning("[LiveScanner] %s on %s failed: %s", strategy.name, symbol, e)
                    continue

                if signal.signal_type == "NONE":
                    continue
                if filter_type and signal.signal_type != filter_type:
                    continue

                results.append({
                    "symbol": symbol,
                    "strategy_id": self._id_map.get(strategy.name),
                    "strategy_name": strategy.name,
                    "signal_type": signal.signal_type,
                    "confidence": round(signal.confidence, 4),
                    "price": price,
                    "stop_loss_pct": signal.stop_loss_pct if signal.stop_loss_pct else None,
                    "target_pct": signal.target_pct if signal.target_pct else None,
                    "holding_days": signal.holding_days,
                })

        results.sort(key=lambda r: r["confidence"], reverse=True)
        logger.info("[LiveScanner] %d signals found", len(results))
        return results

    def _get_symbols(self, limit: int) -> list[str]:
        rows = self.db.execute(
            text("""
                SELECT DISTINCT symbol FROM stock_prices_daily
                WHERE date >= date('now', '-10 days')
                ORDER BY symbol
                LIMIT :lim
            """),
            {"lim": limit},
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
