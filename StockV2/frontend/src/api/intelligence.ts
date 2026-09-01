import { apiFetch } from './client'

export interface MarketRegime {
  regime: string
  confidence: number
  pct_above_sma50: number
  pct_above_sma200: number
  advance_decline_ratio: number
  avg_atr_ratio: number
  stocks_counted: number
  as_of_date: string
}

export interface OpportunityBreakdown {
  historical_win_rate: number | null
  strategy_confidence: number | null
  regime_alignment: number | null
  regime_strategy: number | null
  mtf_alignment: number | null
  volume: number | null
  sr_context: number | null
  ml_signal_probability: number | null
  false_signal_rate: number | null
  sector_health: number | null
}

export interface TopOpportunity {
  signal_id: number
  symbol: string
  strategy_id: number
  strategy_name: string
  signal_date: string
  confidence_score: number | null
  price_at_signal: number
  stop_loss_price: number | null
  target_price: number | null
  stop_loss_pct: number | null
  target_pct: number | null
  holding_days: number | null
  rr: number | null
  reasoning_json: string | null
  score: number
  grade: string
  regime: string
  mtf_alignment: number | null
  ml_probability: number | null
  false_signal_rate: number | null
  sector_name: string | null
  confluence_count: number
  days_to_earnings: number | null
  breakdown: OpportunityBreakdown
}

export interface StrategyRank {
  rank: number
  strategy_id: number
  strategy_name: string
  regime_win_rate: number | null
  overall_win_rate: number | null
  regime_trades: number
}

export interface FalseSignalStat {
  strategy_id: number
  strategy_name: string
  total_evaluated: number
  win_rate: number | null
  false_signal_rate: number | null
  avg_pnl_pct: number | null
}

export interface CorrelationPair {
  strategy_id_a: number
  strategy_name_a: string
  strategy_id_b: number
  strategy_name_b: string
  correlation: number
  shared_signals: number
}

export const getMarketRegime = () =>
  apiFetch<MarketRegime>('/market/regime')

export const getTopOpportunities = (limit = 20) =>
  apiFetch<TopOpportunity[]>(`/intelligence/top-opportunities?limit=${limit}`)

export const getStrategyRanking = (regime?: string) => {
  const qs = regime ? `?regime=${encodeURIComponent(regime)}` : ''
  return apiFetch<StrategyRank[]>(`/intelligence/strategy-ranking${qs}`)
}

export const getFalseSignalStats = () =>
  apiFetch<FalseSignalStat[]>('/intelligence/false-signal-stats')

export const getStrategyCorrelations = () =>
  apiFetch<CorrelationPair[]>('/intelligence/strategy-correlations')

// ── AI Signal Explanation ────────────────────────────────────────────────────

export interface SignalExplanation {
  // BUY signal fields
  summary?: string
  bull_case?: string[]
  bear_case?: string[]
  confidence_reasoning?: string
  suggested_entry?: number | null
  stop_loss?: number | null
  target_1?: number | null
  target_2?: number | null
  holding_period?: string | null
  risk_rating?: string | null
  // SELL signal fields
  exit_reasons?: string[]
  risk_if_held?: string[]
  action?: string | null
}

export const getSignalExplanation = (signalId: number) =>
  apiFetch<SignalExplanation>(`/signals/${signalId}/explanation`)
