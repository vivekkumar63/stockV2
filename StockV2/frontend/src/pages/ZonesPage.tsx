import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import {
  analyzeZones, getZoneRankings, recomputeAll, getRecomputeStatus,
  type ZoneCard, type ZoneRankRow, type ZoneResult, type RecomputeStatus,
} from '../api/zones'

// ── Helpers ──────────────────────────────────────────────────────────────────

const POSITION_BADGE: Record<string, { bg: string; text: string; label: string }> = {
  in_demand:   { bg: 'bg-green-100',  text: 'text-green-700',  label: '✦ IN DEMAND' },
  near_demand: { bg: 'bg-yellow-100', text: 'text-yellow-700', label: '⚡ NEAR DEMAND' },
  near_supply: { bg: 'bg-orange-100', text: 'text-orange-700', label: '⚠ NEAR SUPPLY' },
  in_supply:   { bg: 'bg-red-100',    text: 'text-red-700',    label: '✦ IN SUPPLY' },
  breakout:    { bg: 'bg-blue-100',   text: 'text-blue-700',   label: '🚀 BREAKOUT' },
  neutral:     { bg: 'bg-gray-100',   text: 'text-gray-600',   label: '− NEUTRAL' },
}

const TREND_BADGE: Record<string, { bg: string; text: string }> = {
  bullish:  { bg: 'bg-green-100',  text: 'text-green-700' },
  bearish:  { bg: 'bg-red-100',    text: 'text-red-700' },
  sideways: { bg: 'bg-gray-100',   text: 'text-gray-600' },
}

const FRESHNESS_STYLE: Record<string, string> = {
  fresh:    'text-green-600',
  tested:   'text-yellow-600',
  weakened: 'text-red-500',
}

function scoreColor(s: number | null): string {
  if (s == null) return 'text-gray-400'
  if (s >= 75) return 'text-green-600 font-bold'
  if (s >= 50) return 'text-yellow-600 font-semibold'
  return 'text-red-500'
}

function SourceTag({ tag }: { tag: string }) {
  return (
    <span className="inline-block px-1.5 py-0.5 rounded text-[10px] bg-blue-50 text-blue-700 border border-blue-100 mr-1 mb-0.5">
      {tag}
    </span>
  )
}

// ── Zone Card ─────────────────────────────────────────────────────────────────

function ZoneCardUI({ zone, type }: { zone: ZoneCard; type: 'demand' | 'supply' }) {
  const borderColor = type === 'demand' ? 'border-l-green-500' : 'border-l-red-500'
  const priceColor  = type === 'demand' ? 'text-green-700' : 'text-red-700'
  const badgeBg     = type === 'demand' ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'
  return (
    <div className={`bg-white rounded-md border border-gray-100 border-l-4 ${borderColor} p-3 mb-2`}>
      <div className="flex items-center justify-between mb-1">
        <span className={`font-bold text-sm ${priceColor}`}>
          ₹{zone.low.toLocaleString('en-IN', { maximumFractionDigits: 0 })} –{' '}
          ₹{zone.high.toLocaleString('en-IN', { maximumFractionDigits: 0 })}
        </span>
        <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${badgeBg}`}>
          {zone.score}/100
        </span>
      </div>
      <div className="text-xs text-gray-500 mb-1.5">
        <span className={FRESHNESS_STYLE[zone.freshness] || 'text-gray-500'}>
          {zone.freshness.charAt(0).toUpperCase() + zone.freshness.slice(1)}
        </span>
        {zone.touch_count > 0 && ` · ${zone.touch_count} touch${zone.touch_count > 1 ? 'es' : ''}`}
        {zone.last_reaction_pct > 0 && ` · Last ${zone.last_reaction_pct.toFixed(1)}%`}
      </div>
      <div className="flex flex-wrap">
        {zone.source_tags.map(t => <SourceTag key={t} tag={t} />)}
      </div>
    </div>
  )
}

// ── Analysis Panel ─────────────────────────────────────────────────────────────

function AnalysisPanel({ result }: { result: ZoneResult }) {
  const [showShort, setShowShort] = useState(false)
  const posTag   = POSITION_BADGE[result.position_tag] ?? POSITION_BADGE.neutral
  const trendTag = TREND_BADGE[result.market_structure] ?? TREND_BADGE.sideways

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4 mb-4">
      {/* Market structure strip */}
      <div className="flex flex-wrap items-center gap-3 px-3 py-2 bg-gray-50 rounded-md mb-4 text-sm">
        <span className="font-bold text-base">{result.symbol}</span>
        <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${trendTag.bg} ${trendTag.text}`}>
          {result.market_structure.toUpperCase()} TREND
        </span>
        <span>Price <b>₹{result.price.toLocaleString('en-IN', { maximumFractionDigits: 0 })}</b></span>
        <span>ATR <b>{result.atr.toFixed(1)}</b></span>
        <span>RVol <b className={result.rvol >= 1.5 ? 'text-green-600' : ''}>{result.rvol.toFixed(1)}×</b></span>
        <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${posTag.bg} ${posTag.text}`}>
          {posTag.label}
        </span>
      </div>

      {/* Three-column layout */}
      <div className="grid grid-cols-3 gap-3">
        {/* Demand zones */}
        <div className="bg-green-50 border border-green-100 rounded-md p-3">
          <div className="text-xs font-bold text-green-700 mb-2">⬇ DEMAND ZONES ({result.demand_zones.length})</div>
          {result.demand_zones.length === 0 && (
            <div className="text-xs text-gray-400">No demand zones detected</div>
          )}
          {result.demand_zones.map(z => <ZoneCardUI key={`${z.low}-${z.high}`} zone={z} type="demand" />)}
        </div>

        {/* Supply zones */}
        <div className="bg-red-50 border border-red-100 rounded-md p-3">
          <div className="text-xs font-bold text-red-700 mb-2">⬆ SUPPLY ZONES ({result.supply_zones.length})</div>
          {result.supply_zones.length === 0 && (
            <div className="text-xs text-gray-400">No supply zones detected</div>
          )}
          {result.supply_zones.map(z => <ZoneCardUI key={`${z.low}-${z.high}`} zone={z} type="supply" />)}
        </div>

        {/* Setup panel */}
        <div className="bg-blue-50 border border-blue-100 rounded-md p-3">
          {result.long_setup ? (
            <>
              <div className="text-xs font-bold text-blue-700 mb-3">
                🎯 LONG SETUP — {result.long_setup.score}/100
              </div>
              <div className="grid grid-cols-2 gap-x-2 gap-y-1 text-xs mb-3">
                <span className="text-gray-500">Ideal Entry</span>
                <span className="font-semibold">₹{result.long_setup.ideal_entry.toLocaleString('en-IN', { maximumFractionDigits: 0 })}</span>
                <span className="text-gray-500">Aggressive</span>
                <span>₹{result.long_setup.aggressive_entry.toLocaleString('en-IN', { maximumFractionDigits: 0 })}</span>
                <span className="text-gray-500">Conservative</span>
                <span>₹{result.long_setup.conservative_entry.toLocaleString('en-IN', { maximumFractionDigits: 0 })}</span>
                <span className="text-red-500">Stop Loss</span>
                <span className="text-red-600 font-semibold">₹{result.long_setup.stop_loss.toLocaleString('en-IN', { maximumFractionDigits: 0 })}</span>
                <span className="text-green-600">Target 1</span>
                <span className="text-green-700 font-semibold">₹{result.long_setup.t1.toLocaleString('en-IN', { maximumFractionDigits: 0 })} · 1:{result.long_setup.t1_rr}</span>
                <span className="text-green-600">Target 2</span>
                <span className="text-green-700">₹{result.long_setup.t2.toLocaleString('en-IN', { maximumFractionDigits: 0 })} · 1:{result.long_setup.t2_rr}</span>
                <span className="text-green-600">Target 3</span>
                <span className="text-green-700">₹{result.long_setup.t3.toLocaleString('en-IN', { maximumFractionDigits: 0 })} · 1:{result.long_setup.t3_rr}</span>
              </div>
              <div className="text-[10px] text-gray-600 bg-white border border-blue-100 rounded p-2 leading-relaxed mb-2">
                {result.long_setup.explanation}
              </div>
              <div className="text-[10px] text-red-600">{result.long_setup.invalidation}</div>
            </>
          ) : (
            <div className="text-xs text-gray-400">No demand zones — long setup unavailable</div>
          )}

          {result.short_setup && (
            <div className="border-t border-blue-100 mt-3 pt-3">
              <button
                onClick={() => setShowShort(v => !v)}
                className="text-xs font-bold text-purple-700 mb-2 w-full text-left"
              >
                ⬇ SHORT SETUP — {result.short_setup.score}/100 {showShort ? '▲' : '▼'}
              </button>
              {showShort && (
                <div className="text-xs text-gray-700">
                  Entry ₹{result.short_setup.ideal_entry.toLocaleString('en-IN', { maximumFractionDigits: 0 })} ·{' '}
                  SL ₹{result.short_setup.stop_loss.toLocaleString('en-IN', { maximumFractionDigits: 0 })} ·{' '}
                  T1 ₹{result.short_setup.t1.toLocaleString('en-IN', { maximumFractionDigits: 0 })} · R:R 1:{result.short_setup.t1_rr}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Ranking row ───────────────────────────────────────────────────────────────

function RankRow({
  row, onSelect, isSelected,
}: { row: ZoneRankRow; onSelect: (sym: string) => void; isSelected: boolean }) {
  const posStyle = POSITION_BADGE[row.position_tag] ?? POSITION_BADGE.neutral
  return (
    <div
      className={`border-b border-gray-100 cursor-pointer hover:bg-gray-50 ${isSelected ? 'bg-blue-50 border-l-2 border-l-blue-500' : ''}`}
    >
      <div
        className="grid gap-1 px-3 py-2 text-xs"
        style={{ gridTemplateColumns: '28px 80px 55px 100px 70px 55px 55px 50px 50px 70px' }}
        onClick={() => onSelect(row.symbol)}
      >
        <span className="text-gray-400">{row.rank}</span>
        <span className={`font-bold ${isSelected ? 'text-blue-600' : ''}`}>{row.symbol} {isSelected ? '▼' : '▶'}</span>
        <span className={scoreColor(row.long_setup_score)}>{row.long_setup_score ?? '—'}</span>
        <span className={`px-1.5 py-0.5 rounded-full text-[10px] font-medium ${posStyle.bg} ${posStyle.text}`}>
          {posStyle.label}
        </span>
        <span className={scoreColor(row.short_setup_score)}>
          {row.short_setup_score != null ? `S:${row.short_setup_score}` : '—'}
        </span>
        <span className={scoreColor(row.best_demand_score)}>{row.best_demand_score ?? '—'}</span>
        <span className={scoreColor(row.best_supply_score)}>{row.best_supply_score ?? '—'}</span>
        <span>{row.atr?.toFixed(1) ?? '—'}</span>
        <span className={row.rvol >= 1.5 ? 'text-green-600 font-medium' : ''}>{row.rvol?.toFixed(1) ?? '—'}×</span>
        <span className="text-gray-400">{row.computed_at ? new Date(row.computed_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '—'}</span>
      </div>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

type SortKey = 'long_score' | 'short_score' | 'demand_score' | 'supply_score' | 'rvol' | 'atr'
type FilterKey = '' | 'long' | 'short' | 'in_demand' | 'breakout' | 'near_supply'

const FILTERS: { key: FilterKey; label: string }[] = [
  { key: 'long',        label: 'Long' },
  { key: 'short',       label: 'Short' },
  { key: 'in_demand',   label: 'In Demand' },
  { key: 'breakout',    label: 'Breakout' },
  { key: 'near_supply', label: 'Near Supply' },
]

const SORTS: { key: SortKey; label: string }[] = [
  { key: 'long_score',   label: 'Long Score' },
  { key: 'short_score',  label: 'Short Score' },
  { key: 'demand_score', label: 'Demand' },
  { key: 'supply_score', label: 'Supply' },
  { key: 'rvol',         label: 'RVol' },
  { key: 'atr',          label: 'ATR' },
]

export function ZonesPage() {
  const [symbol, setSymbol]     = useState('')
  const [activeSymbol, setActiveSymbol] = useState<string | null>(null)
  const [sortBy, setSortBy]     = useState<SortKey>('long_score')
  const [filterBy, setFilterBy] = useState<FilterKey>('')
  const [expandedSym, setExpandedSym] = useState<string | null>(null)

  const analyzeQuery = useQuery({
    queryKey: ['zone-analyze', activeSymbol],
    queryFn: () => analyzeZones(activeSymbol!),
    enabled: !!activeSymbol,
  })

  const rankingsQuery = useQuery({
    queryKey: ['zone-rankings', sortBy, filterBy],
    queryFn: () => getZoneRankings({ sort_by: sortBy, tag_filter: filterBy || undefined }),
    staleTime: 5 * 60 * 1000,
  })

  const statusQuery = useQuery({
    queryKey: ['zone-recompute-status'],
    queryFn: getRecomputeStatus,
    refetchInterval: (query) => (query.state.data as RecomputeStatus | undefined)?.is_running ? 3000 : false,
  })

  const recomputeMut = useMutation({ mutationFn: recomputeAll })

  const handleAnalyze = () => {
    const sym = symbol.trim().toUpperCase()
    if (sym) { setActiveSymbol(sym); setExpandedSym(sym) }
  }

  const handleRowClick = (sym: string) => {
    if (expandedSym === sym) {
      setExpandedSym(null)
    } else {
      setExpandedSym(sym)
      setActiveSymbol(sym)
    }
  }

  const status = statusQuery.data
  const lastBatch = status?.finished
    ? `Last batch: just now · ${status.total} stocks`
    : status?.is_running
      ? `Recomputing… ${status.done}/${status.total}`
      : status?.started_at
        ? `Last batch: ${new Date(status.started_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`
        : 'No batch run yet'

  return (
    <div>
      {/* Top bar */}
      <div className="flex items-center gap-3 bg-white rounded-lg border border-gray-200 px-4 py-3 mb-4 shadow-sm">
        <span className="font-bold text-base text-gray-800">Demand &amp; Supply Zones</span>
        <input
          className="flex-1 ml-4 border border-gray-300 rounded px-3 py-1.5 text-sm focus:outline-none focus:border-blue-400"
          placeholder="Symbol… RELIANCE"
          value={symbol}
          onChange={e => setSymbol(e.target.value.toUpperCase())}
          onKeyDown={e => e.key === 'Enter' && handleAnalyze()}
        />
        <button
          onClick={handleAnalyze}
          disabled={analyzeQuery.isFetching}
          className="px-4 py-1.5 bg-green-600 text-white text-sm rounded font-medium hover:bg-green-700 disabled:opacity-50"
        >
          {analyzeQuery.isFetching ? 'Analyzing…' : 'Analyze'}
        </button>
        <span className="text-xs text-gray-400 whitespace-nowrap">{lastBatch}</span>
        <button
          onClick={() => recomputeMut.mutate()}
          disabled={status?.is_running || recomputeMut.isPending}
          className="px-3 py-1.5 bg-indigo-600 text-white text-xs rounded font-medium hover:bg-indigo-700 disabled:opacity-50 whitespace-nowrap"
        >
          ⟳ Recompute All
        </button>
      </div>

      {/* Analysis panel */}
      {analyzeQuery.data && <AnalysisPanel result={analyzeQuery.data} />}
      {analyzeQuery.isError && (
        <div className="text-red-600 text-sm mb-4 bg-red-50 border border-red-200 rounded p-3">
          Failed to analyze {activeSymbol}: {(analyzeQuery.error as Error)?.message}
        </div>
      )}

      {/* Rankings table */}
      <div className="bg-white rounded-lg border border-gray-200 shadow-sm">
        <div className="flex items-center gap-2 px-4 py-3 border-b border-gray-100">
          <span className="font-bold text-sm">All Stocks Ranking</span>
          <span className="text-xs text-gray-400">
            {rankingsQuery.data?.length ?? 0} stocks
          </span>
          <div className="ml-auto flex items-center gap-2">
            {/* Filter chips */}
            {FILTERS.map(f => (
              <button
                key={f.key}
                onClick={() => setFilterBy(filterBy === f.key ? '' : f.key)}
                className={`px-2.5 py-1 rounded-full text-xs font-medium border transition-colors ${
                  filterBy === f.key
                    ? 'bg-blue-600 text-white border-blue-600'
                    : 'bg-white text-gray-600 border-gray-300 hover:border-blue-400'
                }`}
              >
                {f.label}
              </button>
            ))}
            {/* Sort select */}
            <select
              value={sortBy}
              onChange={e => setSortBy(e.target.value as SortKey)}
              className="border border-gray-300 rounded text-xs px-2 py-1 ml-2 focus:outline-none"
            >
              {SORTS.map(s => <option key={s.key} value={s.key}>{s.label}</option>)}
            </select>
          </div>
        </div>

        {/* Table header */}
        <div
          className="grid gap-1 px-3 py-2 bg-gray-50 text-xs font-bold text-gray-500 border-b border-gray-100"
          style={{ gridTemplateColumns: '28px 80px 55px 100px 70px 55px 55px 50px 50px 70px' }}
        >
          <span>#</span>
          <span>Symbol</span>
          <span>Score</span>
          <span>Position</span>
          <span>Setup</span>
          <span>Demand</span>
          <span>Supply</span>
          <span>ATR</span>
          <span>RVol</span>
          <span>Computed</span>
        </div>

        {rankingsQuery.isLoading && (
          <div className="text-center py-8 text-gray-400 text-sm">Loading rankings…</div>
        )}

        {rankingsQuery.data?.map(row => (
          <div key={row.symbol}>
            <RankRow
              row={row}
              onSelect={handleRowClick}
              isSelected={expandedSym === row.symbol}
            />
            {expandedSym === row.symbol && analyzeQuery.data?.symbol === row.symbol && (
              <div className="bg-blue-50 px-4 py-2.5 text-xs text-gray-700 border-b border-blue-100">
                <span className="font-semibold">Demand:</span>{' '}
                {analyzeQuery.data.demand_zones.slice(0, 2).map(
                  z => `₹${z.low.toLocaleString('en-IN', { maximumFractionDigits: 0 })}–₹${z.high.toLocaleString('en-IN', { maximumFractionDigits: 0 })} (${z.score})`
                ).join(' · ')}
                {' '}|{' '}
                <span className="font-semibold">Supply:</span>{' '}
                {analyzeQuery.data.supply_zones.slice(0, 2).map(
                  z => `₹${z.low.toLocaleString('en-IN', { maximumFractionDigits: 0 })}–₹${z.high.toLocaleString('en-IN', { maximumFractionDigits: 0 })} (${z.score})`
                ).join(' · ')}
                {analyzeQuery.data.long_setup && (
                  <>{' '}|{' '}<span className="font-semibold">Long:</span> Entry ₹{analyzeQuery.data.long_setup.ideal_entry.toLocaleString('en-IN', { maximumFractionDigits: 0 })} · SL ₹{analyzeQuery.data.long_setup.stop_loss.toLocaleString('en-IN', { maximumFractionDigits: 0 })} · T1 ₹{analyzeQuery.data.long_setup.t1.toLocaleString('en-IN', { maximumFractionDigits: 0 })} · R:R 1:{analyzeQuery.data.long_setup.t1_rr}</>
                )}
                {' '}
                <button
                  className={`underline ml-1 ${analyzeQuery.isFetching && activeSymbol === row.symbol ? 'text-gray-400 cursor-wait' : 'text-blue-600 hover:text-blue-800'}`}
                  onClick={() => {
                    setActiveSymbol(row.symbol)
                    if (analyzeQuery.data?.symbol === row.symbol) {
                      window.scrollTo({ top: 0, behavior: 'smooth' })
                    }
                  }}
                >
                  {analyzeQuery.isFetching && activeSymbol === row.symbol ? 'Loading…' : 'View full analysis ↑'}
                </button>
              </div>
            )}
          </div>
        ))}

        {rankingsQuery.data?.length === 0 && !rankingsQuery.isLoading && (
          <div className="text-center py-8 text-gray-400 text-sm">
            No zone data for today. Click "Recompute All" to generate.
          </div>
        )}
      </div>
    </div>
  )
}
