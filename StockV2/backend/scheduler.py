import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from ist import ist_today, ist_now
from sqlalchemy import text as sa_text

logger = logging.getLogger(__name__)


class JobIds:
    DAILY_EOD_UPDATE = "daily_eod_update"
    DAILY_DATA_REFRESH = "daily_data_refresh"
    INTRADAY_SCAN = "intraday_scan"
    WEEKLY_FUNDAMENTALS = "weekly_fundamentals"
    MONTHLY_ML_RETRAIN = "monthly_ml_retrain"
    DIGEST_0915 = "digest_0915"
    DIGEST_1030 = "digest_1030"
    DIGEST_1200 = "digest_1200"
    DIGEST_1400 = "digest_1400"
    DIGEST_1515 = "digest_1515"
    WEEKLY_PRECOMPUTE = "weekly_precompute"
    LEADERBOARD_REFRESH = "leaderboard_refresh"


scheduler = BackgroundScheduler(timezone="Asia/Kolkata")


def _send_sell_alerts_for_holdings(db) -> None:
    """Query SELL signals for held stocks from the latest scan and fire Telegram alerts."""
    from domains.alerts.telegram import AlertService
    try:
        rows = db.execute(sa_text("""
            WITH latest_scan AS (
                SELECT MAX(signal_date) AS max_date FROM strategy_signals
            )
            SELECT ph.symbol, ph.avg_buy_price,
                   s.name AS strategy_name,
                   ss.signal_date, ss.price_at_signal,
                   ss.confidence_score, ss.reasoning_json
            FROM portfolio_holdings ph
            JOIN strategy_signals ss ON ss.symbol = ph.symbol AND ss.signal_type = 'SELL'
            JOIN strategies s ON s.id = ss.strategy_id
            JOIN latest_scan ls ON ss.signal_date = ls.max_date
            WHERE ph.is_active = 1
            ORDER BY ss.confidence_score DESC
        """)).fetchall()
        alerts = [dict(r._mapping) for r in rows]
        if alerts:
            logger.info("[scheduler] sell alerts for held stocks: %d signals", len(alerts))
            AlertService().send_sell_alerts(alerts)
    except Exception:
        logger.exception("[scheduler] sell alert check failed")


def _is_market_hours() -> bool:
    now = ist_now()
    return now.weekday() < 5 and 9 <= now.hour < 16


def _daily_eod_update():
    from database import SessionLocal
    from domains.strategies.engine import StrategyEngine
    from domains.data.nse_universe import NSE_SYMBOLS
    db = SessionLocal()
    try:
        engine = StrategyEngine(db)
        results = engine.scan_all(NSE_SYMBOLS, ist_today())
        logger.info("[scheduler] daily_eod_update: %d signals generated", len(results))
        _send_sell_alerts_for_holdings(db)
    except Exception:
        logger.exception("[scheduler] daily_eod_update failed")
    finally:
        db.close()


def _intraday_scan():
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
        results = engine.scan_all(NSE_SYMBOLS, ist_today())
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
    from datetime import timedelta
    from database import SessionLocal
    from domains.data.feeds.yfinance_feed import YFinanceFeed
    from domains.data.nse_universe import NSE_SYMBOLS
    import time as _time

    db = SessionLocal()
    feed = YFinanceFeed()
    today = ist_today()
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


def _leaderboard_refresh():
    """Auto-refresh leaderboard after EOD data lands. Skips if cache is already current."""
    from domains.backtest.router import _run_leaderboard_bg, _get_last_price_date, _parse_date, _lb_state, _LEADERBOARD_FROM
    from database import SessionLocal
    from sqlalchemy import text

    db = SessionLocal()
    try:
        last_price_date = _get_last_price_date(db)
        if last_price_date is None:
            return
        cached_to = db.execute(
            text("""
                SELECT MAX(to_date) FROM scan_result_cache
                WHERE stop_loss_pct = 5.0 AND target_pct = 10.0 AND from_date = :fd
            """),
            {"fd": str(_LEADERBOARD_FROM)},
        ).scalar()
        cached_date = _parse_date(cached_to)
        if cached_date is not None and cached_date >= last_price_date:
            logger.info("[leaderboard_refresh] cache already current as of %s — skip", last_price_date)
            return
    finally:
        db.close()

    if _lb_state["is_computing"]:
        logger.info("[leaderboard_refresh] already computing — skip")
        return

    logger.info("[leaderboard_refresh] starting background compute")
    _run_leaderboard_bg(stop_loss_pct=5.0, target_pct=10.0)


def _weekly_fundamentals():
    logger.info("[scheduler] weekly_fundamentals — placeholder (implemented in Plan 2)")


def _weekly_precompute():
    """Compute strategy_performance rows for any strategy that has none yet.
    Runs Sunday night so new strategies added during the week get their backtest data.
    """
    from database import SessionLocal
    from sqlalchemy import text
    from domains.backtest.runner import BacktestRunner
    db = SessionLocal()
    try:
        rows = db.execute(text("""
            SELECT id FROM strategies
            WHERE is_active = 1
            AND id NOT IN (SELECT DISTINCT strategy_id FROM strategy_performance)
        """)).fetchall()
        uncomputed_ids = [r[0] for r in rows]
    finally:
        db.close()

    if not uncomputed_ids:
        logger.info("[precompute] all strategies already computed — nothing to do")
        return

    logger.info("[precompute] starting for %d strategies", len(uncomputed_ids))
    for sid in uncomputed_ids:
        db = SessionLocal()
        try:
            count = BacktestRunner(db).precompute_all_for_strategy(sid)
            logger.info("[precompute] strategy id=%d: %d symbols done", sid, count)
        except Exception:
            logger.exception("[precompute] strategy id=%d failed", sid)
        finally:
            db.close()
    logger.info("[precompute] done")


def _intraday_digest():
    """Scan all stocks, send top BUY signals + sell alerts for held positions to Telegram."""
    from database import SessionLocal
    from domains.strategies.engine import StrategyEngine
    from domains.data.nse_universe import NSE_SYMBOLS
    from domains.strategies.service import StrategyService
    from domains.alerts.telegram import AlertService

    today = ist_today()
    db = SessionLocal()
    try:
        engine = StrategyEngine(db)
        scan_count = len(engine.scan_all(NSE_SYMBOLS, today))
        logger.info("[scheduler] intraday_digest scan: %d signals generated", scan_count)

        today_str = today.strftime("%Y-%m-%d")
        signals = StrategyService(db).get_today_signals(signal_date=today_str)
        buy_signals = [s for s in signals if s["signal_type"] == "BUY"]
        top_10 = sorted(buy_signals, key=lambda x: x.get("confidence_score") or 0, reverse=True)[:10]
        AlertService().send_daily_digest(top_10, scan_date=today)
        logger.info("[scheduler] intraday_digest sent: %d buy signals", len(top_10))

        # Also fire sell alerts for any held positions
        _send_sell_alerts_for_holdings(db)
    except Exception:
        logger.exception("[scheduler] intraday_digest failed")
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
        _weekly_precompute,
        CronTrigger(day_of_week="sun", hour=22, minute=0),
        id=JobIds.WEEKLY_PRECOMPUTE,
        replace_existing=True,
    )
    # 4:30pm — refresh leaderboard after EOD data lands (3:45 data fetch + 4:00 EOD scan)
    scheduler.add_job(
        _leaderboard_refresh,
        CronTrigger(hour=16, minute=30, day_of_week="mon-fri"),
        id=JobIds.LEADERBOARD_REFRESH,
        replace_existing=True,
    )
    for job_id, hour, minute in [
        (JobIds.DIGEST_0915,  9, 15),   # market open
        (JobIds.DIGEST_1030, 10, 30),   # mid-morning
        (JobIds.DIGEST_1200, 12,  0),   # midday
        (JobIds.DIGEST_1400, 14,  0),   # afternoon
        (JobIds.DIGEST_1515, 15, 15),   # pre-close (15 min before 3:30)
    ]:
        scheduler.add_job(
            _intraday_digest,
            CronTrigger(hour=hour, minute=minute, day_of_week="mon-fri"),
            id=job_id,
            replace_existing=True,
        )
    logger.info("APScheduler jobs registered: %s", [j.id for j in scheduler.get_jobs()])
