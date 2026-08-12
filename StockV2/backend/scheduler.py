import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)


class JobIds:
    DAILY_EOD_UPDATE = "daily_eod_update"
    DAILY_DATA_REFRESH = "daily_data_refresh"
    INTRADAY_SCAN = "intraday_scan"
    WEEKLY_FUNDAMENTALS = "weekly_fundamentals"
    MONTHLY_ML_RETRAIN = "monthly_ml_retrain"
    DAILY_DIGEST = "daily_digest"


scheduler = BackgroundScheduler(timezone="Asia/Kolkata")


def _is_market_hours() -> bool:
    from datetime import datetime
    from zoneinfo import ZoneInfo
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    return now.weekday() < 5 and 9 <= now.hour < 16


def _daily_eod_update():
    from datetime import date
    from database import SessionLocal
    from domains.strategies.engine import StrategyEngine
    from domains.data.nse_universe import NSE_SYMBOLS
    db = SessionLocal()
    try:
        engine = StrategyEngine(db)
        results = engine.scan_all(NSE_SYMBOLS, date.today())
        logger.info("[scheduler] daily_eod_update: %d signals generated", len(results))
    except Exception:
        logger.exception("[scheduler] daily_eod_update failed")
    finally:
        db.close()


def _intraday_scan():
    from datetime import date
    from database import SessionLocal
    from domains.strategies.engine import StrategyEngine
    from domains.data.nse_universe import NSE_SYMBOLS
    from sqlalchemy import text
    if not _is_market_hours():
        return
    db = SessionLocal()
    try:
        # Strategy scan
        engine = StrategyEngine(db)
        results = engine.scan_all(NSE_SYMBOLS, date.today())
        logger.info("[scheduler] intraday_scan: %d signals", len(results))

        # Exit monitor: get open positions and their last known close prices
        open_rows = db.execute(
            text("SELECT ph.symbol FROM portfolio_holdings ph WHERE ph.is_active=1")
        ).fetchall()
        open_symbols = [r[0] for r in open_rows]
        if open_symbols:
            placeholders = ",".join(f"'{s}'" for s in open_symbols)
            price_rows = db.execute(
                text(f"""
                    SELECT symbol, close FROM stock_prices_daily
                    WHERE (symbol, date) IN (
                        SELECT symbol, MAX(date) FROM stock_prices_daily
                        WHERE symbol IN ({placeholders})
                        GROUP BY symbol
                    )
                """)
            ).fetchall()
            current_prices = {r[0]: r[1] for r in price_rows}
            if current_prices:
                from domains.portfolio.exit_monitor import ExitMonitor
                exits = ExitMonitor(db).scan_exits(current_prices)
                if exits:
                    logger.info("[scheduler] intraday_scan: %d positions exited", len(exits))
    except Exception:
        logger.exception("[scheduler] intraday_scan failed")
    finally:
        db.close()


def _daily_data_refresh():
    """Download only the missing OHLCV days for every stock (incremental, not full re-download)."""
    from datetime import date, timedelta
    from database import SessionLocal
    from domains.data.feeds.yfinance_feed import YFinanceFeed
    from domains.data.nse_universe import NSE_SYMBOLS
    import time as _time

    db = SessionLocal()
    feed = YFinanceFeed()
    today = date.today()
    updated = 0
    skipped = 0
    failed = 0
    try:
        for symbol in NSE_SYMBOLS:
            last = feed.get_last_date(db, symbol)
            if last is None:
                skipped += 1
                continue  # not bootstrapped yet — bootstrap job handles it
            if last >= today:
                skipped += 1
                continue  # already up to date
            since = last + timedelta(days=1)
            df = feed.download_since(symbol, since)
            if not df.empty:
                feed.upsert_prices(db, symbol, df)
                updated += 1
            else:
                failed += 1
            _time.sleep(0.2)
        logger.info("[data_refresh] updated=%d skipped=%d failed=%d", updated, skipped, failed)
    except Exception:
        logger.exception("[data_refresh] failed")
    finally:
        db.close()


def _weekly_fundamentals():
    logger.info("[scheduler] weekly_fundamentals — placeholder (implemented in Plan 2)")


def _daily_digest():
    from datetime import date
    from database import SessionLocal
    from domains.strategies.service import StrategyService
    from domains.alerts.telegram import AlertService
    db = SessionLocal()
    try:
        today_str = date.today().strftime("%Y-%m-%d")
        signals = StrategyService(db).get_today_signals(signal_date=today_str)
        buy_signals = [s for s in signals if s["signal_type"] == "BUY"]
        top_10 = sorted(buy_signals, key=lambda x: x.get("confidence_score") or 0, reverse=True)[:10]
        AlertService().send_daily_digest(top_10, scan_date=date.today())
        logger.info("[scheduler] daily_digest sent: %d buy signals today", len(top_10))
    except Exception:
        logger.exception("[scheduler] daily_digest failed")
    finally:
        db.close()


def register_jobs():
    # 3:45pm — fetch today's closing data before EOD scan runs at 4pm
    scheduler.add_job(
        _daily_data_refresh,
        CronTrigger(hour=15, minute=45, day_of_week="mon-fri"),
        id=JobIds.DAILY_DATA_REFRESH,
        replace_existing=True,
    )
    scheduler.add_job(
        _daily_eod_update,
        CronTrigger(hour=16, minute=0, day_of_week="mon-fri"),
        id=JobIds.DAILY_EOD_UPDATE,
        replace_existing=True,
    )
    scheduler.add_job(
        _intraday_scan,
        CronTrigger(minute="*/15", hour="9-15", day_of_week="mon-fri"),
        id=JobIds.INTRADAY_SCAN,
        replace_existing=True,
    )
    scheduler.add_job(
        _weekly_fundamentals,
        CronTrigger(day_of_week="sun", hour=20, minute=0),
        id=JobIds.WEEKLY_FUNDAMENTALS,
        replace_existing=True,
    )
    scheduler.add_job(
        _daily_digest,
        CronTrigger(hour=17, minute=15, day_of_week="mon-fri"),
        id=JobIds.DAILY_DIGEST,
        replace_existing=True,
    )
    logger.info("APScheduler jobs registered: %s", [j.id for j in scheduler.get_jobs()])
