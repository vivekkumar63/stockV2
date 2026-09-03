import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from ist import ist_today, ist_now
from sqlalchemy import text as sa_text

logger = logging.getLogger(__name__)


class JobIds:
    DAILY_EOD_UPDATE = "daily_eod_update"
    DAILY_DATA_REFRESH = "daily_data_refresh"
    DAILY_INDEX_UPDATE = "daily_index_update"
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
    COMBINATION_ANALYSIS = "combination_analysis"
    FII_DII_FETCH = "fii_dii_fetch"
    SECTOR_ROTATION = "sector_rotation_daily"
    EARNINGS_REFRESH = "earnings_calendar_refresh"


_IST = "Asia/Kolkata"
scheduler = BackgroundScheduler(timezone=_IST)


def _check_special_sell_alerts(db) -> None:
    """Check special-strategy sell signals for manually-held positions and fire Telegram alerts."""
    import logging as _log
    import pandas as _pd
    from domains.alerts.telegram import AlertService
    from domains.special_strategies import ALL_SPECIAL_STRATEGIES
    from domains.data.indicators import IndicatorEngine
    _logger = _log.getLogger(__name__)

    try:
        rows = db.execute(sa_text("""
            SELECT ph.symbol, ph.avg_buy_price, ph.special_strategy_id,
                   ss.name AS strategy_name
            FROM portfolio_holdings ph
            JOIN special_strategies ss ON ss.id = ph.special_strategy_id
            WHERE ph.is_active = true AND ph.special_strategy_id IS NOT NULL
        """)).fetchall()
        if not rows:
            return

        strategy_map = {s.name: s for s in ALL_SPECIAL_STRATEGIES}
        alerts = []
        for row in rows:
            symbol, avg_buy, _, strategy_name = row[0], row[1], row[2], row[3]
            strategy = strategy_map.get(strategy_name)
            if strategy is None:
                continue
            try:
                price_rows = db.execute(sa_text("""
                    SELECT date, open, high, low, close, volume FROM (
                        SELECT date, open, high, low, close, volume
                        FROM stock_prices_daily WHERE symbol = :s
                        ORDER BY date DESC LIMIT 250
                    ) ORDER BY date ASC
                """), {"s": symbol}).fetchall()
                if len(price_rows) < 3:
                    continue
                df = _pd.DataFrame(price_rows, columns=["date", "open", "high", "low", "close", "volume"])
                for col in ("open", "high", "low", "close", "volume"):
                    df[col] = df[col].astype(float)
                df_ind = IndicatorEngine.compute(df)
                if strategy.sell_signal(df_ind):
                    current_price = float(df_ind["close"].iloc[-1])
                    alerts.append({
                        "symbol": symbol,
                        "strategy_name": strategy_name,
                        "avg_buy_price": float(avg_buy),
                        "current_price": current_price,
                    })
            except Exception:
                _logger.exception("[scheduler] special sell check failed for %s", symbol)

        if alerts:
            _logger.info("[scheduler] special strategy sell alerts: %d positions", len(alerts))
            AlertService().send_special_portfolio_sell_alerts(alerts)
    except Exception:
        _logger.exception("[scheduler] _check_special_sell_alerts failed")


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
            WHERE ph.is_active = true
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
        _check_special_sell_alerts(db)
        # Zone precompute (after prices are fresh)
        try:
            from domains.zones.precompute import ZonePrecomputer
            ZonePrecomputer().run_all(db)
        except Exception:
            logger.exception("[scheduler] zone precompute failed")
    except Exception:
        logger.exception("[scheduler] daily_eod_update failed")
    finally:
        db.close()


def _intraday_scan():
    from database import SessionLocal
    from domains.strategies.engine import StrategyEngine
    from domains.strategies.service import StrategyService
    from domains.data.nse_universe import NSE_SYMBOLS
    from domains.data.live_price_fetcher import fetch_live_prices
    from domains.data.fii_dii_fetcher import get_latest_fii_dii
    from domains.alerts.entry_window import get_signals_in_entry_window
    from domains.alerts.telegram import AlertService
    from sqlalchemy import text

    if not _is_market_hours():
        return
    db = SessionLocal()
    try:
        # Phase 1: run all strategies (stores signals to DB)
        engine = StrategyEngine(db)
        results = engine.scan_all(NSE_SYMBOLS, ist_today())
        logger.info("[scheduler] intraday_scan: %d signals", len(results))

        # Phase 2: exit monitor for open positions
        open_rows = db.execute(
            text("SELECT ph.symbol FROM portfolio_holdings ph WHERE ph.is_active=true")
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

        # Phase 3: entry-window checking (no per-signal alerts — digest handles recommendations)
        today_str = ist_today().strftime("%Y-%m-%d")
        signals = StrategyService(db).get_today_signals(signal_date=today_str)
        buy_signals = [s for s in signals if s.get("signal_type") == "BUY"]
        if buy_signals:
            symbols_with_signals = list({s["symbol"] for s in buy_signals})
            live_prices = fetch_live_prices(symbols_with_signals)
            if live_prices:
                in_window = get_signals_in_entry_window(db, buy_signals, live_prices)
                if in_window:
                    logger.info("[scheduler] intraday_scan: %d signals in entry window", len(in_window))

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


def _market_regime_compute():
    """Compute and persist today's market regime after EOD prices are available."""
    from database import SessionLocal
    from domains.market.regime import MarketRegimeEngine
    db = SessionLocal()
    try:
        engine = MarketRegimeEngine()
        result = engine.compute(db)
        engine.save(db, result)
        logger.info("[regime] %s confidence=%.0f%% breadth_sma50=%.0f%%",
                    result.regime, result.confidence * 100, result.pct_above_sma50 * 100)
    except Exception:
        logger.exception("[regime] compute failed")
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


def _signal_outcome_compute():
    """Evaluate outcomes for BUY signals that are old enough (nightly)."""
    from database import SessionLocal
    from domains.intelligence.false_signal_detector import FalseSignalDetector
    db = SessionLocal()
    try:
        n = FalseSignalDetector().compute_outcomes(db)
        logger.info("[signal_outcomes] %d new outcomes recorded", n)
    except Exception:
        logger.exception("[signal_outcomes] failed")
    finally:
        db.close()


def _strategy_correlation_compute():
    """Recompute strategy signal-overlap correlation matrix (weekly)."""
    from database import SessionLocal
    from domains.intelligence.strategy_correlation import StrategyCorrelationEngine
    db = SessionLocal()
    try:
        engine = StrategyCorrelationEngine()
        pairs = engine.compute(db)
        engine.save(db, pairs)
        logger.info("[correlations] %d strategy pairs computed", len(pairs))
    except Exception:
        logger.exception("[correlations] failed")
    finally:
        db.close()


def _weekly_fundamentals():
    from database import SessionLocal
    from domains.data.fundamentals import FundamentalsService
    from domains.data.nse_universe import NSE_SYMBOLS
    db = SessionLocal()
    try:
        result = FundamentalsService(db).refresh_all(NSE_SYMBOLS)
        logger.info("[weekly_fundamentals] updated=%d skipped=%d",
                    result["updated"], result["skipped"])
    except Exception:
        logger.exception("[weekly_fundamentals] failed")
    finally:
        db.close()


def _monthly_ml_retrain():
    """Retrain all per-strategy ML models (normal + special) after outcomes accumulate."""
    from database import SessionLocal
    from domains.intelligence.ml_scorer import MLSignalScorer
    from domains.special_strategies.ml_scorer import SpecialMLScorer
    db = SessionLocal()
    try:
        normal = MLSignalScorer().train_all(db)
        n_trained = sum(1 for r in normal.values() if r.get("samples", 0) > 0)
        logger.info("[ml_retrain] normal: trained %d/%d strategy models", n_trained, len(normal))

        special = SpecialMLScorer().train_all(db)
        s_trained = sum(1 for r in special.values() if r.get("samples", 0) > 0)
        logger.info("[ml_retrain] special: trained %d/%d strategy models", s_trained, len(special))
    except Exception:
        logger.exception("[ml_retrain] failed")
    finally:
        db.close()


def _eod_precompute():
    """Daily EOD: recompute strategy_performance for all stale (strategy, symbol) pairs.

    Uses precompute_all_strategies() which:
      - Shares indicator computation across all strategies per symbol (1× not 115×)
      - Processes symbols in parallel via ThreadPoolExecutor
      - Skips pairs already current (to_date == last_price_date)
    """
    from database import SessionLocal
    from domains.backtest.runner import BacktestRunner

    db = SessionLocal()
    try:
        count = BacktestRunner(db).precompute_all_strategies()
        logger.info("[eod_precompute] done — %d pairs updated", count)
    except Exception:
        logger.exception("[eod_precompute] failed")
    finally:
        db.close()


def _intraday_digest():
    """Send one combined Telegram message: top 5 normal + top 5 special strategies.

    Fires twice a day (9:15 morning, 15:15 pre-close). Does NOT re-run scan_all —
    signals already stored by _intraday_scan every 15 min.
    """
    from database import SessionLocal
    from domains.strategies.service import StrategyService
    from domains.alerts.telegram import AlertService
    from domains.special_strategies.scanner import SpecialScanner
    from domains.special_strategies.router import _enrich_with_performance, _save_scan_cache

    today = ist_today()
    today_str = today.strftime("%Y-%m-%d")
    period = "Morning" if ist_now().hour < 12 else "Pre-Close"
    db = SessionLocal()
    try:
        # Normal strategies: top 5 qualified BUY signals by confidence
        signals = StrategyService(db).get_today_signals(signal_date=today_str)
        buy_signals = [s for s in signals if s["signal_type"] == "BUY"]
        qualified = [
            s for s in buy_signals
            if s.get("historical_win_rate") is None or (s["historical_win_rate"] or 0) >= 0.40
        ]
        normal_top5 = sorted(
            qualified,
            key=lambda x: x.get("opportunity_score") or x.get("confidence_score") or 0,
            reverse=True,
        )[:5]

        # Special strategies: top 5 by ML probability then confidence
        special_signals = SpecialScanner(db).scan()
        enriched = _enrich_with_performance(special_signals, db)
        _save_scan_cache(enriched, today, db)
        special_top5 = sorted(
            enriched,
            key=lambda x: x.get("ml_probability") or x.get("confidence") or 0,
            reverse=True,
        )[:5]

        # One combined message
        alert_svc = AlertService()
        ok = alert_svc.send_combined_digest(normal_top5, special_top5, scan_date=today, period=period)
        if ok:
            logger.info("[scheduler] digest(%s) sent: %d normal, %d special",
                        period, len(normal_top5), len(special_top5))
        else:
            logger.error("[scheduler] digest(%s) Telegram send failed", period)

        # Sell alerts for held positions (kept separate — always important)
        _send_sell_alerts_for_holdings(db)
        _check_special_sell_alerts(db)
    except Exception:
        logger.exception("[scheduler] intraday_digest failed")
    finally:
        db.close()


def _combination_analysis():
    """Weekly combination analysis: discover best strategy combinations."""
    from database import SessionLocal
    from domains.combinations.engine import CombinationEngine
    db = SessionLocal()
    try:
        engine = CombinationEngine(db)
        run_id = engine.run_full_analysis()
        logger.info("[combination_analysis] complete: run_id=%d", run_id)
    except Exception:
        logger.exception("[combination_analysis] failed")
    finally:
        db.close()


def _daily_index_update():
    """Fetch latest index OHLCV and recompute trend labels. Runs at 4:20 PM IST on weekdays."""
    from database import SessionLocal
    from domains.data.index_fetcher import fetch_and_store_index_prices, compute_index_trends
    db = SessionLocal()
    try:
        fetch_and_store_index_prices(db, days=5)
        compute_index_trends(db)
        logger.info("[daily_index_update] complete")
    except Exception:
        logger.exception("[daily_index_update] failed")
    finally:
        db.close()


def _fii_dii_fetch():
    """Fetch NSE FII/DII participant data after market close and store for alert enrichment."""
    from database import SessionLocal
    from domains.data.fii_dii_fetcher import fetch_and_store_fii_dii
    db = SessionLocal()
    try:
        fetch_and_store_fii_dii(db)
    except Exception:
        logger.exception("[fii_dii_fetch] failed")
    finally:
        db.close()


def _earnings_refresh():
    """Fetch upcoming earnings/results dates from NSE and upsert into earnings_calendar."""
    from database import SessionLocal
    from domains.data.earnings_fetcher import EarningsFetcher
    db = SessionLocal()
    try:
        n = EarningsFetcher().refresh(db)
        logger.info("[earnings_refresh] upserted %d rows", n)
    except Exception:
        logger.exception("[earnings_refresh] failed")
    finally:
        db.close()


def _sector_rotation_daily():
    """Compute sector breadth and signal flow after EOD data and index trends are available."""
    from datetime import timedelta
    from database import SessionLocal
    from domains.sector_rotation.engine import SectorRotationEngine
    from ist import ist_today
    db = SessionLocal()
    try:
        engine = SectorRotationEngine()
        today = ist_today()
        week_start = today - timedelta(days=today.weekday())
        b = engine.compute_breadth(db, today)
        f = engine.compute_signal_flow(db, week_start)
        logger.info("[sector_rotation_daily] breadth=%d flow=%d", b, f)
    except Exception:
        logger.exception("[sector_rotation_daily] failed")
    finally:
        db.close()


def register_jobs():
    # 3:45pm — fetch today's closing data before EOD scan runs at 4pm
    scheduler.add_job(
        _daily_data_refresh,
        CronTrigger(hour=15, minute=45, day_of_week="mon-fri", timezone=_IST),
        id=JobIds.DAILY_DATA_REFRESH,
        replace_existing=True,
    )
    scheduler.add_job(
        _daily_eod_update,
        CronTrigger(hour=16, minute=0, day_of_week="mon-fri", timezone=_IST),
        id=JobIds.DAILY_EOD_UPDATE,
        replace_existing=True,
    )
    scheduler.add_job(
        _intraday_scan,
        CronTrigger(minute="*/15", hour="9-15", day_of_week="mon-fri", timezone=_IST),
        id=JobIds.INTRADAY_SCAN,
        replace_existing=True,
    )
    scheduler.add_job(
        _weekly_fundamentals,
        CronTrigger(day_of_week="sun", hour=20, minute=0, timezone=_IST),
        id=JobIds.WEEKLY_FUNDAMENTALS,
        replace_existing=True,
    )
    # 4:50pm — update strategy_performance for new price data (skips symbols already current)
    scheduler.add_job(
        _eod_precompute,
        CronTrigger(hour=16, minute=50, day_of_week="mon-fri", timezone=_IST),
        id=JobIds.WEEKLY_PRECOMPUTE,
        replace_existing=True,
    )
    scheduler.add_job(
        _monthly_ml_retrain,
        CronTrigger(day_of_week="sun", hour=22, minute=30, day="1-7", timezone=_IST),
        id=JobIds.MONTHLY_ML_RETRAIN,
        replace_existing=True,
    )
    # 4:15pm — compute market regime after EOD data (3:45 fetch + 4:00 scan)
    scheduler.add_job(
        _market_regime_compute,
        CronTrigger(hour=16, minute=15, day_of_week="mon-fri", timezone=_IST),
        id="market_regime_compute",
        replace_existing=True,
    )
    # 4:20pm — fetch index prices and compute trends
    scheduler.add_job(
        _daily_index_update,
        CronTrigger(hour=16, minute=20, day_of_week="mon-fri", timezone=_IST),
        id=JobIds.DAILY_INDEX_UPDATE,
        replace_existing=True,
    )
    # 4:35pm — fetch FII/DII participant flow data from NSE after market close
    scheduler.add_job(
        _fii_dii_fetch,
        CronTrigger(hour=16, minute=35, day_of_week="mon-fri", timezone=_IST),
        id=JobIds.FII_DII_FETCH,
        replace_existing=True,
    )
    # 4:30pm — refresh leaderboard after EOD data lands (3:45 data fetch + 4:00 EOD scan)
    scheduler.add_job(
        _leaderboard_refresh,
        CronTrigger(hour=16, minute=30, day_of_week="mon-fri", timezone=_IST),
        id=JobIds.LEADERBOARD_REFRESH,
        replace_existing=True,
    )
    # 4:45pm — evaluate signal outcomes for signals old enough (holding period elapsed)
    scheduler.add_job(
        _signal_outcome_compute,
        CronTrigger(hour=16, minute=45, day_of_week="mon-fri", timezone=_IST),
        id="signal_outcome_compute",
        replace_existing=True,
    )
    # Sunday 21:00 — recompute strategy correlation matrix weekly
    scheduler.add_job(
        _strategy_correlation_compute,
        CronTrigger(day_of_week="sun", hour=21, minute=0, timezone=_IST),
        id="strategy_correlation_compute",
        replace_existing=True,
    )
    # Two digests per day: morning open + pre-close. Each is one combined message.
    for job_id, hour, minute in [
        (JobIds.DIGEST_0915,  9, 15),   # morning — right after market opens
        (JobIds.DIGEST_1515, 15, 15),   # pre-close — 15 min before 3:30
    ]:
        scheduler.add_job(
            _intraday_digest,
            CronTrigger(hour=hour, minute=minute, day_of_week="mon-fri", timezone=_IST),
            id=job_id,
            replace_existing=True,
        )
    # Sunday 23:00 — weekly combination analysis (after 22:00 precompute)
    scheduler.add_job(
        _combination_analysis,
        CronTrigger(day_of_week="sun", hour=23, minute=0, timezone=_IST),
        id=JobIds.COMBINATION_ANALYSIS,
        replace_existing=True,
    )
    # 4:40pm — sector rotation (after 4:20 index trend update and 4:35 FII/DII)
    scheduler.add_job(
        _sector_rotation_daily,
        CronTrigger(hour=16, minute=40, day_of_week="mon-fri", timezone=_IST),
        id=JobIds.SECTOR_ROTATION,
        replace_existing=True,
    )
    # 6:15am — fetch upcoming earnings dates before market opens
    scheduler.add_job(
        _earnings_refresh,
        CronTrigger(hour=6, minute=15, timezone=_IST),
        id=JobIds.EARNINGS_REFRESH,
        replace_existing=True,
    )
    logger.info("APScheduler jobs registered: %s", [j.id for j in scheduler.get_jobs()])
