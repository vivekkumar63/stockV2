import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  getBacktestTrades, listBacktestResults, runBacktest,
  getPrecomputedScan, getScanStatus, triggerPrecompute, getPrecomputeStatus,
  runWalkForward, getWalkForwardResult, resetDb,
  type BacktestResult, type BacktestTrade, type ScanResult, type WalkForwardResult,
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
    stop_loss_pct: '',
    target_pct: '',
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
  const [scanLoading, setScanLoading] = useState(false)
  const [wfRunning, setWfRunning] = useState(false)

  useQuery({
    queryKey: ['backtest', 'scan', 'status'],
    queryFn: getScanStatus,
    refetchInterval: (query) => {
      const data = query.state.data
      return data && !data.ready ? 5000 : false
    },
  })

  const { data: precomputeStatus, refetch: refetchPrecompute } = useQuery({
    queryKey: ['backtest', 'precompute', 'status'],
    queryFn: getPrecomputeStatus,
    refetchInterval: (query) => query.state.data?.is_running ? 3000 : false,
  })
  const [forceConfirm, setForceConfirm] = useState(false)
  const [resetConfirm, setResetConfirm] = useState<'computed' | 'full' | null>(null)
  const [resetResult, setResetResult] = useState<string | null>(null)

  const precomputeMut = useMutation({
    mutationFn: (force: boolean) => triggerPrecompute(force),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['backtest', 'scan', 'status'] })
      queryClient.invalidateQueries({ queryKey: ['backtest', 'precompute', 'status'] })
    },
  })

  const resetMut = useMutation({
    mutationFn: (scope: 'computed' | 'full') => resetDb(scope),
    onSuccess: (data) => {
      setResetResult(data.message)
      queryClient.invalidateQueries({ queryKey: ['backtest', 'precompute', 'status'] })
      queryClient.invalidateQueries({ queryKey: ['backtest', 'results'] })
      queryClient.invalidateQueries({ queryKey: ['backtest', 'scan', 'status'] })
    },
    onError: (err) => setResetResult(`Error: ${String(err)}`),
  })

  const wfMut = useMutation({
    mutationFn: () => runWalkForward(form.symbol, Number(form.strategy_id)),
    onSuccess: () => {
      setWfRunning(true)
      queryClient.invalidateQueries({ queryKey: ['walk-forward', form.symbol, form.strategy_id] })
    },
  })

  const { data: wfResult } = useQuery({
    queryKey: ['walk-forward', form.symbol, form.strategy_id],
    queryFn: () => getWalkForwardResult(form.symbol, Number(form.strategy_id)),
    enabled: wfRunning && !!form.symbol && !!form.strategy_id,
    refetchInterval: (query) => {
      const d = query.state.data
      if (!d || d.status === 'pending') return 3000
      return false
    },
    retry: false,
  })

  useEffect(() => {
    if (wfResult?.status === 'ok' || wfResult?.status === 'failed') {
      setWfRunning(false)
    }
  }, [wfResult?.status])

  const handleScan = async () => {
    setScanLoading(true)
    try {
      const stratId = form.strategy_id ? Number(form.strategy_id) : undefined
      const data = await getPrecomputedScan(stratId)
      setScanResults(data)
    } finally {
      setScanLoading(false)
    }
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
      stop_loss_pct: form.stop_loss_pct ? Number(form.stop_loss_pct) : undefined,
      target_pct: form.target_pct ? Number(form.target_pct) : undefined,
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

          {/* Stop loss override */}
          <div>
            <label className="block text-xs text-gray-500 mb-1">Stop Loss %</label>
            <input
              type="number"
              min="0.5"
              max="50"
              step="0.5"
              placeholder="auto"
              className="border border-gray-300 rounded px-3 py-1.5 text-sm w-24"
              value={form.stop_loss_pct}
              onChange={(e) => setForm((f) => ({ ...f, stop_loss_pct: e.target.value }))}
            />
          </div>

          {/* Target override */}
          <div>
            <label className="block text-xs text-gray-500 mb-1">Target %</label>
            <input
              type="number"
              min="1"
              max="200"
              step="1"
              placeholder="auto"
              className="border border-gray-300 rounded px-3 py-1.5 text-sm w-24"
              value={form.target_pct}
              onChange={(e) => setForm((f) => ({ ...f, target_pct: e.target.value }))}
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
            disabled={scanLoading}
            className="px-4 py-1.5 bg-emerald-600 text-white text-sm rounded hover:bg-emerald-700 disabled:opacity-50"
          >
            {scanLoading ? 'Loading…' : 'Scan All Stocks'}
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
        {precomputeStatus?.is_running && (
          <div className="flex items-center gap-3 bg-amber-50 border border-amber-200 rounded px-3 py-2">
            <span className="text-amber-600 text-sm animate-pulse">
              Precomputing strategy data… ({precomputeStatus.pct_done.toFixed(0)}%)
            </span>
          </div>
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

      {/* Precompute Control Panel */}
      <section className="border border-gray-200 rounded-lg bg-white shadow-sm">
        <div className="px-4 py-3 border-b border-gray-100 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-gray-700">Strategy Performance Cache</h2>
          <div className="flex items-center gap-2">
            <button
              onClick={() => refetchPrecompute()}
              disabled={precomputeStatus?.is_running}
              className="px-3 py-1.5 text-xs bg-gray-100 text-gray-700 border border-gray-300 rounded hover:bg-gray-200 disabled:opacity-50"
            >
              Refresh Status
            </button>
            {!forceConfirm ? (
              <button
                onClick={() => setForceConfirm(true)}
                disabled={precomputeStatus?.is_running}
                className="px-3 py-1.5 text-xs bg-red-600 text-white rounded hover:bg-red-700 disabled:opacity-50"
              >
                Force Recompute
              </button>
            ) : (
              <div className="flex items-center gap-2">
                <span className="text-xs text-red-600">Delete all data and recompute?</span>
                <button
                  onClick={() => { precomputeMut.mutate(true); setForceConfirm(false) }}
                  disabled={precomputeMut.isPending}
                  className="px-2 py-1 text-xs bg-red-600 text-white rounded hover:bg-red-700 disabled:opacity-50"
                >
                  Yes, wipe &amp; recompute
                </button>
                <button
                  onClick={() => setForceConfirm(false)}
                  className="px-2 py-1 text-xs bg-gray-200 text-gray-700 rounded hover:bg-gray-300"
                >
                  Cancel
                </button>
              </div>
            )}
          </div>
        </div>
        <div className="px-4 py-3">
          {precomputeStatus?.is_running ? (
            <p className="text-sm text-amber-600 animate-pulse">
              Precomputing… ({precomputeStatus.pct_done.toFixed(0)}%)
            </p>
          ) : precomputeStatus ? (
            <div className="flex flex-wrap gap-6 text-sm">
              <div>
                <span className="text-gray-500">Pairs computed</span>
                <span className="ml-2 font-semibold text-gray-800">{precomputeStatus.symbol_strategy_pairs.toLocaleString()}</span>
                <span className="ml-1 text-gray-400 text-xs">
                  ({precomputeStatus.symbols_computed} symbols × {precomputeStatus.total_active_strategies} strategies)
                </span>
              </div>
              <div>
                <span className="text-gray-500">Last updated</span>
                <span className="ml-2 font-semibold text-gray-800">
                  {precomputeStatus.last_updated ?? 'never'}
                </span>
              </div>
              {precomputeStatus.error && (
                <div className="text-red-600 text-xs">Error: {precomputeStatus.error}</div>
              )}
            </div>
          ) : (
            <p className="text-sm text-gray-400">Loading…</p>
          )}
        </div>
      </section>

      {/* Database Management */}
      <section className="border border-gray-200 rounded-lg bg-white shadow-sm">
        <div className="px-4 py-3 border-b border-gray-100">
          <h2 className="text-sm font-semibold text-gray-700">Database Management</h2>
          <p className="text-xs text-gray-400 mt-0.5">
            Clear cached or all data to start fresh.
          </p>
        </div>
        <div className="px-4 py-3 space-y-3">
          {/* Computed-only reset */}
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-sm font-medium text-gray-700">Clear Computed Data</p>
              <p className="text-xs text-gray-400">
                Deletes strategy performance, indicator cache, scan cache, backtests, combinations.
                Keeps price data — fast (&lt;1s).
              </p>
            </div>
            {resetConfirm !== 'computed' ? (
              <button
                onClick={() => { setResetConfirm('computed'); setResetResult(null) }}
                disabled={resetMut.isPending}
                className="shrink-0 px-3 py-1.5 text-xs bg-amber-500 text-white rounded hover:bg-amber-600 disabled:opacity-50"
              >
                Clear Computed
              </button>
            ) : (
              <div className="flex items-center gap-2 shrink-0">
                <span className="text-xs text-amber-700">Delete computed data?</span>
                <button
                  onClick={() => { resetMut.mutate('computed'); setResetConfirm(null) }}
                  disabled={resetMut.isPending}
                  className="px-2 py-1 text-xs bg-amber-500 text-white rounded hover:bg-amber-600 disabled:opacity-50"
                >
                  Yes, clear it
                </button>
                <button
                  onClick={() => setResetConfirm(null)}
                  className="px-2 py-1 text-xs bg-gray-200 text-gray-700 rounded hover:bg-gray-300"
                >
                  Cancel
                </button>
              </div>
            )}
          </div>

          <div className="border-t border-gray-100" />

          {/* Full reset */}
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-sm font-medium text-red-700">Full Reset</p>
              <p className="text-xs text-gray-400">
                Wipes ALL data including price history, portfolio, fundamentals.
                Re-seeds strategies and triggers re-download (takes hours).
              </p>
            </div>
            {resetConfirm !== 'full' ? (
              <button
                onClick={() => { setResetConfirm('full'); setResetResult(null) }}
                disabled={resetMut.isPending}
                className="shrink-0 px-3 py-1.5 text-xs bg-red-600 text-white rounded hover:bg-red-700 disabled:opacity-50"
              >
                Full Reset
              </button>
            ) : (
              <div className="flex items-center gap-2 shrink-0">
                <span className="text-xs text-red-700 font-medium">Wipe ALL data? This cannot be undone.</span>
                <button
                  onClick={() => { resetMut.mutate('full'); setResetConfirm(null) }}
                  disabled={resetMut.isPending}
                  className="px-2 py-1 text-xs bg-red-600 text-white rounded hover:bg-red-700 disabled:opacity-50"
                >
                  Yes, wipe everything
                </button>
                <button
                  onClick={() => setResetConfirm(null)}
                  className="px-2 py-1 text-xs bg-gray-200 text-gray-700 rounded hover:bg-gray-300"
                >
                  Cancel
                </button>
              </div>
            )}
          </div>

          {/* Feedback */}
          {resetMut.isPending && (
            <p className="text-xs text-amber-600 animate-pulse">Resetting…</p>
          )}
          {resetResult && (
            <p className={`text-xs ${resetResult.startsWith('Error') ? 'text-red-600' : 'text-green-600'}`}>
              {resetResult}
            </p>
          )}
        </div>
      </section>

      {/* Walk-Forward Analysis */}
      <section className="mt-8 border-t pt-6">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-semibold text-gray-700">Walk-Forward Analysis</h2>
          <div className="flex items-center gap-3">
            {form.symbol && form.strategy_id ? (
              <span className="text-xs text-gray-400">
                {form.symbol} — {strategies?.find(s => s.id === Number(form.strategy_id))?.name ?? `Strategy ${form.strategy_id}`}
              </span>
            ) : (
              <span className="text-xs text-gray-400">Select a symbol and strategy above</span>
            )}
            <button
              onClick={() => wfMut.mutate()}
              disabled={!form.symbol || !form.strategy_id || wfMut.isPending || wfRunning}
              className="px-3 py-1.5 bg-indigo-600 text-white text-sm rounded hover:bg-indigo-700 disabled:opacity-50"
            >
              {wfRunning ? 'Computing…' : wfMut.isPending ? 'Starting…' : 'Run Walk-Forward'}
            </button>
          </div>
        </div>

        {wfRunning && !wfResult && (
          <p className="text-sm text-gray-400">Running out-of-sample analysis… this takes 30–60 seconds.</p>
        )}

        {wfResult?.status === 'failed' && (
          <p className="text-sm text-red-600">Walk-forward failed: {wfResult.error}</p>
        )}

        {wfResult?.status === 'ok' && (
          <WalkForwardResults result={wfResult} />
        )}
      </section>
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

function WalkForwardResults({ result }: { result: WalkForwardResult }) {
  const [showWindows, setShowWindows] = useState(false)
  const pct = (v: number | null) => v != null ? `${Math.round(v * 100)}%` : '—'
  const num = (v: number | null, dp = 2) => v != null ? v.toFixed(dp) : '—'

  return (
    <div className="space-y-4">
      {/* Summary metrics */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <MetricCard label="OOS Win Rate (mean)" value={pct(result.oos_win_rate_mean)} />
        <MetricCard label="OOS Win Rate (std)" value={pct(result.oos_win_rate_std)} />
        <MetricCard label="Consistency Score" value={pct(result.consistency_score)} />
        <MetricCard label="In-Sample Win Rate" value={pct(result.in_sample_win_rate)} />
      </div>
      <p className="text-xs text-gray-400">{result.n_windows} windows · computed {result.computed_at?.slice(0, 10)}</p>

      {/* Windows toggle */}
      <button
        onClick={() => setShowWindows(v => !v)}
        className="text-xs text-indigo-600 hover:underline"
      >
        {showWindows ? '▼ Hide windows' : '▶ Show per-window results'}
      </button>

      {showWindows && (
        <div className="overflow-x-auto rounded-lg border border-gray-200">
          <table className="w-full text-xs">
            <thead className="bg-gray-50 text-gray-500 text-left">
              <tr>
                <th className="px-3 py-2">#</th>
                <th className="px-3 py-2">Train</th>
                <th className="px-3 py-2">Test</th>
                <th className="px-3 py-2 text-right">OOS Win%</th>
                <th className="px-3 py-2 text-right">Trades</th>
                <th className="px-3 py-2 text-right">Avg Return</th>
                <th className="px-3 py-2 text-right">Max DD</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-100">
              {result.windows.map(w => (
                <tr key={w.window_index} className="hover:bg-gray-50">
                  <td className="px-3 py-1.5 text-gray-400">{w.window_index + 1}</td>
                  <td className="px-3 py-1.5 text-gray-500">{w.train_from} → {w.train_to}</td>
                  <td className="px-3 py-1.5 text-gray-500">{w.test_from} → {w.test_to}</td>
                  <td className="px-3 py-1.5 text-right">
                    {w.oos_metrics.win_rate != null ? (
                      <span className={w.oos_metrics.win_rate >= 0.5 ? 'text-green-600 font-medium' : 'text-red-500'}>
                        {Math.round(w.oos_metrics.win_rate * 100)}%
                      </span>
                    ) : '—'}
                  </td>
                  <td className="px-3 py-1.5 text-right text-gray-500">{w.oos_metrics.total_trades}</td>
                  <td className="px-3 py-1.5 text-right text-gray-500">{num(w.oos_metrics.avg_return_pct)}%</td>
                  <td className="px-3 py-1.5 text-right text-gray-500">{num(w.oos_metrics.max_drawdown_pct)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function MetricCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-gray-50 border border-gray-200 rounded-lg p-3">
      <p className="text-xs text-gray-500 mb-0.5">{label}</p>
      <p className="text-lg font-bold text-gray-800">{value}</p>
    </div>
  )
}
