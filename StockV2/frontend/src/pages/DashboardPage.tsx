import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { enterPosition, getPortfolioSummary } from '../api/portfolio'
import { getTodaySignals, type Signal } from '../api/signals'
import { inr } from '../utils/format'

const SIGNALS_POLL_MS = 3 * 60 * 1000 // re-fetch every 3 minutes

export function DashboardPage() {
  const queryClient = useQueryClient()

  const { data: summary, isLoading: loadingSummary, isError: summaryError } = useQuery({
    queryKey: ['portfolio', 'summary'],
    queryFn: getPortfolioSummary,
  })

  const {
    data: signals = [],
    isLoading: loadingSignals,
    isError: signalsError,
    isFetching: fetchingSignals,
    dataUpdatedAt,
  } = useQuery({
    queryKey: ['signals', 'today'],
    queryFn: getTodaySignals,
    refetchInterval: SIGNALS_POLL_MS,
    refetchIntervalInBackground: false,
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
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-baseline gap-3">
            <h2 className="text-lg font-semibold text-gray-700">BUY Signals</h2>
            {!loadingSignals && buySignals.length > 0 && (() => {
              const d = buySignals[0].signal_date
              const today = new Date().toISOString().slice(0, 10)
              return d !== today ? (
                <span className="text-xs text-amber-600 font-medium">
                  from {d} — scans at 9:00, 9:15, 12:00, 15:00 IST
                </span>
              ) : (
                <span className="text-xs text-gray-400">today</span>
              )
            })()}
          </div>
          <div className="flex items-center gap-2">
            {dataUpdatedAt > 0 && (
              <span className="text-xs text-gray-400">
                updated {new Date(dataUpdatedAt).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })}
              </span>
            )}
            <button
              onClick={() => queryClient.invalidateQueries({ queryKey: ['signals', 'today'] })}
              disabled={fetchingSignals}
              className="text-xs px-2 py-1 rounded border border-gray-300 text-gray-500 hover:text-gray-700 hover:border-gray-400 disabled:opacity-40"
              title="Refresh signals"
            >
              {fetchingSignals ? '↻ …' : '↻ Refresh'}
            </button>
          </div>
        </div>
        {loadingSignals ? (
          <p className="text-gray-400">Loading…</p>
        ) : signalsError ? (
          <p className="text-red-600 text-sm">Failed to load signals.</p>
        ) : buySignals.length === 0 ? (
          <p className="text-gray-500 py-4">No BUY signals yet — scans run at 9:00, 9:15, 12:00, 15:00 IST on trading days.</p>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-gray-200">
            <table className="w-full text-sm">
              <thead className="bg-gray-100 text-gray-600 text-left">
                <tr>
                  <th className="px-4 py-2 w-6" scope="col" />
                  <th className="px-4 py-2" scope="col">Symbol</th>
                  <th className="px-4 py-2" scope="col">Strategy</th>
                  <th className="px-4 py-2" scope="col">Confidence</th>
                  <th className="px-4 py-2" scope="col">Price</th>
                  <th className="px-4 py-2" scope="col">Stop Loss</th>
                  <th className="px-4 py-2" scope="col">Target</th>
                  <th className="px-4 py-2" scope="col">Hold</th>
                  <th className="px-4 py-2" scope="col" />
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-100">
                {buySignals.map((sig) => (
                  <SignalRow
                    key={sig.id}
                    sig={sig}
                    onEnter={() =>
                      enterMut.mutate({
                        signalId: sig.id,
                        price: sig.latest_price ?? sig.price_at_signal,
                      })
                    }
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

function parseConditions(reasoningJson: string | null): { met: string[]; failed: string[] } {
  if (!reasoningJson) return { met: [], failed: [] }
  try {
    const parsed = JSON.parse(reasoningJson)
    return {
      met: parsed.conditions_met ?? [],
      failed: parsed.conditions_failed ?? [],
    }
  } catch {
    return { met: [], failed: [] }
  }
}

function ConfidenceBadge({ score, conditions }: { score: number | null; conditions: string[] }) {
  if (score == null) return <span className="text-gray-400">—</span>
  const pct = Math.round(score * 100)
  const color = pct >= 80 ? 'bg-green-100 text-green-700' : 'bg-yellow-100 text-yellow-700'

  // Build tooltip: list the conditions that drove this score
  const tooltip =
    conditions.length > 0
      ? `Confidence ${pct}%:\n${conditions.map((c) => `• ${c}`).join('\n')}`
      : `Confidence score: ${pct}%`

  return (
    <span
      className={`px-2 py-0.5 rounded text-xs font-semibold cursor-default ${color}`}
      title={tooltip}
    >
      {pct}%
    </span>
  )
}

function SignalRow({
  sig,
  onEnter,
  entering,
}: {
  sig: Signal
  onEnter: () => void
  entering: boolean
}) {
  const [expanded, setExpanded] = useState(false)
  const { met, failed } = parseConditions(sig.reasoning_json)

  const displayPrice = sig.latest_price ?? sig.price_at_signal
  const priceStale =
    sig.latest_price != null &&
    sig.latest_price_date != null &&
    sig.latest_price_date !== sig.signal_date

  return (
    <>
      <tr className="hover:bg-gray-50">
        <td className="px-2 py-2 text-center">
          <button
            onClick={() => setExpanded((v) => !v)}
            aria-label={expanded ? 'Collapse reasoning' : 'Expand reasoning'}
            className="text-gray-400 hover:text-gray-600 text-xs font-bold w-5 h-5 flex items-center justify-center rounded border border-gray-200 hover:border-gray-400"
          >
            {expanded ? '−' : '+'}
          </button>
        </td>
        <td className="px-4 py-2 font-semibold">{sig.symbol}</td>
        <td className="px-4 py-2 text-gray-500 max-w-[160px] truncate" title={sig.strategy_name}>
          {sig.strategy_name}
        </td>
        <td className="px-4 py-2">
          <ConfidenceBadge score={sig.confidence_score} conditions={met} />
        </td>
        <td className="px-4 py-2">
          <span>{displayPrice != null ? inr(displayPrice) : '—'}</span>
          {priceStale && (
            <span className="block text-xs text-gray-400">{sig.latest_price_date}</span>
          )}
        </td>
        <td className="px-4 py-2 text-red-600">
          {sig.suggested_stop_loss != null ? inr(sig.suggested_stop_loss) : '—'}
        </td>
        <td className="px-4 py-2 text-green-600">
          {sig.suggested_target != null ? inr(sig.suggested_target) : '—'}
        </td>
        <td className="px-4 py-2 text-gray-500">
          {sig.holding_period_days != null ? `${sig.holding_period_days}d` : '—'}
        </td>
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
      {expanded && (
        <tr className="bg-blue-50">
          <td colSpan={9} className="px-6 py-3">
            <div className="text-xs space-y-1">
              <p className="font-semibold text-gray-700 mb-1">
                Why {sig.symbol}? — {sig.strategy_name}
              </p>
              {met.length > 0 && (
                <ul className="space-y-0.5">
                  {met.map((c, i) => (
                    <li key={i} className="flex items-start gap-1.5 text-green-700">
                      <span className="mt-0.5">✓</span>
                      <span>{c}</span>
                    </li>
                  ))}
                </ul>
              )}
              {failed.length > 0 && (
                <ul className="mt-1 space-y-0.5">
                  {failed.map((c, i) => (
                    <li key={i} className="flex items-start gap-1.5 text-gray-400">
                      <span className="mt-0.5">✗</span>
                      <span>{c}</span>
                    </li>
                  ))}
                </ul>
              )}
              {sig.expected_upside_pct != null && (
                <p className="mt-1 text-blue-600">
                  Expected upside: {sig.expected_upside_pct.toFixed(1)}%
                  {sig.holding_period_days != null && ` over ~${sig.holding_period_days} days`}
                </p>
              )}
              <p className="mt-1 text-gray-400 italic">
                Confidence {sig.confidence_score != null ? Math.round(sig.confidence_score * 100) : '—'}%
                — based on how strongly the conditions above are satisfied
              </p>
            </div>
          </td>
        </tr>
      )}
    </>
  )
}
