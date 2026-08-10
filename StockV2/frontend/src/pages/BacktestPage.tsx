import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  getBacktestTrades, listBacktestResults, runBacktest,
  type BacktestResult, type BacktestTrade,
} from '../api/backtest'

export function BacktestPage() {
  const queryClient = useQueryClient()
  const [form, setForm] = useState({ symbol: '', from_date: '', to_date: '' })
  const [selectedId, setSelectedId] = useState<number | null>(null)

  const { data: results = [], isError: resultsError } = useQuery({
    queryKey: ['backtest', 'results'],
    queryFn: () => listBacktestResults(),
  })

  const { data: trades = [] } = useQuery({
    queryKey: ['backtest', 'trades', selectedId],
    queryFn: () => getBacktestTrades(selectedId!),
    enabled: selectedId != null,
  })

  const runMut = useMutation({
    mutationFn: runBacktest,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['backtest', 'results'] }),
    onError: (err) => console.error('Backtest failed:', err),
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    runMut.mutate(form)
  }

  const toggleRow = (id: number) => setSelectedId((prev) => (prev === id ? null : id))

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-800">Backtest</h1>

      {/* Run form */}
      <form
        onSubmit={handleSubmit}
        className="bg-white border border-gray-200 rounded-lg p-4 flex flex-wrap gap-4 items-end shadow-sm"
      >
        <div>
          <label className="block text-xs text-gray-500 mb-1">Symbol</label>
          <input
            className="border border-gray-300 rounded px-3 py-1.5 text-sm w-28 uppercase"
            placeholder="e.g. TCS"
            value={form.symbol}
            onChange={(e) => setForm((f) => ({ ...f, symbol: e.target.value.toUpperCase() }))}
            required
          />
        </div>
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
        <button
          type="submit"
          disabled={runMut.isPending}
          className="px-4 py-1.5 bg-blue-600 text-white text-sm rounded hover:bg-blue-700 disabled:opacity-50"
        >
          {runMut.isPending ? 'Running…' : 'Run Backtest'}
        </button>
        {runMut.isError && (
          <span className="text-red-600 text-sm">{String(runMut.error)}</span>
        )}
        {runMut.isSuccess && runMut.data && (
          <span className="text-green-600 text-sm">
            Done — {runMut.data.total_trades} trades, CAGR {runMut.data.cagr?.toFixed(2)}%
          </span>
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
                {results.map((r) => (
                  <ResultRow
                    key={r.id ?? r.result_id}
                    result={r}
                    selected={selectedId === r.id}
                    onClick={() => toggleRow(r.id!)}
                  />
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}

      {/* Trade detail */}
      {selectedId != null && trades.length > 0 && (
        <section>
          <h2 className="text-lg font-semibold text-gray-700 mb-3">
            Trades — result #{selectedId}
          </h2>
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
        </section>
      )}
    </div>
  )
}

function ResultRow({
  result: r, selected, onClick,
}: { result: BacktestResult; selected: boolean; onClick: () => void }) {
  return (
    <tr
      onClick={onClick}
      className={`cursor-pointer hover:bg-blue-50 transition-colors ${selected ? 'bg-blue-50' : ''}`}
    >
      <td className="px-4 py-2 font-semibold">{r.symbol}</td>
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
      <td className="px-4 py-2">{t.entry_price.toFixed(2)}</td>
      <td className="px-4 py-2">{t.exit_price.toFixed(2)}</td>
      <td className={`px-4 py-2 font-semibold ${pos ? 'text-green-600' : 'text-red-600'}`}>
        {t.pnl.toFixed(2)}
      </td>
      <td className={`px-4 py-2 ${pos ? 'text-green-600' : 'text-red-600'}`}>
        {t.pnl_pct.toFixed(2)}%
      </td>
      <td className="px-4 py-2 text-gray-500">{t.exit_reason}</td>
    </tr>
  )
}
