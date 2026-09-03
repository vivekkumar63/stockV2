import { apiFetch } from './client'

export interface ZoneCard {
  low: number
  high: number
  score: number
  freshness: 'fresh' | 'tested' | 'weakened'
  touch_count: number
  last_reaction_pct: number
  source_tags: string[]
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
  computed_at?: string
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
}

export interface RecomputeStatus {
  done: number
  total: number
  finished: boolean
  is_running: boolean
  started_at: string | null
  error: string | null
}

export const analyzeZones = (symbol: string) =>
  apiFetch<ZoneResult>(`/zones/analyze/${symbol.toUpperCase()}`)

export const getZoneResult = (symbol: string) =>
  apiFetch<ZoneResult>(`/zones/results/${symbol.toUpperCase()}`)

export const getZoneRankings = (params?: { sort_by?: string; filter?: string; limit?: number }) => {
  const qs = new URLSearchParams()
  if (params?.sort_by) qs.set('sort_by', params.sort_by)
  if (params?.filter)  qs.set('filter',  params.filter)
  if (params?.limit)   qs.set('limit',   String(params.limit))
  const q = qs.toString()
  return apiFetch<ZoneRankRow[]>(`/zones/rankings${q ? '?' + q : ''}`)
}

export const recomputeAll = () =>
  apiFetch<{ status: string; symbol_count: number }>('/zones/recompute-all', { method: 'POST' })

export const getRecomputeStatus = () =>
  apiFetch<RecomputeStatus>('/zones/recompute-status')
