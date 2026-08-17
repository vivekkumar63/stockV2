import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { getStrategies } from '../api/strategies'
import { runLiveScan, type LiveScanResult } from '../api/signals'
import { StrategyCard } from '../components/StrategyCard'

type SortKey = keyof LiveScanResult
type SortDir = 'asc' | 'desc'

function OppScoreBadge({ score, grade }: { score: number | null; grade: string | null }) {
  if (score == null) return <span className="text-gray-300 text-sm">—</span>
  const color =
    score >= 80 ? 'bg-emerald-100 text-emerald-700' :
    score >= 65 ? 'bg-green-100 text-green-700' :
    score >= 50 ? 'bg-yellow-100 text-yellow-700' :
    score >= 35 ? 'bg-orange-100 text-orange-700' :
    'bg-red-100 text-red-600'
  return (
    <span
      className={`px-2 py-0.5 rounded text-xs font-semibold ${color}`}
      title={`Opportunity score: ${score}/100 (grade ${grade})`}
    >
      {score} {grade}
    </span>
  )
}

export function ScannerPage() {
  const [strategyId, setStrategyId] = useState<string>('')
  const [signalType, setSignalType] = useState<string>('')
  const [limit, setLimit] = useState<number>(200)
  const [results, setResults] = useState<LiveScanResult[] | null>(null)
  const [sortKey, setSortKey] = useState<SortKey>('confidence')
  const [sortDir, setSortDir] = useState<SortDir>('desc')

  const { data: strategies = [] } = useQuery({
    queryKey: ['strategies'],
    queryFn: getStrategies,
  })

  const scanMut = useMutation({
    mutationFn: runLiveScan,
    onSuccess: (data) => setResults(data),
  })

  const handleScan = () => {
    setResults(null)
    scanMut.mutate({
      strategy_id: strategyId ? Number(strategyId) : undefined,
      signal_type: signalType ? (signalType as 'BUY' | 'SELL') : undefined,
      limit,
    })
  }

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortKey(key)
      setSortDir('desc')
    }
  }

  const sorted = results
    ? [...results].sort((a, b) => {
        const av = a[sortKey] ?? 0
        const bv = b[sortKey] ?? 0
        const cmp = av < bv ? -1 : av > bv ? 1 : 0
        return sortDir === 'asc' ? cmp : -cmp
      })
    : []

  const Th = ({ label, col }: { label: string; col: SortKey }) => (
    <th
      className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase cursor-pointer select-none hover:text-gray-800"
      onClick={() => toggleSort(col)}
    >
      {label}
      {sortKey === col ? (sortDir === 'desc' ? ' ↓' : ' ↑') : ''}
    </th>
  )

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-800">Strategy Scanner</h1>
      <p className="text-sm text-gray-500">
        Run any strategy against all stocks in real-time and see which ones have an active signal today.
      </p>

      {/* Controls */}
      <div className="bg-white rounded-lg shadow p-5 flex flex-wrap gap-4 items-end">
        <div className="flex flex-col gap-1 w-full sm:w-auto">
          <label className="text-xs font-medium text-gray-600">Strategy</label>
          <select
            className="border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-blue-400 w-full sm:min-w-[220px]"
            value={strategyId}
            onChange={(e) => setStrategyId(e.target.value)}
          >
            <option value="">All Strategies</option>
            {strategies.map((s: { id: number; name: string }) => (
              <option key={s.id} value={s.id}>{s.name}</option>
            ))}
          </select>
        </div>

        <div className="flex flex-col gap-1 w-full sm:w-auto">
          <label className="text-xs font-medium text-gray-600">Signal Type</label>
          <select
            className="border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-blue-400 w-full sm:w-auto"
            value={signalType}
            onChange={(e) => setSignalType(e.target.value)}
          >
            <option value="">BUY + SELL</option>
            <option value="BUY">BUY only</option>
            <option value="SELL">SELL only</option>
          </select>
        </div>

        <div className="flex flex-col gap-1 w-full sm:w-auto">
          <label className="text-xs font-medium text-gray-600">Stocks to scan</label>
          <select
            className="border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-blue-400 w-full sm:w-auto"
            value={limit}
            onChange={(e) => setLimit(Number(e.target.value))}
          >
            <option value={100}>Top 100</option>
            <option value={200}>Top 200</option>
            <option value={500}>All (~500)</option>
          </select>
        </div>

        <button
          className="bg-blue-600 hover:bg-blue-700 text-white px-5 py-2 rounded text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed w-full sm:w-auto"
          onClick={handleScan}
          disabled={scanMut.isPending}
        >
          {scanMut.isPending ? 'Scanning…' : 'Run Scan'}
        </button>
      </div>

      {strategyId && (
        <StrategyCard strategyId={Number(strategyId)} />
      )}

      {/* Status */}
      {scanMut.isPending && (
        <div className="bg-blue-50 border border-blue-200 rounded p-4 text-sm text-blue-700">
          Scanning {limit} stocks — this takes 10–60 seconds depending on your VM speed…
        </div>
      )}

      {scanMut.isError && (
        <div className="bg-red-50 border border-red-200 rounded p-4 text-sm text-red-700">
          Scan failed: {(scanMut.error as Error)?.message}
        </div>
      )}

      {/* Results */}
      {results !== null && (
        <div className="bg-white rounded-lg shadow">
          <div className="px-5 py-3 border-b border-gray-100 flex items-center justify-between">
            <span className="font-semibold text-gray-700">
              {sorted.length > 0
                ? `${sorted.length} signal${sorted.length !== 1 ? 's' : ''} found`
                : 'No active signals found'}
            </span>
            {sorted.length > 0 && (
              <span className="text-xs text-gray-400">Click column header to sort</span>
            )}
          </div>

          {sorted.length > 0 && (
            <div className="overflow-x-auto rounded-b-lg">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 border-b border-gray-200">
                  <tr>
                    <Th label="Symbol" col="symbol" />
                    <Th label="Strategy" col="strategy_name" />
                    <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Signal</th>
                    <Th label="Confidence" col="confidence" />
                    <Th label="Price ₹" col="price" />
                    <Th label="Stop Loss %" col="stop_loss_pct" />
                    <Th label="Target %" col="target_pct" />
                    <Th label="Hold Days" col="holding_days" />
                    <Th label="History Win%" col="historical_win_rate" />
                    <Th label="Opp Score" col="opportunity_score" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {sorted.map((r, i) => (
                    <tr key={i} className="hover:bg-gray-50">
                      <td className="px-3 py-2 font-mono font-semibold text-gray-800">{r.symbol}</td>
                      <td className="px-3 py-2 text-gray-600 max-w-[200px] truncate" title={r.strategy_name}>
                        {r.strategy_name}
                      </td>
                      <td className="px-3 py-2">
                        <span className={`inline-block px-2 py-0.5 rounded text-xs font-bold ${
                          r.signal_type === 'BUY'
                            ? 'bg-green-100 text-green-700'
                            : r.signal_type === 'SELL'
                            ? 'bg-red-100 text-red-700'
                            : 'bg-yellow-100 text-yellow-700'
                        }`}>
                          {r.signal_type}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-gray-700">{(r.confidence * 100).toFixed(1)}%</td>
                      <td className="px-3 py-2 text-gray-700">₹{r.price.toLocaleString('en-IN', { maximumFractionDigits: 2 })}</td>
                      <td className="px-3 py-2 text-red-600">
                        {r.stop_loss_pct != null ? `${r.stop_loss_pct.toFixed(1)}%` : '—'}
                      </td>
                      <td className="px-3 py-2 text-green-600">
                        {r.target_pct != null ? `${r.target_pct.toFixed(1)}%` : '—'}
                      </td>
                      <td className="px-3 py-2 text-gray-500">
                        {r.holding_days != null ? `${r.holding_days}d` : '—'}
                      </td>
                      <td className="px-3 py-2">
                        {r.historical_win_rate != null ? (
                          <span className={`font-medium ${r.historical_win_rate >= 0.6 ? 'text-green-600' : r.historical_win_rate >= 0.4 ? 'text-yellow-600' : 'text-red-500'}`}>
                            {(r.historical_win_rate * 100).toFixed(0)}%
                          </span>
                        ) : (
                          <span className="text-gray-300">—</span>
                        )}
                      </td>
                      <td className="px-3 py-2">
                        <OppScoreBadge score={r.opportunity_score} grade={r.opportunity_grade} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
