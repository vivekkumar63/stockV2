import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)


class JobIds:
    DAILY_EOD_UPDATE = "daily_eod_update"
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
    if not _is_market_hours():
        return
    db = SessionLocal()
    try:
        engine = StrategyEngine(db)
        results = engine.scan_all(NSE_SYMBOLS, date.today())
        logger.info("[scheduler] intraday_scan: %d signals", len(results))
    except Exception:
        logger.exception("[scheduler] intraday_scan failed")
    finally:
        db.close()


def _weekly_fundamentals():
    logger.info("[scheduler] weekly_fundamentals — placeholder (implemented in Plan 2)")


def _daily_digest():
    logger.info("[scheduler] daily_digest — placeholder (implemented in Plan 3)")


def register_jobs():
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
