import { useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  getBacktestTrades, listBacktestResults, runBacktest, runScan,
  type BacktestResult, type BacktestTrade, type ScanResult,
} from '../api/backtest'
import { getStrategies, getStockList } from '../api/strategies'
import { inr } from '../utils/format'

const resultId = (r: BacktestResult): number | undefined => r.id ?? r.result_id

function isoDate(d: Date) {
  return d.toISOString().slice(0, 10)
}

function datePresets() {
  const today = new Date()
  const ytd = new Date(today.getFullYear(), 0, 1)
  const y1 = new Date(today); y1.setFullYear(today.getFullYear() - 1)
  const y3 = new Date(today); y3.setFullYear(today.getFullYear() - 3)
  const y5 = new Date(today); y5.setFullYear(today.getFullYear() - 5)
  return [
    { label: 'YTD', from: isoDate(ytd) },
    { label: '1Y', from: isoDate(y1) },
    { label: '3Y', from: isoDate(y3) },
    { label: '5Y', from: isoDate(y5) },
  ]
}

const PRESETS = datePresets()
const TODAY = isoDate(new Date())

export function BacktestPage() {
  const queryClient = useQueryClient()
  const [form, setForm] = useState({
    symbol: '',
    from_date: PRESETS[1].from,
    to_date: TODAY,
    strategy_id: '' as string,
    initial_capital: '500000',
  })
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [symbolSearch, setSymbolSearch] = useState('')
  const [showDropdown, setShowDropdown] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const { data: strategies = [] } = useQuery({
    queryKey: ['strategies'],
    queryFn: getStrategies,
  })

  const { data: stocks = [] } = useQuery({
    queryKey: ['stocks'],
    queryFn: getStockList,
    staleTime: 5 * 60 * 1000,
  })

  const { data: results = [], isError: resultsError } = useQuery({
    queryKey: ['backtest', 'results'],
    queryFn: () => listBacktestResults(),
  })

  const { data: trades = [], isFetching: tradesFetching } = useQuery({
    queryKey: ['backtest', 'trades', selectedId],
    queryFn: () => getBacktestTrades(selectedId!),
    enabled: selectedId != null,
    placeholderData: undefined,
  })

  const runMut = useMutation({
    mutationFn: runBacktest,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['backtest', 'results'] }),
    onError: (err) => console.error('Backtest failed:', err),
  })

  const [scanResults, setScanResults] = useState<ScanResult[] | null>(null)
  const [scanHideZero, setScanHideZero] = useState(true)
  const [scanSort, setScanSort] = useState<keyof ScanResult>('cagr')
  const [scanDir, setScanDir] = useState<'asc' | 'desc'>('desc')

  const scanMut = useMutation({
    mutationFn: runScan,
    onSuccess: (data) => setScanResults(data),
    onError: (err) => console.error('Scan failed:', err),
  })

  const handleScan = () => {
    setScanResults(null)
    scanMut.mutate({
      from_date: form.from_date,
      to_date: form.to_date,
      initial_capital: Number(form.initial_capital) || 500000,
    })
  }

  const toggleScanSort = (key: keyof ScanResult) => {
    if (scanSort === key) setScanDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    else { setScanSort(key); setScanDir('desc') }
  }

  const filteredStocks = symbolSearch.length >= 1
    ? stocks.filter(
        (s) =>
          s.symbol.startsWith(symbolSearch.toUpperCase()) ||
          s.name?.toLowerCase().includes(symbolSearch.toLowerCase()),
      ).slice(0, 10)
    : []

  const selectSymbol = (sym: string) => {
    setForm((f) => ({ ...f, symbol: sym }))
    setSymbolSearch(sym)
    setShowDropdown(false)
    inputRef.current?.blur()
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.symbol) return
    runMut.mutate({
      symbol: form.symbol,
      from_date: form.from_date,
      to_date: form.to_date,
      strategy_id: form.strategy_id ? Number(form.strategy_id) : undefined,
      initial_capital: Number(form.initial_capital) || 500000,
    })
  }

  const toggleRow = (id: number) => setSelectedId((prev) => (prev === id ? null : id))

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-800">Backtest</h1>

      {/* Run form */}
      <form
        onSubmit={handleSubmit}
        className="bg-white border border-gray-200 rounded-lg p-4 shadow-sm space-y-4"
      >
        <div className="flex flex-wrap gap-4 items-end">
          {/* Symbol autocomplete */}
          <div className="relative">
            <label className="block text-xs text-gray-500 mb-1">Symbol</label>
            <input
              ref={inputRef}
              className="border border-gray-300 rounded px-3 py-1.5 text-sm w-40"
              placeholder="e.g. TCS, Infosys…"
              value={symbolSearch}
              onChange={(e) => {
                setSymbolSearch(e.target.value)
                setForm((f) => ({ ...f, symbol: e.target.value.toUpperCase() }))
                setShowDropdown(true)
              }}
              onFocus={() => setShowDropdown(true)}
              onBlur={() => setTimeout(() => setShowDropdown(false), 150)}
              autoComplete="off"
              required
            />
            {showDropdown && filteredStocks.length > 0 && (
              <ul className="absolute z-20 mt-1 w-64 bg-white border border-gray-200 rounded-lg shadow-lg max-h-52 overflow-y-auto text-sm">
                {filteredStocks.map((s) => (
                  <li
                    key={s.symbol}
                    onMouseDown={() => selectSymbol(s.symbol)}
                    className="px-3 py-2 cursor-pointer hover:bg-blue-50 flex justify-between"
                  >
                    <span className="font-semibold">{s.symbol}</span>
                    <span className="text-gray-400 truncate ml-2 text-xs">{s.name}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* Strategy dropdown */}
          <div>
            <label className="block text-xs text-gray-500 mb-1">Strategy</label>
            <select
              className="border border-gray-300 rounded px-3 py-1.5 text-sm w-48"
              value={form.strategy_id}
              onChange={(e) => setForm((f) => ({ ...f, strategy_id: e.target.value }))}
            >
              <option value="">All strategies</option>
              {strategies.filter((s) => s.is_active).map((s) => (
                <option key={s.id} value={s.id}>{s.name}</option>
              ))}
            </select>
          </div>

          {/* Date range */}
          <div>
            <label className="block text-xs text-gray-500 mb-1">From</label>
            <input
              type="date"
              className="border border-gray-300 rounded px-3 py-1.5 text-sm"
              value={form.from_date}
              onChange={(e) => setForm((f) => ({ ...f, from_date: e.target.value }))}
              required
            />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">To</label>
            <input
              type="date"
              className="border border-gray-300 rounded px-3 py-1.5 text-sm"
              value={form.to_date}
              onChange={(e) => setForm((f) => ({ ...f, to_date: e.target.value }))}
              required
            />
          </div>

          {/* Initial capital */}
          <div>
            <label className="block text-xs text-gray-500 mb-1">Capital (₹)</label>
            <input
              type="number"
              min="10000"
              step="10000"
              className="border border-gray-300 rounded px-3 py-1.5 text-sm w-36"
              value={form.initial_capital}
              onChange={(e) => setForm((f) => ({ ...f, initial_capital: e.target.value }))}
            />
          </div>

          <button
            type="submit"
            disabled={runMut.isPending || !form.symbol}
            className="px-4 py-1.5 bg-blue-600 text-white text-sm rounded hover:bg-blue-700 disabled:opacity-50"
          >
            {runMut.isPending ? 'Running…' : 'Run Backtest'}
          </button>

          <button
            type="button"
            onClick={handleScan}
            disabled={scanMut.isPending}
            className="px-4 py-1.5 bg-emerald-600 text-white text-sm rounded hover:bg-emerald-700 disabled:opacity-50"
          >
            {scanMut.isPending ? 'Scanning…' : 'Scan All Stocks'}
          </button>
        </div>

        {/* Date presets */}
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-400">Quick range:</span>
          {PRESETS.map((p) => (
            <button
              key={p.label}
              type="button"
              onClick={() => setForm((f) => ({ ...f, from_date: p.from, to_date: TODAY }))}
              className={`px-2 py-0.5 text-xs rounded border transition-colors ${
                form.from_date === p.from && form.to_date === TODAY
                  ? 'border-blue-500 bg-blue-50 text-blue-700'
                  : 'border-gray-300 text-gray-500 hover:border-gray-400'
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>

        {/* Feedback */}
        {runMut.isError && (
          <p className="text-red-600 text-sm">{String(runMut.error)}</p>
        )}
        {runMut.isSuccess && runMut.data && (
          <p className="text-green-600 text-sm">
            Done — {runMut.data.total_trades} trades · CAGR {runMut.data.cagr?.toFixed(2)}% · Sharpe {runMut.data.sharpe_ratio?.toFixed(2) ?? '—'}
          </p>
        )}
        {scanMut.isPending && (
          <p className="text-emerald-600 text-sm animate-pulse">Scanning all stocks — this may take 20–60 s…</p>
        )}
        {scanMut.isError && (
          <p className="text-red-600 text-sm">{String(scanMut.error)}</p>
        )}
      </form>

      {/* Results table */}
      {resultsError ? (
        <p className="text-red-600 text-sm">Failed to load backtest results.</p>
      ) : results.length > 0 ? (
        <section>
          <h2 className="text-lg font-semibold text-gray-700 mb-3">
            Results <span className="text-sm font-normal text-gray-400">(click row for trades)</span>
          </h2>
          <div className="overflow-x-auto rounded-lg border border-gray-200">
            <table className="w-full text-sm">
              <thead className="bg-gray-100 text-gray-600 text-left">
                <tr>
                  <th scope="col" className="px-4 py-2">Symbol</th>
                  <th scope="col" className="px-4 py-2">Strategy</th>
                  <th scope="col" className="px-4 py-2">From</th>
                  <th scope="col" className="px-4 py-2">To</th>
                  <th scope="col" className="px-4 py-2">Trades</th>
                  <th scope="col" className="px-4 py-2">Win%</th>
                  <th scope="col" className="px-4 py-2">CAGR</th>
                  <th scope="col" className="px-4 py-2">Sharpe</th>
                  <th scope="col" className="px-4 py-2">Max DD</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-100">
                {results.map((r) => {
                  const rid = resultId(r)
                  const stratName = strategies.find((s) => s.id === r.strategy_id)?.name
                  return (
                    <ResultRow
                      key={rid ?? `${r.symbol}-${r.from_date}`}
                      result={r}
                      strategyName={stratName}
                      selected={selectedId === rid}
                      onClick={() => rid != null ? toggleRow(rid) : undefined}
                    />
                  )
                })}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}

      {/* Scan results */}
      {scanResults != null && (
        <section>
          <div className="flex items-center gap-4 mb-3">
            <h2 className="text-lg font-semibold text-gray-700">
              Scan Results
              <span className="ml-2 text-sm font-normal text-gray-400">
                ({scanResults.filter((r) => !scanHideZero || r.total_trades > 0).length} rows)
              </span>
            </h2>
            <label className="flex items-center gap-1.5 text-sm text-gray-500 cursor-pointer">
              <input
                type="checkbox"
                checked={scanHideZero}
                onChange={(e) => setScanHideZero(e.target.checked)}
                className="rounded"
              />
              Hide zero-trade rows
            </label>
          </div>
          <ScanResultsTable
            results={scanResults}
            hideZero={scanHideZero}
            sortKey={scanSort}
            sortDir={scanDir}
            onSort={toggleScanSort}
          />
        </section>
      )}

      {/* Trade detail */}
      {selectedId != null && (
        <section>
          <h2 className="text-lg font-semibold text-gray-700 mb-3">
            Trades — result #{selectedId}
          </h2>
          {tradesFetching ? (
            <p className="text-gray-400">Loading trades…</p>
          ) : trades.length > 0 ? (
            <div className="overflow-x-auto rounded-lg border border-gray-200">
              <table className="w-full text-sm">
                <thead className="bg-gray-100 text-gray-600 text-left">
                  <tr>
                    <th scope="col" className="px-4 py-2">Entry</th>
                    <th scope="col" className="px-4 py-2">Exit</th>
                    <th scope="col" className="px-4 py-2">Qty</th>
                    <th scope="col" className="px-4 py-2">Entry ₹</th>
                    <th scope="col" className="px-4 py-2">Exit ₹</th>
                    <th scope="col" className="px-4 py-2">P&amp;L</th>
                    <th scope="col" className="px-4 py-2">P&amp;L %</th>
                    <th scope="col" className="px-4 py-2">Days</th>
                    <th scope="col" className="px-4 py-2">Reason</th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-100">
                  {trades.map((t) => (
                    <TradeRow key={t.id} trade={t} />
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-gray-500">No trades for this result.</p>
          )}
        </section>
      )}
    </div>
  )
}

type SortKey = keyof ScanResult

function SortTh({
  label, sortKey, active, dir, onSort,
}: { label: string; sortKey: SortKey; active: boolean; dir: 'asc' | 'desc'; onSort: (k: SortKey) => void }) {
  return (
    <th
      scope="col"
      onClick={() => onSort(sortKey)}
      className="px-4 py-2 cursor-pointer select-none hover:bg-gray-200 whitespace-nowrap"
    >
      {label}
      {active && <span className="ml-1 text-blue-500">{dir === 'desc' ? '▼' : '▲'}</span>}
    </th>
  )
}

function ScanResultsTable({
  results, hideZero, sortKey, sortDir, onSort,
}: {
  results: ScanResult[]
  hideZero: boolean
  sortKey: SortKey
  sortDir: 'asc' | 'desc'
  onSort: (k: SortKey) => void
}) {
  const visible = results
    .filter((r) => !hideZero || r.total_trades > 0)
    .sort((a, b) => {
      const av = a[sortKey] ?? (sortDir === 'desc' ? -Infinity : Infinity)
      const bv = b[sortKey] ?? (sortDir === 'desc' ? -Infinity : Infinity)
      if (av < bv) return sortDir === 'desc' ? 1 : -1
      if (av > bv) return sortDir === 'desc' ? -1 : 1
      return 0
    })

  if (visible.length === 0) return <p className="text-gray-500 text-sm">No results to display.</p>

  return (
    <div className="overflow-x-auto rounded-lg border border-gray-200">
      <table className="w-full text-sm">
        <thead className="bg-gray-100 text-gray-600 text-left">
          <tr>
            <SortTh label="Symbol" sortKey="symbol" active={sortKey === 'symbol'} dir={sortDir} onSort={onSort} />
            <SortTh label="Strategy" sortKey="strategy_name" active={sortKey === 'strategy_name'} dir={sortDir} onSort={onSort} />
            <SortTh label="CAGR %" sortKey="cagr" active={sortKey === 'cagr'} dir={sortDir} onSort={onSort} />
            <SortTh label="P&L ₹" sortKey="total_pnl" active={sortKey === 'total_pnl'} dir={sortDir} onSort={onSort} />
            <SortTh label="Trades" sortKey="total_trades" active={sortKey === 'total_trades'} dir={sortDir} onSort={onSort} />
            <SortTh label="Win %" sortKey="win_rate" active={sortKey === 'win_rate'} dir={sortDir} onSort={onSort} />
            <SortTh label="Sharpe" sortKey="sharpe_ratio" active={sortKey === 'sharpe_ratio'} dir={sortDir} onSort={onSort} />
            <SortTh label="Max DD" sortKey="max_drawdown" active={sortKey === 'max_drawdown'} dir={sortDir} onSort={onSort} />
            <SortTh label="PF" sortKey="profit_factor" active={sortKey === 'profit_factor'} dir={sortDir} onSort={onSort} />
          </tr>
        </thead>
        <tbody className="bg-white divide-y divide-gray-100">
          {visible.map((r) => {
            const pos = (r.cagr ?? 0) >= 0
            return (
              <tr key={`${r.symbol}-${r.strategy_id}`} className="hover:bg-blue-50 transition-colors">
                <td className="px-4 py-2 font-semibold">{r.symbol}</td>
                <td className="px-4 py-2 text-gray-500 text-xs">{r.strategy_name}</td>
                <td className={`px-4 py-2 font-semibold ${pos ? 'text-green-600' : 'text-red-600'}`}>
                  {r.cagr != null ? `${r.cagr.toFixed(2)}%` : '—'}
                </td>
                <td className={`px-4 py-2 ${r.total_pnl >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                  {inr(r.total_pnl)}
                </td>
                <td className="px-4 py-2">{r.total_trades}</td>
                <td className="px-4 py-2">
                  {r.win_rate != null ? `${(r.win_rate * 100).toFixed(1)}%` : '—'}
                </td>
                <td className="px-4 py-2">{r.sharpe_ratio != null ? r.sharpe_ratio.toFixed(2) : '—'}</td>
                <td className="px-4 py-2 text-red-600">
                  {r.max_drawdown != null ? `${r.max_drawdown.toFixed(2)}%` : '—'}
                </td>
                <td className="px-4 py-2">{r.profit_factor != null ? r.profit_factor.toFixed(2) : '—'}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function ResultRow({
  result: r, strategyName, selected, onClick,
}: { result: BacktestResult; strategyName?: string; selected: boolean; onClick: () => void }) {
  return (
    <tr
      onClick={onClick}
      className={`cursor-pointer hover:bg-blue-50 transition-colors ${selected ? 'bg-blue-50' : ''}`}
    >
      <td className="px-4 py-2 font-semibold">{r.symbol}</td>
      <td className="px-4 py-2 text-gray-500 text-xs">{strategyName ?? 'All'}</td>
      <td className="px-4 py-2 text-gray-500">{r.from_date}</td>
      <td className="px-4 py-2 text-gray-500">{r.to_date}</td>
      <td className="px-4 py-2">{r.total_trades}</td>
      <td className="px-4 py-2">{r.win_rate != null ? `${(r.win_rate * 100).toFixed(1)}%` : '—'}</td>
      <td className={`px-4 py-2 font-semibold ${(r.cagr ?? 0) >= 0 ? 'text-green-600' : 'text-red-600'}`}>
        {r.cagr != null ? `${r.cagr.toFixed(2)}%` : '—'}
      </td>
      <td className="px-4 py-2">{r.sharpe_ratio != null ? r.sharpe_ratio.toFixed(2) : '—'}</td>
      <td className="px-4 py-2 text-red-600">{r.max_drawdown != null ? `${r.max_drawdown.toFixed(2)}%` : '—'}</td>
    </tr>
  )
}

function TradeRow({ trade: t }: { trade: BacktestTrade }) {
  const pos = t.pnl >= 0
  return (
    <tr className="hover:bg-gray-50">
      <td className="px-4 py-2">{t.entry_date}</td>
      <td className="px-4 py-2">{t.exit_date}</td>
      <td className="px-4 py-2">{t.quantity}</td>
      <td className="px-4 py-2">{inr(t.entry_price)}</td>
      <td className="px-4 py-2">{inr(t.exit_price)}</td>
      <td className={`px-4 py-2 font-semibold ${pos ? 'text-green-600' : 'text-red-600'}`}>
        {inr(t.pnl)}
      </td>
      <td className={`px-4 py-2 ${pos ? 'text-green-600' : 'text-red-600'}`}>
        {t.pnl_pct.toFixed(2)}%
      </td>
      <td className="px-4 py-2 text-gray-400">{t.holding_days}</td>
      <td className="px-4 py-2 text-gray-500">{t.exit_reason}</td>
    </tr>
  )
}
