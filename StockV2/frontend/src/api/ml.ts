import { apiFetch } from './client'

export interface MLModelStatus {
  exists: boolean
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
  auc_roc?: number
  precision_at_60?: number
  high_conf_signals?: number
  class_balance?: number
}

export const getNormalMLStatus  = () => apiFetch<MLModelStatus>('/intelligence/ml-status')
export const trainNormalModel   = () => apiFetch<MLTrainResult>('/intelligence/train', { method: 'POST' })

export const getSpecialMLStatus = () => apiFetch<MLModelStatus>('/special/ml-status')
export const trainSpecialModel  = () => apiFetch<MLTrainResult>('/special/ml/train', { method: 'POST' })
