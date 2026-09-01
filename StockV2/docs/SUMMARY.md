# StockV2 — What's Built

## Backend (FastAPI + SQLite)

- **Market data** — Historical OHLCV for 237 NSE stocks via YFinance. Auto-bootstrap on first run, incremental daily updates at 3:45 PM IST.
- **26+ technical indicators** — SMA, EMA, RSI, MACD, Bollinger Bands, ATR, ADX, SuperTrend, Stochastic, OBV, etc. — computed fresh on every scan.
- **87 trading strategies** — momentum, crossovers, breakouts, candlestick patterns, Bollinger, MACD, ChartInk-derived. Auto-discovered from files at startup.
- **Signal engine** — Runs all strategies on all stocks, saves BUY/SELL signals with confidence score, stop loss, target, reasoning.
- **Live scanner** — On-demand scan endpoint; returns results with historical win rate attached.
- **Backtesting** — Run any (stock, strategy) pair from a custom date range. Computes CAGR, Sharpe, win rate, max drawdown, profit factor.
- **Leaderboard** — Full 237×87 backtest from 2015. Results cached. Auto-refreshes daily at 4:30 PM IST after EOD data lands.
- **Historical win rate on signals** — Every signal (live scan + today's signals) carries the historical win rate from the leaderboard cache.
- **Paper trading** — Enter/exit positions with position sizing, stop loss/target rules, max position limits.
- **Portfolio tracking** — Open holdings, closed P&L, trade history.
- **Sell alerts** — If any strategy fires SELL on a stock you hold, it's shown in the UI and sent to Telegram.
- **Telegram digests** — 5 times a day (9:15, 10:30, 12:00, 14:00, 15:15 IST). Only suggests stocks with historical win rate ≥ 40%. Shows win rate, confidence, price, SL, target.
- **Claude AI explanations** — On-demand explanation of any signal via Anthropic API (cached).
- **IST timezone** — All scheduler jobs and date logic run in Asia/Kolkata.

## Frontend (React + Vite + TailwindCSS)

- **Dashboard** — Today's BUY signals table with confidence, price, SL, target, hold days, historical win rate. Expandable rows showing conditions met/failed. Enter position button.
- **Portfolio** — Sell alert banner for held stocks. Open positions with manual exit. Closed P&L table.
- **Strategy Scanner** — Live scan with strategy/signal type filters. Results table with historical win rate column (color-coded). Strategy detail card.
- **Strategy Match (Leaderboard)** — All strategy-stock pairs ranked by win rate. Click any row to see full trade history. Compute/refresh controls with cache status.
- **Backtest** — Manual backtest runner for any stock + strategy + date range.
