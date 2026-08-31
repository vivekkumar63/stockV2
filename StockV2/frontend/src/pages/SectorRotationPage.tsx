import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getSectorSummary, getSectorStocks, recomputeSectors, type SectorData, type SectorSummary, type SectorStock } from '../api/sector'

type Tab = 'breadth' | 'signals'

const PHASE_STYLE: Record<string, { bg: string; text: string; label: string }> = {
  EXPANSION:   { bg: 'bg-emerald-100', text: 'text-emerald-700', label: 'EXPANSION' },
  CONTRACTION: { bg: 'bg-red-100',     text: 'text-red-700',     label: 'CONTRACTION' },
  RECOVERY:    { bg: 'bg-blue-100',    text: 'text-blue-700',    label: 'RECOVERY' },
  SLOWDOWN:    { bg: 'bg-amber-100',   text: 'text-amber-700',   label: 'SLOWDOWN' },
  UNKNOWN:     { bg: 'bg-gray-100',    text: 'text-gray-500',    label: 'UNKNOWN' },
}

const DIR_STYLE: Record<string, { dot: string; text: string; badge: string; label: string }> = {
  ROTATING_IN:  { dot: 'bg-emerald-400', text: 'text-emerald-600', badge: 'bg-emerald-50 text-emerald-700 border border-emerald-200', label: '↑ Rotating In' },
  NEUTRAL:      { dot: 'bg-gray-400',    text: 'text-gray-500',    badge: 'bg-gray-50 text-gray-600 border border-gray-200',          label: '→ Neutral' },
  ROTATING_OUT: { dot: 'bg-red-400',     text: 'text-red-600',     badge: 'bg-red-50 text-red-700 border border-red-200',             label: '↓ Rotating Out' },
}

function signalStatus(curr: number, prev: number): { label: string; cls: string } {
  const delta = curr - prev
  if (delta >= 5)  return { label: '🔥 Heating Up',  cls: 'text-orange-600' }
  if (delta >= 1)  return { label: '📈 Rising',       cls: 'text-emerald-600' }
  if (delta === 0) return { label: '➡ Stable',        cls: 'text-gray-500' }
  return              { label: '📉 Cooling',          cls: 'text-red-500' }
}

function ScoreBar({ value, max = 100 }: { value: number; max?: number }) {
  const pct = Math.round((value / max) * 100)
  const color = value >= 60 ? 'bg-emerald-400' : value >= 40 ? 'bg-amber-400' : 'bg-red-400'
  return (
    <div className="flex items-center gap-1.5">
      <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs w-8 text-right text-gray-500">{value.toFixed(0)}</span>
    </div>
  )
}

function ReturnCell({ value }: { value: number }) {
  const cls = value >= 0 ? 'text-emerald-600 font-medium' : 'text-red-600 font-medium'
  return <span className={cls}>{value >= 0 ? '+' : ''}{value.toFixed(1)}%</span>
}

function Sidebar({ summary, activeTab }: { summary: SectorSummary; activeTab: Tab }) {
  const phase = PHASE_STYLE[summary.market_phase] ?? PHASE_STYLE.UNKNOWN
  return (
    <div className="w-48 shrink-0 flex flex-col gap-3">
      <div className="bg-white rounded-lg border border-gray-200 p-3">
        <div className="text-xs text-gray-400 uppercase tracking-wide mb-1">Market Phase</div>
        <span className={`inline-block px-2 py-0.5 rounded text-sm font-bold ${phase.bg} ${phase.text}`}>
          {phase.label}
        </span>
        {summary.as_of && (
          <div className="text-xs text-gray-400 mt-1">as of {summary.as_of}</div>
        )}
      </div>

      <div className="bg-white rounded-lg border border-gray-200 p-3 flex-1">
        <div className="text-xs text-gray-400 uppercase tracking-wide mb-2">
          {activeTab === 'breadth' ? 'Sector Rotation' : 'Signal Heat Map'}
        </div>
        <div className="space-y-1.5">
          {summary.sectors.map(s => {
            const ds = DIR_STYLE[s.rotation_direction] ?? DIR_STYLE.NEUTRAL
            return (
              <div key={s.name} className="flex items-center gap-1.5 text-xs">
                <div className={`w-2 h-2 rounded-full shrink-0 ${ds.dot}`} />
                <span className="font-medium w-14 shrink-0">{s.name}</span>
                {activeTab === 'breadth' ? (
                  <span className={`${ds.text} text-xs`}>{s.sector_health_score.toFixed(0)}</span>
                ) : (
                  <span className={`${ds.text} text-xs`}>{s.signal_count_this_week} sig</span>
                )}
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

function pctColor(v: number | null) {
  if (v == null) return 'text-gray-400'
  return v >= 0 ? 'text-emerald-600' : 'text-red-600'
}

function StockTable({ sector }: { sector: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ['sector-stocks', sector],
    queryFn: () => getSectorStocks(sector),
    staleTime: 30 * 60 * 1000,
  })

  if (isLoading) return <p className="text-xs text-gray-400 py-2">Loading stocks…</p>
  if (!data || data.length === 0) return <p className="text-xs text-gray-400 py-2">No stock data available.</p>

  const sorted = [...data].sort((a, b) => (b.return_3m ?? -Infinity) - (a.return_3m ?? -Infinity))

  return (
    <div className="mt-3 overflow-x-auto">
      <table className="w-full text-xs border-collapse">
        <thead>
          <tr className="text-gray-400 border-b border-gray-200">
            <th className="text-left py-1 pr-3 font-medium">Symbol</th>
            <th className="text-right py-1 px-2 font-medium">Close</th>
            <th className="text-right py-1 px-2 font-medium">vs SMA20</th>
            <th className="text-right py-1 px-2 font-medium">vs SMA50</th>
            <th className="text-right py-1 px-2 font-medium">3M Return ↓</th>
            <th className="text-center py-1 px-2 font-medium">SMA20</th>
            <th className="text-center py-1 px-2 font-medium">SMA50</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map(s => (
            <tr key={s.symbol} className="border-b border-gray-100 hover:bg-white">
              <td className="py-1 pr-3 font-semibold text-gray-800">{s.symbol}</td>
              <td className="py-1 px-2 text-right text-gray-600">₹{s.close.toFixed(1)}</td>
              <td className={`py-1 px-2 text-right font-medium ${pctColor(s.pct_vs_sma20)}`}>
                {s.pct_vs_sma20 != null ? `${s.pct_vs_sma20 >= 0 ? '+' : ''}${s.pct_vs_sma20.toFixed(1)}%` : '—'}
              </td>
              <td className={`py-1 px-2 text-right font-medium ${pctColor(s.pct_vs_sma50)}`}>
                {s.pct_vs_sma50 != null ? `${s.pct_vs_sma50 >= 0 ? '+' : ''}${s.pct_vs_sma50.toFixed(1)}%` : '—'}
              </td>
              <td className={`py-1 px-2 text-right font-medium ${pctColor(s.return_3m)}`}>
                {s.return_3m != null ? `${s.return_3m >= 0 ? '+' : ''}${s.return_3m.toFixed(1)}%` : '—'}
              </td>
              <td className="py-1 px-2 text-center">
                <span className={`inline-block w-2 h-2 rounded-full ${s.above_sma20 ? 'bg-emerald-400' : 'bg-red-400'}`} />
              </td>
              <td className="py-1 px-2 text-center">
                <span className={`inline-block w-2 h-2 rounded-full ${s.above_sma50 ? 'bg-emerald-400' : 'bg-red-400'}`} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function BreadthRow({ sector }: { sector: SectorData }) {
  const [expanded, setExpanded] = useState(false)
  const ds = DIR_STYLE[sector.rotation_direction] ?? DIR_STYLE.NEUTRAL

  return (
    <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
      <button
        onClick={() => setExpanded(v => !v)}
        className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-gray-50 text-left"
      >
        <span className="text-gray-400 text-xs w-3">{expanded ? '▼' : '▶'}</span>
        <span className="font-semibold text-sm w-16">{sector.name}</span>
        <span className="text-sm font-medium">{sector.sector_health_score.toFixed(0)}</span>
        <ScoreBar value={sector.sector_health_score} />
        <ReturnCell value={sector.return_1m} />
        <span className={`text-xs ml-auto shrink-0 px-2 py-0.5 rounded ${ds.badge}`}>
          {ds.label}
        </span>
      </button>

      {expanded && (
        <div className="px-4 pb-4 bg-gray-50 border-t border-gray-100">
          <div className="grid grid-cols-3 gap-3 mt-3 mb-3">
            <div className="bg-white rounded p-2 text-center border border-gray-100">
              <div className="text-xs text-gray-400 mb-0.5">% above SMA50</div>
              <div className={`text-lg font-bold ${sector.pct_above_sma50 >= 60 ? 'text-emerald-600' : sector.pct_above_sma50 >= 40 ? 'text-amber-600' : 'text-red-600'}`}>
                {sector.pct_above_sma50.toFixed(0)}%
              </div>
            </div>
            <div className="bg-white rounded p-2 text-center border border-gray-100">
              <div className="text-xs text-gray-400 mb-0.5">Index vs SMA20</div>
              <div className={`text-lg font-bold ${sector.index_vs_sma20 >= 0 ? 'text-emerald-600' : 'text-red-600'}`}>
                {sector.index_vs_sma20 >= 0 ? '+' : ''}{sector.index_vs_sma20.toFixed(1)}%
              </div>
            </div>
            <div className="bg-white rounded p-2 text-center border border-gray-100">
              <div className="text-xs text-gray-400 mb-0.5">3M Return</div>
              <div className={`text-lg font-bold ${sector.return_3m >= 0 ? 'text-emerald-600' : 'text-red-600'}`}>
                {sector.return_3m >= 0 ? '+' : ''}{sector.return_3m.toFixed(1)}%
              </div>
            </div>
          </div>
          <StockTable sector={sector.name} />
        </div>
      )}
    </div>
  )
}

function SignalRow({ sector }: { sector: SectorData }) {
  const [expanded, setExpanded] = useState(false)
  const status = signalStatus(sector.signal_count_this_week, sector.signal_count_prev_week)
  const delta = sector.signal_count_this_week - sector.signal_count_prev_week

  return (
    <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
      <button
        onClick={() => setExpanded(v => !v)}
        className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-gray-50 text-left"
      >
        <span className="text-gray-400 text-xs w-3">{expanded ? '▼' : '▶'}</span>
        <span className="font-semibold text-sm w-16">{sector.name}</span>
        <span className="text-sm">{sector.signal_count_this_week} signals</span>
        <span className={`text-xs ${delta >= 0 ? 'text-emerald-600' : 'text-red-500'}`}>
          {delta >= 0 ? '+' : ''}{delta} vs last wk
        </span>
        <span className={`text-xs ml-auto shrink-0 ${status.cls}`}>{status.label}</span>
      </button>

      {expanded && (
        <div className="px-4 pb-4 bg-gray-50 border-t border-gray-100">
          <div className="grid grid-cols-4 gap-3 mt-3 mb-3">
            <div className="bg-white rounded p-2 text-center border border-gray-100">
              <div className="text-xs text-gray-400 mb-0.5">This week</div>
              <div className="text-lg font-bold text-emerald-600">{sector.signal_count_this_week}</div>
            </div>
            <div className="bg-white rounded p-2 text-center border border-gray-100">
              <div className="text-xs text-gray-400 mb-0.5">Last week</div>
              <div className="text-lg font-bold text-gray-700">{sector.signal_count_prev_week}</div>
            </div>
            <div className="bg-white rounded p-2 text-center border border-gray-100">
              <div className="text-xs text-gray-400 mb-0.5">Avg win rate</div>
              <div className={`text-lg font-bold ${sector.avg_win_rate != null && sector.avg_win_rate >= 0.5 ? 'text-emerald-600' : 'text-gray-500'}`}>
                {sector.avg_win_rate != null ? `${(sector.avg_win_rate * 100).toFixed(0)}%` : '—'}
              </div>
            </div>
            <div className="bg-white rounded p-2 text-center border border-gray-100">
              <div className="text-xs text-gray-400 mb-0.5">Top strategy</div>
              <div className="text-xs font-semibold text-gray-700 mt-1 truncate" title={sector.top_strategy ?? ''}>
                {sector.top_strategy ?? '—'}
              </div>
            </div>
          </div>
          <StockTable sector={sector.name} />
        </div>
      )}
    </div>
  )
}

export function SectorRotationPage() {
  const [tab, setTab] = useState<Tab>('breadth')
  const qc = useQueryClient()

  const { data: summary, isLoading, isError } = useQuery({
    queryKey: ['sector-summary'],
    queryFn: getSectorSummary,
    staleTime: 10 * 60 * 1000,
  })

  const recompute = useMutation({
    mutationFn: recomputeSectors,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sector-summary'] }),
  })

  const tabCls = (t: Tab) =>
    t === tab
      ? 'px-4 py-2 text-sm font-semibold text-blue-600 border-b-2 border-blue-600 -mb-px'
      : 'px-4 py-2 text-sm text-gray-500 hover:text-gray-700'

  if (isLoading) {
    return (
      <div className="space-y-4">
        <h1 className="text-xl font-bold text-gray-800">Sector Rotation</h1>
        <p className="text-gray-500">Loading sector data…</p>
      </div>
    )
  }

  if (isError || !summary) {
    return (
      <div className="space-y-4">
        <h1 className="text-xl font-bold text-gray-800">Sector Rotation</h1>
        <div className="bg-amber-50 border border-amber-200 rounded p-4 text-sm text-amber-700">
          No sector data yet. Click Recompute to generate the first snapshot.
          <button
            onClick={() => recompute.mutate()}
            disabled={recompute.isPending}
            className="ml-3 px-3 py-1 bg-amber-600 text-white rounded hover:bg-amber-700 disabled:opacity-50 text-xs"
          >
            {recompute.isPending ? 'Computing…' : 'Recompute'}
          </button>
        </div>
      </div>
    )
  }

  const sortedBySignal = [...summary.sectors].sort(
    (a, b) => b.signal_count_this_week - a.signal_count_this_week,
  )

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-gray-800">Sector Rotation</h1>
        <button
          onClick={() => recompute.mutate()}
          disabled={recompute.isPending}
          className="px-3 py-1.5 bg-gray-800 text-white text-xs rounded hover:bg-gray-700 disabled:opacity-50"
        >
          {recompute.isPending ? 'Computing…' : '↺ Recompute'}
        </button>
      </div>

      {/* Tab bar */}
      <div className="border-b border-gray-200 flex">
        <button className={tabCls('breadth')} onClick={() => setTab('breadth')}>
          📊 Breadth &amp; Momentum
        </button>
        <button className={tabCls('signals')} onClick={() => setTab('signals')}>
          🎯 Signal Flow
        </button>
      </div>

      <div className="flex gap-4">
        <Sidebar summary={summary} activeTab={tab} />

        <div className="flex-1 space-y-2">
          {tab === 'breadth' && summary.sectors.map(s => (
            <BreadthRow key={s.name} sector={s} />
          ))}
          {tab === 'signals' && sortedBySignal.map(s => (
            <SignalRow key={s.name} sector={s} />
          ))}
        </div>
      </div>
    </div>
  )
}
