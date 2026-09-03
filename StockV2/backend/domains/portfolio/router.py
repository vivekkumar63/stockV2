from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from database import get_db
from domains.portfolio.paper_trader import PaperTrader
from domains.portfolio.service import PortfolioService
from domains.portfolio.watchlist_service import WatchlistService

router = APIRouter(tags=["portfolio"])


class EnterBody(BaseModel):
    price: float


class ExitBody(BaseModel):
    price: float
    reason: str = "manual"


class WatchlistBody(BaseModel):
    reason: Optional[str] = None


class ManualEntryBody(BaseModel):
    symbol: str
    quantity: int
    price: float
    stop_loss: float
    target: float
    strategy_id: Optional[int] = None
    special_strategy_id: Optional[int] = None


@router.get("/portfolio/summary")
def portfolio_summary(db: Session = Depends(get_db)):
    return PortfolioService(db).get_portfolio_summary()


@router.get("/portfolio/holdings")
def portfolio_holdings(db: Session = Depends(get_db)):
    return PortfolioService(db).get_holdings()


@router.get("/portfolio/trades")
def portfolio_trades(
    symbol: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    return PortfolioService(db).get_trade_history(symbol=symbol, limit=limit)


@router.get("/portfolio/pnl")
def portfolio_pnl(db: Session = Depends(get_db)):
    return PortfolioService(db).get_closed_pnl()


@router.get("/portfolio/sell-alerts")
def portfolio_sell_alerts(db: Session = Depends(get_db)):
    """Return SELL signals from the most recent scan date for stocks currently held."""
    rows = db.execute(text("""
        WITH latest_scan AS (
            SELECT MAX(signal_date) AS max_date FROM strategy_signals
        )
        SELECT
            ph.symbol,
            ph.avg_buy_price,
            ss.strategy_id,
            s.name  AS strategy_name,
            ss.signal_date,
            ss.price_at_signal,
            ss.confidence_score,
            ss.suggested_stop_loss,
            ss.suggested_target,
            ss.reasoning_json
        FROM portfolio_holdings ph
        JOIN strategy_signals ss ON ss.symbol = ph.symbol AND ss.signal_type = 'SELL'
        JOIN strategies s ON s.id = ss.strategy_id
        JOIN latest_scan ls ON ss.signal_date = ls.max_date
        WHERE ph.is_active = true
        ORDER BY ss.confidence_score DESC
    """)).fetchall()
    return [dict(r._mapping) for r in rows]


@router.post("/portfolio/enter/{signal_id}")
def paper_enter(signal_id: int, body: EnterBody, db: Session = Depends(get_db)):
    trade = PaperTrader(db).enter(signal_id, body.price)
    if trade is None:
        raise HTTPException(
            status_code=400,
            detail="Entry rejected — check signal validity and position limits",
        )
    return trade


@router.post("/portfolio/exit/{symbol}")
def paper_exit(symbol: str, body: ExitBody, db: Session = Depends(get_db)):
    trade = PaperTrader(db).exit(symbol.upper(), body.price, body.reason)
    if trade is None:
        raise HTTPException(status_code=404, detail=f"No active position for {symbol}")
    return trade


@router.post("/portfolio/manual-entry")
def manual_entry(body: ManualEntryBody, db: Session = Depends(get_db)):
    """Add a manually-bought position without requiring a scanner signal."""
    symbol = body.symbol.upper().strip()
    trader = PaperTrader(db)

    # Use PaperTrader internal helpers directly — no signal required
    total_value = round(body.quantity * body.price, 2)
    trade_id = trader._insert_trade(
        symbol=symbol,
        trade_type="BUY",
        quantity=body.quantity,
        price=body.price,
        total_value=total_value,
        strategy_id=body.strategy_id,
        signal_id=None,
    )
    trader._upsert_holding(symbol, body.quantity, body.price)

    # Update the holding with manual-entry metadata
    db.execute(text("""
        UPDATE portfolio_holdings
        SET special_strategy_id = :ssid, entry_source = 'manual'
        WHERE symbol = :sym AND is_active = true
    """), {"ssid": body.special_strategy_id, "sym": symbol})

    trader._insert_exit_rule(
        trade_id=trade_id,
        symbol=symbol,
        entry_price=body.price,
        stop_loss_price=body.stop_loss,
        target_price=body.target,
        holding_days=365,  # no expiry for manual entries
    )
    db.commit()
    return trader._load_trade(trade_id)


@router.get("/portfolio/special-sell-alerts")
def special_sell_alerts(db: Session = Depends(get_db)):
    """Return special strategy sell signals for currently-held positions."""
    import logging
    import pandas as pd
    from domains.special_strategies import ALL_SPECIAL_STRATEGIES
    from domains.data.indicators import IndicatorEngine

    _log = logging.getLogger(__name__)

    # Load holdings linked to a special strategy
    rows = db.execute(text("""
        SELECT ph.symbol, ph.avg_buy_price, ph.special_strategy_id,
               ss.name AS strategy_name
        FROM portfolio_holdings ph
        JOIN special_strategies ss ON ss.id = ph.special_strategy_id
        WHERE ph.is_active = true AND ph.special_strategy_id IS NOT NULL
    """)).fetchall()

    strategy_map = {s.name: s for s in ALL_SPECIAL_STRATEGIES}
    alerts = []

    for row in rows:
        symbol, avg_buy, _, strategy_name = row[0], row[1], row[2], row[3]
        strategy = strategy_map.get(strategy_name)
        if strategy is None:
            continue

        try:
            price_rows = db.execute(text("""
                SELECT date, open, high, low, close, volume FROM (
                    SELECT date, open, high, low, close, volume
                    FROM stock_prices_daily WHERE symbol = :s
                    ORDER BY date DESC LIMIT 250
                ) ORDER BY date ASC
            """), {"s": symbol}).fetchall()
            if len(price_rows) < 3:
                continue
            df = pd.DataFrame(price_rows, columns=["date", "open", "high", "low", "close", "volume"])
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
            _log.exception("[special-sell-alerts] error checking %s", symbol)

    return alerts


@router.get("/watchlist")
def watchlist_list(db: Session = Depends(get_db)):
    return WatchlistService(db).get_all()


@router.post("/watchlist/{symbol}")
def watchlist_add(symbol: str, body: WatchlistBody, db: Session = Depends(get_db)):
    return WatchlistService(db).add(symbol.upper(), body.reason)


@router.delete("/watchlist/{symbol}")
def watchlist_remove(symbol: str, db: Session = Depends(get_db)):
    removed = WatchlistService(db).remove(symbol.upper())
    if not removed:
        raise HTTPException(status_code=404, detail=f"{symbol} not in watchlist")
    return {"removed": symbol.upper()}
