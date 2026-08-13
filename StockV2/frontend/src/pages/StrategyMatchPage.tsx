import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getLeaderboard, getLeaderboardStatus, triggerLeaderboardCompute,
  type LeaderboardRow,
} from '../api/leaderboard'
import { getStrategies } from '../api/strategies'
import { inr } from '../utils/format'

type SortKey = keyof LeaderboardRow
type SortDir = 'asc' | 'desc'

function winBadge(wr: number | null) {
  if (wr == null) return <span className="text-gray-400">—</span>
  const pct = Math.round(wr * 100)
  const cls =
    pct >= 65 ? 'bg-green-100 text-green-800 border-green-300'
    : pct >= 50 ? 'bg-amber-100 text-amber-800 border-amber-300'
    : 'bg-red-100 text-red-700 border-red-300'
  return (
    <span className={`inline-block px-2 py-0.5 text-xs font-bold rounded border ${cls}`}>
      {pct}%
    </span>
  )
}

function SortTh({
  label, col, sort, dir, onSort,
}: { label: string; col: SortKey; sort: SortKey; dir: SortDir; onSort: (c: SortKey) => void }) {
  return (
    <th
      onClick={() => onSort(col)}
      className="px-3 py-2 cursor-pointer select-none hover:bg-gray-200 whitespace-nowrap text-left"
    >
      {label}
      {sort === col && <span className="ml-1 text-blue-500">{dir === 'desc' ? '▼' : '▲'}</span>}
    </th>
  )
}

export function StrategyMatchPage() {
  const qc = useQueryClient()

  const [sl, setSl] = useState(5)
  const [tgt, setTgt] = useState(10)
  const [minTrades, setMinTrades] = useState(3)
  const [symbolFilter, setSymbolFilter] = useState('')
  const [stratFilter, setStratFilter] = useState<number | ''>('')
  const [sort, setSort] = useState<SortKey>('win_rate')
  const [dir, setDir] = useState<SortDir>('desc')

  const { data: strategies = [] } = useQuery({
    queryKey: ['strategies'],
    queryFn: getStrategies,
  })

  const { data: status, isLoading: statusLoading } = useQuery({
    queryKey: ['leaderboard', 'status', sl, tgt],
    queryFn: () => getLeaderboardStatus(sl, tgt),
    refetchInterval: (query) => {
      const d = query.state.data
      return d?.is_computing ? 4000 : false
    },
  })

  const { data: rows = [], isFetching } = useQuery({
    queryKey: ['leaderboard', 'data', sl, tgt, minTrades],
    queryFn: () => getLeaderboard({ stop_loss_pct: sl, target_pct: tgt, min_trades: minTrades }),
    refetchInterval: (query) => {
      // keep refreshing while computing so new results appear
      return status?.is_computing ? 8000 : false
    },
    enabled: (status?.pairs_cached ?? 0) > 0,
  })

  const computeMut = useMutation({
    mutationFn: (force = false) => triggerLeaderboardCompute(sl, tgt, force),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['leaderboard'] })
    },
  })

  const handleSort = (col: SortKey) => {
    if (sort === col) setDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    else { setSort(col); setDir('desc') }
  }

  const visible = rows
    .filter((r) => {
      if (symbolFilter && !r.symbol.includes(symbolFilter.toUpperCase())) return false
      if (stratFilter !== '' && r.strategy_id !== stratFilter) return false
      return true
    })
    .sort((a, b) => {
      const av = a[sort] ?? (dir === 'desc' ? -Infinity : Infinity)
      const bv = b[sort] ?? (dir === 'desc' ? -Infinity : Infinity)
      if (av < bv) return dir === 'desc' ? 1 : -1
      if (av > bv) return dir === 'desc' ? -1 : 1
      return 0
    })

  const top = visible[0]

  return (
    <div className="space-y-5">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-800">Strategy Match</h1>
        <p className="text-sm text-gray-500 mt-1">
          Which strategy works best with which stock? Backtested across all NSE stocks
          from 2015 to today.
        </p>
      </div>

      {/* Params + Compute panel */}
      <div className="bg-white border border-gray-200 rounded-lg p-4 shadow-sm">
        <div className="flex flex-wrap gap-4 items-end">
          <div>
            <label className="block text-xs text-gray-500 mb-1">Stop Loss %</label>
            <input
              type="number" min={1} max={30} step={0.5}
              value={sl}
              onChange={(e) => setSl(Number(e.target.value))}
              className="border border-gray-300 rounded px-3 py-1.5 text-sm w-24"
            />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">Target %</label>
            <input
              type="number" min={1} max={100} step={1}
              value={tgt}
              onChange={(e) => setTgt(Number(e.target.value))}
              className="border border-gray-300 rounded px-3 py-1.5 text-sm w-24"
            />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">Min Trades</label>
            <input
              type="number" min={1} max={100} step={1}
              value={minTrades}
              onChange={(e) => setMinTrades(Number(e.target.value))}
              className="border border-gray-300 rounded px-3 py-1.5 text-sm w-24"
            />
          </div>

          <button
            onClick={() => computeMut.mutate(status?.is_current ? true : false)}
            disabled={computeMut.isPending || status?.is_computing}
            className={`px-4 py-1.5 text-white text-sm rounded disabled:opacity-50 ${
              status?.is_current
                ? 'bg-gray-500 hover:bg-gray-600'
                : 'bg-blue-600 hover:bg-blue-700'
            }`}
          >
            {status?.is_computing
              ? 'Computing…'
              : computeMut.isPending
              ? 'Starting…'
              : status?.is_current
              ? 'Force Refresh'
              : 'Compute Now'}
          </button>

          {computeMut.isSuccess && computeMut.data && (
            <span className="text-emerald-600 text-sm">{computeMut.data.message}</span>
          )}
          {computeMut.isError && (
            <span className="text-red-600 text-sm">{String(computeMut.error)}</span>
          )}
        </div>

        {/* Status bar */}
        {!statusLoading && status && (
          <div className="mt-3">
            {status.is_computing ? (
              <div>
                <div className="flex justify-between text-xs text-gray-500 mb-1">
                  <span className="animate-pulse text-blue-600 font-medium">
                    Computing… {status.pairs_cached.toLocaleString()} / {status.total_expected.toLocaleString()} pairs
                  </span>
                  <span>{status.pct_done}%</span>
                </div>
                <div className="w-full bg-gray-200 rounded-full h-1.5">
                  <div
                    className="bg-blue-500 h-1.5 rounded-full transition-all duration-500"
                    style={{ width: `${Math.min(status.pct_done, 100)}%` }}
                  />
                </div>
              </div>
            ) : status.pairs_cached > 0 ? (
              <p className="text-sm text-gray-500">
                <span className="text-emerald-600 font-semibold">{status.pairs_cached.toLocaleString()}</span> pairs
                computed across {status.total_symbols} stocks × {status.total_strategies} strategies
                {status.is_current && status.last_price_date && (
                  <span className="ml-2 text-emerald-600 font-medium">
                    · up to date as of {status.last_price_date}
                  </span>
                )}
                {!status.is_current && status.last_price_date && (
                  <span className="ml-2 text-amber-600">
                    · new data available ({status.last_price_date})
                  </span>
                )}
                {status.error && <span className="text-red-500 ml-2">· last run had errors</span>}
              </p>
            ) : (
              <p className="text-sm text-amber-600">
                No data yet. Click <strong>Compute Now</strong> to run the analysis — takes ~5-10 minutes.
              </p>
            )}
          </div>
        )}
      </div>

      {/* Top pick callout */}
      {top && (
        <div className="bg-emerald-50 border border-emerald-200 rounded-lg px-4 py-3 flex items-center gap-4">
          <div className="text-2xl font-bold text-emerald-700">#1</div>
          <div>
            <div className="font-semibold text-gray-800">
              {top.symbol}
              <span className="mx-2 text-gray-400">+</span>
              <span className="text-blue-700">{top.strategy_name}</span>
            </div>
            <div className="text-sm text-gray-500 mt-0.5">
              Win rate {winBadge(top.win_rate)}
              <span className="mx-2 text-gray-300">·</span>
              {top.total_trades} trades
              <span className="mx-2 text-gray-300">·</span>
              CAGR {top.cagr != null ? `${top.cagr.toFixed(1)}%` : '—'}
              <span className="mx-2 text-gray-300">·</span>
              P&L {inr(top.total_pnl)}
            </div>
          </div>
        </div>
      )}

      {/* Filter bar */}
      {rows.length > 0 && (
        <div className="flex flex-wrap gap-3 items-end">
          <div>
            <label className="block text-xs text-gray-500 mb-1">Filter by stock</label>
            <input
              placeholder="e.g. RELIANCE"
              value={symbolFilter}
              onChange={(e) => setSymbolFilter(e.target.value)}
              className="border border-gray-300 rounded px-3 py-1.5 text-sm w-36"
            />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">Filter by strategy</label>
            <select
              value={stratFilter}
              onChange={(e) => setStratFilter(e.target.value === '' ? '' : Number(e.target.value))}
              className="border border-gray-300 rounded px-3 py-1.5 text-sm w-56"
            >
              <option value="">All strategies</option>
              {strategies.filter((s) => s.is_active).map((s) => (
                <option key={s.id} value={s.id}>{s.name}</option>
              ))}
            </select>
          </div>
          <span className="text-xs text-gray-400 self-end pb-2">
            {visible.length.toLocaleString()} pairs shown
            {isFetching && <span className="ml-2 animate-pulse text-blue-400">refreshing…</span>}
          </span>
        </div>
      )}

      {/* Leaderboard table */}
      {visible.length > 0 ? (
        <div className="overflow-x-auto rounded-lg border border-gray-200">
          <table className="w-full text-sm">
            <thead className="bg-gray-100 text-gray-600 text-xs">
              <tr>
                <th className="px-3 py-2 text-left text-gray-400 w-8">#</th>
                <SortTh label="Stock" col="symbol" sort={sort} dir={dir} onSort={handleSort} />
                <SortTh label="Strategy" col="strategy_name" sort={sort} dir={dir} onSort={handleSort} />
                <SortTh label="Win %" col="win_rate" sort={sort} dir={dir} onSort={handleSort} />
                <SortTh label="Trades" col="total_trades" sort={sort} dir={dir} onSort={handleSort} />
                <SortTh label="CAGR %" col="cagr" sort={sort} dir={dir} onSort={handleSort} />
                <SortTh label="P&L ₹" col="total_pnl" sort={sort} dir={dir} onSort={handleSort} />
                <SortTh label="Sharpe" col="sharpe_ratio" sort={sort} dir={dir} onSort={handleSort} />
                <SortTh label="Max DD" col="max_drawdown" sort={sort} dir={dir} onSort={handleSort} />
                <SortTh label="PF" col="profit_factor" sort={sort} dir={dir} onSort={handleSort} />
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-100">
              {visible.map((r, i) => {
                const wr = r.win_rate ?? 0
                const rowBg = wr >= 0.65 ? 'hover:bg-green-50' : wr >= 0.5 ? 'hover:bg-amber-50' : 'hover:bg-gray-50'
                return (
                  <tr key={`${r.symbol}-${r.strategy_id}`} className={`transition-colors ${rowBg}`}>
                    <td className="px-3 py-2 text-gray-400 text-xs">{i + 1}</td>
                    <td className="px-3 py-2 font-semibold text-gray-800">{r.symbol}</td>
                    <td className="px-3 py-2 text-gray-500 text-xs max-w-[180px] truncate" title={r.strategy_name}>
                      {r.strategy_name}
                    </td>
                    <td className="px-3 py-2">{winBadge(r.win_rate)}</td>
                    <td className="px-3 py-2 text-gray-600">{r.total_trades}</td>
                    <td className={`px-3 py-2 font-semibold ${(r.cagr ?? 0) >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                      {r.cagr != null ? `${r.cagr.toFixed(1)}%` : '—'}
                    </td>
                    <td className={`px-3 py-2 ${r.total_pnl >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                      {inr(r.total_pnl)}
                    </td>
                    <td className="px-3 py-2 text-gray-500">
                      {r.sharpe_ratio != null ? r.sharpe_ratio.toFixed(2) : '—'}
                    </td>
                    <td className="px-3 py-2 text-red-500">
                      {r.max_drawdown != null ? `${r.max_drawdown.toFixed(1)}%` : '—'}
                    </td>
                    <td className="px-3 py-2 text-gray-500">
                      {r.profit_factor != null ? r.profit_factor.toFixed(2) : '—'}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      ) : (status?.pairs_cached ?? 0) === 0 ? null : (
        <p className="text-gray-500 text-sm">No results match the current filters.</p>
      )}
    </div>
  )
}
