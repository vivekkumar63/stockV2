import { apiFetch } from './client'

export interface PortfolioSummary {
  paper_capital: number
  total_invested: number
  cash_available: number
  open_positions: number
  max_positions: number
}

export interface Holding {
  id: number
  symbol: string
  quantity: number
  avg_buy_price: number
  first_buy_date: string
  last_buy_date: string
  invested_value: number
  stop_loss_price: number | null
  target_1_price: number | null
  max_exit_date: string | null
  special_strategy_id: number | null
  special_strategy_name: string | null
  entry_source: string | null
}

export interface ClosedPnl {
  total_pnl: number
  closed_trades: ClosedTrade[]
}

export interface ClosedTrade {
  symbol: string
  trade_date: string
  quantity: number
  price: number
  buy_avg?: number
  pnl?: number
  pnl_pct?: number
}

export interface TradeRecord {
  id: number
  symbol: string
  trade_date: string
  price: number
  quantity: number
  trade_type: string
}

export const getPortfolioSummary = () => apiFetch<PortfolioSummary>('/portfolio/summary')
export const getHoldings = () => apiFetch<Holding[]>('/portfolio/holdings')
export const getClosedPnl = () => apiFetch<ClosedPnl>('/portfolio/pnl')

export const enterPosition = (signalId: number, price: number) =>
  apiFetch<TradeRecord>(`/portfolio/enter/${signalId}`, {
    method: 'POST',
    body: JSON.stringify({ price }),
  })

export const exitPosition = (symbol: string, price: number, reason = 'manual') =>
  apiFetch<TradeRecord>(`/portfolio/exit/${symbol}`, {
    method: 'POST',
    body: JSON.stringify({ price, reason }),
  })

export interface SellAlert {
  symbol: string
  avg_buy_price: number
  strategy_id: number
  strategy_name: string
  signal_date: string
  price_at_signal: number
  confidence_score: number | null
  suggested_stop_loss: number | null
  suggested_target: number | null
  reasoning_json: string | null
}

export const getSellAlerts = () => apiFetch<SellAlert[]>('/portfolio/sell-alerts')

export interface ManualEntryRequest {
  symbol: string
  quantity: number
  price: number
  stop_loss: number
  target: number
  strategy_id?: number
  special_strategy_id?: number
}

export const manualEntry = (req: ManualEntryRequest) =>
  apiFetch<TradeRecord>('/portfolio/manual-entry', {
    method: 'POST',
    body: JSON.stringify(req),
  })

export interface SpecialSellAlert {
  symbol: string
  strategy_name: string
  avg_buy_price: number
  current_price: number | null
}

export const getSpecialSellAlerts = () => apiFetch<SpecialSellAlert[]>('/portfolio/special-sell-alerts')
