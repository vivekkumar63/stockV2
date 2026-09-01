import { apiFetch } from './client'

export interface SpecialStrategy {
  id: number
  name: string
  description: string | null
  is_active: boolean
}

export interface SpecialScanRequest {
  strategy_id?: number
}

export interface SpecialScanResult {
  symbol: string
  strategy_id: number | null
  strategy_name: string
  signal_type: string
  confidence: number
  price: number
  conditions_met: string[]
}

export interface SpecialBacktestRequest {
  symbol: string
  from_date: string
  to_date: string
  special_strategy_id: number
  initial_capital?: number
}

export interface SpecialBacktestResult {
  id: number
  special_strategy_id: number
  strategy_name?: string
  symbol: string
  from_date: string
  to_date: string
  total_trades: number
  win_rate: number | null
  total_pnl: number
  avg_pnl_pct: number | null
  ran_at: string
}

export interface SpecialTrade {
  id: number
  symbol: string
  entry_date: string
  entry_price: number
  exit_date: string | null
  exit_price: number | null
  quantity: number
  pnl: number | null
  pnl_pct: number | null
  exit_reason: string
  holding_days: number | null
}

export const getSpecialStrategies = () => apiFetch<SpecialStrategy[]>('/special/strategies')

export const runSpecialScan = (req: SpecialScanRequest) =>
  apiFetch<SpecialScanResult[]>('/special/scan', {
    method: 'POST',
    body: JSON.stringify(req),
  })

export const runSpecialBacktest = (req: SpecialBacktestRequest) =>
  apiFetch<SpecialBacktestResult>('/special/backtest/run', {
    method: 'POST',
    body: JSON.stringify(req),
  })

export const getSpecialBacktestResults = () =>
  apiFetch<SpecialBacktestResult[]>('/special/backtest/results')

export const getSpecialBacktestTrades = (id: number) =>
  apiFetch<SpecialTrade[]>(`/special/backtest/results/${id}/trades`)

// ── Precompute / All-stocks scan ──────────────────────────────────────────────

export interface SpecialPrecomputeStatus {
  is_running: boolean
  done: number
  total: number
  pct_done: number
  phase: string
  message: string
  error: string | null
  symbol_strategy_pairs: number
  symbols_computed: number
  total_active_strategies: number
  last_updated: string | null
}

export interface SpecialPerformanceRow {
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
  avg_pnl_pct: number | null
  to_date: string | null
}

export interface SpecialRecommendation extends SpecialScanResult {
  total_trades: number | null
  win_rate: number | null
  cagr: number | null
  sharpe_ratio: number | null
  max_drawdown: number | null
  profit_factor: number | null
  total_pnl: number | null
  avg_pnl_pct: number | null
}

export interface SpecialRecommendationsResponse {
  scanned_at: string
  results: SpecialRecommendation[]
}

export const getSpecialRecommendations = (force = false) =>
  apiFetch<SpecialRecommendationsResponse>(`/special/recommendations${force ? '?force=true' : ''}`)

export const getSpecialStrategyTrades = (strategyId: number, symbol: string) =>
  apiFetch<SpecialTrade[]>(`/special/performance/trades?strategy_id=${strategyId}&symbol=${encodeURIComponent(symbol)}`)

export const triggerSpecialPrecompute = (force = false) =>
  apiFetch<{ status: string; message: string; strategies_queued: number }>(`/special/precompute?force=${force}`, { method: 'POST' })

export const getSpecialPrecomputeStatus = () =>
  apiFetch<SpecialPrecomputeStatus>('/special/precompute/status')

export const getSpecialScanResults = (strategy_id?: number, min_trades = 0) =>
  apiFetch<SpecialPerformanceRow[]>(`/special/scan/results?min_trades=${min_trades}${strategy_id ? `&strategy_id=${strategy_id}` : ''}`)
