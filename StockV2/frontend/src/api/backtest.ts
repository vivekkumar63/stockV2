import { apiFetch } from './client'

export interface BacktestRunRequest {
  symbol: string
  from_date: string
  to_date: string
  strategy_id?: number
  initial_capital?: number
}

export interface BacktestResult {
  id?: number
  result_id?: number
  symbol: string
  from_date: string
  to_date: string
  total_trades: number
  win_rate: number | null
  total_pnl?: number
  cagr: number | null
  sharpe_ratio: number | null
  max_drawdown: number | null
  profit_factor: number | null
  avg_return_pct: number | null
  ran_at?: string
}

export interface BacktestTrade {
  id: number
  symbol: string
  entry_date: string
  entry_price: number
  exit_date: string
  exit_price: number
  quantity: number
  pnl: number
  pnl_pct: number
  exit_reason: string
  holding_days: number
}

export const runBacktest = (req: BacktestRunRequest) =>
  apiFetch<BacktestResult>('/backtest/run', {
    method: 'POST',
    body: JSON.stringify(req),
  })

export const listBacktestResults = (symbol?: string, limit = 20) => {
  const q = new URLSearchParams({ limit: String(limit) })
  if (symbol) q.set('symbol', symbol)
  return apiFetch<BacktestResult[]>(`/backtest/results?${q.toString()}`)
}

export const getBacktestResult = (id: number) =>
  apiFetch<BacktestResult>(`/backtest/results/${id}`)

export const getBacktestTrades = (id: number) =>
  apiFetch<BacktestTrade[]>(`/backtest/results/${id}/trades`)
