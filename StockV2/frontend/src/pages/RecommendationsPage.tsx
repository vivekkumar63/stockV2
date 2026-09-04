import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getZoneRecommendations, getMLStatus, trainMLModel,
  type ZoneRecommendation, type ZoneSetup,
} from '../api/zones'

// ── Helpers ──────────────────────────────────────────────────────────────────

const POSITION_BADGE: Record<string, { bg: string; text: string; label: string }> = {
  in_demand:   { bg: 'bg-green-100',  text: 'text-green-700',  label: '✦ IN DEMAND' },
  near_demand: { bg: 'bg-yellow-100', text: 'text-yellow-700', label: '⚡ NEAR DEMAND' },
  near_supply: { bg: 'bg-orange-100', text: 'text-orange-700', label: '⚠ NEAR SUPPLY' },
  in_supply:   { bg: 'bg-red-100',    text: 'text-red-700',    label: '✦ IN SUPPLY' },
  breakout:    { bg: 'bg-blue-100',   text: 'text-blue-700',   label: '⬆ BREAKOUT' },
  neutral:     { bg: 'bg-gray-100',   text: 'text-gray-600',   label: '− NEUTRAL' },
}

const TREND_BADGE: Record<string, { bg: string; text: string }> = {
  bullish:  { bg: 'bg-green-100', text: 'text-green-700' },
  bearish:  { bg: 'bg-red-100',   text: 'text-red-700' },
  sideways: { bg: 'bg-gray-100',  text: 'text-gray-600' },
}

const CANDLE_BADGE: Record<string, { bg: string; text: string; label: string }> = {
  hammer:            { bg: 'bg-green-100', text: 'text-green-700', label: '🔨 Hammer' },
  bullish_engulfing: { bg: 'bg-green-100', text: 'text-green-700', label: '↑ Bull Engulf' },
  shooting_star:     { bg: 'bg-red-100',   text: 'text-red-700',   label: '★ Shooting Star' },
  bearish_engulfing: { bg: 'bg-red-100',   text: 'text-red-700',   label: '↓ Bear Engulf' },
  doji:              { bg: 'bg-gray-100',  text: 'text-gray-600',  label: '≡ Doji' },
}

function mlBadge(conf: number): { bg: string; text: string } {
  if (conf >= 70) return { bg: 'bg-green-100', text: 'text-green-700' }
  if (conf >= 55) return { bg: 'bg-yellow-100', text: 'text-yellow-700' }
  return { bg: 'bg-gray-100', text: 'text-gray-500' }
}

function fmt(n: number | null | undefined, dec = 0): string {
  if (n == null) return '—'
  return n.toLocaleString('en-IN', { maximumFractionDigits: dec })
}

function SetupRow({ setup, type }: { setup: ZoneSetup; type: 'long' | 'short' }) {
  const c = type === 'long' ? 'text-green-700' : 'text-red-600'
  return (
    <div className="grid grid-cols-4 gap-1 text-xs mt-1">
      <div><span className="text-gray-400">Entry</span><div className={`font-semibold ${c}`}>₹{fmt(setup.ideal_entry)}</div></div>
      <div><span className="text-gray-400">SL</span><div className="font-semibold text-red-500">₹{fmt(setup.stop_loss)}</div></div>
      <div><span className="text-gray-400">T1</span><div className="font-semibold text-green-600">₹{fmt(setup.t1)}</div></div>
      <div><span className="text-gray-400">R:R</span><div className="font-semibold">1:{setup.t1_rr}</div></div>
    </div>
  )
}

// ── Recommendation Card ───────────────────────────────────────────────────────

function RecoCard({
  rec, rank, expanded, onExpand,
}: {
  rec: ZoneRecommendation
  rank: number
  expanded: boolean
  onExpand: () => void
}) {
  const posStyle = POSITION_BADGE[rec.position_tag] ?? POSITION_BADGE.neutral
  const trendStyle = TREND_BADGE[rec.market_structure] ?? TREND_BADGE.sideways
  const candle = rec.candle_signal && rec.candle_signal !== 'NONE' ? CANDLE_BADGE[rec.candle_signal] : null
  const ml = mlBadge(rec.ml_confidence)

  return (
    <div className={`bg-white rounded-lg border shadow-sm overflow-hidden transition-all ${
      expanded ? 'border-blue-300 ring-1 ring-blue-200' : 'border-gray-200'
    }`}>
      {/* Main row — always visible */}
      <div
        className="flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-gray-50"
        onClick={onExpand}
      >
        {/* Rank */}
        <span className="text-gray-400 text-sm w-6 shrink-0">#{rank}</span>

        {/* Symbol + badges */}
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-bold text-gray-900 text-sm">{rec.symbol}</span>
            <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded-full ${posStyle.bg} ${posStyle.text}`}>
              {posStyle.label}
            </span>
            <span className={`text-[10px] px-1.5 py-0.5 rounded ${trendStyle.bg} ${trendStyle.text} capitalize`}>
              {rec.market_structure}
            </span>
            {candle && (
              <span className={`text-[10px] px-1.5 py-0.5 rounded ${candle.bg} ${candle.text}`}>
                {candle.label}
              </span>
            )}
          </div>
          <div className="text-[10px] text-gray-500 mt-0.5">{rec.reason}</div>
        </div>

        {/* ML Confidence */}
        <div className="text-center shrink-0 w-16">
          <div className={`text-xl font-bold px-2 py-1 rounded-lg ${ml.bg} ${ml.text}`}>
            {rec.ml_confidence.toFixed(0)}%
          </div>
          <div className="text-[9px] text-gray-400 mt-0.5">ML Conf</div>
        </div>

        {/* Composite Score */}
        <div className="text-center shrink-0 w-14">
          <div className="text-lg font-bold text-gray-800">{rec.composite_score.toFixed(0)}</div>
          <div className="text-[9px] text-gray-400">Score</div>
        </div>

        {/* Price + R:R */}
        <div className="text-right shrink-0 w-20">
          <div className="text-sm font-semibold">₹{fmt(rec.price)}</div>
          {rec.best_long_rr != null && (
            <div className="text-[10px] text-green-600">R:R 1:{rec.best_long_rr.toFixed(1)}</div>
          )}
        </div>

        {/* Expand toggle */}
        <span className="text-gray-400 text-xs shrink-0">{expanded ? '▲' : '▼'}</span>
      </div>

      {/* Expanded detail */}
      {expanded && (
        <div className="border-t border-gray-100 px-4 py-3 bg-blue-50 text-xs">
          <div className="grid grid-cols-2 gap-4">
            {/* Long setup */}
            {rec.long_setup && (
              <div className="bg-white rounded border border-green-100 p-2.5">
                <div className="font-bold text-green-700 mb-1">
                  Long Setup — {rec.long_setup_score}/100
                </div>
                <SetupRow setup={rec.long_setup} type="long" />
                {rec.long_setup.explanation && (
                  <div className="text-gray-500 mt-2 text-[10px] leading-relaxed">
                    {rec.long_setup.explanation}
                  </div>
                )}
              </div>
            )}

            {/* Short setup */}
            {rec.short_setup && (
              <div className="bg-white rounded border border-red-100 p-2.5">
                <div className="font-bold text-red-600 mb-1">
                  Short Setup — {rec.short_setup_score}/100
                </div>
                <SetupRow setup={rec.short_setup} type="short" />
                {rec.short_setup.explanation && (
                  <div className="text-gray-500 mt-2 text-[10px] leading-relaxed">
                    {rec.short_setup.explanation}
                  </div>
                )}
              </div>
            )}

            {/* Zone + context */}
            <div>
              <div className="font-semibold text-gray-600 mb-1">Demand Zones</div>
              {rec.demand_zones.map((z, i) => (
                <div key={i} className="text-gray-600 text-[10px]">
                  ₹{fmt(z.low)} – ₹{fmt(z.high)}
                  <span className="ml-1 text-gray-400">({z.score}/100 · {z.freshness})</span>
                </div>
              ))}
              {rec.demand_zones.length === 0 && <div className="text-gray-400">None</div>}

              <div className="font-semibold text-gray-600 mt-2 mb-1">Supply Zones</div>
              {rec.supply_zones.map((z, i) => (
                <div key={i} className="text-gray-600 text-[10px]">
                  ₹{fmt(z.low)} – ₹{fmt(z.high)}
                  <span className="ml-1 text-gray-400">({z.score}/100 · {z.freshness})</span>
                </div>
              ))}
              {rec.supply_zones.length === 0 && <div className="text-gray-400">None</div>}
            </div>

            <div>
              <div className="font-semibold text-gray-600 mb-1">Context</div>
              <div className="space-y-0.5 text-gray-600">
                <div>ATR: {rec.atr != null ? rec.atr.toFixed(1) : '—'}</div>
                <div>RVOL: <span className={rec.rvol >= 1.5 ? 'text-green-600 font-medium' : ''}>{rec.rvol?.toFixed(1)}×</span></div>
                {rec.pct_from_52w_high != null && (
                  <div>From 52W High: {rec.pct_from_52w_high.toFixed(1)}%</div>
                )}
                {rec.pct_from_52w_low != null && (
                  <div>From 52W Low: +{rec.pct_from_52w_low.toFixed(1)}%</div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export function RecommendationsPage() {
  const queryClient = useQueryClient()
  const [setupType, setSetupType] = useState<'long' | 'short'>('long')
  const [limit, setLimit]         = useState(20)
  const [expanded, setExpanded]   = useState<string | null>(null)

  const recoQuery = useQuery({
    queryKey: ['zone-recommendations', setupType, limit],
    queryFn:  () => getZoneRecommendations({ setup_type: setupType, limit }),
    staleTime: 5 * 60 * 1000,
  })

  const mlStatusQuery = useQuery({
    queryKey: ['zones-ml-status'],
    queryFn:  getMLStatus,
    staleTime: 30 * 1000,
  })

  const trainMutation = useMutation({
    mutationFn: trainMLModel,
    onSuccess:  () => {
      queryClient.invalidateQueries({ queryKey: ['zones-ml-status'] })
      queryClient.invalidateQueries({ queryKey: ['zone-recommendations'] })
    },
  })

  const ml = mlStatusQuery.data
  const trainResult = trainMutation.data

  return (
    <div>
      {/* Top bar */}
      <div className="flex items-center gap-3 bg-white rounded-lg border border-gray-200 px-4 py-3 mb-4 shadow-sm flex-wrap">
        <span className="font-bold text-base text-gray-800">Zone Recommendations</span>
        <span className="text-xs text-gray-400">Ranked by ML confidence × zone quality × R:R × volume</span>

        {/* Setup type toggle */}
        <div className="flex gap-1 ml-2">
          {(['long', 'short'] as const).map(t => (
            <button key={t} onClick={() => setSetupType(t)}
              className={`px-3 py-1 text-xs rounded font-medium ${
                setupType === t ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
              }`}
            >
              {t === 'long' ? 'Long Setups' : 'Short Setups'}
            </button>
          ))}
        </div>

        {/* Limit */}
        <select value={limit} onChange={e => setLimit(Number(e.target.value))}
          className="border border-gray-300 rounded px-2 py-1 text-xs focus:outline-none">
          <option value={10}>Top 10</option>
          <option value={20}>Top 20</option>
          <option value={30}>Top 30</option>
          <option value={50}>Top 50</option>
        </select>

        {/* Refresh */}
        <button
          onClick={() => queryClient.invalidateQueries({ queryKey: ['zone-recommendations'] })}
          disabled={recoQuery.isFetching}
          className="px-3 py-1.5 bg-green-600 text-white text-xs rounded font-medium hover:bg-green-700 disabled:opacity-50"
        >
          {recoQuery.isFetching ? 'Loading…' : 'Refresh'}
        </button>

        {/* ML Status + Train */}
        <div className="ml-auto flex items-center gap-2">
          {ml && (
            <span className={`text-xs px-2 py-1 rounded ${ml.using_ml ? 'bg-green-100 text-green-700' : 'bg-yellow-100 text-yellow-700'}`}>
              {ml.note}
            </span>
          )}
          <button
            onClick={() => trainMutation.mutate()}
            disabled={trainMutation.isPending}
            className="px-3 py-1.5 border border-indigo-300 text-indigo-600 text-xs rounded hover:bg-indigo-50 disabled:opacity-50"
          >
            {trainMutation.isPending ? 'Training…' : 'Train ML Model'}
          </button>
        </div>
      </div>

      {/* Train result banner */}
      {trainResult && (
        <div className={`mb-4 px-4 py-2.5 rounded-lg border text-sm ${
          trainResult.trained ? 'bg-green-50 border-green-200 text-green-800' : 'bg-yellow-50 border-yellow-200 text-yellow-800'
        }`}>
          {trainResult.trained
            ? `ML model trained on ${trainResult.samples} samples · CV accuracy: ${(trainResult.cv_accuracy! * 100).toFixed(1)}% · positive rate: ${(trainResult.positive_rate! * 100).toFixed(0)}%`
            : `Not trained: ${trainResult.reason}`
          }
        </div>
      )}

      {/* Results */}
      {recoQuery.isLoading && (
        <div className="text-center py-16 text-gray-400 text-sm">Loading recommendations…</div>
      )}

      {recoQuery.isError && (
        <div className="text-center py-8 text-red-500 text-sm">
          Failed to load recommendations. Run "Recompute All" in the Zones page first.
        </div>
      )}

      {!recoQuery.isLoading && recoQuery.data?.length === 0 && (
        <div className="text-center py-16 text-gray-400 text-sm">
          No recommendations available. Run "Recompute All" in the Zones page to generate zone data.
        </div>
      )}

      <div className="space-y-2">
        {recoQuery.data?.map((rec, i) => (
          <RecoCard
            key={rec.symbol}
            rec={rec}
            rank={i + 1}
            expanded={expanded === rec.symbol}
            onExpand={() => setExpanded(expanded === rec.symbol ? null : rec.symbol)}
          />
        ))}
      </div>
    </div>
  )
}
