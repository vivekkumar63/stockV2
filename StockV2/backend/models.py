from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Boolean, Date, DateTime, Float, Index, Integer,
    String, Text, UniqueConstraint, text as sa_text,
)
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


# ─── Market Data ──────────────────────────────────────────────────────────────

class Stock(Base):
    __tablename__ = "stocks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), default="")
    sector: Mapped[Optional[str]] = mapped_column(String(100))
    industry: Mapped[Optional[str]] = mapped_column(String(200))
    market_cap: Mapped[Optional[float]] = mapped_column(Float)
    exchange: Mapped[str] = mapped_column(String(10), default="NSE")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    added_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=sa_text("CURRENT_TIMESTAMP"))


class StockPriceDaily(Base):
    __tablename__ = "stock_prices_daily"
    __table_args__ = (
        UniqueConstraint("symbol", "date", name="uq_daily_symbol_date"),
        Index("idx_prices_daily_symbol_date", "symbol", "date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[int] = mapped_column(Integer)
    adj_close: Mapped[Optional[float]] = mapped_column(Float)
    data_source: Mapped[str] = mapped_column(String(20), default="yfinance")


class StockPriceIntraday(Base):
    __tablename__ = "stock_prices_intraday"
    __table_args__ = (
        UniqueConstraint("symbol", "timestamp", "interval", name="uq_intraday_symbol_ts"),
        Index("idx_prices_intraday_symbol_ts", "symbol", "timestamp"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[int] = mapped_column(Integer)
    interval: Mapped[str] = mapped_column(String(5), default="15m")


class Fundamental(Base):
    __tablename__ = "fundamentals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    pe_ratio: Mapped[Optional[float]] = mapped_column(Float)
    pb_ratio: Mapped[Optional[float]] = mapped_column(Float)
    eps: Mapped[Optional[float]] = mapped_column(Float)
    revenue: Mapped[Optional[float]] = mapped_column(Float)
    net_profit: Mapped[Optional[float]] = mapped_column(Float)
    debt_equity: Mapped[Optional[float]] = mapped_column(Float)
    roe: Mapped[Optional[float]] = mapped_column(Float)
    promoter_holding: Mapped[Optional[float]] = mapped_column(Float)
    fii_holding: Mapped[Optional[float]] = mapped_column(Float)
    dii_holding: Mapped[Optional[float]] = mapped_column(Float)
    dividend_yield: Mapped[Optional[float]] = mapped_column(Float)   # Phase F
    data_as_of: Mapped[Optional[date]] = mapped_column(Date)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=sa_text("CURRENT_TIMESTAMP"))


class CorporateAction(Base):
    __tablename__ = "corporate_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    action_type: Mapped[str] = mapped_column(String(20))
    ex_date: Mapped[Optional[date]] = mapped_column(Date)
    record_date: Mapped[Optional[date]] = mapped_column(Date)
    value: Mapped[Optional[float]] = mapped_column(Float)
    notes: Mapped[Optional[str]] = mapped_column(Text)


class News(Base):
    __tablename__ = "news"
    __table_args__ = (
        Index("idx_news_symbol_published", "symbol", "published_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[Optional[str]] = mapped_column(String(20))
    headline: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[Optional[str]] = mapped_column(Text)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    sentiment: Mapped[Optional[str]] = mapped_column(String(10))
    impact_score: Mapped[Optional[float]] = mapped_column(Float)
    category: Mapped[Optional[str]] = mapped_column(String(30))
    ai_summary: Mapped[Optional[str]] = mapped_column(Text)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=sa_text("CURRENT_TIMESTAMP"))


# ─── Strategy & Signals ───────────────────────────────────────────────────────

class Strategy(Base):
    __tablename__ = "strategies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    type: Mapped[str] = mapped_column(String(20))
    description: Mapped[Optional[str]] = mapped_column(Text)
    parameters_json: Mapped[Optional[str]] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=sa_text("CURRENT_TIMESTAMP"))


class StrategySignal(Base):
    __tablename__ = "strategy_signals"
    __table_args__ = (
        Index("idx_signals_symbol_date", "symbol", "signal_date"),
        Index("idx_signals_strategy_date", "strategy_id", "signal_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    strategy_id: Mapped[int] = mapped_column(Integer, nullable=False)
    signal_date: Mapped[date] = mapped_column(Date, nullable=False)
    signal_type: Mapped[str] = mapped_column(String(10))
    price_at_signal: Mapped[Optional[float]] = mapped_column(Float)
    confidence_score: Mapped[Optional[float]] = mapped_column(Float)
    risk_score: Mapped[Optional[float]] = mapped_column(Float)
    expected_upside_pct: Mapped[Optional[float]] = mapped_column(Float)
    suggested_stop_loss: Mapped[Optional[float]] = mapped_column(Float)
    suggested_target: Mapped[Optional[float]] = mapped_column(Float)
    holding_period_days: Mapped[Optional[int]] = mapped_column(Integer)
    reasoning_json: Mapped[Optional[str]] = mapped_column(Text)
    indicators_json: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=sa_text("CURRENT_TIMESTAMP"))


class StrategyPerformance(Base):
    """Permanent precomputed backtest results for every (strategy, stock) pair.
    Computed once from all available price history. Recomputed only when a
    new strategy is added (detected at startup by absence of rows for that strategy_id).
    """
    __tablename__ = "strategy_performance"
    __table_args__ = (
        UniqueConstraint("strategy_id", "symbol", name="uq_strat_perf"),
        Index("idx_strat_perf_strategy", "strategy_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    strategy_id: Mapped[int] = mapped_column(Integer, nullable=False)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    total_trades: Mapped[int] = mapped_column(Integer, default=0)
    win_rate: Mapped[Optional[float]] = mapped_column(Float)
    cagr: Mapped[Optional[float]] = mapped_column(Float)
    sharpe_ratio: Mapped[Optional[float]] = mapped_column(Float)
    max_drawdown: Mapped[Optional[float]] = mapped_column(Float)
    profit_factor: Mapped[Optional[float]] = mapped_column(Float)
    total_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=sa_text("CURRENT_TIMESTAMP"))


class ScanResultCache(Base):
    """Cache for scan_all() results keyed by (symbol, strategy, date_range, capital, sl, target).

    stop_loss_pct / target_pct = -1.0 means "strategy's own default was used".
    UNIQUE constraint prevents duplicate entries; INSERT OR REPLACE refreshes stale ones.
    """
    __tablename__ = "scan_result_cache"
    __table_args__ = (
        UniqueConstraint(
            "symbol", "strategy_id", "from_date", "to_date",
            "initial_capital", "stop_loss_pct", "target_pct",
            name="uq_scan_cache_key",
        ),
        Index("idx_scan_cache_lookup", "from_date", "to_date", "initial_capital",
              "stop_loss_pct", "target_pct"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    strategy_id: Mapped[int] = mapped_column(Integer, nullable=False)
    from_date: Mapped[date] = mapped_column(Date, nullable=False)
    to_date: Mapped[date] = mapped_column(Date, nullable=False)
    initial_capital: Mapped[float] = mapped_column(Float, nullable=False)
    stop_loss_pct: Mapped[float] = mapped_column(Float, nullable=False, default=-1.0)
    target_pct: Mapped[float] = mapped_column(Float, nullable=False, default=-1.0)
    total_trades: Mapped[int] = mapped_column(Integer, default=0)
    win_rate: Mapped[Optional[float]] = mapped_column(Float)
    cagr: Mapped[Optional[float]] = mapped_column(Float)
    sharpe_ratio: Mapped[Optional[float]] = mapped_column(Float)
    max_drawdown: Mapped[Optional[float]] = mapped_column(Float)
    profit_factor: Mapped[Optional[float]] = mapped_column(Float)
    total_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    cached_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=sa_text("CURRENT_TIMESTAMP"))


class BacktestResult(Base):
    __tablename__ = "backtest_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    strategy_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    symbol: Mapped[Optional[str]] = mapped_column(String(20))
    from_date: Mapped[date] = mapped_column(Date)
    to_date: Mapped[date] = mapped_column(Date)
    total_trades: Mapped[int] = mapped_column(Integer, default=0)
    win_rate: Mapped[Optional[float]] = mapped_column(Float)
    cagr: Mapped[Optional[float]] = mapped_column(Float)
    sharpe_ratio: Mapped[Optional[float]] = mapped_column(Float)
    sortino_ratio: Mapped[Optional[float]] = mapped_column(Float)
    max_drawdown: Mapped[Optional[float]] = mapped_column(Float)
    profit_factor: Mapped[Optional[float]] = mapped_column(Float)
    avg_return_pct: Mapped[Optional[float]] = mapped_column(Float)
    full_metrics_json: Mapped[Optional[str]] = mapped_column(Text)
    ran_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=sa_text("CURRENT_TIMESTAMP"))


class BacktestTrade(Base):
    __tablename__ = "backtest_trades"
    __table_args__ = (
        Index("idx_backtest_trades_result", "backtest_result_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    backtest_result_id: Mapped[int] = mapped_column(Integer, nullable=False)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    entry_date: Mapped[date] = mapped_column(Date)
    entry_price: Mapped[float] = mapped_column(Float)
    exit_date: Mapped[Optional[date]] = mapped_column(Date)
    exit_price: Mapped[Optional[float]] = mapped_column(Float)
    quantity: Mapped[int] = mapped_column(Integer)
    pnl: Mapped[Optional[float]] = mapped_column(Float)
    pnl_pct: Mapped[Optional[float]] = mapped_column(Float)
    exit_reason: Mapped[Optional[str]] = mapped_column(String(30))
    holding_days: Mapped[Optional[int]] = mapped_column(Integer)


class WalkForwardResult(Base):
    """Out-of-sample walk-forward consistency metrics per (symbol, strategy)."""
    __tablename__ = "walk_forward_results"
    __table_args__ = (
        UniqueConstraint("symbol", "strategy_id", name="uq_wf_result"),
        Index("idx_wf_strategy", "strategy_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    strategy_id: Mapped[int] = mapped_column(Integer, nullable=False)
    n_windows: Mapped[int] = mapped_column(Integer, default=0)
    oos_win_rate_mean: Mapped[Optional[float]] = mapped_column(Float)
    oos_win_rate_std: Mapped[Optional[float]] = mapped_column(Float)
    consistency_score: Mapped[float] = mapped_column(Float, default=0.0)
    in_sample_win_rate: Mapped[Optional[float]] = mapped_column(Float)
    windows_json: Mapped[Optional[str]] = mapped_column(Text)
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=sa_text("CURRENT_TIMESTAMP"))


# ─── Portfolio ────────────────────────────────────────────────────────────────

class PortfolioHolding(Base):
    __tablename__ = "portfolio_holdings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    avg_buy_price: Mapped[float] = mapped_column(Float, nullable=False)
    first_buy_date: Mapped[date] = mapped_column(Date)
    last_buy_date: Mapped[date] = mapped_column(Date)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class Trade(Base):
    __tablename__ = "trades"
    __table_args__ = (
        Index("idx_trades_symbol_date", "symbol", "trade_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    trade_type: Mapped[str] = mapped_column(String(4))
    quantity: Mapped[int] = mapped_column(Integer)
    price: Mapped[float] = mapped_column(Float)
    total_value: Mapped[float] = mapped_column(Float)
    brokerage: Mapped[float] = mapped_column(Float, default=0.0)
    trade_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=sa_text("CURRENT_TIMESTAMP"))
    order_id: Mapped[Optional[int]] = mapped_column(Integer)
    mode: Mapped[str] = mapped_column(String(10), default="paper")
    strategy_id: Mapped[Optional[int]] = mapped_column(Integer)
    signal_id: Mapped[Optional[int]] = mapped_column(Integer)
    notes: Mapped[Optional[str]] = mapped_column(Text)


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    order_type: Mapped[str] = mapped_column(String(10))
    side: Mapped[str] = mapped_column(String(4))
    quantity: Mapped[int] = mapped_column(Integer)
    price: Mapped[Optional[float]] = mapped_column(Float)
    trigger_price: Mapped[Optional[float]] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(15), default="pending")
    broker_order_id: Mapped[Optional[str]] = mapped_column(String(50))
    placed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=sa_text("CURRENT_TIMESTAMP"))
    executed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    mode: Mapped[str] = mapped_column(String(10), default="paper")


class ExitRule(Base):
    __tablename__ = "exit_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(Integer, nullable=False)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    entry_price: Mapped[float] = mapped_column(Float)
    stop_loss_price: Mapped[float] = mapped_column(Float)
    target_1_price: Mapped[float] = mapped_column(Float)
    target_2_price: Mapped[float] = mapped_column(Float)
    max_exit_date: Mapped[Optional[date]] = mapped_column(Date)
    partial_exit_at_t1: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class Watchlist(Base):
    __tablename__ = "watchlist"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    added_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=sa_text("CURRENT_TIMESTAMP"))
    reason: Mapped[Optional[str]] = mapped_column(Text)
    strategy_id: Mapped[Optional[int]] = mapped_column(Integer)
    alert_price: Mapped[Optional[float]] = mapped_column(Float)


# ─── AI ───────────────────────────────────────────────────────────────────────

class AIAnalysis(Base):
    __tablename__ = "ai_analyses"
    __table_args__ = (
        Index("idx_ai_analyses_subject", "subject_type", "subject_id", "expires_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subject_type: Mapped[str] = mapped_column(String(20))
    subject_id: Mapped[Optional[str]] = mapped_column(String(50))
    analysis_type: Mapped[str] = mapped_column(String(30))
    content: Mapped[str] = mapped_column(Text)
    model_used: Mapped[str] = mapped_column(String(50), default="claude-sonnet-4-6")
    tokens_used: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=sa_text("CURRENT_TIMESTAMP"))
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime)


class AIConversation(Base):
    __tablename__ = "ai_conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    role: Mapped[str] = mapped_column(String(10))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=sa_text("CURRENT_TIMESTAMP"))


# ─── Alerts ───────────────────────────────────────────────────────────────────

class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    alert_type: Mapped[str] = mapped_column(String(30))
    symbol: Mapped[Optional[str]] = mapped_column(String(20))
    condition_json: Mapped[Optional[str]] = mapped_column(Text)
    message_template: Mapped[Optional[str]] = mapped_column(Text)
    channels_json: Mapped[str] = mapped_column(Text, default='["telegram"]')
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=sa_text("CURRENT_TIMESTAMP"))


class AlertHistory(Base):
    __tablename__ = "alert_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    alert_id: Mapped[int] = mapped_column(Integer, nullable=False)
    symbol: Mapped[Optional[str]] = mapped_column(String(20))
    triggered_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=sa_text("CURRENT_TIMESTAMP"))
    message_sent: Mapped[Optional[str]] = mapped_column(Text)
    delivery_status_json: Mapped[Optional[str]] = mapped_column(Text)


# ─── System ───────────────────────────────────────────────────────────────────

class DataQualityLog(Base):
    __tablename__ = "data_quality_log"
    __table_args__ = (
        Index("idx_data_quality_symbol", "symbol", "logged_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[Optional[str]] = mapped_column(String(20))
    date: Mapped[Optional[date]] = mapped_column(Date)
    issue_type: Mapped[str] = mapped_column(String(30))
    details: Mapped[Optional[str]] = mapped_column(Text)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    logged_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=sa_text("CURRENT_TIMESTAMP"))


# ─── Market Intelligence ──────────────────────────────────────────────────────

class MarketRegime(Base):
    """Daily snapshot of broad market regime computed from stock-universe breadth."""
    __tablename__ = "market_regime"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, unique=True, index=True)
    # One of: STRONG_BULL | BULL | SIDEWAYS | BEAR | STRONG_BEAR | HIGH_VOLATILITY
    regime: Mapped[str] = mapped_column(String(20), nullable=False)
    confidence: Mapped[Optional[float]] = mapped_column(Float)
    pct_above_sma50: Mapped[Optional[float]] = mapped_column(Float)
    pct_above_sma200: Mapped[Optional[float]] = mapped_column(Float)
    advance_decline_ratio: Mapped[Optional[float]] = mapped_column(Float)
    avg_atr_ratio: Mapped[Optional[float]] = mapped_column(Float)
    stocks_counted: Mapped[Optional[int]] = mapped_column(Integer)
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=sa_text("CURRENT_TIMESTAMP"))


class SupportResistanceLevel(Base):
    """Computed support and resistance levels per symbol, refreshed daily."""
    __tablename__ = "support_resistance_levels"
    __table_args__ = (
        UniqueConstraint("symbol", "computed_date", "level_source"),
        Index("idx_sr_symbol_date", "symbol", "computed_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    computed_date: Mapped[date] = mapped_column(Date, nullable=False)
    level_type: Mapped[str] = mapped_column(String(15), nullable=False)   # SUPPORT | RESISTANCE
    level_source: Mapped[str] = mapped_column(String(30), nullable=False) # SWING_HIGH | SMA50 | 52W_HIGH | …
    price: Mapped[float] = mapped_column(Float, nullable=False)
    strength: Mapped[Optional[float]] = mapped_column(Float)   # 0–1, significance of this level
    distance_pct: Mapped[Optional[float]] = mapped_column(Float)  # from current price; negative = below


class SignalOutcome(Base):
    """
    Tracks actual outcome for each strategy signal after its holding period.
    Populated nightly by FalseSignalDetector for signals old enough to evaluate.
    """
    __tablename__ = "signal_outcomes"
    __table_args__ = (
        UniqueConstraint("signal_id", name="uq_signal_outcome"),
        Index("idx_signal_outcome_strategy", "strategy_id", "signal_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    signal_id: Mapped[int] = mapped_column(Integer, nullable=False)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    strategy_id: Mapped[int] = mapped_column(Integer, nullable=False)
    signal_date: Mapped[date] = mapped_column(Date, nullable=False)
    signal_type: Mapped[str] = mapped_column(String(10), nullable=False)  # BUY | SELL
    price_at_signal: Mapped[float] = mapped_column(Float, nullable=False)
    outcome_price: Mapped[Optional[float]] = mapped_column(Float)
    outcome_date: Mapped[Optional[date]] = mapped_column(Date)
    pnl_pct: Mapped[Optional[float]] = mapped_column(Float)       # % change at outcome
    is_profitable: Mapped[Optional[bool]] = mapped_column(Boolean)
    holding_days_actual: Mapped[Optional[int]] = mapped_column(Integer)
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=sa_text("CURRENT_TIMESTAMP"))


class StrategyCorrelation(Base):
    """
    Pairwise signal-overlap correlation between strategies.
    High value = both strategies tend to fire on the same stock simultaneously.
    """
    __tablename__ = "strategy_correlations"
    __table_args__ = (
        UniqueConstraint("strategy_id_a", "strategy_id_b", name="uq_strat_corr"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    strategy_id_a: Mapped[int] = mapped_column(Integer, nullable=False)
    strategy_id_b: Mapped[int] = mapped_column(Integer, nullable=False)
    correlation: Mapped[float] = mapped_column(Float, nullable=False)   # 0.0–1.0
    shared_signals: Mapped[int] = mapped_column(Integer, default=0)
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=sa_text("CURRENT_TIMESTAMP"))


class StrategyRegimePerformance(Base):
    """Per-strategy win-rate breakdown by market regime. Populated by RegimePerformanceEngine."""
    __tablename__ = "strategy_regime_performance"
    __table_args__ = (
        UniqueConstraint("strategy_id", "regime", name="uq_regime_perf"),
        Index("idx_regime_perf_strategy", "strategy_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    strategy_id: Mapped[int] = mapped_column(Integer, nullable=False)
    regime: Mapped[str] = mapped_column(String(20), nullable=False)
    total_trades: Mapped[int] = mapped_column(Integer, default=0)
    win_rate: Mapped[Optional[float]] = mapped_column(Float)       # 0.0–1.0
    avg_pnl_pct: Mapped[Optional[float]] = mapped_column(Float)    # average % return per trade
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, server_default=sa_text("CURRENT_TIMESTAMP"))
