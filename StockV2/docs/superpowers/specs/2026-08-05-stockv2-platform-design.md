# StockV2 — AI Stock Analysis & Automated Trading Platform
## Design Specification

**Date:** 2026-08-05  
**Author:** Vivek Kumar  
**Status:** Approved  

---

## Table of Contents

1. [Product Overview](#1-product-overview)
2. [Scope & Constraints](#2-scope--constraints)
3. [System Architecture](#3-system-architecture)
4. [Database Schema](#4-database-schema)
5. [Strategy Engine](#5-strategy-engine)
6. [AI Architecture](#6-ai-architecture)
7. [Data Ingestion Pipeline](#7-data-ingestion-pipeline)
8. [Portfolio Management & Broker Integration](#8-portfolio-management--broker-integration)
9. [Alerts & Notifications](#9-alerts--notifications)
10. [REST API Design](#10-rest-api-design)
11. [Backtesting Engine](#11-backtesting-engine)
12. [Technology Stack](#12-technology-stack)
13. [Development Roadmap](#13-development-roadmap)
14. [Feature Priority Matrix](#14-feature-priority-matrix)

---

## 1. Product Overview

StockV2 is a personal AI-powered stock analysis and automated trading platform for NSE/BSE markets. It functions as a 24/7 research analyst, portfolio manager, and trading assistant — continuously scanning the market, generating AI-explained signals, tracking paper and real trades, and eventually executing orders automatically.

### What it does
- Continuously monitors 237+ NSE stocks using 26 trading strategies simultaneously
- Generates buy/sell/watch signals with AI-written explanations in plain English
- Tracks portfolio holdings with real-time P&L, risk analysis, and performance metrics
- Executes paper trades automatically; supports semi-auto and full-auto real trading via Angel One
- Sends proactive Telegram/email alerts for signals, news, stop losses, and targets
- Answers natural language questions about stocks, portfolio, and strategies
- Lets you create custom strategies by describing them in plain English
- Backtests every strategy with realistic cost simulation and walk-forward validation
- Learns from past trade outcomes to improve future recommendations

### What it is NOT
- Not a multi-user SaaS platform — single user only, runs locally or on a personal VPS
- Not a real-time HFT system — designed for positional/swing trading (days to weeks)
- Not financial advice — a personal research and automation tool

---

## 2. Scope & Constraints

| Dimension | Decision |
|---|---|
| Markets (MVP) | NSE/BSE only |
| Markets (future) | Architecture allows US, crypto, ETF, F&O addition |
| Users | Single user only — no auth complexity, no multi-tenancy |
| Deployment | Local machine or cheap VPS (no Docker for now) |
| Trading (MVP) | Paper trading only |
| Trading (V2+) | Semi-auto and full-auto via Angel One SmartAPI |
| Infrastructure | No Docker, no Redis, no Celery — pure Python + SQLite + APScheduler |
| AI Provider | Claude API (anthropic SDK) |
| Live Data | Angel One SmartAPI (free with account) + yfinance fallback |
| Historical Data | yfinance (15 years, 237+ NSE stocks) |

---

## 3. System Architecture

### Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        StockV2 - Personal Trading Platform       │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    Next.js Frontend                       │   │
│  │   Dashboard │ Strategies │ Portfolio │ AI Chat │ Alerts   │   │
│  └──────────────────────┬───────────────────────────────────┘   │
│                         │ HTTP + WebSocket                       │
│  ┌──────────────────────▼───────────────────────────────────┐   │
│  │                    FastAPI Backend                        │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐   │   │
│  │  │   Data   │ │Strategy  │ │    AI    │ │Portfolio │   │   │
│  │  │  Domain  │ │  Domain  │ │  Domain  │ │  Domain  │   │   │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘   │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐                │   │
│  │  │  Broker  │ │  Alerts  │ │Backtesting│               │   │
│  │  │  Domain  │ │  Domain  │ │  Domain  │                │   │
│  │  └──────────┘ └──────────┘ └──────────┘                │   │
│  │                    APScheduler                           │   │
│  └──────────────────────┬───────────────────────────────────┘   │
│                         │                                        │
│  ┌──────────────────────▼───────────────────────────────────┐   │
│  │                    SQLite (WAL mode)                      │   │
│  │  stocks │ prices │ signals │ portfolio │ trades │ news   │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  External APIs: Angel One │ yfinance │ Claude API │ Telegram     │
└─────────────────────────────────────────────────────────────────┘
```

### Domain Isolation Rule
Each domain owns its routes, services, models, and DB access. No domain reaches directly into another domain's tables. Cross-domain communication happens through service calls only.

### APScheduler Jobs (inside FastAPI process)
All heavy background work runs as scheduled jobs in the same process. No separate worker process needed.

### Startup Sequence
```
python backend/main.py
  → FastAPI app starts on :8000
  → SQLite connection pool opens (WAL mode)
  → APScheduler starts with all jobs
  → Angel One WebSocket connects (if market hours)
  → Historical data check (bootstrap if first run)

npx next dev (or next start)
  → Next.js on :3000
  → Connects to FastAPI via HTTP + WebSocket
```

---

## 4. Database Schema

SQLite 3.45+ with WAL mode enabled. All tables listed with key columns.

### Market Data Domain

```sql
-- Master stock universe
stocks (
  id, symbol, name, sector, industry, market_cap,
  exchange TEXT DEFAULT 'NSE', is_active, added_at
)

-- End-of-day OHLCV from yfinance or NSE bhav copy
stock_prices_daily (
  id, symbol, date, open, high, low, close, volume,
  adj_close, data_source TEXT DEFAULT 'yfinance'
)

-- Intraday candles from Angel One live feed
stock_prices_intraday (
  id, symbol, timestamp, open, high, low, close,
  volume, interval TEXT  -- '1m' | '5m' | '15m' | '1h'
)

-- Quarterly fundamentals scraped from screener.in
fundamentals (
  id, symbol, date, pe_ratio, pb_ratio, eps, revenue,
  net_profit, debt_equity, roe, promoter_holding,
  fii_holding, dii_holding, data_as_of
)

-- Dividends, splits, bonuses from NSE
corporate_actions (
  id, symbol, action_type, ex_date, record_date, value, notes
)

-- News with AI sentiment (added for news analysis feature)
news (
  id, symbol,  -- nullable for market-wide news
  headline, source_url, published_at,
  sentiment TEXT,  -- 'positive' | 'negative' | 'neutral'
  impact_score REAL,  -- 0.0 to 1.0
  category TEXT,  -- 'earnings' | 'management' | 'regulatory' | etc.
  ai_summary TEXT,
  fetched_at
)
```

### Strategy & Signals Domain

```sql
-- Strategy definitions (built-in + user-created)
strategies (
  id, name, type TEXT,  -- 'technical' | 'fundamental' | 'ml' | 'custom'
  description, parameters_json, is_active, created_at
)

-- Core signal table — one row per stock+strategy+date
strategy_signals (
  id, symbol, strategy_id, signal_date,
  signal_type TEXT,  -- 'BUY' | 'SELL' | 'WATCH'
  price_at_signal, confidence_score, risk_score,
  expected_upside_pct, suggested_stop_loss, suggested_target,
  holding_period_days,
  reasoning_json,    -- full AI explanation stored here
  indicators_json,   -- which indicators triggered
  created_at
)

-- Backtest summary per strategy
backtest_results (
  id, strategy_id, symbol,  -- null = all stocks
  from_date, to_date,
  total_trades, win_rate, cagr, sharpe_ratio, sortino_ratio,
  max_drawdown, profit_factor, avg_return_pct,
  full_metrics_json,  -- all other metrics
  ran_at
)

-- Individual trades from each backtest run
backtest_trades (
  id, backtest_result_id, symbol,
  entry_date, entry_price, exit_date, exit_price,
  quantity, pnl, pnl_pct, exit_reason,
  holding_days
)

-- Data quality issues flagged during ingestion
data_quality_log (
  id, symbol, date, issue_type, details, resolved, logged_at
)
```

### Portfolio Domain

```sql
-- Current holdings
portfolio_holdings (
  id, symbol, quantity, avg_buy_price,
  first_buy_date, last_buy_date, notes, is_active
)

-- Every trade ever (paper + real)
trades (
  id, symbol, trade_type TEXT,  -- 'BUY' | 'SELL'
  quantity, price, total_value, brokerage,
  trade_date, order_id,
  mode TEXT DEFAULT 'paper',  -- 'paper' | 'real'
  strategy_id,    -- nullable, which strategy triggered this
  signal_id,      -- nullable, which signal led to this trade
  notes
)

-- All orders placed (pending + executed + cancelled)
orders (
  id, symbol, order_type TEXT,  -- 'MARKET' | 'LIMIT' | 'SL'
  side TEXT,  -- 'BUY' | 'SELL'
  quantity, price, trigger_price,
  status TEXT,  -- 'pending' | 'executed' | 'cancelled' | 'rejected'
  broker_order_id, placed_at, executed_at,
  mode TEXT DEFAULT 'paper'
)

-- Exit rules registered after every buy
exit_rules (
  id, order_id, symbol, entry_price,
  stop_loss_price, target_1_price, target_2_price,
  max_exit_date, partial_exit_at_t1 BOOLEAN
)

-- Watchlist
watchlist (
  id, symbol, added_at, reason,
  strategy_id,  -- nullable
  alert_price   -- nullable
)
```

### AI Domain

```sql
-- Cached AI responses — never re-call API for same analysis
ai_analyses (
  id,
  subject_type TEXT,  -- 'signal' | 'stock' | 'news' | 'portfolio'
  subject_id,
  analysis_type TEXT,
  content TEXT,       -- full AI response JSON
  model_used,
  tokens_used,
  created_at,
  expires_at          -- cache TTL
)

-- Chatbot conversation history
ai_conversations (
  id, role TEXT,  -- 'user' | 'assistant'
  content TEXT,
  created_at
)
```

### Alerts Domain

```sql
alerts (
  id, alert_type TEXT, symbol,
  condition_json,       -- what triggers this alert
  message_template,
  channels_json,        -- ["telegram", "email"]
  is_active, created_at
)

alert_history (
  id, alert_id, symbol, triggered_at,
  message_sent, delivery_status_json
)
```

### Key Indexes

```sql
CREATE INDEX idx_prices_daily_symbol_date ON stock_prices_daily(symbol, date);
CREATE INDEX idx_prices_intraday_symbol_ts ON stock_prices_intraday(symbol, timestamp);
CREATE INDEX idx_signals_symbol_date ON strategy_signals(symbol, signal_date);
CREATE INDEX idx_signals_strategy ON strategy_signals(strategy_id, signal_date);
CREATE INDEX idx_trades_symbol ON trades(symbol, trade_date);
CREATE INDEX idx_news_symbol_published ON news(symbol, published_at);
CREATE INDEX idx_ai_analyses_subject ON ai_analyses(subject_type, subject_id, expires_at);
CREATE INDEX idx_backtest_trades_result ON backtest_trades(backtest_result_id);
CREATE INDEX idx_data_quality_symbol ON data_quality_log(symbol, logged_at);
```

---

## 5. Strategy Engine

### Architecture

```
New Price Data (daily EOD / intraday tick)
              │
              ▼
    IndicatorEngine.compute()
    (RSI, MACD, EMA, ATR, BB, Volume, SuperTrend, etc.)
              │
              ▼
    StrategyEngine.scan_all()
    (runs all active strategies on each stock)
              │
              ▼
    SignalAggregator
    (consensus score, confidence ranking)
              │
              ▼
    Save to strategy_signals
              │
              ▼
    AIExplainer.explain_top_signals()  ← top 10 only
              │
              ▼
    AlertEngine.evaluate()
```

### Base Strategy Interface

```python
class BaseStrategy:
    name: str
    strategy_type: StrategyType   # TECHNICAL | FUNDAMENTAL | ML | CUSTOM
    timeframe: Timeframe          # DAILY | INTRADAY_15M | INTRADAY_1H
    min_holding_days: int
    max_holding_days: int

    def generate_signal(self, df: DataFrame, fundamentals: dict) -> Signal
    def get_parameters(self) -> dict
    def validate_parameters(self, params) -> bool
    def get_required_indicators(self) -> list[str]

@dataclass
class Signal:
    signal_type: Literal["BUY", "SELL", "WATCH", "NONE"]
    confidence: float          # 0.0 - 1.0
    risk_score: float          # 0.0 - 1.0
    expected_upside_pct: float
    stop_loss_pct: float
    target_pct: float
    holding_days: int
    conditions_met: list[str]
    conditions_failed: list[str]
```

### Strategy Registry — 26 Built-in Strategies

**Group 1: Momentum & Trend (7)**
| Strategy | Timeframe | Typical Hold |
|---|---|---|
| RSI Oversold/Overbought | Daily | 5-15 days |
| MACD Crossover | Daily | 10-30 days |
| EMA Crossover (9/21) | Daily/15m | 5-20 days |
| SMA Crossover (20/50) | Daily | 20-60 days |
| SuperTrend | Daily | 15-45 days |
| Trend Following (ADX) | Daily | 30-90 days |
| Momentum (Rate of Change) | Daily | 10-30 days |

**Group 2: Volatility & Mean Reversion (5)**
| Strategy | Timeframe | Typical Hold |
|---|---|---|
| Bollinger Band Squeeze | Daily | 5-20 days |
| Volume Breakout | Daily/15m | 3-10 days |
| Mean Reversion + Volatility Filter | Daily | 7-21 days |
| Volatility Breakout | Daily | 3-7 days |
| Swing Trade Trend Rider | Daily | 7-21 days |

**Group 3: Smart Money (4)**
| Strategy | Timeframe | Notes |
|---|---|---|
| FII/DII Net Buying | Weekly | From fundamentals data |
| Institutional Accumulation | Daily | Volume + price pattern |
| Smart Money Concepts (BOS/CHoCH) | Daily | Break of structure |
| Sector Rotation | Weekly | Relative sector strength |

**Group 4: Fundamental (5)**
| Strategy | Rerun Frequency |
|---|---|
| CANSLIM | Weekly |
| Magic Formula (Greenblatt) | Weekly |
| Value Investing (Graham Number) | Weekly |
| Growth Investing | Weekly |
| Dividend Investing | Weekly |

**Group 5: ML-Based (3)**
| Strategy | Model |
|---|---|
| Smart Entry Confirmation | XGBoost + RF ensemble |
| Weekly Setup Precision | LightGBM |
| AI Momentum Predictor | Claude-enhanced features |

**Group 6: Custom** — created by user via NL strategy builder

### Signal Aggregation

```
consensus_score = weighted average of all BUY signals
                  weighted by: strategy_type_weight × confidence

Strategy type weights:
  ML strategies:           0.35
  Smart Money:             0.25
  Technical (momentum):    0.20
  Technical (volatility):  0.15
  Fundamental:             0.05

Final signal:
  BUY   if consensus_score > 0.65 AND ≥3 strategies agree
  WATCH if consensus_score > 0.45 AND ≥2 strategies agree
  SELL  if any sell condition triggers on a held stock
```

### APScheduler Jobs

```
Market Hours (9:15 AM – 3:30 PM IST)
  Every 15 min  → fetch Angel One intraday ticks → run intraday strategies
  Every 1 hour  → check exit conditions on all portfolio holdings

Post Market (after 3:30 PM IST)
  4:00 PM  → fetch EOD data (yfinance) → run all daily strategies
  4:30 PM  → ML model inference on fresh signals
  5:00 PM  → AI explain top 10 signals of the day
  5:15 PM  → send Telegram daily digest

Weekly (Sunday 8 PM)
  → run fundamental strategies (CANSLIM, Magic Formula, etc.)
  → update FII/DII data
  → retrain ML models if enough new data accumulated

Monthly
  → full ML retrain on all 237 NSE stocks
```

### Sell Signal Engine

For every holding, after each price update:

```
evaluate_exit_conditions(holding, current_price, exit_rules):
  stop_loss_triggered?     → SELL immediately
  target_2_reached?        → SELL immediately
  target_1_reached?        → SELL 50% if partial_exit enabled
  max_holding_days passed? → SELL (time-based exit)
  original_strategy_reversal? → SELL
  momentum_broken?         → WATCH → escalate to SELL

Each exit generates AI explanation:
  "Stop loss triggered at ₹842. Entry was ₹920, loss -8.5%.
   MACD bearish. No reversal pattern confirmed. Exit recommended."
```

---

## 6. AI Architecture

### Capability Map

```
Claude API (claude-sonnet-4-6)
         │
         ├── SignalExplainer      → "Why should I buy this stock?"
         ├── SellExplainer        → "Why should I exit this position?"
         ├── NewsAnalyzer         → News sentiment + impact scoring
         ├── DocumentAnalyzer     → Earnings/annual report summaries
         ├── NLStrategyBuilder    → Plain English → executable strategy
         ├── PortfolioAdvisor     → Portfolio health + improvement suggestions
         ├── StockComparator      → Side-by-side stock analysis
         ├── MarketChatbot        → Free-form Q&A with portfolio context
         ├── AnomalyDetector      → Unusual volume/price/news patterns
         └── TradeMemory          → Learn from past trade outcomes
```

### Core Design Principles

1. **Cache aggressively** — every response stored in `ai_analyses` with TTL
   - Signal explanations: 6 hours
   - News summaries: 2 hours
   - Portfolio advice: 1 hour
   - Annual report summaries: 30 days

2. **Structured outputs** — all Claude calls use tool use / JSON mode, no free-form parsing

3. **Prompt caching** — system prompt sent with `cache_control: ephemeral`, cutting costs ~70% on repeated calls

### SignalExplainer Output Structure

```json
{
  "summary": "RELIANCE showing strong breakout above 6-month resistance...",
  "bull_case": ["Volume 3x average on breakout", "FII net buyers last 3 weeks"],
  "bear_case": ["Broader market weak", "Sector rotation away from energy"],
  "confidence_reasoning": "3 of 5 ML strategies agree, institutional accumulation confirmed",
  "suggested_entry": 2847.50,
  "stop_loss": 2720.00,
  "target_1": 3050.00,
  "target_2": 3200.00,
  "holding_period": "15-25 days",
  "risk_rating": "MEDIUM"
}
```

### NLStrategyBuilder Pipeline

```
User text: "Find companies with PE below 20, profit growing > 15% YoY,
            RSI below 40, and FII buying last month"
    │
    ▼
Claude extracts structured intent (JSON)
    │
    ▼
StrategyCompiler converts to BaseStrategy subclass
    │
    ▼
Validate: can all required indicators be computed? → Yes/No
    │
    ▼
Save to strategies table with type='custom'
    │
    ▼
Run immediately → show matching stocks to user
```

### TradeMemory (V3)

After every closed trade:
1. Record: entry signal → strategy → AI reasoning → exit → P&L
2. Monthly: Claude reviews all closed trades, identifies patterns
3. Generates "Trading Insights":
   - Which strategies have best win rate for you specifically
   - Patterns in losing trades
   - Recommended strategy confidence threshold adjustments
4. Confidence scores adjusted based on personal historical accuracy

### Prompt Architecture

```python
# System prompt — cached, sent once per session window
SYSTEM_PROMPT = """
You are an expert Indian stock market analyst with 20 years of NSE/BSE experience.
You specialize in technical analysis, fundamental analysis, and quantitative strategies.
You always explain reasoning in plain English, give specific price levels,
and never give generic advice. You understand NSE regulations, F&O dynamics,
FII/DII behavior, and sector cycles in Indian markets.
"""

# Per-call payload — only fresh data, small
user_prompt = f"""
Analyse BUY signal for {symbol}:
Triggered strategies: {strategies_triggered}
Indicators: RSI={rsi}, MACD={macd_hist}, Volume={vol_ratio}x avg
Price action (30d): {price_summary}
Recent news: {news_headlines}
Fundamentals: {fundamental_snapshot}
Generate structured analysis.
"""
```

### Estimated Daily API Cost

| Feature | Avg Tokens/Call | Cache Hit | Est. Daily Cost |
|---|---|---|---|
| Signal explanations (top 10) | ~2,000 | 80% | ~₹8 |
| News analysis (20 stocks) | ~1,500 | 60% | ~₹12 |
| Portfolio advice | ~3,000 | 70% | ~₹4 |
| Chatbot (10 questions) | ~1,000 | 50% | ~₹5 |
| **Total (with caching)** | | | **~₹10-15/day** |

---

## 7. Data Ingestion Pipeline

### Data Sources

| Source | What it provides | Cost | Frequency |
|---|---|---|---|
| yfinance | Historical OHLCV (15yr) | Free | Daily EOD |
| Angel One SmartAPI | Live quotes + intraday | Free* | Real-time |
| NSE Bhav Copy | Official EOD (fallback) | Free | Daily |
| Screener.in (scrape) | Fundamentals | Free | Weekly |
| NSE Website | FII/DII data, corp actions | Free | Daily |
| Google News RSS | News headlines | Free | Every 2hr |

### Pipeline Architecture

```
DataIngestionService
  ├── HistoricalFeed (yfinance)
  ├── LiveFeed (Angel One WebSocket)
  ├── FundaFeed (Screener.in scraper)
  └── NewsFeed (Google News RSS)
         │
         ▼
    DataValidator
    (gaps, outliers, splits, bad ticks)
         │
         ▼
    IndicatorEngine
    (compute all indicators on save)
         │
         ▼
    SQLite DB
```

### Feed 1: Historical Bootstrap (first run only, ~30-45 min)

```
For each symbol in NSE universe (237 stocks):
  1. Download 15yr daily OHLCV via yfinance (symbol + ".NS")
  2. Detect and handle splits/bonuses
  3. Validate: fill gaps, flag missing > 5 consecutive days
  4. Compute all indicators on full history
  5. Batch insert to stock_prices_daily (500 rows/batch)

Progress saved per stock — crash-safe and resumable.
```

### Feed 2: Daily Incremental (4:00 PM IST)

```
For each symbol:
  1. Find last date in DB
  2. Fetch only missing dates from yfinance (usually 1 day)
  3. Recompute indicators for last 60 days
  4. Upsert to stock_prices_daily
```

### Feed 3: Live Intraday (Angel One WebSocket, market hours)

```
Subscribe to: portfolio stocks + watchlist + top signal stocks (~50 stocks)
On tick:
  → Aggregate into 1m/5m/15m candles
  → Store in stock_prices_intraday
  → Push to FastAPI WebSocket → UI live updates
  → Every 15 min: run intraday strategies
  → Check exit conditions on portfolio

Fallback: yfinance fast_info (15min delayed) if Angel One unavailable
```

### Feed 4: Fundamentals (Screener.in, Sunday 8 PM)

Scrapes per stock: PE, PB, EPS, revenue (8 quarters), net profit (8 quarters), debt/equity, ROE, ROCE, promoter holding %, FII %, DII %, market cap. 2-second delay between requests.

### Feed 5: News (Google News RSS, every 2 hours)

```
Fetch RSS for portfolio + watchlist stocks
→ Deduplicate by hash(title + source)
→ Claude batch-analyze: sentiment + impact_score + category
→ impact_score > 0.7 → immediate alert (bypass digest schedule)
→ Store in news table
```

### Data Quality Rules

```python
VALIDATION_RULES = {
    "price_spike":    high / low < 2.0,       # flag >100% intraday range
    "zero_volume":    volume > 0,
    "future_date":    date <= today,
    "negative_price": close > 0,
    "gap_threshold":  7,                       # flag if >7 trading days missing
}
```

---

## 8. Portfolio Management & Broker Integration

### PortfolioService

Every 15 min (market hours):
```
For each holding:
  unrealized_pnl = (current_price - avg_buy_price) × quantity
  unrealized_pnl_pct = unrealized_pnl / (avg_buy_price × quantity) × 100

Portfolio aggregates:
  total_invested = Σ(avg_buy_price × quantity)
  current_value  = Σ(current_price × quantity)
  cash_available = total_capital - total_invested
  allocation_pct = holding_value / total_capital × 100
```

### PerformanceCalculator

```python
daily_pnl()              → today's portfolio move (₹ and %)
total_return_pct()       → inception to date
cagr()                   → annualized return
win_rate()               → % of closed trades profitable
sharpe_ratio()           → vs Nifty 50 as benchmark
benchmark_comparison()   → your CAGR vs Nifty CAGR
best_trade()             → highest % gain ever
worst_trade()            → biggest % loss ever
```

### RiskAnalyzer

```python
sector_exposure()        → {"IT": 28%, "Banking": 22%, ...}
concentration_risk()     → stocks breaching max_single_stock_pct
portfolio_beta()         → sensitivity vs Nifty 50
value_at_risk()          → 1-day VaR at 95% confidence

# Configurable limits (settings.json)
max_single_stock_pct = 20.0   # no stock > 20% of portfolio
max_sector_pct = 35.0         # no sector > 35%
```

### Broker Abstraction Layer

```python
class BrokerInterface(ABC):
    def place_order(self, order: Order) -> OrderResponse
    def cancel_order(self, order_id: str) -> bool
    def get_order_status(self, order_id: str) -> OrderStatus
    def get_positions(self) -> list[Position]
    def get_account_balance(self) -> float

class PaperBroker(BrokerInterface):
    # Simulates execution. fill_price = market_price × (1 + slippage)
    # Records to trades table with mode='paper'

class AngelOneBroker(BrokerInterface):
    # Real execution via Angel One SmartAPI
    # Records to trades table with mode='real'

# One config change to switch:
TRADING_MODE = "paper"  # → "real" when ready
broker = PaperBroker() if TRADING_MODE == "paper" else AngelOneBroker()
```

### Order Execution Flow

```
Signal (BUY, confidence 0.78)
    │
    ▼
RiskValidator
  ✓ Position size ≤ 20% portfolio?
  ✓ Sector exposure within limits?
  ✓ Cash available?
  ✓ Daily loss limit not exceeded?
  ✓ Max open positions not reached?
    │ PASS
    ▼
TradingModeGate
  ├── SEMI_AUTO → push notification → you approve → execute
  └── FULL_AUTO → execute immediately
    │
    ▼
OrderManager
  place_order() → save to orders → poll status →
  on FILLED: update trades + holdings + register exit_rules + send alert
```

### Automatic Exit Rules

Registered after every buy:
```python
ExitRules:
  stop_loss_price   = entry × (1 - stop_loss_pct/100)   # e.g., -7%
  target_1_price    = entry × (1 + target_1_pct/100)    # e.g., +10%
  target_2_price    = entry × (1 + target_2_pct/100)    # e.g., +20%
  max_exit_date     = entry_date + max_holding_days
  partial_exit_at_t1 = True   # sell 50% at T1, trail remainder
```

### Trading Settings (settings.json)

```json
{
  "trading_mode": "paper",
  "total_capital": 500000,
  "risk_per_trade_pct": 2.0,
  "max_open_positions": 8,
  "max_single_stock_pct": 20.0,
  "max_sector_pct": 35.0,
  "daily_loss_limit_pct": 3.0,
  "auto_trading_enabled": false,
  "paper_capital": 500000
}
```

**Master kill switch:** `POST /api/v1/trading/kill-switch` — disables all automated order placement immediately. One-button emergency stop.

---

## 9. Alerts & Notifications

### Alert Types

```
Signal alerts:
  NEW_BUY_SIGNAL          → strategy BUY with confidence > threshold
  NEW_SELL_SIGNAL         → exit signal on a holding
  WATCHLIST_SIGNAL        → watchlist stock got a signal

Price alerts:
  PRICE_TARGET_HIT        → stock crossed custom price
  STOP_LOSS_TRIGGERED     → holding crossed stop loss
  TARGET_REACHED          → holding hit profit target
  PRICE_SPIKE             → unusual intraday move > X%

Portfolio alerts:
  PORTFOLIO_DOWN_X_PCT    → portfolio fell X% today
  HOLDING_UP_X_PCT        → a holding gained X% (lock profit reminder)
  POSITION_OVERWEIGHT     → single stock > max_single_stock_pct

Events:
  HIGH_IMPACT_NEWS        → news impact_score > 0.7 for a holding
  EARNINGS_TOMORROW       → earnings announcement next trading day
  EX_DIVIDEND_TOMORROW    → ex-dividend date tomorrow
  PROMOTER_SELLING        → promoter shareholding dropped significantly

System:
  DATA_FEED_DOWN          → Angel One or yfinance not responding
  ML_RETRAIN_COMPLETE     → weekly ML retrain finished
  DAILY_DIGEST            → end-of-day summary (always at 5:15 PM)
```

### Notification Channels

**Telegram (primary)** — inherited from v1, proven to work. Every signal alert, stop loss, target, and daily digest goes to Telegram.

**Email (secondary)** — Gmail SMTP with app password. Used only for: daily digest, weekly performance report, high-impact news. Not every signal (too noisy for email).

**In-app (WebSocket push)** — toast notifications in the UI, delivered via the same WebSocket connection used for live prices.

### Daily Telegram Digest (5:15 PM IST)

```
📊 DAILY DIGEST — 05 Aug 2026
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PORTFOLIO: ₹5,42,300 (+₹8,200 today, +1.5%)
vs Nifty 50: +0.8% → outperformed by 0.7%

NEW SIGNALS TODAY (3):
  🟢 TITAN — BUY (82% confidence)
  🟢 HDFCBANK — BUY (71% confidence)
  🔴 WIPRO — SELL (holding at -4.2%)

HOLDINGS:
  TCS:      +2.1% today | +12.3% overall ✅
  RELIANCE: -0.8% today | +4.1% overall
  INFY:     -1.2% today | -2.3% overall ⚠️

TOP NEWS:
  • TCS wins $500M deal from US bank (POSITIVE)
  • RBI holds rates (NEUTRAL for banking)
```

---

## 10. REST API Design

Base URL: `http://localhost:8000/api/v1`  
Auth: `X-API-Key: <your-secret-key>` header on all requests.

### Market Data
```
GET  /stocks                            → list all NSE stocks
GET  /stocks/{symbol}                   → stock detail + current price
GET  /stocks/{symbol}/prices            → OHLCV (params: from, to, interval)
GET  /stocks/{symbol}/indicators        → current technical indicators
GET  /stocks/{symbol}/fundamentals      → latest fundamental data
GET  /stocks/{symbol}/news              → recent news with sentiment
GET  /market/sentiment                  → overall market sentiment
GET  /market/top-movers                 → top gainers/losers today
```

### Signals & Strategies
```
GET  /signals                           → all signals (params: date, type, strategy_id)
GET  /signals/today                     → today's signals ranked by confidence
GET  /signals/{id}                      → signal detail with AI explanation
GET  /signals/{id}/explanation          → AI explanation (generates if not cached)

GET  /strategies                        → all strategies with performance stats
GET  /strategies/{id}                   → strategy detail
POST /strategies/{id}/run               → run strategy now on all stocks
POST /strategies/create-from-nl         → NL strategy builder
     body: { "description": "..." }

GET  /backtest/{strategy_id}            → latest backtest results
POST /backtest/run                      → trigger backtest (async, returns job_id)
     body: { "strategy_id": 1, "from": "2020-01-01", "to": "2024-12-31" }
GET  /backtest/status/{job_id}          → progress check
```

### Portfolio
```
GET  /portfolio                         → full portfolio summary
GET  /portfolio/holdings                → all holdings with P&L
GET  /portfolio/performance             → CAGR, Sharpe, win rate, etc.
GET  /portfolio/risk                    → sector exposure, concentration, VaR
GET  /portfolio/trades                  → trade history (params: mode, from, to)
POST /portfolio/trades                  → manual trade entry
```

### Orders & Trading
```
GET  /orders                            → order history
POST /orders                            → place order
DELETE /orders/{id}                     → cancel order
GET  /orders/{id}/status                → order status

GET  /settings/trading                  → current trading config
PUT  /settings/trading                  → update config
POST /trading/kill-switch               → disable all auto-trading immediately
```

### AI & Chat
```
GET  /ai/analyse/{symbol}               → full AI analysis for a stock
POST /ai/compare                        → compare 2-3 stocks
     body: { "symbols": ["TCS", "INFY", "WIPRO"] }
POST /ai/chat                           → chatbot message
     body: { "message": "Which holdings are at risk?" }
GET  /ai/chat/history                   → conversation history
GET  /ai/portfolio-advice               → AI portfolio improvement suggestions
GET  /ai/trade-insights                 → lessons from past trades (V3)
```

### Alerts & Watchlist
```
GET    /alerts                          → all configured alerts
POST   /alerts                          → create alert
DELETE /alerts/{id}                     → delete alert
GET    /alerts/history                  → fired alert history

GET    /watchlist                       → watchlist
POST   /watchlist                       → add stock to watchlist
DELETE /watchlist/{symbol}              → remove from watchlist
```

### WebSocket Endpoints
```
WS /ws/prices      → live price stream (subscribed symbols)
WS /ws/signals     → real-time new signal notifications
WS /ws/alerts      → real-time alert pushes
WS /ws/orders      → order status updates
```

---

## 11. Backtesting Engine

### Architecture

```
BacktestRequest (strategy_id, symbols, from_date, to_date, capital)
    │
    ▼
DataLoader.load_historical()  ← loads prices + indicators for range
    │
    ▼
BacktestRunner.run()
  For each trading day in range:
    strategy.generate_signal(df) → Signal
    open_position() or close_position()
    check_exit_conditions()
    apply_slippage_and_commission()
    │
    ▼
MetricsCalculator.compute()
    │
    ▼
Save to backtest_results + backtest_trades
    │
    ▼
AI summary of results (optional)
```

### Realistic Cost Simulation

```python
BacktestConfig:
  initial_capital = 500_000       # ₹5 lakh
  position_size_pct = 10.0        # 10% per trade
  max_open_positions = 10

  brokerage_pct = 0.03            # NSE retail typical
  stt_pct = 0.1                   # STT on sell side
  exchange_charges_pct = 0.00345
  gst_on_charges = 0.18
  slippage_pct = 0.05

  stop_loss_pct = 7.0
  target_pct = 15.0
  max_holding_days = 30

  min_avg_volume = 100_000        # liquidity filter
  min_price = 50.0                # no penny stocks
```

### Performance Metrics Computed

```
Returns:    total_return_pct, cagr, benchmark_cagr (Nifty 50), alpha
Risk:       max_drawdown_pct, max_drawdown_duration_days,
            volatility_annualized, sharpe_ratio, sortino_ratio, calmar_ratio
Trades:     total_trades, win_rate, avg_win_pct, avg_loss_pct,
            profit_factor, avg_holding_days, expectancy,
            largest_win_pct, largest_loss_pct
Exit types: exits_via_target, exits_via_stop_loss,
            exits_via_time, exits_via_strategy_reversal
```

### Walk-Forward Validation

```
Full 15-year history split:
  Training: 2010-2022 (80%)  ← strategy calibration
  Test:     2023-2025 (20%)  ← honest out-of-sample result

Rolling walk-forward:
  Train 2010-2019 → Test 2020
  Train 2010-2020 → Test 2021
  Train 2010-2021 → Test 2022
  Train 2010-2022 → Test 2023
  → Average out-of-sample metrics = true expected performance
```

Critical for ML strategies: in-sample accuracy of 75% regularly becomes 55% out-of-sample. Walk-forward gives the honest number.

---

## 12. Technology Stack

### Backend
```
Python 3.11+
├── FastAPI 0.110+         API framework, WebSocket support
├── uvicorn               ASGI server
├── SQLAlchemy 2.0        ORM with async (aiosqlite driver)
├── Alembic               database migrations
├── APScheduler 3.10+     background job scheduler
├── Pydantic v2           data validation, settings
├── anthropic 0.25+       Claude API
├── python-telegram-bot   Telegram notifications
└── httpx                 async HTTP client

Data & ML
├── pandas 2.0+           data manipulation
├── numpy 1.26+
├── pandas-ta             technical indicators (no C compiler needed)
├── scikit-learn 1.4+     ML models
├── xgboost, lightgbm     ensemble models (from v1, retrained)
├── yfinance 0.2+         historical data
└── smartapi-python       Angel One SmartAPI client
```

### Frontend
```
Next.js 14 (React 18 + TypeScript)
├── TanStack Query v5                server state + caching
├── Zustand                          client state
├── TradingView Lightweight Charts   candlestick/indicator charts
├── Recharts                         portfolio performance charts
├── Tailwind CSS                     styling
└── shadcn/ui                        accessible component primitives
```

### Dev Tools
```
Poetry              Python dependency management
pytest + pytest-asyncio  testing
ruff                linting + formatting
```

### Folder Structure
```
stockv2/
├── backend/
│   ├── main.py                  FastAPI app entry point
│   ├── settings.py              config (API keys, trading params)
│   ├── scheduler.py             APScheduler job definitions
│   ├── database.py              SQLAlchemy engine + session factory
│   ├── domains/
│   │   ├── data/                market data ingestion feeds
│   │   ├── strategies/          26 strategies + engine + aggregator
│   │   ├── ai/                  Claude integration + all AI features
│   │   ├── portfolio/           holdings, P&L, performance, risk
│   │   ├── broker/              Angel One + paper broker
│   │   ├── alerts/              alert engine + notification channels
│   │   └── backtesting/         backtest runner + metrics calculator
│   └── tests/
├── frontend/
│   ├── app/                     Next.js app router pages
│   ├── components/              shared UI components
│   └── lib/                     API client, hooks, utils
└── docs/
    └── superpowers/specs/
```

---

## 13. Development Roadmap

### MVP — Phase 1 (Weeks 1–8)
**Goal:** Daily signal digest with AI explanations, paper trading, portfolio tracking.

```
Week 1-2: Foundation
  ✓ FastAPI + SQLite setup with all tables + Alembic migrations
  ✓ yfinance historical bootstrap (237 NSE stocks, 15 years)
  ✓ IndicatorEngine (pandas-ta, all indicators)
  ✓ Angel One SmartAPI connection + live quotes

Week 3-4: Strategy Engine (10 core strategies)
  ✓ RSI, MACD, EMA Cross, SMA Cross, SuperTrend
  ✓ Bollinger Band Squeeze, Volume Breakout
  ✓ Swing Trade Trend Rider, Mean Reversion, Volatility Breakout
  ✓ Signal aggregator + consensus scoring
  ✓ APScheduler: daily 4 PM run + 15-min intraday scan

Week 5: AI Integration
  ✓ Claude API: SignalExplainer + SellExplainer
  ✓ ai_analyses caching
  ✓ Telegram daily digest + real-time signal alerts

Week 6: Portfolio + Paper Trading
  ✓ Manual trade entry endpoint
  ✓ PaperBroker: simulated execution with slippage
  ✓ Holdings P&L, unrealized gains, performance stats
  ✓ Exit condition monitoring (SL, target, time, reversal)

Week 7: Backtesting
  ✓ BacktestRunner for 10 MVP strategies
  ✓ All performance metrics
  ✓ Results saved to DB + API endpoint

Week 8: Frontend MVP
  ✓ Dashboard: sentiment, top signals, portfolio summary
  ✓ Signal list with AI explanations
  ✓ Portfolio view (holdings, P&L, performance chart)
  ✓ Live price WebSocket feed
```

**MVP Deliverable:** Every day at 4 PM, system scans 237 NSE stocks, ranks top 10 signals, explains them in plain English, sends Telegram digest, tracks paper trades, monitors exit conditions.

---

### V2 — Phase 2 (Weeks 9–16)
**Goal:** Full strategy suite, AI chatbot, news sentiment, fundamental strategies, semi-auto trading.

```
Week 9-10: Remaining Strategies + Fundamentals
  ✓ All 26 strategies implemented
  ✓ Screener.in fundamentals scraper
  ✓ CANSLIM, Magic Formula, Value, Growth, Dividend strategies
  ✓ FII/DII activity feed + strategy
  ✓ NSE corporate actions feed

Week 11: AI Upgrade
  ✓ NewsAnalyzer (every 2hr, Google News RSS + ET Markets)
  ✓ MarketChatbot (free-form Q&A with portfolio context)
  ✓ StockComparator
  ✓ PortfolioAdvisor (weekly portfolio health report)

Week 12: NL Strategy Builder
  ✓ Claude converts plain English → strategy config
  ✓ Custom strategy saves to DB and runs immediately
  ✓ Validation: show user what the strategy will screen for

Week 13: Advanced Backtesting
  ✓ Walk-forward validation
  ✓ Multi-strategy comparison leaderboard
  ✓ Per-symbol breakdown in results
  ✓ Equity curve data for charting

Week 14: Semi-Auto Trading
  ✓ AngelOneBroker implementation (real orders)
  ✓ SEMI_AUTO mode: approve via UI or Telegram reply
  ✓ Full RiskValidator pre-trade checks
  ✓ Master kill switch endpoint
  ✓ Order status monitoring

Week 15-16: V2 Frontend
  ✓ Strategy management + NL builder page
  ✓ Backtesting UI with equity curves and comparison
  ✓ AI chat interface
  ✓ Alert configuration UI
  ✓ Full order management view
```

---

### V3 — Future (Post Week 16)

```
Full Auto Trading
  → FULL_AUTO mode with Angel One real execution
  → TradeMemory: Claude learns from your trade history
  → Confidence-adjusted position sizing from personal win rate data

Document Analysis
  → Earnings report summarizer (NSE PDF filings)
  → Annual report summarizer with key metric extraction
  → QoQ / YoY automatic comparison

Smart Money Concepts (Advanced)
  → Break of Structure (BOS) + Change of Character (CHoCH) detection
  → Order block identification
  → Liquidity sweep detection

Additional Data
  → Options chain data (put/call ratio, max pain, OI buildup)
  → Sector rotation signals from mutual fund data
  → Global macro impact signals (DXY, crude oil, US Fed)

UI Beautification
  → Full charting suite (multiple timeframes, drawing tools)
  → Mobile-responsive design
  → Dark/light theme toggle
```

---

## 14. Feature Priority Matrix

| Feature | MVP | V2 | V3 |
|---|---|---|---|
| Historical data ingestion (yfinance) | ✓ | | |
| Live data (Angel One WebSocket) | ✓ | | |
| 10 core technical strategies | ✓ | | |
| Signal aggregation + consensus scoring | ✓ | | |
| AI signal explanations (buy + sell) | ✓ | | |
| Telegram alerts + daily digest | ✓ | | |
| Paper trading simulation | ✓ | | |
| Portfolio P&L tracking | ✓ | | |
| Exit condition monitoring (SL/target/time) | ✓ | | |
| Basic backtesting (10 strategies) | ✓ | | |
| Basic dashboard (signals + portfolio) | ✓ | | |
| All 26 strategies | | ✓ | |
| Fundamentals scraping (Screener.in) | | ✓ | |
| CANSLIM, Magic Formula, Value strategies | | ✓ | |
| FII/DII activity strategy | | ✓ | |
| News sentiment analysis | | ✓ | |
| AI chatbot (portfolio Q&A) | | ✓ | |
| NL strategy builder | | ✓ | |
| Walk-forward backtesting | | ✓ | |
| Strategy comparison leaderboard | | ✓ | |
| Semi-auto trading (Angel One) | | ✓ | |
| Full auto trading | | | ✓ |
| TradeMemory (learn from trades) | | | ✓ |
| Earnings/annual report analysis | | | ✓ |
| Options chain data | | | ✓ |
| Smart Money Concepts (BOS/CHoCH) | | | ✓ |
| Mobile-responsive UI | | | ✓ |

---

*End of StockV2 Design Specification*
