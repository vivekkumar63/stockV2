import { apiFetch } from './client'

export interface SectorData {
  name: string
  rotation_direction: 'ROTATING_IN' | 'NEUTRAL' | 'ROTATING_OUT'
  sector_health_score: number
  pct_above_sma50: number
  index_vs_sma20: number
  return_1m: number
  return_3m: number
  signal_count_this_week: number
  signal_count_prev_week: number
  avg_win_rate: number | null
  top_strategy: string | null
  stocks_with_signals: string[]
}

export interface SectorSummary {
  market_phase: 'EXPANSION' | 'CONTRACTION' | 'RECOVERY' | 'SLOWDOWN' | 'UNKNOWN'
  as_of: string | null
  sectors: SectorData[]
}

export interface SectorStock {
  symbol: string
  close: number
  last_date: string
  above_sma20: boolean
  above_sma50: boolean
  pct_vs_sma20: number | null
  pct_vs_sma50: number | null
  return_3m: number | null
}

export const getSectorSummary = () =>
  apiFetch<SectorSummary>('/sector/summary')

export const getSectorStocks = (sector: string) =>
  apiFetch<SectorStock[]>(`/sector/${encodeURIComponent(sector)}/stocks`)

export const recomputeSectors = () =>
  apiFetch<{ status: string; breadth_written: number; flow_written: number }>(
    '/sector/recompute',
    { method: 'POST' },
  )
