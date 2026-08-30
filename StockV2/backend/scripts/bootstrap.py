"""One-shot historical data bootstrap. Run once to seed 15 years of OHLCV.

Usage:
    cd backend && poetry run python -m scripts.bootstrap

Resumable: already-downloaded symbols are automatically skipped.
"""
import logging
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).parent.parent))

from database import SessionLocal, engine, Base
from domains.data.feeds.yfinance_feed import YFinanceFeed
from domains.data.indicators import IndicatorEngine
from domains.data.nse_universe import NSE_SYMBOLS
import models  # noqa

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


@dataclass
class BootstrapStats:
    total: int = 0
    downloaded: int = 0
    skipped: int = 0
    failed: int = 0
    failed_symbols: list[str] = field(default_factory=list)


class BootstrapRunner:
    def __init__(self, db: Session, symbols: Optional[list[str]] = None):
        self.db = db
        self.symbols = symbols or NSE_SYMBOLS
        self.feed = YFinanceFeed()

    def _ensure_stock_record(self, symbol: str) -> None:
        self.db.execute(
            text("""
                INSERT INTO stocks (symbol, name, exchange, is_active, added_at)
                VALUES (:sym, :sym, 'NSE', true, CURRENT_TIMESTAMP)
                ON CONFLICT (symbol) DO NOTHING
            """),
            {"sym": symbol},
        )
        self.db.commit()

    def _already_downloaded(self, symbol: str) -> bool:
        result = self.db.execute(
            text("SELECT COUNT(*) FROM stock_prices_daily WHERE symbol = :s LIMIT 1"),
            {"s": symbol},
        ).scalar()
        return (result or 0) > 0

    def run(self, years: int = 15) -> dict:
        stats = BootstrapStats(total=len(self.symbols))

        for i, symbol in enumerate(self.symbols, 1):
            logger.info("[%d/%d] %s", i, stats.total, symbol)

            if self._already_downloaded(symbol):
                logger.info("  → skipping (already downloaded)")
                stats.skipped += 1
                continue

            self._ensure_stock_record(symbol)

            df = self.feed.download(symbol, years=years)
            if df.empty:
                logger.warning("  → no data returned")
                stats.failed += 1
                stats.failed_symbols.append(symbol)
                continue

            df_with_indicators = IndicatorEngine.compute(df)
            inserted = self.feed.upsert_prices(self.db, symbol, df_with_indicators)
            logger.info("  → inserted %d rows", inserted)
            stats.downloaded += 1

            time.sleep(0.3)

        logger.info(
            "Bootstrap complete. Downloaded: %d, Skipped: %d, Failed: %d",
            stats.downloaded, stats.skipped, stats.failed,
        )
        if stats.failed_symbols:
            logger.warning("Failed symbols: %s", stats.failed_symbols)

        return {
            "total": stats.total,
            "downloaded": stats.downloaded,
            "skipped": stats.skipped,
            "failed": stats.failed,
            "failed_symbols": stats.failed_symbols,
        }


if __name__ == "__main__":
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        runner = BootstrapRunner(db=db)
        runner.run(years=15)
    finally:
        db.close()
