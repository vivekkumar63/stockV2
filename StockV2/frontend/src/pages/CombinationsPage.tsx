// frontend/src/pages/CombinationsPage.tsx
import { useQuery } from '@tanstack/react-query'
import {
  getRunStatus, getCombinationRankings, getBestCombinations,
  type CombinationSummary,
} from '../api/combinations'

export function CombinationsPage() {
  const { data: status } = useQuery({
    queryKey: ['combinations-status'],
    queryFn: getRunStatus,
    refetchInterval: (query) => query.state.data?.status === 'running' ? 10_000 : false,
  })

  const { data: best } = useQuery({
    queryKey: ['combinations-best'],
    queryFn: getBestCombinations,
    enabled: status?.status === 'complete',
  })

  const { data: rankings = [] } = useQuery({
    queryKey: ['combinations-rankings'],
    queryFn: () => getCombinationRankings(),
    enabled: status?.status === 'complete',
  })

  if (!status || status.status === 'never_run') {
    return (
      <div className="p-6">
        <h1 className="text-2xl font-bold mb-4">Strategy Combinations</h1>
        <p className="text-gray-500">No analysis has been run yet. Check back after Sunday 11 PM.</p>
      </div>
    )
  }

  if (status.status === 'running') {
    return (
      <div className="p-6">
        <h1 className="text-2xl font-bold mb-4">Strategy Combinations</h1>
        <p className="text-gray-500">Analysis in progress…</p>
      </div>
    )
  }

  if (status.status === 'failed') {
    return (
      <div className="p-6">
        <h1 className="text-2xl font-bold mb-4">Strategy Combinations</h1>
        <p className="text-red-500">Last analysis failed. Check back after the next scheduled run.</p>
      </div>
    )
  }

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold">Strategy Combinations</h1>
        <span className="text-sm text-gray-500">
          Last run: {status.last_completed_at
            ? new Date(status.last_completed_at).toLocaleString()
            : 'N/A'}
          {status.combinations_tested != null && ` · ${status.combinations_tested} combos tested`}
        </span>
      </div>

      {/* Best-of cards */}
      {best && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
          <BestCard title="Best Overall" combo={best.overall} />
          <BestCard title="Lowest Risk" combo={best.low_risk} />
          <BestCard title="Highest Growth" combo={best.high_growth} />
          <BestCard title="Most Consistent" combo={best.most_consistent} />
        </div>
      )}

      {/* Rankings table */}
      <div className="bg-white rounded-lg shadow overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b">
            <tr>
              <th className="px-4 py-3 text-left font-medium text-gray-600">Rank</th>
              <th className="px-4 py-3 text-left font-medium text-gray-600">Strategies</th>
              <th className="px-4 py-3 text-right font-medium text-gray-600">OOS CAGR</th>
              <th className="px-4 py-3 text-right font-medium text-gray-600">Max DD</th>
              <th className="px-4 py-3 text-right font-medium text-gray-600">Sharpe</th>
              <th className="px-4 py-3 text-right font-medium text-gray-600">Win Rate</th>
              <th className="px-4 py-3 text-left font-medium text-gray-600">Reliability</th>
            </tr>
          </thead>
          <tbody>
            {rankings.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-gray-400">
                  No combinations available yet.
                </td>
              </tr>
            ) : (
              rankings.map((combo, idx) => (
                <tr key={combo.combination_id} className="border-t hover:bg-gray-50">
                  <td className="px-4 py-3 text-gray-500">{idx + 1}</td>
                  <td className="px-4 py-3 font-medium">{combo.strategies?.join(' + ') ?? combo.name}</td>
                  <td className="px-4 py-3 text-right">{combo.oos_cagr != null ? `${combo.oos_cagr.toFixed(1)}%` : '—'}</td>
                  <td className="px-4 py-3 text-right">{combo.oos_max_drawdown != null ? `${combo.oos_max_drawdown.toFixed(1)}%` : '—'}</td>
                  <td className="px-4 py-3 text-right">{combo.oos_sharpe != null ? combo.oos_sharpe.toFixed(2) : '—'}</td>
                  <td className="px-4 py-3 text-right">{combo.oos_win_rate != null ? `${(combo.oos_win_rate * 100).toFixed(0)}%` : '—'}</td>
                  <td className="px-4 py-3">
                    <ReliabilityBadge label={combo.reliability_label} />
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function BestCard({ title, combo }: { title: string; combo: CombinationSummary | null | undefined }) {
  if (!combo) return (
    <div className="bg-white p-4 rounded-lg shadow border border-dashed border-gray-200">
      <div className="text-sm text-gray-400 mb-1">{title}</div>
      <div className="text-gray-400 text-sm">No data yet</div>
    </div>
  )
  return (
    <div className="bg-white p-4 rounded-lg shadow">
      <div className="text-sm text-gray-500 mb-1">{title}</div>
      <div className="font-semibold text-base mb-1 truncate" title={combo.name}>{combo.name}</div>
      <div className="text-sm text-gray-600 mb-2">
        {combo.strategies?.slice(0, 2).join(' + ')}
        {(combo.strategies?.length ?? 0) > 2 && ` +${(combo.strategies?.length ?? 0) - 2}`}
      </div>
      <div className="text-sm">OOS: <span className="font-medium">{combo.oos_cagr != null ? `${combo.oos_cagr.toFixed(1)}%` : '—'}</span></div>
      <div className="mt-2"><ReliabilityBadge label={combo.reliability_label} /></div>
    </div>
  )
}

const LABEL_COLORS: Record<string, string> = {
  'Strong evidence': 'bg-emerald-100 text-emerald-800',
  'Moderate evidence': 'bg-blue-100 text-blue-800',
  'Weak evidence': 'bg-amber-100 text-amber-800',
  'Likely Overfitted': 'bg-red-100 text-red-800',
  'Insufficient Data': 'bg-gray-100 text-gray-500',
}

function ReliabilityBadge({ label }: { label: string | null | undefined }) {
  if (!label) return <span className="text-gray-400">—</span>
  const color = LABEL_COLORS[label] ?? 'bg-gray-100 text-gray-500'
  return (
    <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${color}`}>
      {label}
    </span>
  )
}
