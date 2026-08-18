import logging
import time
from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class FundamentalsService:
    def __init__(self, db: Session):
        self.db = db

    def get_latest(self, symbol: str) -> dict:
        row = self.db.execute(
            text("""
                SELECT pe_ratio, pb_ratio, eps, revenue, net_profit,
                       debt_equity, roe, dividend_yield, data_as_of
                FROM fundamentals
                WHERE symbol = :sym
                ORDER BY data_as_of DESC LIMIT 1
            """),
            {"sym": symbol},
        ).fetchone()
        if not row:
            return {}
        return {
            "pe_ratio":       row[0],
            "pb_ratio":       row[1],
            "eps":            row[2],
            "revenue":        row[3],
            "net_profit":     row[4],
            "debt_equity":    row[5],
            "roe":            row[6],
            "dividend_yield": row[7],
            "data_as_of":     str(row[8]) if row[8] else None,
        }

    def refresh_one(self, symbol: str) -> bool:
        try:
            import yfinance as yf
            ticker = yf.Ticker(symbol + ".NS")
            info = ticker.info or {}

            pe      = _safe_float(info.get("trailingPE"))
            pb      = _safe_float(info.get("priceToBook"))
            eps     = _safe_float(info.get("trailingEps"))
            revenue = _safe_float(info.get("totalRevenue"))
            profit  = _safe_float(info.get("netIncomeToCommon"))
            roe     = _safe_float(info.get("returnOnEquity"))
            div_yld = _safe_float(info.get("dividendYield"))

            # yfinance debtToEquity: returned as percentage (43.5 means 0.435 ratio)
            # Normalise to decimal ratio; values <= 2 are already in ratio form
            raw_de = info.get("debtToEquity")
            de = None
            if raw_de is not None:
                de = float(raw_de) / 100 if float(raw_de) > 2 else float(raw_de)

            self.db.execute(
                text("DELETE FROM fundamentals WHERE symbol = :sym"),
                {"sym": symbol},
            )
            self.db.execute(
                text("""
                    INSERT INTO fundamentals
                        (symbol, pe_ratio, pb_ratio, eps, revenue, net_profit,
                         debt_equity, roe, dividend_yield, data_as_of, updated_at)
                    VALUES (:sym, :pe, :pb, :eps, :rev, :np,
                            :de, :roe, :dy, :asof, datetime('now'))
                """),
                {
                    "sym": symbol, "pe": pe, "pb": pb, "eps": eps,
                    "rev": revenue, "np": profit, "de": de, "roe": roe,
                    "dy": div_yld, "asof": str(date.today()),
                },
            )
            self.db.commit()
            return True
        except Exception as e:
            self.db.rollback()
            logger.warning("[FundamentalsService] refresh_one %s: %s", symbol, e)
            return False

    def refresh_all(self, symbols: list[str]) -> dict:
        updated = skipped = 0
        for i, symbol in enumerate(symbols):
            if self.refresh_one(symbol):
                updated += 1
            else:
                skipped += 1
            if (i + 1) % 50 == 0:
                logger.info("[FundamentalsService] %d/%d done", i + 1, len(symbols))
            time.sleep(0.3)
        logger.info("[FundamentalsService] complete: updated=%d skipped=%d", updated, skipped)
        return {"updated": updated, "skipped": skipped}


def _safe_float(v) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None
