import type { MarketRegime } from '../api/intelligence'

const REGIME_CONFIG: Record<string, { label: string; color: string }> = {
  STRONG_BULL:     { label: 'Strong Bull',    color: 'bg-emerald-100 text-emerald-800 border-emerald-300' },
  BULL:            { label: 'Bull Trend',      color: 'bg-green-100 text-green-800 border-green-300' },
  SIDEWAYS:        { label: 'Sideways',        color: 'bg-amber-100 text-amber-800 border-amber-300' },
  BEAR:            { label: 'Bear Trend',      color: 'bg-red-100 text-red-800 border-red-300' },
  STRONG_BEAR:     { label: 'Strong Bear',     color: 'bg-rose-100 text-rose-800 border-rose-300' },
  HIGH_VOLATILITY: { label: 'High Volatility', color: 'bg-purple-100 text-purple-800 border-purple-300' },
}

export function RegimeBanner({ regime }: { regime: MarketRegime }) {
  const cfg = REGIME_CONFIG[regime.regime] ?? {
    label: regime.regime,
    color: 'bg-gray-100 text-gray-800 border-gray-300',
  }
  return (
    <div className={`flex flex-wrap items-center gap-4 px-4 py-2 rounded-lg border text-sm font-medium ${cfg.color}`}>
      <span className="font-bold uppercase tracking-wide">{cfg.label}</span>
      <span>Confidence: {Math.round(regime.confidence * 100)}%</span>
      <span>Breadth (SMA50): {Math.round(regime.pct_above_sma50 * 100)}%</span>
      <span>A/D Ratio: {regime.advance_decline_ratio.toFixed(2)}</span>
      <span className="text-xs opacity-70">as of {regime.as_of_date}</span>
    </div>
  )
}
