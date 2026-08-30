import { apiFetch } from './client'

export interface CombinationSummary {
  combination_id: number
  name: string
  strategies: string[]
  size: number
  oos_cagr: number | null
  oos_max_drawdown: number | null
  oos_sharpe: number | null
  oos_win_rate: number | null
  oos_total_trades: number | null
  train_cagr: number | null
  wf_consistency_score: number | null
  reliability_score: number | null
  reliability_label: 'Strong evidence' | 'Moderate evidence' | 'Weak evidence' | 'Likely Overfitted' | 'Insufficient Data' | null
  sensitivity_score: number | null
  vs_buy_and_hold_cagr: number | null
  vs_best_single_cagr: number | null
}

export interface RegimePerf {
  regime: string
  win_rate: number | null
  avg_pnl_pct: number | null
  trade_count: number | null
  cagr: number | null
}

export interface CombinationExplanation {
  what_each_captures: string[]
  why_complementary: string
  typical_stocks: string
  works_well_in: string
  struggles_in: string
  risks_and_weaknesses: string
}

export interface CombinationDetail extends CombinationSummary {
  val_cagr: number | null
  oos_sortino: number | null
  oos_median_return_pct: number | null
  oos_profit_factor: number | null
  vs_sma_crossover_cagr: number | null
  regime_perf: RegimePerf[]
  explanation: CombinationExplanation | null
}

export interface BestCombinations {
  overall: CombinationSummary | null
  low_risk: CombinationSummary | null
  high_growth: CombinationSummary | null
  most_consistent: CombinationSummary | null
}

export interface RunStatus {
  status: 'running' | 'complete' | 'failed' | 'never_run'
  last_completed_at: string | null
  last_run_id: number | null
  combinations_tested: number | null
  top_combination: { name: string; oos_cagr: number | null; reliability_label: string | null } | null
  error_message: string | null
}

export interface RankingsParams {
  size?: number
  sort_by?: 'reliability_score' | 'oos_cagr' | 'oos_sharpe' | 'oos_win_rate'
}

export const getRunStatus = (): Promise<RunStatus> =>
  apiFetch<RunStatus>('/combinations/run-status')

export const getCombinationRankings = (params?: RankingsParams): Promise<CombinationSummary[]> => {
  const query = new URLSearchParams()
  if (params?.size != null) query.set('size', String(params.size))
  if (params?.sort_by) query.set('sort_by', params.sort_by)
  const qs = query.toString()
  return apiFetch<CombinationSummary[]>(`/combinations/rankings${qs ? `?${qs}` : ''}`)
}

export const getBestCombinations = (): Promise<BestCombinations> =>
  apiFetch<BestCombinations>('/combinations/best')

export const getCombinationsToAvoid = (): Promise<CombinationSummary[]> =>
  apiFetch<CombinationSummary[]>('/combinations/avoid')

export const getCombinationDetail = (id: number): Promise<CombinationDetail> =>
  apiFetch<CombinationDetail>(`/combinations/${id}`)

export const triggerAnalysis = (): Promise<{ status: string; message?: string; run_id?: number | null }> =>
  apiFetch('/combinations/analyze', { method: 'POST' })

export const resetStuckRuns = (): Promise<{ reset: number; message: string }> =>
  apiFetch('/combinations/reset-stuck', { method: 'POST' })
