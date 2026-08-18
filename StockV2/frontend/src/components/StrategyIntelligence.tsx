import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  getFalseSignalStats,
  getStrategyCorrelations,
  getStrategyRanking,
} from '../api/intelligence'

const HIGH_CORR_THRESHOLD = 0.70

export function StrategyIntelligence({ regime }: { regime: string | undefined }) {
  const [open, setOpen] = useState(false)

  const { data: ranking = [], isLoading: rankLoading } = useQuery({
    queryKey: ['intelligence', 'strategy-ranking', regime],
    queryFn:  () => getStrategyRanking(regime),
    enabled:  open,
  })

  const { data: falseStats = [], isLoading: falseLoading } = useQuery({
    queryKey: ['intelligence', 'false-signal-stats'],
    queryFn:  getFalseSignalStats,
    enabled:  open,
  })

  const { data: correlations = [], isLoading: corrLoading } = useQuery({
    queryKey: ['intelligence', 'correlations'],
    queryFn:  getStrategyCorrelations,
    enabled:  open,
  })

  const highCorr = correlations
    .filter(p => p.correlation > HIGH_CORR_THRESHOLD)
    .sort((a, b) => b.correlation - a.correlation)

  const regimeLabel = regime?.replace(/_/g, ' ') ?? 'Current Regime'

  return (
    <section>
      <button
        onClick={() => setOpen(v => !v)}
        className="flex items-center gap-2 text-sm font-semibold text-gray-600 hover:text-gray-800 mb-3"
      >
        <span className="text-gray-400 text-xs">{open ? '▼' : '▶'}</span>
        Strategy Intelligence
        {regime && (
          <span className="text-xs font-normal text-gray-400">— {regimeLabel}</span>
        )}
      </button>

      {open && (
        <div className="space-y-5">

          {/* Strategy Ranking */}
          <div>
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
              Strategy Ranking — {regimeLabel}
            </h3>
            {rankLoading ? (
              <p className="text-gray-400 text-sm">Loading…</p>
            ) : ranking.length === 0 ? (
              <p className="text-gray-400 text-sm">
                No regime performance data yet. Run the regime backfill to populate.
              </p>
            ) : (
              <div className="overflow-x-auto rounded-lg border border-gray-200">
                <table className="w-full text-xs">
                  <thead className="bg-gray-50 text-gray-500 text-left">
                    <tr>
                      <th className="px-3 py-2 text-center">Rank</th>
                      <th className="px-3 py-2">Strategy</th>
                      <th className="px-3 py-2 text-right">Regime Win%</th>
                      <th className="px-3 py-2 text-right">Overall Win%</th>
                      <th className="px-3 py-2 text-right">Trades</th>
                    </tr>
                  </thead>
                  <tbody className="bg-white divide-y divide-gray-100">
                    {ranking.map(r => (
                      <tr key={r.strategy_id} className="hover:bg-gray-50">
                        <td className="px-3 py-1.5 text-center text-gray-400">#{r.rank}</td>
                        <td className="px-3 py-1.5">{r.strategy_name}</td>
                        <td className="px-3 py-1.5 text-right">
                          {r.regime_win_rate != null ? (
                            <span className={
                              r.regime_win_rate >= 0.6  ? 'text-green-600 font-medium' :
                              r.regime_win_rate >= 0.4  ? 'text-yellow-600' :
                              'text-red-500'
                            }>
                              {Math.round(r.regime_win_rate * 100)}%
                            </span>
                          ) : '—'}
                        </td>
                        <td className="px-3 py-1.5 text-right text-gray-500">
                          {r.overall_win_rate != null
                            ? `${Math.round(r.overall_win_rate * 100)}%`
                            : '—'}
                        </td>
                        <td className="px-3 py-1.5 text-right text-gray-400">{r.regime_trades}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* False Signal Rates + Correlations side by side */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">

            {/* False Signal Rates */}
            <div>
              <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
                False Signal Rates
              </h3>
              {falseLoading ? (
                <p className="text-gray-400 text-sm">Loading…</p>
              ) : falseStats.length === 0 ? (
                <p className="text-gray-400 text-sm">
                  No outcome data yet — needs 15d+ of signal history.
                </p>
              ) : (
                <div className="overflow-x-auto rounded-lg border border-gray-200">
                  <table className="w-full text-xs">
                    <thead className="bg-gray-50 text-gray-500 text-left">
                      <tr>
                        <th className="px-3 py-2">Strategy</th>
                        <th className="px-3 py-2 text-right">False Rate</th>
                        <th className="px-3 py-2 text-right">Signals</th>
                      </tr>
                    </thead>
                    <tbody className="bg-white divide-y divide-gray-100">
                      {falseStats.map(s => (
                        <tr key={s.strategy_id} className="hover:bg-gray-50">
                          <td className="px-3 py-1.5 truncate max-w-[160px]" title={s.strategy_name}>
                            {s.strategy_name}
                          </td>
                          <td className="px-3 py-1.5 text-right">
                            {s.false_signal_rate != null ? (
                              <span className={`font-medium ${
                                s.false_signal_rate <= 0.30 ? 'text-green-600' :
                                s.false_signal_rate <= 0.50 ? 'text-amber-600' :
                                'text-red-600'
                              }`}>
                                {Math.round(s.false_signal_rate * 100)}%
                              </span>
                            ) : (
                              <span className="text-gray-300">—</span>
                            )}
                          </td>
                          <td className="px-3 py-1.5 text-right text-gray-400">
                            {s.total_evaluated}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            {/* High Correlation Pairs */}
            <div>
              <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
                High Correlation Pairs
              </h3>
              <p className="text-xs text-gray-400 mb-2">
                High correlation = fewer independent confirmations
              </p>
              {corrLoading ? (
                <p className="text-gray-400 text-sm">Loading…</p>
              ) : highCorr.length === 0 ? (
                <p className="text-gray-400 text-sm">
                  {`No high-correlation pairs (threshold: ${HIGH_CORR_THRESHOLD}). Run correlation compute first.`}
                </p>
              ) : (
                <div className="overflow-x-auto rounded-lg border border-gray-200">
                  <table className="w-full text-xs">
                    <thead className="bg-gray-50 text-gray-500 text-left">
                      <tr>
                        <th className="px-3 py-2">Strategy A</th>
                        <th className="px-3 py-2">Strategy B</th>
                        <th className="px-3 py-2 text-right">Corr</th>
                      </tr>
                    </thead>
                    <tbody className="bg-white divide-y divide-gray-100">
                      {highCorr.map(p => (
                        <tr key={`${p.strategy_id_a}-${p.strategy_id_b}`} className="hover:bg-gray-50">
                          <td className="px-3 py-1.5 truncate max-w-[120px]" title={p.strategy_name_a}>
                            {p.strategy_name_a}
                          </td>
                          <td className="px-3 py-1.5 truncate max-w-[120px]" title={p.strategy_name_b}>
                            {p.strategy_name_b}
                          </td>
                          <td className="px-3 py-1.5 text-right font-medium text-amber-600">
                            {p.correlation.toFixed(2)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

          </div>
        </div>
      )}
    </section>
  )
}
