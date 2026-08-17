import { apiFetch } from './client'

export interface Signal {
  id: number
  symbol: string
  strategy_id: number
  strategy_name: string
  signal_date: string
  signal_type: 'BUY' | 'SELL' | 'NONE'
  price_at_signal: number
  confidence_score: number | null
  risk_score: number | null
  expected_upside_pct: number | null
  suggested_stop_loss: number | null
  suggested_target: number | null
  holding_period_days: number | null
  latest_price: number | null
  latest_price_date: string | null
  reasoning_json: string | null
  historical_win_rate: number | null
  opportunity_score: number | null
  opportunity_grade: string | null
}

export interface LiveScanRequest {
  strategy_id?: number
  signal_type?: 'BUY' | 'SELL'
  limit?: number
}

export interface LiveScanResult {
  symbol: string
  strategy_id: number | null
  strategy_name: string
  signal_type: string
  confidence: number
  price: number
  stop_loss_pct: number | null
  target_pct: number | null
  holding_days: number | null
  historical_win_rate: number | null
  opportunity_score: number | null
  opportunity_grade: string | null
}

export const runLiveScan = (req: LiveScanRequest) =>
  apiFetch<LiveScanResult[]>('/signals/scan', {
    method: 'POST',
    body: JSON.stringify(req),
  })

export const getTodaySignals = () => apiFetch<Signal[]>('/signals/today')

export const getSignals = (params?: {
  symbol?: string
  signal_type?: 'BUY' | 'SELL' | 'NONE'
  from_date?: string
  limit?: number
}) => {
  const q = new URLSearchParams()
  if (params?.symbol) q.set('symbol', params.symbol)
  if (params?.signal_type) q.set('signal_type', params.signal_type)
  if (params?.from_date) q.set('from_date', params.from_date)
  if (params?.limit != null) q.set('limit', String(params.limit))
  const qs = q.toString()
  return apiFetch<Signal[]>(`/signals${qs ? `?${qs}` : ''}`)
}
