"""Entry-window filtering and dedup for intraday BUY signal alerts."""
import logging
from datetime import date
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

ENTRY_WINDOW_PCT = 0.02  # ±2% of signal entry price


def is_in_entry_window(current_price: float, entry_price: float) -> bool:
    """Return True if current_price is within ENTRY_WINDOW_PCT of entry_price."""
    return abs(current_price - entry_price) / entry_price <= ENTRY_WINDOW_PCT


def get_signals_in_entry_window(
    db: Session,
    scan_results: list[dict],
    live_prices: dict[str, float],
) -> list[dict]:
    """
    From scan_results (output of StrategyService.get_today_signals()), return
    signals where:
      1. signal_type == 'BUY'
      2. symbol has a live price available
      3. current price is within ENTRY_WINDOW_PCT of price_at_signal
      4. (symbol, strategy_id, signal_date) has NOT already been alerted today
    """
    today = str(date.today())
    in_window: list[dict] = []

    for signal in scan_results:
        if signal.get("signal_type") != "BUY":
            continue

        sym = signal.get("symbol")
        entry_price = signal.get("price_at_signal")
        strategy_id = signal.get("strategy_id")
        signal_date = str(signal.get("signal_date", today))

        if not sym or not entry_price or sym not in live_prices:
            continue

        current_price = live_prices[sym]
        if not is_in_entry_window(current_price, float(entry_price)):
            continue

        # Dedup check
        already_sent = db.execute(
            text("""
                SELECT 1 FROM intraday_alerts_sent
                WHERE symbol = :sym AND strategy_id = :sid AND signal_date = :date
                LIMIT 1
            """),
            {"sym": sym, "sid": strategy_id, "date": signal_date},
        ).fetchone()

        if already_sent:
            logger.debug("[entry_window] %s/%s already alerted today — skip", sym, strategy_id)
            continue

        in_window.append(signal)

    return in_window
