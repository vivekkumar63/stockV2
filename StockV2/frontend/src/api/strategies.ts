import { apiFetch } from './client'

export interface Strategy {
  id: number
  name: string
  type: string
  description: string | null
  is_active: boolean
}

export interface StockSummary {
  symbol: string
  name: string | null
  sector: string | null
}

export interface StrategyDetail extends Strategy {
  timeframe: string | null
  min_holding_days: number | null
  max_holding_days: number | null
  weight: number | null
  required_indicators: string[]
  parameters: Record<string, unknown>
  created_at: string | null
}

export const getStrategies = () => apiFetch<Strategy[]>('/strategies')
export const getStrategyDetail = (id: number) => apiFetch<StrategyDetail>(`/strategies/${id}`)
export const getStockList = () => apiFetch<StockSummary[]>('/stocks')
