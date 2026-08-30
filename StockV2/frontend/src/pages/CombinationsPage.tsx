// frontend/src/pages/CombinationsPage.tsx
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getRunStatus, getCombinationRankings, getBestCombinations, triggerAnalysis, resetStuckRuns,
  type CombinationSummary,
} from '../api/combinations'
import { getScanStatus, triggerPrecompute, getPrecomputeStatus } from '../api/backtest'

export function CombinationsPage() {
  const queryClient = useQueryClient()

  const { data: status } = useQuery({
    queryKey: ['combinations-status'],
    queryFn: getRunStatus,
    refetchInterval: (query) => query.state.data?.status === 'running' ? 10_000 : false,
  })

  const { data: scanStatus } = useQuery({
    queryKey: ['backtest', 'scan', 'status'],
    queryFn: getScanStatus,
  })

  const { data: precomputeStatus } = useQuery({
    queryKey: ['backtest', 'precompute', 'status'],
    queryFn: getPrecomputeStatus,
    refetchInterval: (query) => query.state.data?.is_running ? 3000 : 10_000,
  })

  const precomputeMut = useMutation({
    mutationFn: () => triggerPrecompute(false),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['backtest', 'scan', 'status'] })
      queryClient.invalidateQueries({ queryKey: ['backtest', 'precompute', 'status'] })
    },
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

  const trigger = useMutation({
    mutationFn: triggerAnalysis,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['combinations-status'] }),
  })

  const resetStuck = useMutation({
    mutationFn: resetStuckRuns,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['combinations-status'] }),
  })

  const isRunning = status?.status === 'running' || trigger.isPending

  const precomputeBanner = precomputeStatus?.is_running ? (
    <div className="mb-4 flex items-center gap-3 bg-amber-50 border border-amber-200 rounded px-3 py-2 text-sm text-amber-700">
      <span className="animate-pulse">
        Computing strategy performance data: {precomputeStatus.done}/{precomputeStatus.total} strategies
        ({precomputeStatus.pct_done.toFixed(0)}%) — Run Analysis will work once complete.
      </span>
    </div>
  ) : scanStatus && !scanStatus.ready ? (
    <div className="mb-4 flex items-center gap-3 bg-amber-50 border border-amber-200 rounded px-3 py-2 text-sm">
      <span className="text-amber-700">
        {scanStatus.pending} strategies missing performance data. Run Analysis may fail until precompute completes.
      </span>
      <button
        onClick={() => precomputeMut.mutate()}
        disabled={precomputeMut.isPending}
        className="px-2 py-1 text-xs bg-amber-600 text-white rounded hover:bg-amber-700 disabled:opacity-50 whitespace-nowrap"
      >
        {precomputeMut.isPending ? 'Starting…' : 'Precompute Now'}
      </button>
    </div>
  ) : null

  const runButton = (
    <button
      onClick={() => trigger.mutate()}
      disabled={isRunning}
      className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
    >
      {trigger.isPending ? 'Starting…' : 'Run Analysis'}
    </button>
  )

  if (!status || status.status === 'never_run') {
    return (
      <div className="p-6">
        <div className="flex justify-between items-center mb-4">
          <h1 className="text-2xl font-bold">Strategy Combinations</h1>
          {runButton}
        </div>
        {precomputeBanner}
        <p className="text-gray-500">No analysis has been run yet.</p>
        {trigger.isError && (
          <p className="text-red-500 text-sm mt-2">{(trigger.error as Error).message}</p>
        )}
      </div>
    )
  }

  if (status.status === 'running') {
    return (
      <div className="p-6">
        <div className="flex justify-between items-center mb-4">
          <h1 className="text-2xl font-bold">Strategy Combinations</h1>
          <div className="flex gap-2">
            {runButton}
            <button
              onClick={() => resetStuck.mutate()}
              disabled={resetStuck.isPending}
              title="Use if analysis has been stuck for more than a few minutes"
              className="px-3 py-1.5 text-sm border border-red-300 text-red-600 rounded hover:bg-red-50 disabled:opacity-50"
            >
              {resetStuck.isPending ? 'Resetting…' : 'Reset Stuck'}
            </button>
          </div>
        </div>
        {precomputeBanner}
        <p className="text-gray-500">Analysis in progress… (if this doesn't complete, click Reset Stuck)</p>
      </div>
    )
  }

  if (status.status === 'failed') {
    return (
      <div className="p-6">
        <div className="flex justify-between items-center mb-4">
          <h1 className="text-2xl font-bold">Strategy Combinations</h1>
          {runButton}
        </div>
        {precomputeBanner}
        <p className="text-red-500 font-medium">Last analysis failed.</p>
        {status.error_message && (
          <p className="text-red-400 text-sm mt-1 font-mono bg-red-50 px-3 py-2 rounded border border-red-200">
            {status.error_message}
          </p>
        )}
        {trigger.isError && (
          <p className="text-red-500 text-sm mt-2">{(trigger.error as Error).message}</p>
        )}
      </div>
    )
  }

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="flex justify-between items-center mb-4">
        <h1 className="text-2xl font-bold">Strategy Combinations</h1>
        <div className="flex items-center gap-3">
          {trigger.isError && (
            <span className="text-red-500 text-sm">{(trigger.error as Error).message}</span>
          )}
          <span className="text-sm text-gray-500">
            Last run: {status.last_completed_at
              ? new Date(status.last_completed_at).toLocaleString()
              : 'N/A'}
            {status.combinations_tested != null && ` · ${status.combinations_tested} combos tested`}
          </span>
          {runButton}
        </div>
      </div>

      {precomputeBanner}

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
