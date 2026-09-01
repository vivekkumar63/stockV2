import { apiFetch } from './client'

export interface MLModelStatus {
  exists: boolean
  models_trained: number
  models_total: number
  last_trained: string | null
  samples_available: number
  auc_roc: number | null
  precision_at_60: number | null
  high_conf_signals: number | null
  class_balance: number | null
}

export interface MLTrainResult {
  status: 'ok' | 'skipped'
  samples: number
  message: string
  strategies_trained?: number
  strategies_total?: number
  auc_roc?: number
  precision_at_60?: number
  high_conf_signals?: number
  class_balance?: number
}

export interface ComputeOutcomesResult {
  new_outcomes_recorded: number
  total_labelled_outcomes: number
  ready_to_train: boolean
}

export interface BackfillStatus {
  is_running: boolean
  done: number
  total: number
  signals_saved: number
  outcomes_labelled: number
  error: string | null
}

export const getNormalMLStatus     = () => apiFetch<MLModelStatus>('/intelligence/ml-status')
export const trainNormalModel      = () => apiFetch<MLTrainResult>('/intelligence/train', { method: 'POST' })
export const computeSignalOutcomes = () => apiFetch<ComputeOutcomesResult>('/intelligence/compute-outcomes', { method: 'POST' })
export const triggerBackfill       = (daysBack = 90) => apiFetch<{ status: string; symbols: number; dates: number }>(`/intelligence/backfill-signals?days_back=${daysBack}`, { method: 'POST' })
export const getBackfillStatus     = () => apiFetch<BackfillStatus>('/intelligence/backfill-status')

export const getSpecialMLStatus = () => apiFetch<MLModelStatus>('/special/ml-status')
export const trainSpecialModel  = () => apiFetch<MLTrainResult>('/special/ml/train', { method: 'POST' })

export const refreshFundamentals = () =>
  apiFetch<{ status: string; symbols: number }>('/data/fundamentals/refresh', { method: 'POST' })

export const getFundamentalsCount = () =>
  apiFetch<{ count: number }>('/data/fundamentals/count')
