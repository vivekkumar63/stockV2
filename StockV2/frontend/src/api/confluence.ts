import { apiFetch } from './client'

export interface ConfluenceBreakout {
  symbol: string
  category: 'breakout'
  current_price: number
  resistance: number
  breakout_pct: number
  volume_ratio: number
  rsi: number
  ema50_slope_pct: number
  body_ratio: number
  range_atr_ratio: number
  conviction_score: number
  signals_met: string[]
  signals_failed: string[]
  zone_ml_confidence: number
  breakout_ml_probability: number
  combined_score: number
  zone_score: number
  market_structure: string
  candle_signal: string
  position_tag: string
  long_setup: {
    score: number
    ideal_entry: number
    stop_loss: number
    t1: number; t1_rr: number
    t2: number; t2_rr: number
  } | null
  short_setup: {
    score: number
    ideal_entry: number
    stop_loss: number
    t1: number; t1_rr: number
    t2: number; t2_rr: number
  } | null
}

export interface ConfluenceNearBreakout {
  symbol: string
  category: 'near_breakout'
  current_price: number
  resistance: number
  dist_to_resistance: number   // negative = below resistance
  volume_ratio: number
  rsi: number
  ema50_slope_pct: number
  zone_ml_confidence: number
  combined_score: number
  zone_score: number
  market_structure: string
  candle_signal: string
  position_tag: string
  long_setup: {
    score: number
    ideal_entry: number
    stop_loss: number
    t1: number; t1_rr: number
    t2: number; t2_rr: number
  } | null
  demand_zones: { low: number; high: number; score: number; freshness: string }[]
}

export interface ConfluenceScanResult {
  breakouts: ConfluenceBreakout[]
  near_breakout: ConfluenceNearBreakout[]
}

export const getConfluenceScan = () =>
  apiFetch<ConfluenceScanResult>('/confluence/scan')
