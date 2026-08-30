import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import {
  getSpecialStrategies,
  getSpecialBacktestResults,
  getSpecialBacktestTrades,
  runSpecialScan,
  runSpecialBacktest,
  triggerSpecialPrecompute,
  getSpecialPrecomputeStatus,
  getSpecialScanResults,
  type SpecialScanResult,
  type SpecialBacktestResult,
  type SpecialTrade,
  type SpecialPerformanceRow,
} from '../api/special'
import { inr } from '../utils/format'

type Tab = 'scan' | 'backtest' | 'all'
type SortDir = 'asc' | 'desc'

function isoDate(d: Date) { return d.toISOString().slice(0, 10) }
const TODAY = isoDate(new Date())
const Y3 = isoDate(new Date(new Date().setFullYear(new Date().getFullYear() - 3)))

function PnlCell({ v }: { v: number | null }) {
  if (v == null) return <span className="text-gray-400">—</span>
  const cls = v >= 0 ? 'text-green-600 font-medium' : 'text-red-600 font-medium'
  return <span className={cls}>{v >= 0 ? '+' : ''}{v.toFixed(2)}%</span>
}

function ExitBadge({ reason }: { reason: string }) {
  const colors: Record<string, string> = {
    sell_signal: 'bg-blue-100 text-blue-700',
    end_of_period: 'bg-gray-100 text-gray-600',
  }
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${colors[reason] ?? 'bg-gray-100 text-gray-600'}`}>
      {reason.replace(/_/g, ' ')}
    </span>
  )
}

export function SpecialStrategiesPage() {
  const [tab, setTab] = useState<Tab>('scan')

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <h1 className="text-xl font-bold text-gray-800">Special Strategies</h1>
        <span className="text-xs bg-purple-100 text-purple-700 px-2 py-0.5 rounded font-medium">
          Signal-based exit
        </span>
      </div>
      <p className="text-sm text-gray-500">
        Strategies that hold positions until a sell indicator fires — no fixed stop-loss or target.
      </p>

      <div className="flex gap-1 border-b border-gray-200">
        {([['scan', 'Scan'], ['backtest', 'Backtest'], ['all', 'All Stocks']] as [Tab, string][]).map(([t, label]) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-medium transition-colors ${
              tab === t ? 'border-b-2 border-blue-500 text-blue-600' : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === 'scan' && <ScanTab />}
      {tab === 'backtest' && <BacktestTab />}
      {tab === 'all' && <AllStocksTab />}
    </div>
  )
}

// ── Scan Tab ─────────────────────────────────────────────────────────────────

function ScanTab() {
  const [strategyId, setStrategyId] = useState<string>('')
  const [results, setResults] = useState<SpecialScanResult[] | null>(null)

  const { data: strategies = [] } = useQuery({ queryKey: ['special-strategies'], queryFn: getSpecialStrategies })

  const scanMut = useMutation({ mutationFn: runSpecialScan, onSuccess: setResults })

  return (
    <div className="space-y-4">
      <div className="bg-white rounded-lg border border-gray-200 p-4 flex flex-wrap gap-4 items-end">
        <div className="space-y-1">
          <label className="text-xs font-medium text-gray-600">Strategy</label>
          <select value={strategyId} onChange={(e) => setStrategyId(e.target.value)}
            className="border border-gray-300 rounded px-3 py-2 text-sm w-64 focus:outline-none focus:ring-2 focus:ring-blue-400">
            <option value="">All Special Strategies</option>
            {strategies.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </div>
        <button onClick={() => { setResults(null); scanMut.mutate({ strategy_id: strategyId ? Number(strategyId) : undefined }) }}
          disabled={scanMut.isPending}
          className="px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded hover:bg-blue-700 disabled:opacity-50">
          {scanMut.isPending ? 'Scanning…' : 'Run Scan'}
        </button>
      </div>

      {scanMut.isError && <ErrBox msg={(scanMut.error as Error).message} />}

      {results !== null && (
        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
          {results.length === 0
            ? <p className="text-gray-500 text-sm p-4">No buy signals found today.</p>
            : (
              <table className="w-full text-sm">
                <thead className="bg-gray-50 border-b border-gray-200">
                  <tr>{['Symbol', 'Strategy', 'Confidence', 'Price', 'Conditions Met'].map((h) => (
                    <th key={h} className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">{h}</th>
                  ))}</tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {results.map((r, i) => (
                    <tr key={i} className="hover:bg-gray-50">
                      <td className="px-3 py-2 font-semibold text-gray-800">{r.symbol}</td>
                      <td className="px-3 py-2 text-gray-600">{r.strategy_name}</td>
                      <td className="px-3 py-2">
                        <span className="px-2 py-0.5 bg-blue-50 text-blue-700 rounded text-xs font-medium">
                          {(r.confidence * 100).toFixed(0)}%
                        </span>
                      </td>
                      <td className="px-3 py-2 text-gray-700">₹{r.price.toFixed(2)}</td>
                      <td className="px-3 py-2 text-gray-500 text-xs">{r.conditions_met.join(', ')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
        </div>
      )}
    </div>
  )
}

// ── Backtest Tab ──────────────────────────────────────────────────────────────

function BacktestTab() {
  const [form, setForm] = useState({ symbol: '', from_date: Y3, to_date: TODAY, special_strategy_id: '', initial_capital: '500000' })
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [trades, setTrades] = useState<Record<number, SpecialTrade[]>>({})

  const { data: strategies = [] } = useQuery({ queryKey: ['special-strategies'], queryFn: getSpecialStrategies })
  const { data: pastResults = [], refetch: refetchResults } = useQuery({ queryKey: ['special-backtest-results'], queryFn: getSpecialBacktestResults })

  const backtestMut = useMutation({ mutationFn: runSpecialBacktest, onSuccess: () => refetchResults() })

  const handleRun = () => {
    if (!form.symbol || !form.special_strategy_id) return
    backtestMut.mutate({
      symbol: form.symbol.toUpperCase(), from_date: form.from_date, to_date: form.to_date,
      special_strategy_id: Number(form.special_strategy_id), initial_capital: Number(form.initial_capital),
    })
  }

  const toggleTrades = async (id: number) => {
    if (expandedId === id) { setExpandedId(null); return }
    setExpandedId(id)
    if (!trades[id]) {
      const t = await getSpecialBacktestTrades(id)
      setTrades((prev) => ({ ...prev, [id]: t }))
    }
  }

  const latest = backtestMut.data

  return (
    <div className="space-y-4">
      <div className="bg-white rounded-lg border border-gray-200 p-4 space-y-4">
        <div className="flex flex-wrap gap-4 items-end">
          <FormField label="Symbol">
            <input value={form.symbol} onChange={(e) => setForm({ ...form, symbol: e.target.value.toUpperCase() })}
              placeholder="e.g. RELIANCE"
              className="border border-gray-300 rounded px-3 py-2 text-sm w-36 focus:outline-none focus:ring-2 focus:ring-blue-400" />
          </FormField>
          <FormField label="Strategy">
            <select value={form.special_strategy_id} onChange={(e) => setForm({ ...form, special_strategy_id: e.target.value })}
              className="border border-gray-300 rounded px-3 py-2 text-sm w-56 focus:outline-none focus:ring-2 focus:ring-blue-400">
              <option value="">Select strategy</option>
              {strategies.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </FormField>
          <FormField label="From">
            <input type="date" value={form.from_date} onChange={(e) => setForm({ ...form, from_date: e.target.value })}
              className="border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400" />
          </FormField>
          <FormField label="To">
            <input type="date" value={form.to_date} onChange={(e) => setForm({ ...form, to_date: e.target.value })}
              className="border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400" />
          </FormField>
          <FormField label="Capital (₹)">
            <input type="number" value={form.initial_capital} onChange={(e) => setForm({ ...form, initial_capital: e.target.value })}
              className="border border-gray-300 rounded px-3 py-2 text-sm w-36 focus:outline-none focus:ring-2 focus:ring-blue-400" />
          </FormField>
          <button onClick={handleRun} disabled={backtestMut.isPending || !form.symbol || !form.special_strategy_id}
            className="px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded hover:bg-blue-700 disabled:opacity-50">
            {backtestMut.isPending ? 'Running…' : 'Run Backtest'}
          </button>
        </div>

        {backtestMut.isError && <ErrBox msg={(backtestMut.error as Error).message} />}

        {latest && (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-2">
            <MetricCard label="Trades" value={String(latest.total_trades)} />
            <MetricCard label="Success %" value={latest.win_rate != null ? `${latest.win_rate.toFixed(1)}%` : '—'} good={latest.win_rate != null && latest.win_rate >= 50} />
            <MetricCard label="Total PnL" value={inr(latest.total_pnl)} good={latest.total_pnl >= 0} />
            <MetricCard label="Avg PnL %" value={latest.avg_pnl_pct != null ? `${latest.avg_pnl_pct >= 0 ? '+' : ''}${latest.avg_pnl_pct.toFixed(2)}%` : '—'} good={latest.avg_pnl_pct != null && latest.avg_pnl_pct >= 0} />
          </div>
        )}
      </div>

      {pastResults.length > 0 && (
        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
          <div className="px-4 py-2 border-b border-gray-100 bg-gray-50">
            <span className="text-sm font-medium text-gray-700">Past Backtests</span>
          </div>
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>{['Symbol', 'Strategy', 'Period', 'Trades', 'Success %', 'Total PnL', 'Avg PnL%', 'Ran At', ''].map((h) => (
                <th key={h} className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">{h}</th>
              ))}</tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {pastResults.map((r) => (
                <>
                  <tr key={r.id} className="hover:bg-gray-50">
                    <td className="px-3 py-2 font-semibold text-gray-800">{r.symbol}</td>
                    <td className="px-3 py-2 text-gray-600">{r.strategy_name ?? '—'}</td>
                    <td className="px-3 py-2 text-gray-500 text-xs whitespace-nowrap">{r.from_date} → {r.to_date}</td>
                    <td className="px-3 py-2 text-center">{r.total_trades}</td>
                    <td className="px-3 py-2">
                      {r.win_rate != null
                        ? <span className={r.win_rate >= 50 ? 'text-green-600 font-medium' : 'text-red-600'}>{r.win_rate.toFixed(1)}%</span>
                        : '—'}
                    </td>
                    <td className="px-3 py-2">
                      <span className={r.total_pnl >= 0 ? 'text-green-600 font-medium' : 'text-red-600 font-medium'}>{inr(r.total_pnl)}</span>
                    </td>
                    <td className="px-3 py-2"><PnlCell v={r.avg_pnl_pct} /></td>
                    <td className="px-3 py-2 text-xs text-gray-400 whitespace-nowrap">
                      {new Date(r.ran_at).toLocaleString('en-IN', { dateStyle: 'short', timeStyle: 'short' })}
                    </td>
                    <td className="px-3 py-2">
                      <button onClick={() => toggleTrades(r.id)} className="text-xs text-blue-500 hover:underline">
                        {expandedId === r.id ? 'Hide' : 'Trades'}
                      </button>
                    </td>
                  </tr>
                  {expandedId === r.id && trades[r.id] && (
                    <tr key={`trades-${r.id}`}>
                      <td colSpan={9} className="bg-gray-50 px-6 py-3">
                        <TradeTable trades={trades[r.id]} />
                      </td>
                    </tr>
                  )}
                </>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

// ── All Stocks Tab ────────────────────────────────────────────────────────────

type PerfKey = keyof SpecialPerformanceRow

function AllStocksTab() {
  const [strategyId, setStrategyId] = useState<string>('')
  const [minTrades, setMinTrades] = useState('1')
  const [hideZero, setHideZero] = useState(true)
  const [sortKey, setSortKey] = useState<PerfKey>('win_rate')
  const [sortDir, setSortDir] = useState<SortDir>('desc')
  const [scanResults, setScanResults] = useState<SpecialPerformanceRow[] | null>(null)
  const [forceConfirm, setForceConfirm] = useState(false)

  const { data: strategies = [] } = useQuery({ queryKey: ['special-strategies'], queryFn: getSpecialStrategies })

  const { data: status, refetch: refetchStatus } = useQuery({
    queryKey: ['special-precompute-status'],
    queryFn: getSpecialPrecomputeStatus,
    refetchInterval: (query) => query.state.data?.is_running ? 2000 : false,
  })

  const precomputeMut = useMutation({
    mutationFn: (force: boolean) => triggerSpecialPrecompute(force),
    onSuccess: () => { setForceConfirm(false); refetchStatus() },
  })

  const loadResults = async () => {
    const sid = strategyId ? Number(strategyId) : undefined
    const mt = hideZero ? Math.max(Number(minTrades), 1) : 0
    const data = await getSpecialScanResults(sid, mt)
    setScanResults(data)
  }

  const toggleSort = (key: PerfKey) => {
    if (sortKey === key) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    else { setSortKey(key); setSortDir('desc') }
  }

  const sorted = scanResults
    ? [...scanResults]
        .filter((r) => !hideZero || (r.total_trades ?? 0) > 0)
        .sort((a, b) => {
          const av = (a[sortKey] as number) ?? (sortDir === 'desc' ? -Infinity : Infinity)
          const bv = (b[sortKey] as number) ?? (sortDir === 'desc' ? -Infinity : Infinity)
          return sortDir === 'asc' ? (av < bv ? -1 : av > bv ? 1 : 0) : (bv < av ? -1 : bv > av ? 1 : 0)
        })
    : []

  const isRunning = status?.is_running ?? false
  const pct = status?.pct_done ?? 0

  return (
    <div className="space-y-4">
      {/* Precompute panel */}
      <div className="bg-white rounded-lg border border-gray-200 p-4 space-y-3">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div>
            <div className="font-medium text-gray-800 text-sm">Strategy Performance Cache</div>
            {status && (
              <div className="text-xs text-gray-500 mt-0.5">
                {status.symbol_strategy_pairs} pairs across {status.symbols_computed} symbols
                {status.last_updated && ` · last updated ${new Date(status.last_updated).toLocaleString('en-IN', { dateStyle: 'short', timeStyle: 'short' })}`}
              </div>
            )}
          </div>
          <div className="flex gap-2">
            <button onClick={() => precomputeMut.mutate(false)} disabled={isRunning || precomputeMut.isPending}
              className="px-3 py-1.5 bg-blue-600 text-white text-xs font-medium rounded hover:bg-blue-700 disabled:opacity-50">
              {isRunning ? 'Running…' : 'Run Precompute'}
            </button>
            {!forceConfirm
              ? <button onClick={() => setForceConfirm(true)} disabled={isRunning}
                  className="px-3 py-1.5 border border-gray-300 text-gray-600 text-xs rounded hover:bg-gray-50 disabled:opacity-50">
                  Force Recompute
                </button>
              : <>
                  <button onClick={() => precomputeMut.mutate(true)} disabled={isRunning}
                    className="px-3 py-1.5 bg-red-600 text-white text-xs font-medium rounded hover:bg-red-700">
                    Confirm Force
                  </button>
                  <button onClick={() => setForceConfirm(false)} className="px-3 py-1.5 border border-gray-300 text-xs rounded">
                    Cancel
                  </button>
                </>
            }
            <button onClick={() => refetchStatus()} className="px-3 py-1.5 border border-gray-300 text-gray-600 text-xs rounded hover:bg-gray-50">
              Refresh
            </button>
          </div>
        </div>

        {isRunning && (
          <div className="space-y-1">
            <div className="flex justify-between text-xs text-gray-600">
              <span>{status?.phase ?? 'running'} — {status?.message}</span>
              <span>{pct.toFixed(1)}%</span>
            </div>
            <div className="w-full bg-gray-200 rounded-full h-2">
              <div className="bg-blue-500 h-2 rounded-full transition-all" style={{ width: `${pct}%` }} />
            </div>
            <div className="text-xs text-gray-500">{status?.done} / {status?.total} pairs</div>
          </div>
        )}

        {status?.error && <ErrBox msg={status.error} />}
      </div>

      {/* Filter bar */}
      <div className="bg-white rounded-lg border border-gray-200 p-4 flex flex-wrap gap-4 items-end">
        <div className="space-y-1">
          <label className="text-xs font-medium text-gray-600">Strategy</label>
          <select value={strategyId} onChange={(e) => setStrategyId(e.target.value)}
            className="border border-gray-300 rounded px-3 py-2 text-sm w-56 focus:outline-none focus:ring-2 focus:ring-blue-400">
            <option value="">All Special Strategies</option>
            {strategies.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </div>
        <div className="space-y-1">
          <label className="text-xs font-medium text-gray-600">Min Trades</label>
          <input type="number" value={minTrades} onChange={(e) => setMinTrades(e.target.value)} min={0}
            className="border border-gray-300 rounded px-3 py-2 text-sm w-24 focus:outline-none focus:ring-2 focus:ring-blue-400" />
        </div>
        <label className="flex items-center gap-2 text-sm text-gray-600 cursor-pointer">
          <input type="checkbox" checked={hideZero} onChange={(e) => setHideZero(e.target.checked)} className="rounded" />
          Hide zero trades
        </label>
        <button onClick={loadResults}
          className="px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded hover:bg-blue-700">
          Load Results
        </button>
        {scanResults !== null && (
          <span className="text-xs text-gray-500 self-end">{sorted.length} rows</span>
        )}
      </div>

      {/* Results table */}
      {scanResults !== null && (
        <div className="bg-white rounded-lg border border-gray-200 overflow-x-auto">
          {sorted.length === 0
            ? <p className="text-gray-500 text-sm p-4">No results match your filters.</p>
            : (
              <table className="w-full text-sm">
                <thead className="bg-gray-50 border-b border-gray-200 sticky top-0">
                  <tr>
                    {([
                      ['symbol', 'Symbol'],
                      ['strategy_name', 'Strategy'],
                      ['total_trades', 'Trades'],
                      ['win_rate', 'Success %'],
                      ['cagr', 'CAGR %'],
                      ['total_pnl', 'Total PnL'],
                      ['avg_pnl_pct', 'Avg PnL%'],
                      ['sharpe_ratio', 'Sharpe'],
                      ['max_drawdown', 'Max DD'],
                      ['profit_factor', 'PF'],
                    ] as [PerfKey, string][]).map(([col, label]) => (
                      <th key={col}
                        onClick={() => toggleSort(col)}
                        className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase cursor-pointer select-none hover:text-gray-800 whitespace-nowrap">
                        {label}{sortKey === col ? (sortDir === 'desc' ? ' ↓' : ' ↑') : ''}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {sorted.map((r, i) => (
                    <tr key={i} className="hover:bg-gray-50">
                      <td className="px-3 py-2 font-semibold text-gray-800">{r.symbol}</td>
                      <td className="px-3 py-2 text-gray-600 whitespace-nowrap">{r.strategy_name}</td>
                      <td className="px-3 py-2 text-center">{r.total_trades}</td>
                      <td className="px-3 py-2">
                        {r.win_rate != null
                          ? <span className={r.win_rate >= 0.5 ? 'text-green-600 font-medium' : 'text-red-600'}>{(r.win_rate * 100).toFixed(1)}%</span>
                          : <span className="text-gray-400">—</span>}
                      </td>
                      <td className="px-3 py-2">
                        {r.cagr != null
                          ? <span className={r.cagr >= 0 ? 'text-green-600 font-medium' : 'text-red-600'}>{r.cagr >= 0 ? '+' : ''}{r.cagr.toFixed(2)}%</span>
                          : <span className="text-gray-400">—</span>}
                      </td>
                      <td className="px-3 py-2 whitespace-nowrap">
                        <span className={r.total_pnl >= 0 ? 'text-green-600 font-medium' : 'text-red-600 font-medium'}>{inr(r.total_pnl)}</span>
                      </td>
                      <td className="px-3 py-2"><PnlCell v={r.avg_pnl_pct} /></td>
                      <td className="px-3 py-2 text-gray-600">
                        {r.sharpe_ratio != null ? r.sharpe_ratio.toFixed(2) : <span className="text-gray-400">—</span>}
                      </td>
                      <td className="px-3 py-2">
                        {r.max_drawdown != null
                          ? <span className="text-red-600">{r.max_drawdown.toFixed(1)}%</span>
                          : <span className="text-gray-400">—</span>}
                      </td>
                      <td className="px-3 py-2">
                        {r.profit_factor != null ? r.profit_factor.toFixed(2) : <span className="text-gray-400">—</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
        </div>
      )}
    </div>
  )
}

// ── Shared helpers ────────────────────────────────────────────────────────────

function FormField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <label className="text-xs font-medium text-gray-600">{label}</label>
      {children}
    </div>
  )
}

function MetricCard({ label, value, good }: { label: string; value: string; good?: boolean }) {
  return (
    <div className="bg-gray-50 rounded p-3">
      <div className="text-xs text-gray-500 mb-1">{label}</div>
      <div className={`text-lg font-bold ${good === true ? 'text-green-600' : good === false ? 'text-red-600' : 'text-gray-800'}`}>
        {value}
      </div>
    </div>
  )
}

function ErrBox({ msg }: { msg: string }) {
  return <div className="bg-red-50 border border-red-200 text-red-700 rounded p-3 text-sm">{msg}</div>
}

function TradeTable({ trades }: { trades: SpecialTrade[] }) {
  if (!trades.length) return <p className="text-sm text-gray-500">No trades.</p>
  return (
    <table className="w-full text-xs">
      <thead>
        <tr className="text-gray-500">
          {['Entry Date', 'Entry ₹', 'Exit Date', 'Exit ₹', 'Qty', 'PnL', 'PnL %', 'Exit', 'Days'].map((h) => (
            <th key={h} className="px-2 py-1 text-left font-medium">{h}</th>
          ))}
        </tr>
      </thead>
      <tbody className="divide-y divide-gray-100">
        {trades.map((t) => (
          <tr key={t.id} className="hover:bg-white">
            <td className="px-2 py-1">{t.entry_date}</td>
            <td className="px-2 py-1">₹{t.entry_price.toFixed(2)}</td>
            <td className="px-2 py-1">{t.exit_date ?? '—'}</td>
            <td className="px-2 py-1">{t.exit_price != null ? `₹${t.exit_price.toFixed(2)}` : '—'}</td>
            <td className="px-2 py-1">{t.quantity}</td>
            <td className="px-2 py-1">
              {t.pnl != null
                ? <span className={t.pnl >= 0 ? 'text-green-600 font-medium' : 'text-red-600 font-medium'}>{inr(t.pnl)}</span>
                : '—'}
            </td>
            <td className="px-2 py-1"><PnlCell v={t.pnl_pct} /></td>
            <td className="px-2 py-1"><ExitBadge reason={t.exit_reason} /></td>
            <td className="px-2 py-1 text-gray-500">{t.holding_days ?? '—'}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
