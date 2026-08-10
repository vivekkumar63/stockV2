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

export const getStrategies = () => apiFetch<Strategy[]>('/strategies')
export const getStockList = () => apiFetch<StockSummary[]>('/stocks')
