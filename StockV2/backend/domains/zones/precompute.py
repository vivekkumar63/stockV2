from __future__ import annotations
import datetime
import logging
from sqlalchemy import text
from sqlalchemy.orm import Session
from .engine import ZoneEngine

logger = logging.getLogger(__name__)

# Module-level state dict shared with router for status endpoint
_precompute_state: dict = {
    "is_running": False,
    "done": 0,
    "total": 0,
    "finished": False,
    "started_at": None,
    "error": None,
}


def get_precompute_state() -> dict:
    return _precompute_state


class ZonePrecomputer:
    def run_all(self, db: Session) -> None:
        rows = db.execute(
            text("""
                SELECT DISTINCT symbol FROM stock_prices_daily
                WHERE date >= CURRENT_DATE - INTERVAL '10 days'
                ORDER BY symbol
            """)
        ).fetchall()
        symbols = [r[0] for r in rows]
        total = len(symbols)
        _precompute_state.update(
            is_running=True, done=0, total=total, finished=False, error=None,
            started_at=str(datetime.datetime.now()),
        )
        logger.info("[zone_precompute] starting — %d symbols", total)
        engine = ZoneEngine()
        for i, symbol in enumerate(symbols):
            try:
                engine.analyze(symbol, db)
            except Exception as e:
                logger.warning("[zone_precompute] failed for %s: %s", symbol, e)
            _precompute_state["done"] = i + 1
            if (i + 1) % 50 == 0:
                logger.info("[zone_precompute] done %d/%d symbols", i + 1, total)

        _precompute_state.update(is_running=False, finished=True)
        logger.info("[zone_precompute] complete — %d symbols processed", total)
