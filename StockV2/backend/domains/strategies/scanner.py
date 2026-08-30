import logging
from typing import Optional

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from domains.data.indicators import IndicatorEngine
from domains.intelligence.opportunity_scorer import OpportunityScorer
from domains.intelligence.regime_performance import RegimePerformanceEngine
from domains.market.regime import MarketRegimeEngine
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

        # Load regime + regime-strategy win rates once for the full scan
        try:
            regime_result = MarketRegimeEngine().get_or_compute(self.db)
            regime = regime_result.regime
            regime_perf = RegimePerformanceEngine().get_for_regime(self.db, regime)
        except Exception:
            regime = "SIDEWAYS"
            regime_perf = {}

        scorer = OpportunityScorer()
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

                sid = self._id_map.get(strategy.name)
                results.append({
                    "symbol": symbol,
                    "strategy_id": sid,
                    "strategy_name": strategy.name,
                    "signal_type": signal.signal_type,
                    "confidence": round(signal.confidence, 4),
                    "price": price,
                    "stop_loss_pct": signal.stop_loss_pct if signal.stop_loss_pct else None,
                    "target_pct": signal.target_pct if signal.target_pct else None,
                    "holding_days": signal.holding_days,
                    "historical_win_rate": None,
                    "opportunity_score": None,
                    "opportunity_grade": None,
                    "_sid": sid,
                    "_confidence": signal.confidence,
                    "_regime": regime,
                    "_regime_perf": regime_perf,
                })

        results.sort(key=lambda r: r["confidence"], reverse=True)

        if results:
            win_map = self._load_win_rates(results)
            for r in results:
                key = (r["symbol"], r["_sid"])
                r["historical_win_rate"] = win_map.get(key)

                # Compute quick opportunity score (no extra DB queries per symbol)
                regime_wr = r["_regime_perf"].get(r["_sid"])
                opp = scorer.quick_score(
                    symbol=r["symbol"],
                    strategy_id=r["_sid"],
                    confidence=r["_confidence"],
                    historical_win_rate=r["historical_win_rate"],
                    regime=r["_regime"],
                    regime_strategy_win_rate=regime_wr.win_rate if regime_wr else None,
                )
                r["opportunity_score"] = opp.score
                r["opportunity_grade"] = opp.grade

            # Strip internal keys used only for scoring
            for r in results:
                r.pop("_sid", None)
                r.pop("_confidence", None)
                r.pop("_regime", None)
                r.pop("_regime_perf", None)

        logger.info("[LiveScanner] %d signals found", len(results))
        return results

    def _load_win_rates(self, results: list[dict]) -> dict[tuple, Optional[float]]:
        pairs = [(r["symbol"], r["strategy_id"]) for r in results if r["strategy_id"] is not None]
        if not pairs:
            return {}
        symbols = list({p[0] for p in pairs})
        sids = list({p[1] for p in pairs})
        sym_ph = ",".join(f":s{i}" for i in range(len(symbols)))
        sid_ph = ",".join(f":id{i}" for i in range(len(sids)))
        params: dict = {f"s{i}": v for i, v in enumerate(symbols)}
        params.update({f"id{i}": v for i, v in enumerate(sids)})
        rows = self.db.execute(
            text(f"""
                SELECT symbol, strategy_id, win_rate FROM scan_result_cache
                WHERE stop_loss_pct = 5.0 AND target_pct = 10.0
                  AND from_date = '2015-01-01'
                  AND symbol IN ({sym_ph})
                  AND strategy_id IN ({sid_ph})
            """),
            params,
        ).fetchall()
        return {(r[0], r[1]): r[2] for r in rows}

    def _get_symbols(self, limit: int) -> list[str]:
        rows = self.db.execute(
            text("""
                SELECT DISTINCT symbol FROM stock_prices_daily
                WHERE date >= CURRENT_DATE - INTERVAL '10 days'
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
