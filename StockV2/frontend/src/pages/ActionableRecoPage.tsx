import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { getActionableReco, type ActionablePick } from '../api/zones'
import { getConfluenceScan, type ConfluenceBreakout, type ConfluenceNearBreakout } from '../api/confluence'

// ── Helpers ───────────────────────────────────────────────────────────────────

const POS_BADGE: Record<string, { bg: string; text: string; label: string }> = {
  in_demand:   { bg: 'bg-green-100',  text: 'text-green-700',  label: 'IN ZONE' },
  near_demand: { bg: 'bg-yellow-100', text: 'text-yellow-700', label: 'NEAR ZONE' },
  near_supply: { bg: 'bg-orange-100', text: 'text-orange-700', label: 'NEAR SUPPLY' },
  in_supply:   { bg: 'bg-red-100',    text: 'text-red-700',    label: 'IN SUPPLY' },
  breakout:    { bg: 'bg-blue-100',   text: 'text-blue-700',   label: 'BREAKOUT' },
  neutral:     { bg: 'bg-gray-100',   text: 'text-gray-600',   label: 'NEUTRAL' },
}

const TREND_COL: Record<string, string> = {
  bullish:  'text-green-600',
  bearish:  'text-red-600',
  sideways: 'text-gray-500',
}

function fmt(n: number | null | undefined): string {
  if (n == null) return '—'
  return '₹' + n.toLocaleString('en-IN', { maximumFractionDigits: 2 })
}

function distLabel(d: number): { text: string; cls: string } {
  if (d < -1)  return { text: 'IN ZONE',     cls: 'bg-green-100  text-green-700' }
  if (d <= 1)  return { text: 'AT ZONE',     cls: 'bg-blue-100   text-blue-700' }
  if (d <= 3)  return { text: `${d.toFixed(1)}% above`, cls: 'bg-yellow-50  text-yellow-700' }
  return               { text: `${d.toFixed(1)}% above`, cls: 'bg-orange-50 text-orange-700' }
}

function mlBadge(conf: number) {
  const cls = conf >= 70 ? 'bg-green-100 text-green-700' : conf >= 55 ? 'bg-yellow-100 text-yellow-700' : 'bg-gray-100 text-gray-500'
  return <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${cls}`}>{conf}%</span>
}

// ── Pick Row (buys / sells) ───────────────────────────────────────────────────

function PickRow({ pick, expanded, onExpand }: {
  pick: ActionablePick
  expanded: boolean
  onExpand: () => void
}) {
  const dist = distLabel(pick.distance_pct)
  const pb = POS_BADGE[pick.position_tag] || POS_BADGE.neutral
  const riskPct = pick.stop_loss && pick.entry_price
    ? ((pick.entry_price - pick.stop_loss) / pick.entry_price * 100).toFixed(1)
    : null

  return (
    <>
      <tr
        className="hover:bg-gray-50 cursor-pointer border-b border-gray-100"
        onClick={onExpand}
      >
        <td className="px-3 py-2.5">
          <span className="font-semibold text-gray-900 text-sm">{pick.symbol}</span>
        </td>
        <td className="px-3 py-2.5 font-mono text-sm text-gray-700">{fmt(pick.current_price)}</td>
        <td className="px-3 py-2.5 font-mono text-sm font-semibold text-green-700">{fmt(pick.entry_price)}</td>
        <td className="px-3 py-2.5">
          <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${dist.cls}`}>{dist.text}</span>
        </td>
        <td className="px-3 py-2.5 font-mono text-sm text-red-600">{fmt(pick.stop_loss)}</td>
        <td className="px-3 py-2.5 font-mono text-sm text-green-600">{fmt(pick.target1)}</td>
        <td className="px-3 py-2.5 text-xs text-gray-600">{pick.target1_rr ? `1:${pick.target1_rr}` : '—'}</td>
        <td className="px-3 py-2.5">{mlBadge(pick.ml_confidence)}</td>
        <td className="px-3 py-2.5">
          <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${pb.bg} ${pb.text}`}>{pb.label}</span>
        </td>
        <td className="px-3 py-2.5">
          <span className={`text-xs font-medium ${TREND_COL[pick.market_structure] || 'text-gray-500'}`}>
            {pick.market_structure}
          </span>
        </td>
      </tr>
      {expanded && (
        <tr className="bg-blue-50 border-b border-blue-100">
          <td colSpan={10} className="px-4 py-3">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-xs">
              <div>
                <div className="text-gray-500 mb-1 font-medium">Entry</div>
                <div className="text-green-700 font-bold text-base">{fmt(pick.entry_price)}</div>
                <div className="text-gray-500 mt-0.5">Current: {fmt(pick.current_price)}</div>
                {pick.distance_pct > 0
                  ? <div className="text-yellow-700 mt-0.5">Wait for {pick.distance_pct.toFixed(1)}% pullback</div>
                  : <div className="text-green-700 mt-0.5">Already in zone — buy now</div>
                }
              </div>
              <div>
                <div className="text-gray-500 mb-1 font-medium">Stop Loss</div>
                <div className="text-red-600 font-bold text-base">{fmt(pick.stop_loss)}</div>
                {riskPct && <div className="text-red-500 mt-0.5">Risk: {riskPct}%</div>}
              </div>
              <div>
                <div className="text-gray-500 mb-1 font-medium">Targets</div>
                <div className="text-green-600 font-semibold">T1: {fmt(pick.target1)}{pick.target1_rr ? ` (1:${pick.target1_rr})` : ''}</div>
                <div className="text-green-700 font-semibold mt-0.5">T2: {fmt(pick.target2)}{pick.target2_rr ? ` (1:${pick.target2_rr})` : ''}</div>
              </div>
              <div>
                <div className="text-gray-500 mb-1 font-medium">Quality</div>
                <div className="text-gray-700">Zone: <span className="font-semibold">{pick.zone_score?.toFixed(0) ?? '—'}</span>/100</div>
                <div className="text-gray-700">Setup: <span className="font-semibold">{pick.setup_score?.toFixed(0) ?? '—'}</span>/100</div>
                {pick.candle_signal && pick.candle_signal !== 'NONE' &&
                  <div className="text-purple-700 font-medium mt-1 capitalize">{pick.candle_signal.replace(/_/g, ' ')}</div>
                }
                {pick.rvol && pick.rvol > 1.5 &&
                  <div className="text-blue-600 mt-0.5">Vol: {pick.rvol.toFixed(1)}× avg</div>
                }
              </div>
            </div>
            {pick.invalidation && (
              <div className="mt-2 px-3 py-1.5 bg-red-50 rounded border border-red-100 text-xs text-red-700">
                <span className="font-semibold">Setup invalidates if: </span>{pick.invalidation}
              </div>
            )}
          </td>
        </tr>
      )}
    </>
  )
}

// ── Confluence Row ────────────────────────────────────────────────────────────

function ConfluenceRow({ item, expanded, onExpand, zoneEntry }: {
  item: ConfluenceBreakout | ConfluenceNearBreakout
  expanded: boolean
  onExpand: () => void
  zoneEntry?: number
}) {
  const isBreakout = item.category === 'breakout'
  const bi = item as ConfluenceBreakout
  const ni = item as ConfluenceNearBreakout
  const setup = item.long_setup
  const ml = isBreakout
    ? Math.round(bi.breakout_ml_probability * 100)
    : Math.round(item.zone_ml_confidence * 100)

  return (
    <>
      <tr
        className="hover:bg-gray-50 cursor-pointer border-b border-gray-100"
        onClick={onExpand}
      >
        <td className="px-3 py-2.5">
          <span className="font-semibold text-gray-900 text-sm">{item.symbol}</span>
          {zoneEntry && (
            <span className="ml-2 text-[9px] px-1.5 py-0.5 rounded bg-purple-100 text-purple-700 font-bold">ZONE+BKT</span>
          )}
        </td>
        <td className="px-3 py-2.5 font-mono text-sm text-gray-700">{fmt(item.current_price)}</td>
        <td className="px-3 py-2.5 text-sm">
          {isBreakout
            ? <span className="text-blue-700 font-medium">+{bi.breakout_pct?.toFixed(1)}% breakout</span>
            : <span className="text-yellow-700 font-medium">{Math.abs(ni.dist_to_resistance).toFixed(1)}% to resistance</span>
          }
        </td>
        <td className="px-3 py-2.5">
          {isBreakout
            ? <span className="text-[10px] px-1.5 py-0.5 rounded bg-blue-100 text-blue-700 font-medium">{bi.conviction_score}/6</span>
            : <span className="text-[10px] px-1.5 py-0.5 rounded bg-yellow-100 text-yellow-700 font-medium">watching</span>
          }
        </td>
        <td className="px-3 py-2.5 font-mono text-sm text-red-600">{setup ? fmt(setup.stop_loss) : '—'}</td>
        <td className="px-3 py-2.5 font-mono text-sm text-green-600">{setup ? fmt(setup.t1) : '—'}</td>
        <td className="px-3 py-2.5 text-xs text-gray-600">{setup?.t1_rr ? `1:${setup.t1_rr}` : '—'}</td>
        <td className="px-3 py-2.5">{mlBadge(ml)}</td>
        <td className="px-3 py-2.5">
          <span className={`text-xs font-medium ${TREND_COL[item.market_structure] || 'text-gray-500'}`}>
            {item.market_structure}
          </span>
        </td>
        <td className="px-3 py-2.5 text-xs text-gray-500 font-mono">
          {(item.combined_score * 100).toFixed(0)}
        </td>
      </tr>
      {expanded && (
        <tr className="bg-purple-50 border-b border-purple-100">
          <td colSpan={10} className="px-4 py-3">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-xs">
              <div>
                <div className="text-gray-500 mb-1 font-medium">Resistance</div>
                <div className="text-blue-700 font-bold text-base">{fmt(item.resistance)}</div>
                {zoneEntry && <div className="text-purple-700 mt-0.5 font-semibold">Zone entry: {fmt(zoneEntry)}</div>}
              </div>
              <div>
                <div className="text-gray-500 mb-1 font-medium">Stop Loss</div>
                <div className="text-red-600 font-bold text-base">{setup ? fmt(setup.stop_loss) : '—'}</div>
              </div>
              <div>
                <div className="text-gray-500 mb-1 font-medium">Targets</div>
                {setup
                  ? <>
                      <div className="text-green-600 font-semibold">T1: {fmt(setup.t1)} (1:{setup.t1_rr})</div>
                      <div className="text-green-700 font-semibold mt-0.5">T2: {fmt(setup.t2)} (1:{setup.t2_rr})</div>
                    </>
                  : <div className="text-gray-400">No setup data</div>
                }
              </div>
              <div>
                <div className="text-gray-500 mb-1 font-medium">
                  {isBreakout ? 'Signals Met' : 'Zone Support'}
                </div>
                {isBreakout
                  ? bi.signals_met?.map(s => <div key={s} className="text-green-700">✓ {s}</div>)
                  : (item as ConfluenceNearBreakout).demand_zones?.slice(0, 2).map((z, i) => (
                      <div key={i} className="text-green-700">{fmt(z.low)} — {fmt(z.high)}</div>
                    ))
                }
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

type Tab = 'buys' | 'sells' | 'confluence'

export function ActionableRecoPage() {
  const [tab, setTab]         = useState<Tab>('buys')
  const [expanded, setExpanded] = useState<string | null>(null)
  const queryClient = useQueryClient()

  const recoQuery = useQuery({
    queryKey: ['actionable-reco'],
    queryFn:  getActionableReco,
    staleTime: 5 * 60 * 1000,
  })

  const confQuery = useQuery({
    queryKey: ['confluence-scan'],
    queryFn:  getConfluenceScan,
    staleTime: 5 * 60 * 1000,
  })

  const zoneBuys  = recoQuery.data?.zone_buys  ?? []
  const zoneSells = recoQuery.data?.zone_sells ?? []
  const breakouts    = confQuery.data?.breakouts    ?? []
  const nearBreakout = confQuery.data?.near_breakout ?? []

  const zoneBuyMap = new Map(zoneBuys.map(b => [b.symbol, b.entry_price]))

  const confItems = [...breakouts, ...nearBreakout]
    .filter(i => zoneBuyMap.has(i.symbol))
    .sort((a, b) => b.combined_score - a.combined_score)

  const pureBreakouts = breakouts.filter(b => !zoneBuyMap.has(b.symbol))

  const TABS: { id: Tab; label: string; activeClass: string }[] = [
    { id: 'buys',       label: `Zone Buys (${zoneBuys.length})`,
      activeClass: 'border-green-500 text-green-700' },
    { id: 'sells',      label: `Zone Sells (${zoneSells.length})`,
      activeClass: 'border-red-500 text-red-700' },
    { id: 'confluence', label: `Confluence (${confItems.length + pureBreakouts.length})`,
      activeClass: 'border-purple-500 text-purple-700' },
  ]

  const PICK_HEADERS   = ['Symbol', 'Price', 'Entry', 'Distance', 'Stop Loss', 'Target 1', 'R:R', 'ML', 'Position', 'Trend']
  const CONF_HEADERS   = ['Symbol', 'Price', 'Status', 'Signals', 'Stop Loss', 'Target 1', 'R:R', 'ML', 'Trend', 'Score']

  const loading = recoQuery.isLoading || confQuery.isLoading

  function toggle(key: string) {
    setExpanded(prev => prev === key ? null : key)
  }

  return (
    <div>
      {/* Header */}
      <div className="flex items-center gap-4 mb-5">
        <div>
          <h1 className="text-xl font-bold text-gray-900">Actionable Picks</h1>
          <p className="text-xs text-gray-400 mt-0.5">
            Entry within ±5% of current price · actionable in next 4-5 days · click row for full setup
          </p>
        </div>
        <button
          onClick={() => {
            queryClient.invalidateQueries({ queryKey: ['actionable-reco'] })
            queryClient.invalidateQueries({ queryKey: ['confluence-scan'] })
            setExpanded(null)
          }}
          className="ml-auto px-3 py-1.5 text-xs border border-gray-300 text-gray-600 rounded hover:bg-gray-50"
        >
          Refresh
        </button>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-gray-200 mb-5">
        {TABS.map(t => (
          <button
            key={t.id}
            onClick={() => { setTab(t.id); setExpanded(null) }}
            className={`px-5 py-2.5 text-sm font-medium border-b-2 transition-colors ${
              tab === t.id ? t.activeClass : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {loading && (
        <div className="text-center py-16 text-gray-400 text-sm animate-pulse">Loading picks…</div>
      )}

      {/* ── Zone Buys / Zone Sells ─────────────────────────────────────────── */}
      {!loading && (tab === 'buys' || tab === 'sells') && (() => {
        const picks = tab === 'buys' ? zoneBuys : zoneSells
        const accentBg   = tab === 'buys' ? 'bg-green-50'  : 'bg-red-50'
        const accentBdr  = tab === 'buys' ? 'border-green-200' : 'border-red-200'
        const thCls      = tab === 'buys' ? 'text-green-600' : 'text-red-600'
        const emptyText  = tab === 'buys'
          ? 'No actionable buy zones today — run Zone precompute first.'
          : 'No actionable sell zones today — run Zone precompute first.'

        if (!picks.length) return (
          <div className="text-center py-16 text-gray-400 text-sm">{emptyText}</div>
        )
        return (
          <div className={`overflow-x-auto bg-white rounded-lg border ${accentBdr} shadow-sm`}>
            <table className="w-full text-sm">
              <thead>
                <tr className={`${accentBg} border-b ${accentBdr}`}>
                  {PICK_HEADERS.map(h => (
                    <th key={h} className={`px-3 py-2 text-left text-[11px] font-semibold uppercase tracking-wide ${thCls}`}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {picks.map(p => (
                  <PickRow
                    key={p.symbol}
                    pick={p}
                    expanded={expanded === p.symbol}
                    onExpand={() => toggle(p.symbol)}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )
      })()}

      {/* ── Confluence ─────────────────────────────────────────────────────── */}
      {!loading && tab === 'confluence' && (() => {
        const noData = !confItems.length && !pureBreakouts.length
        if (noData) return (
          <div className="text-center py-16 text-gray-400 text-sm">
            No confluence signals — run Zone precompute then scan breakouts.
          </div>
        )
        return (
          <div className="space-y-6">
            {confItems.length > 0 && (
              <div>
                <div className="flex items-center gap-3 mb-2">
                  <span className="text-sm font-bold text-purple-700">Zone + Breakout</span>
                  <span className="text-xs text-gray-400">Breaking out with demand zone as support — highest conviction</span>
                  <span className="ml-auto px-2 py-0.5 rounded-full bg-purple-100 text-purple-700 text-xs font-semibold">
                    {confItems.length} picks
                  </span>
                </div>
                <div className="overflow-x-auto bg-white rounded-lg border border-purple-200 shadow-sm">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="bg-purple-50 border-b border-purple-100">
                        {CONF_HEADERS.map(h => (
                          <th key={h} className="px-3 py-2 text-left text-[11px] font-semibold uppercase tracking-wide text-purple-600">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {confItems.map(item => (
                        <ConfluenceRow
                          key={item.symbol}
                          item={item}
                          expanded={expanded === item.symbol + '-conf'}
                          onExpand={() => toggle(item.symbol + '-conf')}
                          zoneEntry={zoneBuyMap.get(item.symbol)}
                        />
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {pureBreakouts.length > 0 && (
              <div>
                <div className="flex items-center gap-3 mb-2">
                  <span className="text-sm font-bold text-blue-700">Breakouts</span>
                  <span className="text-xs text-gray-400">Momentum breakouts — no active zone overlap</span>
                  <span className="ml-auto px-2 py-0.5 rounded-full bg-blue-100 text-blue-700 text-xs font-semibold">
                    {pureBreakouts.length} picks
                  </span>
                </div>
                <div className="overflow-x-auto bg-white rounded-lg border border-blue-200 shadow-sm">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="bg-blue-50 border-b border-blue-100">
                        {CONF_HEADERS.map(h => (
                          <th key={h} className="px-3 py-2 text-left text-[11px] font-semibold uppercase tracking-wide text-blue-600">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {pureBreakouts.map(item => (
                        <ConfluenceRow
                          key={item.symbol}
                          item={item}
                          expanded={expanded === item.symbol + '-bkt'}
                          onExpand={() => toggle(item.symbol + '-bkt')}
                        />
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )
      })()}
    </div>
  )
}
