import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  analyzeZones, getZoneRankings, recomputeAll, getRecomputeStatus,
  getChartData, runBacktest, getBacktestResults, getBacktestTrades,
  type ZoneCard, type ZoneRankRow, type ZoneResult, type RecomputeStatus,
  type BacktestResult, type BacktestTrade,
} from '../api/zones'
import { PriceChart } from '../components/PriceChart'

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

const EXIT_BADGE: Record<string, string> = {
  supply_zone:   'bg-green-100 text-green-700',
  stop_loss:     'bg-red-100 text-red-700',
  max_hold:      'bg-yellow-100 text-yellow-700',
  end_of_period: 'bg-gray-100 text-gray-600',
}

function scoreColor(s: number | null): string {
  if (s == null) return 'text-gray-400'
  if (s >= 75) return 'text-green-600 font-bold'
  if (s >= 50) return 'text-yellow-600 font-semibold'
  return 'text-red-500'
}

function SourceTag({ tag }: { tag: string }) {
  const isVwap = tag === 'vwap'
  return (
    <span className={`inline-block px-1.5 py-0.5 rounded text-[10px] border mr-1 mb-0.5 ${
      isVwap ? 'bg-purple-50 text-purple-700 border-purple-100' : 'bg-blue-50 text-blue-700 border-blue-100'
    }`}>
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
        <div className="flex items-center gap-1">
          {zone.source === 'vwap' && (
            <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-full bg-purple-100 text-purple-700">VWAP</span>
          )}
          <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${badgeBg}`}>{zone.score}/100</span>
        </div>
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
    <div className="h-full overflow-y-auto">
      {/* Market structure strip */}
      <div className="flex flex-wrap items-center gap-2 px-3 py-2 bg-gray-50 rounded-md mb-3 text-xs">
        <span className="font-bold text-sm">{result.symbol}</span>
        <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${trendTag.bg} ${trendTag.text}`}>
          {result.market_structure.toUpperCase()}
        </span>
        <span>₹{result.price.toLocaleString('en-IN', { maximumFractionDigits: 0 })}</span>
        <span>ATR {result.atr.toFixed(1)}</span>
        <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${posTag.bg} ${posTag.text}`}>
          {posTag.label}
        </span>
      </div>

      {/* Demand zones */}
      <div className="bg-green-50 border border-green-100 rounded-md p-3 mb-2">
        <div className="text-xs font-bold text-green-700 mb-2">⬇ DEMAND ({result.demand_zones.length})</div>
        {result.demand_zones.length === 0
          ? <div className="text-xs text-gray-400">None</div>
          : result.demand_zones.map(z => <ZoneCardUI key={`${z.low}-${z.high}`} zone={z} type="demand" />)
        }
      </div>

      {/* Supply zones */}
      <div className="bg-red-50 border border-red-100 rounded-md p-3 mb-2">
        <div className="text-xs font-bold text-red-700 mb-2">⬆ SUPPLY ({result.supply_zones.length})</div>
        {result.supply_zones.length === 0
          ? <div className="text-xs text-gray-400">None</div>
          : result.supply_zones.map(z => <ZoneCardUI key={`${z.low}-${z.high}`} zone={z} type="supply" />)
        }
      </div>

      {/* Setup panel */}
      <div className="bg-blue-50 border border-blue-100 rounded-md p-3">
        {result.long_setup ? (
          <>
            <div className="text-xs font-bold text-blue-700 mb-2">🎯 LONG — {result.long_setup.score}/100</div>
            <div className="grid grid-cols-2 gap-x-2 gap-y-1 text-xs mb-2">
              <span className="text-gray-500">Ideal Entry</span>
              <span className="font-semibold">₹{result.long_setup.ideal_entry.toLocaleString('en-IN', { maximumFractionDigits: 0 })}</span>
              <span className="text-red-500">Stop Loss</span>
              <span className="text-red-600 font-semibold">₹{result.long_setup.stop_loss.toLocaleString('en-IN', { maximumFractionDigits: 0 })}</span>
              <span className="text-green-600">Target 1</span>
              <span className="text-green-700 font-semibold">₹{result.long_setup.t1.toLocaleString('en-IN', { maximumFractionDigits: 0 })} · 1:{result.long_setup.t1_rr}</span>
              <span className="text-green-600">Target 2</span>
              <span className="text-green-700">₹{result.long_setup.t2.toLocaleString('en-IN', { maximumFractionDigits: 0 })} · 1:{result.long_setup.t2_rr}</span>
            </div>
            <div className="text-[10px] text-gray-600 bg-white border border-blue-100 rounded p-2 leading-relaxed mb-2">
              {result.long_setup.explanation}
            </div>
            <div className="text-[10px] text-red-600">{result.long_setup.invalidation}</div>
          </>
        ) : (
          <div className="text-xs text-gray-400">No long setup</div>
        )}
        {result.short_setup && (
          <div className="border-t border-blue-100 mt-2 pt-2">
            <button onClick={() => setShowShort(v => !v)} className="text-xs font-bold text-purple-700 w-full text-left">
              ⬇ SHORT — {result.short_setup.score}/100 {showShort ? '▲' : '▼'}
            </button>
            {showShort && (
              <div className="text-xs text-gray-700 mt-1">
                Entry ₹{result.short_setup.ideal_entry.toLocaleString('en-IN', { maximumFractionDigits: 0 })} ·{' '}
                SL ₹{result.short_setup.stop_loss.toLocaleString('en-IN', { maximumFractionDigits: 0 })} ·{' '}
                T1 ₹{result.short_setup.t1.toLocaleString('en-IN', { maximumFractionDigits: 0 })} · R:R 1:{result.short_setup.t1_rr}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

// ── Rank Row ──────────────────────────────────────────────────────────────────

const COL_GRID = '28px 72px 50px 95px 60px 50px 50px 45px 45px 62px 62px 62px'

function distColor(v: number | null, isLong: boolean) {
  if (v == null) return 'text-gray-400'
  // long: negative = price below entry (close/in zone), near-zero = at entry, positive = above entry (wait for pullback)
  // short: positive = price above entry (wait for rally), negative = below entry (close/in zone)
  const abs = Math.abs(v)
  if (abs <= 1) return 'text-green-600 font-semibold'
  if (abs <= 3) return 'text-yellow-600'
  return 'text-gray-500'
}

function w52Color(pct: number | null, isHigh: boolean) {
  if (pct == null) return 'text-gray-400'
  if (isHigh && pct >= -3) return 'text-purple-600 font-semibold'
  if (!isHigh && pct <= 3) return 'text-teal-600 font-semibold'
  return 'text-gray-500'
}

function RankRow({
  row, onSelect, isSelected,
}: { row: ZoneRankRow; onSelect: (sym: string) => void; isSelected: boolean }) {
  const posStyle = POSITION_BADGE[row.position_tag] ?? POSITION_BADGE.neutral
  return (
    <div className={`border-b border-gray-100 cursor-pointer hover:bg-gray-50 ${isSelected ? 'bg-blue-50 border-l-2 border-l-blue-500' : ''}`}>
      <div
        className="grid gap-1 px-3 py-2 text-xs"
        style={{ gridTemplateColumns: COL_GRID }}
        onClick={() => onSelect(row.symbol)}
      >
        <span className="text-gray-400">{row.rank}</span>
        <span className={`font-bold ${isSelected ? 'text-blue-600' : ''}`}>{row.symbol} {isSelected ? '▼' : '▶'}</span>
        <span className={scoreColor(row.long_setup_score)}>{row.long_setup_score ?? '—'}</span>
        <span className={`px-1.5 py-0.5 rounded-full text-[10px] font-medium ${posStyle.bg} ${posStyle.text}`}>{posStyle.label}</span>
        <span className={scoreColor(row.short_setup_score)}>{row.short_setup_score != null ? `S:${row.short_setup_score}` : '—'}</span>
        <span className={scoreColor(row.best_demand_score)}>{row.best_demand_score ?? '—'}</span>
        <span className={scoreColor(row.best_supply_score)}>{row.best_supply_score ?? '—'}</span>
        <span className={row.rvol >= 1.5 ? 'text-green-600 font-medium' : ''}>{row.rvol?.toFixed(1) ?? '—'}×</span>
        <span className={distColor(row.dist_to_long, true)} title="% from long entry (–=below entry, +=above)">
          {row.dist_to_long != null ? `${row.dist_to_long > 0 ? '+' : ''}${row.dist_to_long}%` : '—'}
        </span>
        <span className={w52Color(row.pct_from_52w_high, true)} title="% below 52W high (–=below)">
          {row.pct_from_52w_high != null ? `${row.pct_from_52w_high > 0 ? '+' : ''}${row.pct_from_52w_high}%` : '—'}
        </span>
        <span className={w52Color(row.pct_from_52w_low, false)} title="% above 52W low (+= above)">
          {row.pct_from_52w_low != null ? `+${row.pct_from_52w_low}%` : '—'}
        </span>
        <span className="text-gray-400">{row.computed_at ? new Date(row.computed_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '—'}</span>
      </div>
    </div>
  )
}

// ── Backtest Tab ──────────────────────────────────────────────────────────────

function BacktestTab() {
  const [btSymbol, setBtSymbol]   = useState('')
  const [fromDate, setFromDate]   = useState('2022-01-01')
  const [toDate, setToDate]       = useState(new Date().toISOString().slice(0, 10))
  const [selectedResult, setSelectedResult] = useState<BacktestResult | null>(null)
  const queryClient = useQueryClient()

  const btMutation = useMutation({
    mutationFn: runBacktest,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['zone-bt-results'] })
    },
  })

  const resultsQuery = useQuery({
    queryKey: ['zone-bt-results', btSymbol],
    queryFn:  () => getBacktestResults(btSymbol),
    enabled:  btSymbol.length > 0,
  })

  const tradesQuery = useQuery({
    queryKey: ['zone-bt-trades', selectedResult?.id],
    queryFn:  () => getBacktestTrades(selectedResult!.id),
    enabled:  !!selectedResult,
  })

  const handleRun = () => {
    if (!btSymbol.trim()) return
    btMutation.mutate({ symbol: btSymbol.trim().toUpperCase(), from_date: fromDate, to_date: toDate })
  }

  const result = btMutation.data

  return (
    <div>
      {/* Form */}
      <div className="flex items-center gap-3 bg-white rounded-lg border border-gray-200 px-4 py-3 mb-4 shadow-sm">
        <input
          className="border border-gray-300 rounded px-3 py-1.5 text-sm w-28 focus:outline-none focus:border-blue-400"
          placeholder="Symbol"
          value={btSymbol}
          onChange={e => setBtSymbol(e.target.value.toUpperCase())}
        />
        <input type="date" value={fromDate} onChange={e => setFromDate(e.target.value)}
          className="border border-gray-300 rounded px-2 py-1.5 text-sm focus:outline-none" />
        <span className="text-gray-400 text-sm">→</span>
        <input type="date" value={toDate} onChange={e => setToDate(e.target.value)}
          className="border border-gray-300 rounded px-2 py-1.5 text-sm focus:outline-none" />
        <button
          onClick={handleRun}
          disabled={btMutation.isPending || !btSymbol.trim()}
          className="px-4 py-1.5 bg-indigo-600 text-white text-sm rounded font-medium hover:bg-indigo-700 disabled:opacity-50"
        >
          {btMutation.isPending ? 'Simulating…' : 'Run Backtest'}
        </button>
      </div>

      {/* Latest result summary */}
      {result && (
        <div className="bg-white rounded-lg border border-gray-200 p-4 mb-4 shadow-sm">
          <div className="text-sm font-bold text-gray-700 mb-2">{result.symbol} · {result.from_date} → {result.to_date}</div>
          <div className="grid grid-cols-4 gap-4 text-center">
            <div><div className="text-2xl font-bold text-gray-800">{result.total_trades}</div><div className="text-xs text-gray-500">Trades</div></div>
            <div><div className={`text-2xl font-bold ${result.win_rate != null && result.win_rate >= 50 ? 'text-green-600' : 'text-red-600'}`}>{result.win_rate != null ? `${result.win_rate}%` : '—'}</div><div className="text-xs text-gray-500">Win Rate</div></div>
            <div><div className={`text-2xl font-bold ${result.total_pnl_pct >= 0 ? 'text-green-600' : 'text-red-600'}`}>{result.total_pnl_pct >= 0 ? '+' : ''}{result.total_pnl_pct.toFixed(1)}%</div><div className="text-xs text-gray-500">Total PnL</div></div>
            <div><div className="text-2xl font-bold text-gray-800">{result.avg_hold_days != null ? result.avg_hold_days.toFixed(1) : '—'}</div><div className="text-xs text-gray-500">Avg Days</div></div>
          </div>
        </div>
      )}

      {/* Past results + trade table */}
      {btSymbol && (
        <div className="bg-white rounded-lg border border-gray-200 shadow-sm">
          <div className="px-4 py-3 border-b border-gray-100 text-sm font-bold text-gray-700">
            Past Backtests — {btSymbol}
          </div>
          {resultsQuery.data?.map(r => (
            <div key={r.id}>
              <div
                className={`grid gap-2 px-4 py-2 text-xs cursor-pointer hover:bg-gray-50 border-b border-gray-100 ${selectedResult?.id === r.id ? 'bg-blue-50' : ''}`}
                style={{ gridTemplateColumns: '120px 80px 60px 80px 80px' }}
                onClick={() => setSelectedResult(selectedResult?.id === r.id ? null : r)}
              >
                <span>{r.from_date} → {r.to_date}</span>
                <span>{r.total_trades} trades</span>
                <span className={r.win_rate != null && r.win_rate >= 50 ? 'text-green-600 font-medium' : 'text-red-600'}>{r.win_rate != null ? `${r.win_rate}%` : '—'} WR</span>
                <span className={r.total_pnl_pct >= 0 ? 'text-green-600' : 'text-red-600'}>{r.total_pnl_pct >= 0 ? '+' : ''}{r.total_pnl_pct.toFixed(1)}%</span>
                <span className="text-gray-400">{new Date(r.ran_at).toLocaleDateString()}</span>
              </div>
              {selectedResult?.id === r.id && tradesQuery.data && (
                <div className="bg-blue-50 px-4 py-3 border-b border-blue-100">
                  <div className="grid gap-1 mb-1 text-[10px] font-bold text-gray-500" style={{ gridTemplateColumns: '90px 90px 75px 60px 70px 80px' }}>
                    <span>Entry</span><span>Exit</span><span>Prices</span><span>PnL%</span><span>Days</span><span>Reason</span>
                  </div>
                  {tradesQuery.data.map((t: BacktestTrade) => (
                    <div key={t.id} className="grid gap-1 text-xs py-0.5" style={{ gridTemplateColumns: '90px 90px 75px 60px 70px 80px' }}>
                      <span>{t.entry_date}</span>
                      <span>{t.exit_date ?? '—'}</span>
                      <span>₹{t.entry_price?.toLocaleString('en-IN', { maximumFractionDigits: 0 })} → ₹{t.exit_price?.toLocaleString('en-IN', { maximumFractionDigits: 0 }) ?? '—'}</span>
                      <span className={t.pnl_pct != null && t.pnl_pct >= 0 ? 'text-green-600 font-medium' : 'text-red-600'}>{t.pnl_pct != null ? `${t.pnl_pct >= 0 ? '+' : ''}${t.pnl_pct.toFixed(1)}%` : '—'}</span>
                      <span>{t.hold_days ?? '—'}d</span>
                      <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${EXIT_BADGE[t.exit_reason] ?? 'bg-gray-100 text-gray-600'}`}>{t.exit_reason}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
          {resultsQuery.data?.length === 0 && (
            <div className="text-center py-8 text-gray-400 text-sm">No backtests run for {btSymbol} yet.</div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

type SortKey = 'long_score' | 'short_score' | 'demand_score' | 'supply_score' | 'rvol' | 'atr' | 'dist_long' | 'dist_short' | 'near_52w_high' | 'near_52w_low'
type FilterKey = '' | 'long' | 'short' | 'in_demand' | 'breakout' | 'near_supply' | 'near_52w_high' | 'near_52w_low'

const FILTERS: { key: FilterKey; label: string }[] = [
  { key: 'long',          label: 'Long' },
  { key: 'short',         label: 'Short' },
  { key: 'in_demand',     label: 'In Demand' },
  { key: 'breakout',      label: 'Breakout' },
  { key: 'near_supply',   label: 'Near Supply' },
  { key: 'near_52w_high', label: '52W High' },
  { key: 'near_52w_low',  label: '52W Low' },
]

export function ZonesPage() {
  const [symbol, setSymbol]             = useState('')
  const [activeSymbol, setActiveSymbol] = useState<string | null>(null)
  const [sortBy, setSortBy]             = useState<SortKey>('long_score')
  const [filterBy, setFilterBy]         = useState<FilterKey>('')
  const [expandedSym, setExpandedSym]   = useState<string | null>(null)
  const [activeTab, setActiveTab]       = useState<'rankings' | 'backtest'>('rankings')

  const analyzeQuery = useQuery({
    queryKey: ['zone-analyze', activeSymbol],
    queryFn:  () => analyzeZones(activeSymbol!),
    enabled:  !!activeSymbol,
  })

  const chartQuery = useQuery({
    queryKey: ['zone-chart', activeSymbol],
    queryFn:  () => getChartData(activeSymbol!),
    enabled:  !!activeSymbol,
    staleTime: 60 * 1000,
  })

  const rankingsQuery = useQuery({
    queryKey: ['zone-rankings', sortBy, filterBy],
    queryFn:  () => getZoneRankings({ sort_by: sortBy, tag_filter: filterBy || undefined }),
    staleTime: 5 * 60 * 1000,
  })

  const statusQuery = useQuery({
    queryKey: ['zone-recompute-status'],
    queryFn:  getRecomputeStatus,
    refetchInterval: (query) =>
      (query.state.data as RecomputeStatus | undefined)?.is_running ? 3000 : false,
  })

  const recomputeMut = useMutation({
    mutationFn: recomputeAll,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['zone-rankings'] }),
  })

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

  const showChart = !!analyzeQuery.data && !!chartQuery.data

  return (
    <div>
      {/* Top bar */}
      <div className="flex items-center gap-3 bg-white rounded-lg border border-gray-200 px-4 py-3 mb-4 shadow-sm">
        <span className="font-bold text-base text-gray-800">Demand &amp; Supply Zones</span>
        {/* Tab buttons */}
        <div className="flex gap-1 ml-2">
          {(['rankings', 'backtest'] as const).map(tab => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-3 py-1 text-xs rounded font-medium ${
                activeTab === tab
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
              }`}
            >
              {tab.charAt(0).toUpperCase() + tab.slice(1)}
            </button>
          ))}
        </div>
        {activeTab === 'rankings' && (
          <>
            <input
              className="flex-1 ml-2 border border-gray-300 rounded px-3 py-1.5 text-sm focus:outline-none focus:border-blue-400"
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
          </>
        )}
      </div>

      {activeTab === 'backtest' && <BacktestTab />}

      {activeTab === 'rankings' && (
        <>
          {analyzeQuery.isError && (
            <div className="text-red-600 text-sm mb-4 bg-red-50 border border-red-200 rounded p-3">
              Failed to analyze {activeSymbol}: {(analyzeQuery.error as Error)?.message}
            </div>
          )}

          {/* Chart + Analysis panel (layout B: 2/3 + 1/3) */}
          {showChart && (
            <div className="grid gap-4 mb-4" style={{ gridTemplateColumns: '2fr 1fr' }}>
              <div className="bg-white rounded-lg border border-gray-200 overflow-hidden shadow-sm">
                <PriceChart
                  ohlcv={chartQuery.data!.ohlcv}
                  demandBands={chartQuery.data!.demand_bands}
                  supplyBands={chartQuery.data!.supply_bands}
                  longSetup={chartQuery.data!.long_setup}
                  shortSetup={chartQuery.data!.short_setup}
                  height={420}
                />
              </div>
              <div className="bg-white rounded-lg border border-gray-200 p-3 shadow-sm">
                <AnalysisPanel result={analyzeQuery.data!} />
              </div>
            </div>
          )}

          {/* Rankings table */}
          <div className="bg-white rounded-lg border border-gray-200 shadow-sm">
            <div className="flex items-center gap-2 px-4 py-3 border-b border-gray-100">
              <span className="font-bold text-sm">All Stocks Ranking</span>
              <span className="text-xs text-gray-400">{rankingsQuery.data?.length ?? 0} stocks</span>
              <div className="ml-auto flex items-center gap-1.5 flex-wrap">
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
              </div>
            </div>

            <div
              className="grid gap-1 px-3 py-2 bg-gray-50 text-xs font-bold text-gray-500 border-b border-gray-100"
              style={{ gridTemplateColumns: COL_GRID }}
            >
              <span>#</span>
              <span>Symbol</span>
              {(
                [
                  ['long_score',   'LScore'],
                  [null,           'Position'],
                  ['short_score',  'SScore'],
                  ['demand_score', 'Demand'],
                  ['supply_score', 'Supply'],
                  ['rvol',         'RVol'],
                  ['dist_long',    'Dist↓'],
                  ['near_52w_high','52WH%'],
                  ['near_52w_low', '52WL%'],
                  [null,           'Time'],
                ] as [SortKey | null, string][]
              ).map(([key, label], i) =>
                key ? (
                  <button
                    key={i}
                    onClick={() => setSortBy(key)}
                    className={`text-left flex items-center gap-0.5 hover:text-blue-600 ${sortBy === key ? 'text-blue-600' : ''}`}
                  >
                    {label}{sortBy === key ? ' ▲' : ''}
                  </button>
                ) : (
                  <span key={i}>{label}</span>
                )
              )}
            </div>

            {rankingsQuery.isLoading && (
              <div className="text-center py-8 text-gray-400 text-sm">Loading rankings…</div>
            )}

            {rankingsQuery.data?.map(row => (
              <div key={row.symbol}>
                <RankRow row={row} onSelect={handleRowClick} isSelected={expandedSym === row.symbol} />
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
                      <>{' '}|{' '}<span className="font-semibold">Long:</span>{' '}
                        Entry ₹{analyzeQuery.data.long_setup.ideal_entry.toLocaleString('en-IN', { maximumFractionDigits: 0 })} ·{' '}
                        SL ₹{analyzeQuery.data.long_setup.stop_loss.toLocaleString('en-IN', { maximumFractionDigits: 0 })} ·{' '}
                        T1 ₹{analyzeQuery.data.long_setup.t1.toLocaleString('en-IN', { maximumFractionDigits: 0 })} · R:R 1:{analyzeQuery.data.long_setup.t1_rr}
                      </>
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
        </>
      )}
    </div>
  )
}
