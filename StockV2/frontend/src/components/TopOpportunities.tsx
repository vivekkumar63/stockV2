import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { enterPosition } from '../api/portfolio'
import type { TopOpportunity, OpportunityBreakdown, SignalExplanation } from '../api/intelligence'
import { getSignalExplanation } from '../api/intelligence'
import { inr } from '../utils/format'

const REGIME_PILL: Record<string, string> = {
  STRONG_BULL:     'bg-emerald-100 text-emerald-700',
  BULL:            'bg-green-100 text-green-700',
  SIDEWAYS:        'bg-amber-100 text-amber-700',
  BEAR:            'bg-red-100 text-red-700',
  STRONG_BEAR:     'bg-rose-100 text-rose-700',
  HIGH_VOLATILITY: 'bg-purple-100 text-purple-700',
}

const REGIME_SHORT: Record<string, string> = {
  STRONG_BULL: 'S.Bull', BULL: 'Bull', SIDEWAYS: 'Side',
  BEAR: 'Bear', STRONG_BEAR: 'S.Bear', HIGH_VOLATILITY: 'Hi.Vol',
}

function SectorBadge({ sector }: { sector: string | null }) {
  if (!sector) return null
  return (
    <span
      className="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium bg-blue-50 text-blue-600"
      title={`Sector: ${sector}`}
    >
      {sector}
    </span>
  )
}

type ComponentKey = keyof OpportunityBreakdown

const SCORE_COMPONENTS: { key: ComponentKey; label: string; weight: number }[] = [
  { key: 'historical_win_rate',   label: 'Historical Win Rate',   weight: 20 },
  { key: 'strategy_confidence',   label: 'Strategy Confidence',   weight: 16 },
  { key: 'regime_alignment',      label: 'Regime Alignment',      weight: 14 },
  { key: 'mtf_alignment',         label: 'MTF Alignment',         weight: 13 },
  { key: 'sector_health',          label: 'Sector Health',          weight: 10 },
  { key: 'volume',                label: 'Volume',                weight:  9 },
  { key: 'sr_context',            label: 'S/R Context',           weight:  7 },
  { key: 'ml_signal_probability', label: 'ML Probability',        weight:  7 },
  { key: 'regime_strategy',       label: 'Regime-Strategy',       weight:  4 },
]

function parseConditions(json: string | null): { met: string[]; failed: string[] } {
  if (!json) return { met: [], failed: [] }
  try {
    const p = JSON.parse(json)
    return { met: p.conditions_met ?? [], failed: p.conditions_failed ?? [] }
  } catch {
    return { met: [], failed: [] }
  }
}

function GradeBadge({ score, grade }: { score: number; grade: string }) {
  const color =
    score >= 80 ? 'bg-emerald-100 text-emerald-700' :
    score >= 65 ? 'bg-green-100 text-green-700' :
    score >= 50 ? 'bg-yellow-100 text-yellow-700' :
    score >= 35 ? 'bg-orange-100 text-orange-700' :
    'bg-red-100 text-red-600'
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-semibold ${color}`}
          title={`Opportunity score: ${score}/100 (grade ${grade})`}>
      {score} {grade}
    </span>
  )
}

function ScoreBreakdown({ opp }: { opp: TopOpportunity }) {
  const bd = opp.breakdown
  return (
    <div className="space-y-1.5">
      {SCORE_COMPONENTS.map(({ key, label, weight }) => {
        const raw = bd[key]
        const val = typeof raw === 'number' ? raw : null
        const pct = val != null ? Math.round(val * 100) : null
        return (
          <div key={key} className="flex items-center gap-2 text-xs">
            <span className="w-36 text-gray-600 text-right shrink-0">{label}</span>
            <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
              {pct != null && (
                <div className="h-full bg-blue-400 rounded-full" style={{ width: `${pct}%` }} />
              )}
            </div>
            <span className="w-10 text-gray-400 text-right">{pct != null ? `${pct}%` : '—'}</span>
            <span className="w-4 text-gray-300 text-right text-xs">{weight}</span>
          </div>
        )
      })}
      {opp.false_signal_rate != null && (
        <p className="text-xs mt-1 text-gray-500">
          False Signal Rate: {Math.round(opp.false_signal_rate * 100)}%
          {opp.false_signal_rate <= 0.30 ? ' ✓' : opp.false_signal_rate <= 0.50 ? ' ⚠' : ' ✗'}
        </p>
      )}
    </div>
  )
}

function OpportunityRow({
  opp, rank, entering, enterError, onEnter,
}: {
  opp: TopOpportunity; rank: number; entering: boolean
  enterError: string | null; onEnter: () => void
}) {
  const [expanded, setExpanded] = useState(false)
  const [showExplain, setShowExplain] = useState(false)
  const { data: explanation, isLoading: explainLoading, isError: explainError } = useQuery({
    queryKey: ['signal-explanation', opp.signal_id],
    queryFn: () => getSignalExplanation(opp.signal_id),
    enabled: showExplain,
    staleTime: 6 * 60 * 60 * 1000, // 6 hours — matches server-side cache TTL
  })
  const { met, failed } = parseConditions(opp.reasoning_json)
  const regClass = REGIME_PILL[opp.regime] ?? 'bg-gray-100 text-gray-600'
  const regShort = REGIME_SHORT[opp.regime] ?? opp.regime

  return (
    <>
      <tr className="hover:bg-gray-50">
        <td className="px-2 py-2 text-center text-xs text-gray-400">{rank}</td>
        <td className="px-2 py-2 text-center">
          <button
            onClick={() => setExpanded(v => !v)}
            aria-label={expanded ? 'Collapse' : 'Expand'}
            className="text-gray-400 hover:text-gray-600 text-xs font-bold w-5 h-5 flex items-center justify-center rounded border border-gray-200 hover:border-gray-400"
          >
            {expanded ? '−' : '+'}
          </button>
        </td>
        <td className="px-4 py-2">
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className="font-semibold">{opp.symbol}</span>
            <SectorBadge sector={opp.sector_name} />
            {opp.confluence_count >= 2 && (
              <span
                className={`px-1.5 py-0.5 rounded text-xs font-medium ${
                  opp.confluence_count >= 3
                    ? 'bg-green-100 text-green-700'
                    : 'bg-amber-100 text-amber-700'
                }`}
                title={`${opp.confluence_count} strategies agree on this signal`}
              >
                {opp.confluence_count} strats
              </span>
            )}
            {opp.days_to_earnings != null && opp.days_to_earnings <= 5 && (
              <span
                className="px-1.5 py-0.5 rounded text-xs font-medium bg-orange-100 text-orange-700"
                title="Stock reports earnings soon — entering before results is high risk"
              >
                ⚠️ Earnings in {opp.days_to_earnings}d
              </span>
            )}
          </div>
        </td>
        <td className="px-4 py-2"><GradeBadge score={opp.score} grade={opp.grade} /></td>
        <td className="px-4 py-2">
          <span className={`px-2 py-0.5 rounded text-xs font-medium ${regClass}`}>{regShort}</span>
        </td>
        <td className="px-4 py-2 text-xs text-gray-500">
          {opp.mtf_alignment != null ? `${Math.round(opp.mtf_alignment * 100)}%` : '—'}
        </td>
        <td className="px-4 py-2 text-xs text-gray-500">
          {opp.ml_probability != null ? `${Math.round(opp.ml_probability * 100)}%` : '—'}
        </td>
        <td className="px-4 py-2">{inr(opp.price_at_signal)}</td>
        <td className="px-4 py-2 text-red-600">{opp.stop_loss_price != null ? inr(opp.stop_loss_price) : '—'}</td>
        <td className="px-4 py-2 text-green-600">{opp.target_price != null ? inr(opp.target_price) : '—'}</td>
        <td className="px-4 py-2 text-gray-500 text-xs">
          {opp.rr != null ? `1:${opp.rr.toFixed(1)}` : '—'}
        </td>
        <td className="px-4 py-2 text-gray-500 text-xs max-w-[140px] truncate" title={opp.strategy_name}>
          {opp.strategy_name}
        </td>
        <td className="px-4 py-2">
          <div className="flex items-center gap-1.5">
            <button
              onClick={onEnter}
              disabled={entering}
              aria-label={`Enter position for ${opp.symbol}`}
              className="px-3 py-1 bg-blue-600 text-white text-xs rounded hover:bg-blue-700 disabled:opacity-50"
            >
              Enter
            </button>
            <button
              onClick={() => setShowExplain(v => !v)}
              aria-label={`AI explanation for ${opp.symbol}`}
              className={`px-2 py-1 text-xs rounded border ${
                showExplain
                  ? 'bg-violet-100 text-violet-700 border-violet-300'
                  : 'bg-gray-50 text-gray-500 border-gray-300 hover:border-violet-300 hover:text-violet-600'
              }`}
              title="Get AI analysis"
            >
              AI
            </button>
          </div>
          {enterError && (
            <p className="text-red-600 text-xs mt-0.5">{enterError}</p>
          )}
        </td>
      </tr>
      {expanded && (
        <tr className="bg-blue-50">
          <td colSpan={13} className="px-6 py-4">
            <div className="grid grid-cols-2 gap-6 text-xs">
              <div>
                <p className="font-semibold text-gray-700 mb-2">
                  Score Breakdown — {opp.score}/100 ({opp.grade})
                </p>
                <ScoreBreakdown opp={opp} />
              </div>
              <div>
                <p className="font-semibold text-gray-700 mb-2">
                  Why {opp.symbol}? — {opp.strategy_name}
                </p>
                {met.length > 0 && (
                  <ul className="space-y-0.5 mb-1">
                    {met.map((c) => (
                      <li key={c} className="flex items-start gap-1.5 text-green-700">
                        <span className="mt-0.5">✓</span><span>{c}</span>
                      </li>
                    ))}
                  </ul>
                )}
                {failed.length > 0 && (
                  <ul className="space-y-0.5">
                    {failed.map((c) => (
                      <li key={c} className="flex items-start gap-1.5 text-gray-400">
                        <span className="mt-0.5">✗</span><span>{c}</span>
                      </li>
                    ))}
                  </ul>
                )}
                <div className="mt-2 space-y-0.5 text-gray-500">
                  <p>SL: {opp.stop_loss_price != null ? inr(opp.stop_loss_price) : '—'}{opp.stop_loss_pct != null ? ` (${opp.stop_loss_pct.toFixed(1)}%)` : ''}</p>
                  <p>Target: {opp.target_price != null ? inr(opp.target_price) : '—'}{opp.target_pct != null ? ` (+${opp.target_pct.toFixed(1)}%)` : ''}</p>
                  {opp.rr != null && <p>R:R 1:{opp.rr.toFixed(1)}</p>}
                  {opp.holding_days != null && <p>Hold: ~{opp.holding_days}d</p>}
                  {opp.ml_probability != null && (
                    <p>ML Probability: {Math.round(opp.ml_probability * 100)}%</p>
                  )}
                </div>
              </div>
            </div>
          </td>
        </tr>
      )}
      {showExplain && (
        <tr className="bg-violet-50">
          <td colSpan={13} className="px-6 py-4">
            {explainLoading && <p className="text-sm text-gray-400">Fetching AI analysis…</p>}
            {explainError && <p className="text-sm text-red-600">AI explanation unavailable.</p>}
            {explanation && <ExplanationPanel explanation={explanation} symbol={opp.symbol} />}
          </td>
        </tr>
      )}
    </>
  )
}

function ExplanationPanel({ explanation, symbol }: { explanation: SignalExplanation; symbol: string }) {
  const riskColor =
    explanation.risk_rating === 'LOW'    ? 'bg-green-100 text-green-700' :
    explanation.risk_rating === 'MEDIUM' ? 'bg-yellow-100 text-yellow-700' :
    explanation.risk_rating === 'HIGH'   ? 'bg-red-100 text-red-700' :
    'bg-gray-100 text-gray-600'

  return (
    <div className="space-y-3 text-xs max-w-3xl">
      <div className="flex items-center gap-2">
        <span className="font-semibold text-violet-700">AI Analysis — {symbol}</span>
        {explanation.risk_rating && (
          <span className={`px-2 py-0.5 rounded text-xs font-medium ${riskColor}`}>
            {explanation.risk_rating} RISK
          </span>
        )}
        {explanation.action && (
          <span className="px-2 py-0.5 rounded bg-orange-100 text-orange-700 text-xs font-medium">
            {explanation.action}
          </span>
        )}
      </div>

      {explanation.summary && (
        <p className="text-gray-700">{explanation.summary}</p>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {explanation.bull_case && explanation.bull_case.length > 0 && (
          <div>
            <p className="font-semibold text-green-700 mb-1">Bull Case</p>
            <ul className="space-y-0.5">
              {explanation.bull_case.map((c, i) => (
                <li key={i} className="flex items-start gap-1.5 text-green-700">
                  <span className="mt-0.5 shrink-0">✓</span><span>{c}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
        {explanation.bear_case && explanation.bear_case.length > 0 && (
          <div>
            <p className="font-semibold text-gray-500 mb-1">Bear Case</p>
            <ul className="space-y-0.5">
              {explanation.bear_case.map((c, i) => (
                <li key={i} className="flex items-start gap-1.5 text-gray-500">
                  <span className="mt-0.5 shrink-0">✗</span><span>{c}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
        {explanation.exit_reasons && explanation.exit_reasons.length > 0 && (
          <div>
            <p className="font-semibold text-orange-700 mb-1">Exit Reasons</p>
            <ul className="space-y-0.5">
              {explanation.exit_reasons.map((c, i) => (
                <li key={i} className="flex items-start gap-1.5 text-orange-700">
                  <span className="mt-0.5 shrink-0">→</span><span>{c}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {explanation.confidence_reasoning && (
        <p className="text-gray-500 italic">{explanation.confidence_reasoning}</p>
      )}
    </div>
  )
}

export function TopOpportunities({
  opportunities,
  isLoading,
  isError,
}: {
  opportunities: TopOpportunity[]
  isLoading: boolean
  isError: boolean
}) {
  const queryClient = useQueryClient()
  const enterMut = useMutation({
    mutationFn: ({ signalId, price }: { signalId: number; price: number }) =>
      enterPosition(signalId, price),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['portfolio'] }),
  })

  if (isLoading) return <p className="text-gray-400">Loading…</p>
  if (isError)   return <p className="text-red-600 text-sm">Failed to load opportunities.</p>
  if (opportunities.length === 0) return (
    <p className="text-gray-500 py-4">
      No BUY signals yet — scans run at 9:15, 10:30, 12:00, 14:00, 15:15 IST on trading days.
    </p>
  )

  return (
    <>
      <div className="overflow-x-auto rounded-lg border border-gray-200">
        <table className="w-full text-sm">
          <thead className="bg-gray-100 text-gray-600 text-left">
            <tr>
              <th className="px-2 py-2 text-center text-xs">#</th>
              <th className="px-2 py-2 w-6" />
              <th className="px-4 py-2">Symbol</th>
              <th className="px-4 py-2">Score</th>
              <th className="px-4 py-2">Regime</th>
              <th className="px-4 py-2">MTF</th>
              <th className="px-4 py-2">ML%</th>
              <th className="px-4 py-2">Entry</th>
              <th className="px-4 py-2">Stop Loss</th>
              <th className="px-4 py-2">Target</th>
              <th className="px-4 py-2">R:R</th>
              <th className="px-4 py-2">Strategy</th>
              <th className="px-4 py-2" />
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-100">
            {opportunities.map((opp, i) => (
              <OpportunityRow
                key={opp.signal_id}
                opp={opp}
                rank={i + 1}
                entering={enterMut.isPending && enterMut.variables?.signalId === opp.signal_id}
                enterError={
                  enterMut.isError && enterMut.variables?.signalId === opp.signal_id
                    ? String(enterMut.error)
                    : null
                }
                onEnter={() => enterMut.mutate({ signalId: opp.signal_id, price: opp.price_at_signal })}
              />
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}
