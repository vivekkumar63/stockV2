# StockV2 — Project Documentation

> Indian equities paper-trading and strategy analysis platform.
> Backend: FastAPI + SQLite. Frontend: React + Vite. Notifications: Telegram.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [How to Run](#2-how-to-run)
3. [Configuration](#3-configuration)
4. [Database Schema](#4-database-schema)
5. [Backend Domains](#5-backend-domains)
6. [API Reference](#6-api-reference)
7. [Trading Strategies (87 active)](#7-trading-strategies)
8. [Scheduler Jobs](#8-scheduler-jobs)
9. [Frontend Pages](#9-frontend-pages)
10. [Data Flows](#10-data-flows)

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                     React Frontend                      │
│  Dashboard · Scanner · Backtest · Strategy Match · Pf   │
└─────────────────────┬───────────────────────────────────┘
                      │ HTTP  X-API-Key header
┌─────────────────────▼───────────────────────────────────┐
│                   FastAPI Backend                        │
│                                                         │
│  /data  /strategies  /backtest  /portfolio  /ai         │
│                                                         │
│  APScheduler — intraday scan, EOD update, digests       │
└────────┬──────────────────────────────────┬────────────┘
         │ SQLAlchemy                        │ HTTPX
┌────────▼────────┐              ┌──────────▼──────────┐
│  SQLite WAL DB  │              │  Telegram Bot API   │
│  stockv2.db     │              │  YFinance / Angel1  │
└─────────────────┘              └─────────────────────┘
```

**Key choices:**
- SQLite with WAL mode — single-node, zero-ops, good for 237 symbols at daily granularity.
- All timestamps in IST (Asia/Kolkata) via `ist.py`. Scheduler also runs in IST.
- Strategies auto-discovered at startup — drop a `.py` file in `strategies/strategies/` to add one.
- Paper-trading only (no real orders placed). `TRADING_MODE=live` is stubbed.

---

## 2. How to Run

### Backend

```bash
cp .env.example .env        # fill in API_KEY, Telegram tokens, etc.
cd backend
poetry install
poetry run uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

On first startup:
- Database tables are created automatically.
- 87 strategies are seeded from the `strategies/strategies/` directory.
- If no price data exists, a background daemon downloads ~15 years of OHLCV for all 237 NSE stocks via YFinance (takes 20–60 min, resumable).

### Frontend

```bash
cd frontend
npm install
npm run dev          # dev server at http://localhost:5173
npm run build        # production build to dist/
```

### Docker

```bash
docker-compose up --build
```

---

## 3. Configuration

All settings are read from `.env` (via Pydantic `BaseSettings`).

| Variable | Default | Purpose |
|---|---|---|
| `API_KEY` | `change-me` | Header value required on every API call (`X-API-Key`) |
| `CORS_ORIGINS` | `["http://localhost:3000"]` | JSON array of allowed origins |
| `DB_PATH` | `data/stockv2.db` | SQLite file path |
| `HOST` | `127.0.0.1` | Uvicorn bind host |
| `PORT` | `8000` | Uvicorn port |
| `TRADING_MODE` | `paper` | `paper` or `live` |
| `TOTAL_CAPITAL` | `500000` | Total account capital (₹) |
| `PAPER_CAPITAL` | `500000` | Paper trading starting capital |
| `RISK_PER_TRADE_PCT` | `2.0` | Max % of capital risked per trade |
| `MAX_OPEN_POSITIONS` | `8` | Concurrent position limit |
| `MAX_SINGLE_STOCK_PCT` | `20.0` | Max allocation to one stock (%) |
| `MAX_SECTOR_PCT` | `35.0` | Max allocation to one sector (%) |
| `DAILY_LOSS_LIMIT_PCT` | `3.0` | Daily stop-loss (% of capital) |
| `AUTO_TRADING_ENABLED` | `false` | Auto-execute signals |
| `MIN_CONFIDENCE_FOR_ALERT` | `0.65` | Minimum signal confidence for Telegram alert |
| `MAX_AI_SIGNALS_PER_DAY` | `10` | Claude API call budget per day |
| `ANTHROPIC_API_KEY` | — | Claude API key (signal explanations) |
| `TELEGRAM_BOT_TOKEN` | — | Telegram bot token |
| `TELEGRAM_CHAT_ID` | — | Telegram chat/channel ID |
| `ANGEL_ONE_API_KEY` | — | Angel One broker (optional, live feed) |

---

## 4. Database Schema

### Market Data

**`stocks`** — NSE stock universe (237 records)
- `symbol`, `name`, `sector`, `industry`, `exchange`, `is_active`

**`stock_prices_daily`** — OHLCV at daily granularity
- `symbol`, `date`, `open`, `high`, `low`, `close`, `volume`
- Unique on `(symbol, date)`

**`stock_prices_intraday`** — 15-min OHLCV
- `symbol`, `timestamp`, `open`, `high`, `low`, `close`, `volume`

**`fundamentals`** — Annual fundamentals per symbol
- PE, PB, EPS, revenue, net_income, ROE, debt_to_equity, FII holdings, promoter holdings

**`corporate_actions`** — Dividends, splits, rights
- `symbol`, `action_type`, `ex_date`, `value`

**`news`** — News articles
- `symbol`, `headline`, `source`, `published_at`, `sentiment_score`, `ai_summary`

---

### Strategies & Signals

**`strategies`** — Registered strategies
- `id`, `name`, `type`, `description`, `is_active`, `created_at`
- Seeded automatically from Python strategy classes at startup

**`strategy_signals`** — Generated BUY/SELL signals
- `symbol`, `strategy_id`, `signal_date`, `signal_type`
- `price_at_signal`, `confidence_score`, `risk_score`, `expected_upside_pct`
- `suggested_stop_loss`, `suggested_target`, `holding_period_days`
- `reasoning_json` — JSON with `conditions_met` and `conditions_failed` arrays

**`strategy_performance`** — Permanently precomputed backtest metrics per `(symbol, strategy_id)`
- CAGR, Sharpe, max drawdown, win rate, profit factor — for all-time backtest

**`scan_result_cache`** — Leaderboard computation cache
- Keyed by `(symbol, strategy_id, from_date, to_date, stop_loss_pct, target_pct)`
- Used by the Strategy Match / Leaderboard feature

---

### Backtest

**`backtest_results`** — One row per backtest run
- `symbol`, `strategy_id`, `from_date`, `to_date`, `ran_at`
- `total_trades`, `win_rate`, `cagr`, `sharpe_ratio`, `max_drawdown`, `profit_factor`, `total_pnl`

**`backtest_trades`** — Individual trades from a backtest
- `backtest_result_id`, `entry_date`, `entry_price`, `exit_date`, `exit_price`
- `pnl`, `pnl_pct`, `exit_reason`, `holding_days`

---

### Portfolio

**`portfolio_holdings`** — Currently open positions
- `symbol`, `quantity`, `avg_buy_price`, `invested_value`, `is_active`
- `stop_loss_price`, `target_1_price`

**`trades`** — All paper trades (buy + sell)
- `symbol`, `trade_type`, `trade_date`, `quantity`, `price`, `pnl`, `pnl_pct`

**`orders`** — Pending/executed orders
- `symbol`, `order_type`, `quantity`, `price`, `status`

**`exit_rules`** — Stop loss and target for each open position
- `symbol`, `stop_loss_pct`, `target_pct`, `stop_loss_price`, `target_price`

**`watchlist`** — Stocks being watched
- `symbol`, `added_at`, `notes`

---

### AI & Alerts

**`ai_analyses`** — Claude-generated signal explanations (cached with TTL)
- `signal_id`, `analysis`, `model`, `created_at`, `expires_at`

**`ai_conversations`** — Multi-turn chat history
- `session_id`, `role`, `content`, `created_at`

**`alerts`** — User-configured alert rules
- `symbol`, `condition`, `threshold`, `is_active`

**`alert_history`** — Triggered alert log
- `alert_id`, `triggered_at`, `value_at_trigger`, `message`

---

## 5. Backend Domains

### `domains/data/`

| File | Purpose |
|---|---|
| `router.py` | `GET /stocks`, `GET /stocks/{symbol}`, `GET /stocks/{symbol}/prices` |
| `service.py` | Database queries for stock data |
| `indicators.py` | IndicatorEngine — computes 26+ technical indicators on a price DataFrame |
| `nse_universe.py` | `NSE_SYMBOLS` — list of 237 active NSE symbols |
| `feeds/yfinance_feed.py` | Download OHLCV from YFinance, upsert to DB |
| `feeds/angel_one_feed.py` | Live quote feed from Angel One broker (optional) |

**Indicators computed per scan:**
SMA (5/10/20/50), EMA (5/9/10/13/21/26), RSI (5/14), MACD (12/26/9), Bollinger Bands (20,2), ATR (14 Wilder's), ADX (14), SuperTrend (7, 3.0), Stochastic, Williams %R, MFI (14), ROC (10), OBV, OBV SMA (10), Volume SMA (20), Volume Ratio, BB Width.

---

### `domains/strategies/`

| File | Purpose |
|---|---|
| `engine.py` | `StrategyEngine` — runs all strategies on all stocks, saves signals. `ALL_STRATEGIES` — auto-discovered list of live strategy instances |
| `base.py` | `BaseStrategy` abstract class — `generate_signal(df)`, `get_required_indicators()`, `get_parameters()` |
| `scanner.py` | `LiveScanner` — real-time scan without saving to DB; attaches `historical_win_rate` from cache |
| `service.py` | `StrategyService` — query signals, attach `historical_win_rate` via JOIN on `scan_result_cache` |
| `router.py` | `/strategies`, `/strategies/{id}`, `/signals/today`, `/signals/scan`, `/signals` |
| `seed.py` | Insert/update strategy rows in DB from auto-discovered classes |
| `aggregator.py` | Signal aggregation utilities |
| `strategies/` | 87 Python files, one per strategy |

**Adding a new strategy:** Create a file in `strategies/strategies/` that inherits `BaseStrategy`, implement `generate_signal(df) -> Signal`. It will be auto-discovered on next startup.

---

### `domains/backtest/`

| File | Purpose |
|---|---|
| `runner.py` | `BacktestRunner` — `run()` for single pair, `scan_all()` for full leaderboard compute. Saves to `scan_result_cache` and `backtest_results` |
| `simulator.py` | Trade simulation logic (entry/exit on OHLCV data with SL/target) |
| `metrics.py` | CAGR, Sharpe ratio, max drawdown, win rate, profit factor calculations |
| `service.py` | Query backtest_results and backtest_trades from DB |
| `router.py` | All `/backtest/*` endpoints including leaderboard, status, trades drill-down |

**Leaderboard:** Runs all 237 symbols × 87 strategies from 2015-01-01. Results cached in `scan_result_cache`. `POST /backtest/leaderboard/compute` triggers background computation. `GET /backtest/leaderboard/status` returns progress + `is_current` flag. Cache auto-refreshes at 4:30 PM IST daily.

---

### `domains/portfolio/`

| File | Purpose |
|---|---|
| `router.py` | `/portfolio/summary`, `/holdings`, `/trades`, `/pnl`, `/sell-alerts`, `/enter`, `/exit` |
| `service.py` | Portfolio CRUD, P&L calculations |
| `paper_trader.py` | `PaperTrader` — enter/exit positions with sizing, validates limits |
| `position_sizer.py` | Kelly / fixed-fraction position sizing |
| `exit_monitor.py` | `ExitMonitor` — checks if held positions hit stop loss or target |
| `watchlist_service.py` | Watchlist CRUD |

---

### `domains/ai/`

| File | Purpose |
|---|---|
| `explainer.py` | Calls Claude API (`claude-sonnet-4-6`) to explain a signal in plain English. Caches result in `ai_analyses` |
| `router.py` | `GET /signals/{signal_id}/explanation` |

---

### `domains/alerts/`

| File | Purpose |
|---|---|
| `telegram.py` | `AlertService` — `send_daily_digest()`, `send_sell_alerts()`. Formats rich HTML messages with signal blocks, win rates, P&L |

---

## 6. API Reference

All endpoints require `X-API-Key: <your_key>` header and are prefixed `/api/v1`.

### Market Data

| Method | Path | Description |
|---|---|---|
| GET | `/stocks` | List all stocks |
| GET | `/stocks/{symbol}` | Stock detail |
| GET | `/stocks/{symbol}/prices` | OHLCV history (`from_date`, `to_date`, `limit` params) |
| GET | `/health` | Health check (no auth required) |

### Strategies & Signals

| Method | Path | Description |
|---|---|---|
| GET | `/strategies` | List all active strategies |
| GET | `/strategies/{id}` | Strategy detail + live class metadata (timeframe, indicators, parameters) |
| GET | `/signals/today` | Today's signals (falls back to most recent scan date). Includes `historical_win_rate` |
| GET | `/signals` | Query signals (`symbol`, `signal_type`, `from_date`, `limit`) |
| GET | `/signals/{id}` | Single signal detail |
| POST | `/signals/scan` | Live scan — runs strategies right now, returns results with `historical_win_rate` |
| GET | `/signals/{id}/explanation` | Claude AI explanation of the signal |

### Backtest

| Method | Path | Description |
|---|---|---|
| POST | `/backtest/run` | Run backtest for one stock + strategy |
| POST | `/backtest/scan` | Batch scan multiple strategies |
| GET | `/backtest/scan/status` | Precompute readiness |
| GET | `/backtest/scan/results` | Precomputed results |
| GET | `/backtest/results` | Backtest history (`symbol`, `limit`) |
| GET | `/backtest/results/{id}` | Backtest result detail |
| GET | `/backtest/results/{id}/trades` | Individual trades |
| GET | `/backtest/leaderboard` | Top pairs by win rate (`stop_loss_pct`, `target_pct`, `min_trades`, `limit`, `symbol`, `strategy_id`) |
| GET | `/backtest/leaderboard/status` | Cache progress, `is_current`, `last_price_date`, `cached_to_date` |
| POST | `/backtest/leaderboard/compute` | Trigger background leaderboard computation (`force=true` to recompute) |
| GET | `/backtest/leaderboard/trades` | Trade list for a (symbol, strategy_id) pair |

### Portfolio

| Method | Path | Description |
|---|---|---|
| GET | `/portfolio/summary` | Capital, invested, cash, open positions |
| GET | `/portfolio/holdings` | Open positions |
| GET | `/portfolio/trades` | Trade history |
| GET | `/portfolio/pnl` | Closed P&L with per-trade breakdown |
| GET | `/portfolio/sell-alerts` | SELL signals from any strategy for currently held stocks |
| POST | `/portfolio/enter/{signal_id}` | Paper-trade entry |
| POST | `/portfolio/exit/{symbol}` | Paper-trade exit |
| GET | `/watchlist` | Watchlist |
| POST | `/watchlist/{symbol}` | Add to watchlist |
| DELETE | `/watchlist/{symbol}` | Remove from watchlist |

---

## 7. Trading Strategies

87 active strategies, auto-discovered from `backend/domains/strategies/strategies/`.

### Momentum & Oscillators (16)
| Strategy | Signal Logic |
|---|---|
| ADX Momentum | ADX > 25 + DI+ > DI- for trend strength |
| RSI Oversold Bounce | RSI(14) < 35, then crosses back above |
| RSI Overbought Reversal | RSI(14) > 70, sell signal |
| CCI Oversold | CCI < -100 bounce |
| CCI Overbought | CCI > 100 reversal |
| Williams R Oversold | W%R < -80 bounce |
| Williams R Overbought | W%R > -20 sell |
| MFI Oversold | MFI(14) < 25 |
| MFI Overbought | MFI(14) > 75 sell |
| ROC Momentum | Rate of Change crossover |
| Stochastic Oversold Cross | %K < 20 then crosses %D |
| Stochastic Overbought Cross | %K > 80 sell |
| RSI 5 Quick Bounce | RSI(5) < 25, very short-term |
| RSI Crossover 30 | RSI crosses above 30 |
| RSI Crossover 70 | RSI crosses below 70 |
| RSI Level Cross | RSI mid-line cross |

### Moving Average Crossovers (9)
| Strategy | Signal Logic |
|---|---|
| SMA 5/10 Crossover | SMA5 crosses SMA10 |
| SMA 10/20 Crossover | SMA10 crosses SMA20 |
| EMA 5/10 Crossover | EMA5 crosses EMA10 |
| EMA 5/13/26 Crossover | Triple EMA alignment (ChartInk) |
| Dual SMA Crossover | Medium-term SMA cross |
| EMA Ribbon Alignment | Multiple EMAs aligned in direction |
| EMA Triple Crossover | EMA5/13/26 all agree |
| Price SMA50 Bounce | Price bounces off 50-day SMA |
| Mean Reversion Deviation | Price reverts from SMA deviation |

### Bollinger Bands (7)
| Strategy | Signal Logic |
|---|---|
| BB Squeeze | Low BB width (compression) before breakout |
| Price Below Lower BB | Oversold, mean reversion buy |
| Price Above Upper BB Reversal | Overbought sell |
| BB BTST Breakout | Intraday BB breakout for next-day hold |
| MACD BB Squeeze | MACD + BB squeeze confluence |
| Chartink BB BTST Breakout | ChartInk variant |
| Chartink BTST BB | ChartInk BTST pattern |

### Trend Following (6)
| Strategy | Signal Logic |
|---|---|
| Supertrend | Standard SuperTrend(7, 3.0) flip |
| Supertrend ADX | SuperTrend + ADX > 20 filter |
| Swing Trend Rider | Multi-day trend continuation |
| Low ATR ADX Continuation | Low volatility + strong trend |
| Chartink Supertrend Flip | ChartInk SuperTrend variant |
| Chartink Supertrend Bearish | Supertrend sell variant |

### Breakout Strategies (10)
| Strategy | Signal Logic |
|---|---|
| ATR Compression Breakout | ATR compression then expansion |
| ATR Expansion Breakout | Volatility expansion entry |
| Gap and Go | Gap up on volume, continuation |
| Gap Fade | Gap up fade (sell) |
| Gap Volume Fade | Gap + volume confirmation fade |
| Volatility Breakout | ATR-based range breakout |
| Volume Breakout | Price breakout with 2× avg volume |
| Volume Price SMA Breakout | Volume + price above SMA |
| 52 Week High Breakout (ChartInk) | New 52-week high |
| 5 Day Range Breakout (ChartInk) | Breaks 5-day high/low range |

### Volume-Based (6)
| Strategy | Signal Logic |
|---|---|
| Volume Spike Reversal | Volume spike at support/resistance |
| Volume Trend Price Breakout | Volume trend + price breakout |
| OBV Trend | OBV making new highs with price |
| OBV Divergence Sell | Price up but OBV down |
| Volume Breakout | See Breakouts |
| Breaking Day High (ChartInk) | Breaks previous day high on volume |

### Candlestick Patterns (10)
| Strategy | Signal Logic |
|---|---|
| Hammer Reversal | Hammer candle at support |
| Morning Star | 3-candle morning star pattern |
| Bullish Engulfing | Green candle engulfs prior red |
| Bearish Engulfing (ChartInk) | Red candle engulfs prior green |
| Bullish Harami (ChartInk) | Inside bar bullish reversal |
| 3 Red Days Bounce | Three consecutive down days, bounce |
| Consecutive Green Reversal | Too many up days, sell signal |
| Consecutive Red Reversal | Too many down days, buy signal |
| Consecutive Higher Closes (ChartInk) | Sustained upward momentum |
| Doji Reversal (ChartInk) | Indecision + trend change |

### MACD-Based (4)
| Strategy | Signal Logic |
|---|---|
| MACD Crossover | MACD line crosses signal line |
| MACD Bearish Breakdown | MACD bearish cross |
| RSI MACD Confluence Buy | RSI oversold + MACD bullish cross |
| RSI MACD Double Sell | RSI overbought + MACD bearish cross |

### Pattern / ChartInk (20+)
| Strategy | Source |
|---|---|
| NR4 Pattern | Narrow Range 4-day compression |
| NR7 Bearish | Narrow Range 7-day sell |
| NR7 Uptrend | Narrow Range 7-day buy |
| Inside Bar Breakout | Inside bar expansion |
| Open Equals High | OEH pattern (weak open) |
| Open Equals Low | OEL pattern (strong open) |
| Momentum PDH | Previous day high breakout |
| Morning Breakout | Pre-market/opening range |
| FNO Bullish Trend | F&O stocks trending up |
| Strong Uptrend FNO | F&O with strong trend |
| Pure Bullish | Multiple bullish confluences |
| Short Term Breakout | 10–20 day breakout |
| Potential Breakout | Pre-breakout compression |
| NKS Best Buy | NKS scan variant |
| Perfect Sell | Multiple sell confluences |
| RSI Stochastic Bullish | RSI + Stochastic both oversold |
| Stochastic Cross Gap Up | Stochastic cross + gap up |
| Gap Up Breakout | Strong gap up |
| 52 Week Low Bounce | Near 52-week low reversal |
| Mean Reversion | Price far from mean, revert |

---

## 8. Scheduler Jobs

All jobs run in Asia/Kolkata (IST) timezone via APScheduler `BackgroundScheduler`.

| Time | Job | What it does |
|---|---|---|
| 3:45 PM Mon–Fri | `daily_data_refresh` | Incremental OHLCV download for all symbols (only missing days) |
| 4:00 PM Mon–Fri | `daily_eod_update` | Run all 87 strategies on all 237 stocks, save signals. Send SELL alerts to Telegram for any held stocks |
| Every 15 min, 9–15:30 Mon–Fri | `intraday_scan` | Live strategy scan during market hours. Runs exit monitor for open positions |
| 4:30 PM Mon–Fri | `leaderboard_refresh` | Auto-refresh leaderboard cache if new price data has arrived. Skips if already current |
| 9:15 AM Mon–Fri | `digest_0915` | Scan all stocks, send top BUY signals + SELL alerts to Telegram |
| 10:30 AM Mon–Fri | `digest_1030` | Same |
| 12:00 PM Mon–Fri | `digest_1200` | Same |
| 2:00 PM Mon–Fri | `digest_1400` | Same |
| 3:15 PM Mon–Fri | `digest_1515` | Same (pre-close) |
| Sunday 8:00 PM | `weekly_fundamentals` | Placeholder for fundamentals update |
| Sunday 10:00 PM | `weekly_precompute` | Backtest any new strategies that have no `strategy_performance` data yet |

**Digest logic** (`_intraday_digest`):
1. Run full strategy scan on all stocks.
2. Filter BUY signals only.
3. Filter to signals where `historical_win_rate >= 40%` OR no history exists yet.
4. Sort by confidence, take top 10.
5. Send to Telegram with price, SL, target, upside, historical win rate, strategy name, conditions.
6. Also send SELL alerts for any currently held positions.

---

## 9. Frontend Pages

### Dashboard (`/`)
- Portfolio summary cards: total capital, invested, available cash, open positions.
- BUY Signals table: all today's signals with confidence, price, SL, target, hold days, **historical win rate**.
- Click `+` to expand reasoning (conditions met/failed).
- Click `Enter` to paper-trade a position.
- Auto-refreshes every 3 minutes.

### Portfolio (`/portfolio`)
- **Sell Alerts banner**: red cards for any SELL signal on a stock you currently hold (any strategy). Shows signal price, confidence, P&L vs avg buy, conditions.
- **Open Positions table**: symbol, qty, avg price, invested value, stop loss, target. Manual exit with price input.
- **Closed P&L table**: per-trade history with P&L amount and percentage.

### Strategy Scanner (`/scanner`)
- Select strategy (or all), signal type, stock limit.
- Click `Run Scan` to run live strategies right now.
- Results table: symbol, strategy, signal, confidence, price, SL%, target%, hold days, **historical win rate** (green ≥60%, yellow ≥40%, red <40%, dash if no data).
- Sortable by any column.
- Strategy Card shown below controls when a strategy is selected (description, indicators, parameters).

### Strategy Match / Leaderboard (`/strategy-match`)
- Filter by strategy or stock symbol.
- SL% and Target% sliders.
- Status bar: shows cache progress, whether data is current, last price date.
- `Compute Now` button to trigger background computation; `Force Refresh` when already current.
- Table: symbol, strategy, trades, win rate, CAGR, Sharpe, max drawdown, profit factor, P&L.
- Click any row to expand inline trade history (entry/exit dates, prices, P&L, holding days, exit reason).
- Strategy Card shown for selected strategy.

### Backtest (`/backtest`)
- Run a backtest for a single (symbol, strategy) pair with custom date range, SL, target.
- Results: metrics summary + trade-by-trade table.

---

## 10. Data Flows

### 1. Historical Bootstrap (one-time)
```
Startup → no price data? → spawn daemon thread
  → YFinanceFeed.download_since() for each of 237 symbols
  → upsert_prices() → stock_prices_daily
  → ~20–60 min total, resumable (skips already-downloaded symbols)
```

### 2. Daily EOD Cycle
```
3:45 PM  → _daily_data_refresh()
            → for each symbol: get last date in DB
            → download only missing days from YFinance
            → upsert to stock_prices_daily

4:00 PM  → _daily_eod_update()
            → StrategyEngine.scan_all(237 symbols, today)
              → IndicatorEngine.compute(price df)
              → each of 87 strategies: generate_signal()
              → save to strategy_signals
            → _send_sell_alerts_for_holdings()
              → query SELL signals for held stocks
              → AlertService.send_sell_alerts()

4:30 PM  → _leaderboard_refresh()
            → check if scan_result_cache is current vs last price date
            → if stale: run BacktestRunner.scan_all() in background
              → 237 × 87 = ~20,619 backtests from 2015-01-01
              → results → scan_result_cache
```

### 3. Intraday Digests (5× per day)
```
9:15 / 10:30 / 12:00 / 14:00 / 15:15 IST
  → StrategyEngine.scan_all() → strategy_signals
  → StrategyService.get_today_signals()
    → LEFT JOIN scan_result_cache → historical_win_rate per signal
  → filter: win_rate >= 40% OR no history
  → sort by confidence, top 10
  → AlertService.send_daily_digest()
    → Telegram: symbol, strategy, price, SL, target, upside, win rate, conditions
  → _send_sell_alerts_for_holdings()
```

### 4. Live Scan (user-triggered)
```
POST /signals/scan
  → LiveScanner.scan(strategy_id, signal_type, limit)
    → load price data for up to 200 symbols
    → IndicatorEngine.compute() per symbol
    → strategies: generate_signal()
    → batch-load historical_win_rate from scan_result_cache
  → return results with win rate attached
```

### 5. Paper Trade Entry
```
POST /portfolio/enter/{signal_id}
  → PaperTrader.enter_position(signal_id, price)
    → validate: < max_positions, < max_single_stock_pct
    → position_sizer: calculate quantity from RISK_PER_TRADE_PCT
    → insert portfolio_holdings + trades record
    → insert exit_rules (stop_loss and target prices)
```

### 6. Leaderboard Drill-down
```
GET /backtest/leaderboard/trades?symbol=X&strategy_id=Y
  → check backtest_results for existing run from 2015-01-01
  → if found: return cached trades from backtest_trades
  → if not found: run BacktestRunner.run() (few seconds)
    → save to backtest_results + backtest_trades
    → return trades
```

---

## File Map (Quick Reference)

```
backend/
├── main.py                         FastAPI app, lifespan, router registration
├── settings.py                     Pydantic env config
├── database.py                     SQLAlchemy engine (SQLite WAL)
├── models.py                       All ORM models
├── scheduler.py                    APScheduler jobs (IST)
├── ist.py                          IST timezone utility (ist_now, ist_today)
└── domains/
    ├── data/
    │   ├── router.py               /stocks endpoints
    │   ├── indicators.py           IndicatorEngine (26+ indicators)
    │   ├── nse_universe.py         237 NSE symbols
    │   └── feeds/
    │       ├── yfinance_feed.py    Historical + incremental download
    │       └── angel_one_feed.py   Live quote feed (optional)
    ├── strategies/
    │   ├── engine.py               StrategyEngine, ALL_STRATEGIES
    │   ├── base.py                 BaseStrategy abstract class
    │   ├── scanner.py              LiveScanner (with win rate attach)
    │   ├── service.py              StrategyService (signals + win rate JOIN)
    │   ├── router.py               /strategies, /signals endpoints
    │   ├── seed.py                 Auto-seed strategy rows in DB
    │   └── strategies/             87 strategy .py files
    ├── backtest/
    │   ├── runner.py               BacktestRunner (run, scan_all)
    │   ├── simulator.py            Trade simulation engine
    │   ├── metrics.py              CAGR, Sharpe, drawdown, win rate
    │   ├── service.py              Backtest result queries
    │   └── router.py               /backtest/* endpoints + leaderboard
    ├── portfolio/
    │   ├── router.py               /portfolio/* endpoints
    │   ├── paper_trader.py         PaperTrader (enter/exit with sizing)
    │   ├── exit_monitor.py         ExitMonitor (stop loss / target check)
    │   ├── position_sizer.py       Position size calculation
    │   └── watchlist_service.py    Watchlist CRUD
    └── alerts/
        └── telegram.py             AlertService (digest + sell alerts)

frontend/src/
├── App.tsx                         React Router routes
├── components/
│   ├── NavBar.tsx                  Top navigation
│   └── StrategyCard.tsx            Strategy detail card component
├── pages/
│   ├── DashboardPage.tsx           Signals + portfolio summary
│   ├── PortfolioPage.tsx           Holdings + sell alerts + P&L
│   ├── ScannerPage.tsx             Live strategy scanner
│   ├── StrategyMatchPage.tsx       Leaderboard + trade drill-down
│   └── BacktestPage.tsx            Manual backtest runner
└── api/
    ├── client.ts                   apiFetch with X-API-Key
    ├── signals.ts                  Signals + live scan API
    ├── strategies.ts               Strategies API
    ├── backtest.ts                 Backtest API
    ├── leaderboard.ts              Leaderboard API (incl. trades)
    └── portfolio.ts                Portfolio API (incl. sell alerts)
```
