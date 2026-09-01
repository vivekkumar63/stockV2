import { apiFetch } from './client'

export interface MLModelStatus {
  exists: boolean
  last_trained: string | null
  samples_available: number
}

export interface MLTrainResult {
  status: 'ok' | 'skipped'
  samples: number
  message: string
}

export const getNormalMLStatus  = () => apiFetch<MLModelStatus>('/intelligence/ml-status')
export const trainNormalModel   = () => apiFetch<MLTrainResult>('/intelligence/train', { method: 'POST' })

export const getSpecialMLStatus = () => apiFetch<MLModelStatus>('/special/ml-status')
export const trainSpecialModel  = () => apiFetch<MLTrainResult>('/special/ml/train', { method: 'POST' })
