import { useQuery, useQueryClient } from '@tanstack/react-query'
import { getPortfolioSummary } from '../api/portfolio'
import { getMarketRegime, getTopOpportunities } from '../api/intelligence'
import { RegimeBanner } from '../components/RegimeBanner'
import { TopOpportunities } from '../components/TopOpportunities'
import { StrategyIntelligence } from '../components/StrategyIntelligence'
import { inr } from '../utils/format'

const POLL_MS = 3 * 60 * 1000

export function DashboardPage() {
  const queryClient = useQueryClient()

  const { data: summary, isLoading: loadingSummary, isError: summaryError } = useQuery({
    queryKey: ['portfolio', 'summary'],
    queryFn: getPortfolioSummary,
  })

  const { data: regime, isLoading: regimeLoading } = useQuery({
    queryKey: ['market', 'regime'],
    queryFn: getMarketRegime,
    refetchInterval: POLL_MS,
    refetchIntervalInBackground: false,
  })

  const {
    data: opportunities = [],
    isLoading: oppsLoading,
    isError: oppsError,
    isFetching: oppsFetching,
    dataUpdatedAt,
  } = useQuery({
    queryKey: ['intelligence', 'top-opportunities'],
    queryFn: () => getTopOpportunities(20),
    refetchInterval: POLL_MS,
    refetchIntervalInBackground: false,
  })

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-800">Dashboard</h1>

      {/* Regime banner */}
      {!regimeLoading && regime && <RegimeBanner regime={regime} />}

      {/* Portfolio summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {loadingSummary ? (
          <p className="col-span-4 text-gray-400">Loading…</p>
        ) : summaryError ? (
          <p className="col-span-4 text-red-600 text-sm">Failed to load portfolio summary.</p>
        ) : summary ? (
          <>
            <Card label="Paper Capital"  value={inr(summary.paper_capital)} />
            <Card label="Invested"       value={inr(summary.total_invested)} />
            <Card label="Available"      value={inr(summary.cash_available)} />
            <Card label="Positions"      value={`${summary.open_positions} / ${summary.max_positions}`} />
          </>
        ) : null}
      </div>

      {/* Top Opportunities */}
      <section>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-semibold text-gray-700">Top Opportunities</h2>
          <div className="flex items-center gap-2">
            {dataUpdatedAt > 0 && (
              <span className="text-xs text-gray-400">
                updated {new Date(dataUpdatedAt).toLocaleTimeString('en-IN', {
                  hour: '2-digit', minute: '2-digit',
                })}
              </span>
            )}
            <button
              onClick={() =>
                queryClient.invalidateQueries({ queryKey: ['intelligence', 'top-opportunities'] })
              }
              disabled={oppsFetching}
              className="text-xs px-2 py-1 rounded border border-gray-300 text-gray-500 hover:text-gray-700 hover:border-gray-400 disabled:opacity-40"
              title="Refresh opportunities"
            >
              {oppsFetching ? '↻ …' : '↻ Refresh'}
            </button>
          </div>
        </div>
        <TopOpportunities
          opportunities={opportunities}
          isLoading={oppsLoading}
          isError={oppsError}
        />
      </section>

      {/* Strategy Intelligence (collapsed by default) */}
      <StrategyIntelligence regime={regime?.regime} />
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
