import { apiFetch } from './client'

export interface FundamentalsRow {
  symbol?: string
  pe_ratio: number | null
  pb_ratio: number | null
  eps: number | null
  revenue: number | null
  net_profit: number | null
  debt_equity: number | null
  roe: number | null
  dividend_yield: number | null
  data_as_of: string | null
}

export const getAllFundamentals = () =>
  apiFetch<FundamentalsRow[]>('/data/fundamentals')

export const getFundamentalsHistory = (symbol: string) =>
  apiFetch<FundamentalsRow[]>(`/data/fundamentals/${symbol}/history`)
