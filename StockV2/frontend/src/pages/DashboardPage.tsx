import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { enterPosition, getPortfolioSummary } from '../api/portfolio'
import { getTodaySignals, type Signal } from '../api/signals'
import { inr } from '../utils/format'

export function DashboardPage() {
  const queryClient = useQueryClient()

  const { data: summary, isLoading: loadingSummary, isError: summaryError } = useQuery({
    queryKey: ['portfolio', 'summary'],
    queryFn: getPortfolioSummary,
  })

  const { data: signals = [], isLoading: loadingSignals } = useQuery({
    queryKey: ['signals', 'today'],
    queryFn: getTodaySignals,
  })

  const enterMut = useMutation({
    mutationFn: ({ signalId, price }: { signalId: number; price: number }) =>
      enterPosition(signalId, price),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['portfolio'] }),
    onError: (err) => console.error('Failed to enter position:', err),
  })

  const buySignals = signals.filter((s) => s.signal_type === 'BUY')

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-800">Dashboard</h1>

      {/* Summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {loadingSummary ? (
          <p className="col-span-4 text-gray-400">Loading…</p>
        ) : summaryError ? (
          <p className="col-span-4 text-red-600 text-sm">Failed to load portfolio summary.</p>
        ) : summary ? (
          <>
            <Card label="Paper Capital" value={inr(summary.paper_capital)} />
            <Card label="Invested" value={inr(summary.total_invested)} />
            <Card label="Available" value={inr(summary.cash_available)} />
            <Card label="Positions" value={`${summary.open_positions} / ${summary.max_positions}`} />
          </>
        ) : null}
      </div>

      {/* Today's BUY signals */}
      <section>
        <h2 className="text-lg font-semibold text-gray-700 mb-3">Today's BUY Signals</h2>
        {loadingSignals ? (
          <p className="text-gray-400">Loading…</p>
        ) : buySignals.length === 0 ? (
          <p className="text-gray-500 py-4">No BUY signals today.</p>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-gray-200">
            <table className="w-full text-sm">
              <thead className="bg-gray-100 text-gray-600 text-left">
                <tr>
                  <th className="px-4 py-2" scope="col">Symbol</th>
                  <th className="px-4 py-2" scope="col">Strategy</th>
                  <th className="px-4 py-2" scope="col">Confidence</th>
                  <th className="px-4 py-2" scope="col">Price</th>
                  <th className="px-4 py-2" scope="col">Stop Loss</th>
                  <th className="px-4 py-2" scope="col">Target</th>
                  <th className="px-4 py-2" scope="col" />
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-100">
                {buySignals.map((sig) => (
                  <SignalRow
                    key={sig.id}
                    sig={sig}
                    onEnter={() => enterMut.mutate({ signalId: sig.id, price: sig.price_at_signal })}
                    entering={enterMut.isPending && enterMut.variables?.signalId === sig.id}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
        {enterMut.isError && (
          <p className="text-red-600 text-sm mt-2">
            Failed to enter position: {String(enterMut.error)}
          </p>
        )}
      </section>
    </div>
  )
}

function Card({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-white border border-gray-200 rounded-lg p-4 shadow-sm">
      <p className="text-xs text-gray-500 mb-1">{label}</p>
      <p className="text-xl font-bold text-gray-800">{value}</p>
    </div>
  )
}

function SignalRow({ sig, onEnter, entering }: { sig: Signal; onEnter: () => void; entering: boolean }) {
  const conf = sig.confidence_score
  return (
    <tr className="hover:bg-gray-50">
      <td className="px-4 py-2 font-semibold">{sig.symbol}</td>
      <td className="px-4 py-2 text-gray-500">{sig.strategy_name}</td>
      <td className="px-4 py-2">
        {conf != null ? (
          <span className={`px-2 py-0.5 rounded text-xs font-semibold ${conf >= 0.8 ? 'bg-green-100 text-green-700' : 'bg-yellow-100 text-yellow-700'}`}>
            {(conf * 100).toFixed(0)}%
          </span>
        ) : '—'}
      </td>
      <td className="px-4 py-2">{sig.price_at_signal != null ? inr(sig.price_at_signal) : '—'}</td>
      <td className="px-4 py-2 text-red-600">{sig.suggested_stop_loss != null ? inr(sig.suggested_stop_loss) : '—'}</td>
      <td className="px-4 py-2 text-green-600">{sig.suggested_target != null ? inr(sig.suggested_target) : '—'}</td>
      <td className="px-4 py-2">
        <button
          onClick={onEnter}
          disabled={entering}
          aria-label={`Enter position for ${sig.symbol}`}
          className="px-3 py-1 bg-blue-600 text-white text-xs rounded hover:bg-blue-700 disabled:opacity-50"
        >
          Enter
        </button>
      </td>
    </tr>
  )
}
