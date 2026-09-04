import { apiFetch } from './client'

export interface ZoneCard {
  low: number
  high: number
  score: number
  freshness: 'fresh' | 'tested' | 'weakened'
  touch_count: number
  last_reaction_pct: number
  source_tags: string[]
  source: 'daily' | 'vwap'   // NEW in Phase B
}

export interface ZoneSetup {
  score: number
  ideal_entry: number
  aggressive_entry: number
  conservative_entry: number
  stop_loss: number
  t1: number
  t1_rr: number
  t2: number
  t2_rr: number
  t3: number
  t3_rr: number
  explanation: string
  invalidation: string
}

export interface ZoneResult {
  symbol: string
  demand_zones: ZoneCard[]
  supply_zones: ZoneCard[]
  long_setup: ZoneSetup | null
  short_setup: ZoneSetup | null
  market_structure: 'bullish' | 'bearish' | 'sideways'
  atr: number
  rvol: number
  price: number
  position_tag: string
  candle_signal?: string
  computed_at?: string
  computed_date?: string
  long_setup_score?: number
  short_setup_score?: number
}

export interface ZoneRankRow {
  rank: number
  symbol: string
  long_setup_score: number | null
  short_setup_score: number | null
  best_demand_score: number | null
  best_supply_score: number | null
  position_tag: string
  price: number
  atr: number
  rvol: number
  best_long_rr: number | null
  best_short_rr: number | null
  computed_at: string
  pct_from_52w_high: number | null
  pct_from_52w_low: number | null
  dist_to_long: number | null   // (price - long_entry) / price * 100; negative = below entry
  dist_to_short: number | null  // (price - short_entry) / price * 100; positive = above entry
  ml_confidence: number | null  // P(profitable) in [0,1] from ML model or rule-based fallback
}

export interface RecomputeStatus {
  done: number
  total: number
  finished: boolean
  is_running: boolean
  started_at: string | null
  error: string | null
}

// ── Chart overlay ─────────────────────────────────────────────────────────────

export interface OhlcvBar {
  date: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export interface ZoneBand {
  low: number
  high: number
  strength: number
  zone_type: 'demand' | 'supply'
  source: 'daily' | 'vwap'
}

export interface ChartSetupLines {
  entry: number
  stop_loss: number
  target: number | null
}

export interface ChartDataResponse {
  ohlcv: OhlcvBar[]
  demand_bands?: ZoneBand[]
  supply_bands?: ZoneBand[]
  long_setup?: ChartSetupLines
  short_setup?: ChartSetupLines
}

// ── Backtest ──────────────────────────────────────────────────────────────────

export interface BacktestResult {
  id: number
  symbol: string
  from_date: string
  to_date: string
  total_trades: number
  win_rate: number | null
  total_pnl_pct: number
  avg_hold_days: number | null
  ran_at: string
}

export interface BacktestTrade {
  id: number
  entry_date: string
  entry_price: number
  exit_date: string | null
  exit_price: number | null
  pnl_pct: number | null
  exit_reason: string
  hold_days: number | null
}

// ── API functions ─────────────────────────────────────────────────────────────

export const analyzeZones = (symbol: string) =>
  apiFetch<ZoneResult>(`/zones/analyze/${symbol.toUpperCase()}`)

export const getZoneResult = (symbol: string) =>
  apiFetch<ZoneResult>(`/zones/results/${symbol.toUpperCase()}`)

export const getZoneRankings = (params?: { sort_by?: string; tag_filter?: string; limit?: number; min_rr?: number }) => {
  const qs = new URLSearchParams()
  if (params?.sort_by)    qs.set('sort_by',    params.sort_by)
  if (params?.tag_filter) qs.set('tag_filter', params.tag_filter)
  if (params?.limit)      qs.set('limit',      String(params.limit))
  if (params?.min_rr)     qs.set('min_rr',     String(params.min_rr))
  const q = qs.toString()
  return apiFetch<ZoneRankRow[]>(`/zones/rankings${q ? '?' + q : ''}`)
}

export const recomputeAll = () =>
  apiFetch<{ status: string; symbol_count: number }>('/zones/recompute-all', { method: 'POST' })

export const getRecomputeStatus = () =>
  apiFetch<RecomputeStatus>('/zones/recompute-status')

export const getChartData = (symbol: string, bars = 120) =>
  apiFetch<ChartDataResponse>(`/zones/chart-data/${symbol.toUpperCase()}?bars=${bars}`)

export const runBacktest = (params: { symbol: string; from_date: string; to_date: string }) =>
  apiFetch<BacktestResult>(
    `/zones/backtest/run?symbol=${params.symbol.toUpperCase()}&from_date=${params.from_date}&to_date=${params.to_date}`,
    { method: 'POST' },
  )

export const getBacktestResults = (symbol: string) =>
  apiFetch<BacktestResult[]>(`/zones/backtest/results/${symbol.toUpperCase()}`)

export const getBacktestTrades = (resultId: number) =>
  apiFetch<BacktestTrade[]>(`/zones/backtest/trades/${resultId}`)

export const getBacktestSymbols = () =>
  apiFetch<{ symbols: string[] }>('/zones/backtest/symbols')

export const runBacktestAll = (from_date: string, to_date: string) =>
  apiFetch<{ status: string; symbol_count?: number }>(
    `/zones/backtest/run-all?from_date=${from_date}&to_date=${to_date}`,
    { method: 'POST' },
  )

export const getBacktestAllStatus = () =>
  apiFetch<{ running: boolean; done: number; total: number; errors: number; finished: boolean }>(
    '/zones/backtest/run-all/status',
  )

export const getAllBacktestResults = () =>
  apiFetch<BacktestResult[]>('/zones/backtest/all-results')

// ── Breakout scanner ──────────────────────────────────────────────────────────

export interface BreakoutSignal {
  symbol: string
  current_price: number
  resistance: number
  breakout_pct: number
  volume_ratio: number
  rsi: number
  body_ratio: number
  range_atr_ratio: number
  ema50_slope_pct: number
  conviction_score: number
  signals_met: string[]
  signals_failed: string[]
  zone_score: number | null
  market_structure: string
  candle_signal: string
  trendline_resistance: number | null
  true_breakout_probability: number
}

export interface BreakoutBacktestResult {
  id: number
  symbol: string
  from_date: string
  to_date: string
  total_trades: number
  win_rate: number | null
  total_pnl: number
  avg_pnl_pct: number | null
  ran_at: string
}

export interface BreakoutBacktestTrade {
  entry_date: string
  entry_price: number
  resistance: number
  exit_date: string | null
  exit_price: number | null
  pnl_pct: number | null
  exit_reason: string
  hold_days: number | null
  volume_ratio: number
  rsi: number
  conviction_score: number
}

export interface BreakoutSingleBacktestResponse extends BreakoutBacktestResult {
  trades: BreakoutBacktestTrade[]
}

export const scanBreakouts = () =>
  apiFetch<BreakoutSignal[]>('/zones/breakout/scan')

export const runBreakoutBacktest = (params: { symbol: string; from_date: string; to_date: string }) =>
  apiFetch<BreakoutSingleBacktestResponse>(
    `/zones/breakout/backtest?symbol=${params.symbol.toUpperCase()}&from_date=${params.from_date}&to_date=${params.to_date}`,
    { method: 'POST' },
  )

export const runBreakoutBacktestAll = (from_date: string, to_date: string) =>
  apiFetch<{ status: string; total?: number }>(
    `/zones/breakout/backtest-all?from_date=${from_date}&to_date=${to_date}`,
    { method: 'POST' },
  )

export const getBreakoutBacktestAllStatus = () =>
  apiFetch<{ running: boolean; done: number; total: number; errors: number; finished: boolean }>(
    '/zones/breakout/backtest-all/status',
  )

export const getBreakoutBacktestResults = () =>
  apiFetch<BreakoutBacktestResult[]>('/zones/breakout/backtest-results')

export const getBreakoutBacktestTrades = (resultId: number) =>
  apiFetch<BreakoutBacktestTrade[]>(`/zones/breakout/backtest-results/${resultId}/trades`)

// ── Breakout ML ────────────────────────────────────────────────────────────────

export interface BreakoutMLStatus {
  model_exists: boolean
  using_ml: boolean
  note: string
}

export const getBreakoutMLStatus = () => apiFetch<BreakoutMLStatus>('/zones/breakout/ml/status')
export const trainBreakoutML = () => apiFetch<MLTrainResult>('/zones/breakout/ml/train', { method: 'POST' })

// ── ML Zone Scorer ─────────────────────────────────────────────────────────────

export interface MLModelStatus {
  model_exists: boolean
  using_ml: boolean
  note: string
}

export interface MLTrainResult {
  trained: boolean
  samples: number
  cv_accuracy?: number
  positive_rate?: number
  reason?: string
}

export const getMLStatus = () => apiFetch<MLModelStatus>('/zones/ml/status')
export const trainMLModel = () => apiFetch<MLTrainResult>('/zones/ml/train', { method: 'POST' })

// ── Recommendations ────────────────────────────────────────────────────────────

export interface ZoneRecommendation {
  symbol: string
  composite_score: number
  ml_confidence: number
  long_setup_score: number | null
  short_setup_score: number | null
  best_long_rr: number | null
  best_short_rr: number | null
  rvol: number
  position_tag: string
  price: number
  atr: number
  pct_from_52w_high: number | null
  pct_from_52w_low: number | null
  long_setup: ZoneSetup | null
  short_setup: ZoneSetup | null
  demand_zones: ZoneCard[]
  supply_zones: ZoneCard[]
  market_structure: string
  candle_signal: string
  reason: string
}

export const getZoneRecommendations = (params?: { setup_type?: string; limit?: number }) => {
  const qs = new URLSearchParams()
  if (params?.setup_type) qs.set('setup_type', params.setup_type)
  if (params?.limit)      qs.set('limit', String(params.limit))
  const q = qs.toString()
  return apiFetch<ZoneRecommendation[]>(`/zones/recommendations${q ? '?' + q : ''}`)
}
