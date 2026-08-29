import { apiFetch } from './client'

export interface BacktestRunRequest {
  symbol: string
  from_date: string
  to_date: string
  strategy_id?: number
  initial_capital?: number
  stop_loss_pct?: number
  target_pct?: number
}

export interface BacktestResult {
  id?: number        // from GET /backtest/results
  result_id?: number // from POST /backtest/run response
  strategy_id?: number
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

export interface ScanRequest {
  from_date: string
  to_date: string
  strategy_ids?: number[]
  initial_capital?: number
  limit?: number
  stop_loss_pct?: number
  target_pct?: number
}

export interface ScanResult {
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

export const runScan = (req: ScanRequest) =>
  apiFetch<ScanResult[]>('/backtest/scan', {
    method: 'POST',
    body: JSON.stringify(req),
  })

export interface ScanStatus {
  total: number
  computed: number
  pending: number
  ready: boolean
}

export const getScanStatus = () => apiFetch<ScanStatus>('/backtest/scan/status')

export interface PrecomputeStatus {
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

export const triggerPrecompute = (force = false) =>
  apiFetch<{ status: string; strategies_queued?: number; message?: string }>(
    `/backtest/precompute${force ? '?force=true' : ''}`,
    { method: 'POST' },
  )

export const getPrecomputeStatus = () =>
  apiFetch<PrecomputeStatus>('/backtest/precompute/status')

export const getPrecomputedScan = (strategyId?: number, minTrades = 0) => {
  const q = new URLSearchParams({ min_trades: String(minTrades) })
  if (strategyId != null) q.set('strategy_id', String(strategyId))
  return apiFetch<ScanResult[]>(`/backtest/scan/results?${q.toString()}`)
}

// ── Walk-Forward Analysis ────────────────────────────────────────────────────

export interface WalkForwardWindow {
  window_index: number
  train_from: string
  train_to: string
  test_from: string
  test_to: string
  oos_metrics: {
    win_rate: number | null
    total_trades: number
    avg_return_pct: number | null
    max_drawdown_pct: number | null
  }
}

export interface WalkForwardResult {
  status: 'ok' | 'failed' | 'pending'
  symbol: string
  strategy_id: number
  n_windows: number
  oos_win_rate_mean: number | null
  oos_win_rate_std: number | null
  consistency_score: number | null
  in_sample_win_rate: number | null
  windows: WalkForwardWindow[]
  computed_at: string | null
  error: string | null
}

export const runWalkForward = (symbol: string, strategyId: number) =>
  apiFetch<{ status: string; symbol: string; strategy_id: number }>(
    `/backtests/walk-forward?symbol=${encodeURIComponent(symbol)}&strategy_id=${strategyId}`,
    { method: 'POST' },
  )

export const getWalkForwardResult = (symbol: string, strategyId: number) =>
  apiFetch<WalkForwardResult>(
    `/backtests/walk-forward/${encodeURIComponent(symbol)}/${strategyId}`,
  )

export interface ResetDbResult {
  status: string
  scope: string
  tables_cleared: number
  bootstrap_started: boolean
  message: string
}

export const resetDb = (scope: 'computed' | 'full') =>
  apiFetch<ResetDbResult>(`/admin/reset-db?scope=${scope}`, { method: 'POST' })
