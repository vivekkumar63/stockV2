import { apiFetch } from './client'

export interface LeaderboardRow {
  symbol: string
  strategy_id: number
  strategy_name: string
  total_trades: number
  win_rate: number | null
  cagr: number | null
  sharpe_ratio: number | null
  max_drawdown: number | null
  profit_factor: number | null
  total_pnl: number
}

export interface LeaderboardStatus {
  is_computing: boolean
  pairs_cached: number
  total_expected: number
  total_symbols: number
  total_strategies: number
  pct_done: number
  error: string | null
  is_current: boolean
  last_price_date: string | null
  cached_to_date: string | null
  params: { stop_loss_pct: number; target_pct: number; from_date: string }
}

export const getLeaderboard = (params: {
  stop_loss_pct?: number
  target_pct?: number
  min_trades?: number
  limit?: number
  symbol?: string
  strategy_id?: number
}) => {
  const q = new URLSearchParams()
  if (params.stop_loss_pct != null) q.set('stop_loss_pct', String(params.stop_loss_pct))
  if (params.target_pct != null) q.set('target_pct', String(params.target_pct))
  if (params.min_trades != null) q.set('min_trades', String(params.min_trades))
  if (params.limit != null) q.set('limit', String(params.limit))
  if (params.symbol) q.set('symbol', params.symbol)
  if (params.strategy_id != null) q.set('strategy_id', String(params.strategy_id))
  return apiFetch<LeaderboardRow[]>(`/backtest/leaderboard?${q.toString()}`)
}

export const getLeaderboardStatus = (sl = 5.0, tgt = 10.0) =>
  apiFetch<LeaderboardStatus>(
    `/backtest/leaderboard/status?stop_loss_pct=${sl}&target_pct=${tgt}`
  )

export const triggerLeaderboardCompute = (sl = 5.0, tgt = 10.0, force = false) =>
  apiFetch<{ status: string; message: string }>(
    `/backtest/leaderboard/compute?stop_loss_pct=${sl}&target_pct=${tgt}&force=${force}`,
    { method: 'POST' }
  )

export interface TradeDetail {
  entry_date: string
  entry_price: number
  exit_date: string
  exit_price: number
  pnl: number
  pnl_pct: number
  exit_reason: string
  holding_days: number
}

export const getLeaderboardTrades = (
  symbol: string,
  strategyId: number,
  sl = 5.0,
  tgt = 10.0,
) =>
  apiFetch<TradeDetail[]>(
    `/backtest/leaderboard/trades?symbol=${symbol}&strategy_id=${strategyId}&stop_loss_pct=${sl}&target_pct=${tgt}`
  )
