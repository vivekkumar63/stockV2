import { useQuery } from '@tanstack/react-query'
import { getStrategyDetail } from '../api/strategies'

const TIMEFRAME_LABEL: Record<string, string> = {
  daily: 'Daily',
  intraday_15m: '15-min Intraday',
  intraday_1h: '1-hour Intraday',
}

const TYPE_COLOR: Record<string, string> = {
  technical: 'bg-blue-100 text-blue-700',
  fundamental: 'bg-purple-100 text-purple-700',
  ml: 'bg-orange-100 text-orange-700',
  custom: 'bg-gray-100 text-gray-700',
}

export function StrategyCard({ strategyId }: { strategyId: number }) {
  const { data, isLoading } = useQuery({
    queryKey: ['strategy', strategyId],
    queryFn: () => getStrategyDetail(strategyId),
    staleTime: 5 * 60 * 1000,
  })

  if (isLoading) {
    return (
      <div className="bg-blue-50 border border-blue-100 rounded-lg p-3 text-xs text-blue-400 animate-pulse">
        Loading strategy details…
      </div>
    )
  }
  if (!data) return null

  const typeColor = TYPE_COLOR[data.type] ?? TYPE_COLOR.custom
  const tfLabel = data.timeframe ? (TIMEFRAME_LABEL[data.timeframe] ?? data.timeframe) : null
  const hasIndicators = data.required_indicators?.length > 0
  const hasParams = data.parameters && Object.keys(data.parameters).length > 0

  return (
    <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 space-y-2">
      <div className="flex items-center gap-2 flex-wrap">
        <span className="font-semibold text-gray-800 text-sm">{data.name}</span>
        <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${typeColor}`}>
          {data.type}
        </span>
        {tfLabel && (
          <span className="text-xs px-2 py-0.5 rounded-full bg-gray-100 text-gray-600">
            {tfLabel}
          </span>
        )}
        {data.min_holding_days != null && data.max_holding_days != null && (
          <span className="text-xs text-gray-500">
            Hold {data.min_holding_days}–{data.max_holding_days}d
          </span>
        )}
      </div>

      {data.description && (
        <p className="text-sm text-gray-700">{data.description}</p>
      )}

      {hasIndicators && (
        <div className="flex flex-wrap gap-1 pt-1">
          {data.required_indicators.map((ind) => (
            <span key={ind} className="text-xs bg-white border border-gray-200 rounded px-2 py-0.5 text-gray-500 font-mono">
              {ind}
            </span>
          ))}
        </div>
      )}

      {hasParams && (
        <div className="flex flex-wrap gap-2 pt-1">
          {Object.entries(data.parameters).map(([k, v]) => (
            <span key={k} className="text-xs bg-white border border-gray-200 rounded px-2 py-0.5 text-gray-500">
              <span className="font-medium text-gray-700">{k}</span>: {String(v)}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}
