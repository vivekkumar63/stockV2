import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  MLModelStatus,
  MLTrainResult,
  getNormalMLStatus,
  getSpecialMLStatus,
  trainNormalModel,
  trainSpecialModel,
} from '../api/ml'

function MetricsRow({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <div className="flex items-baseline justify-between text-sm">
      <span className="text-gray-500">{label}</span>
      <span className="font-mono text-gray-900 font-medium">{value}</span>
      <span className="text-xs text-gray-400 ml-2">{note}</span>
    </div>
  )
}

function ModelCard({
  title,
  description,
  queryKey,
  fetchStatus,
  triggerTrain,
}: {
  title: string
  description: string
  queryKey: string
  fetchStatus: () => Promise<MLModelStatus>
  triggerTrain: () => Promise<MLTrainResult>
}) {
  const qc = useQueryClient()
  const { data: status, isLoading: statusLoading } = useQuery({
    queryKey: [queryKey],
    queryFn: fetchStatus,
  })

  const { mutate: train, isPending, data: trainResult, error } = useMutation({
    mutationFn: triggerTrain,
    onSuccess: () => qc.invalidateQueries({ queryKey: [queryKey] }),
  })

  const metrics = trainResult?.status === 'ok' ? trainResult : status

  return (
    <div className="bg-white rounded-lg shadow p-6 flex flex-col gap-4 flex-1">
      <div>
        <h2 className="text-lg font-semibold text-gray-800">{title}</h2>
        <p className="text-sm text-gray-500 mt-1">{description}</p>
      </div>

      {statusLoading ? (
        <p className="text-sm text-gray-400">Loading status…</p>
      ) : status ? (
        <div className="space-y-1.5 text-sm">
          <div className="flex items-center gap-2">
            <span
              className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${status.exists ? 'bg-green-500' : 'bg-gray-400'}`}
            />
            <span className={status.exists ? 'text-green-700 font-medium' : 'text-gray-500'}>
              {status.exists ? 'Trained' : 'Not Trained'}
            </span>
            {status.last_trained && (
              <span className="text-gray-400 text-xs ml-auto">
                {new Date(status.last_trained).toLocaleString()}
              </span>
            )}
          </div>
          <div className="text-gray-500 text-xs">
            Samples available:{' '}
            <span className="font-mono text-gray-700">{status.samples_available}</span>
          </div>
        </div>
      ) : null}

      {metrics && metrics.auc_roc != null && (
        <div className="border border-gray-100 rounded-md p-3 space-y-1.5 bg-gray-50">
          <MetricsRow
            label="AUC-ROC"
            value={metrics.auc_roc.toFixed(3)}
            note="random=0.50, perfect=1.00"
          />
          {metrics.precision_at_60 != null && (
            <MetricsRow
              label="Precision @60%"
              value={`${(metrics.precision_at_60 * 100).toFixed(1)}%`}
              note="win rate on high-conf calls"
            />
          )}
          {metrics.high_conf_signals != null && (
            <MetricsRow
              label="High-conf signals"
              value={String(metrics.high_conf_signals)}
              note="predicted ≥60% in cal set"
            />
          )}
          {metrics.class_balance != null && (
            <MetricsRow
              label="Class balance"
              value={`${(metrics.class_balance * 100).toFixed(1)}%`}
              note="profitable in training data"
            />
          )}
        </div>
      )}

      {trainResult && (
        <div
          className={`text-sm rounded px-3 py-2 ${
            trainResult.status === 'ok'
              ? 'bg-green-50 text-green-800'
              : 'bg-yellow-50 text-yellow-800'
          }`}
        >
          {trainResult.message}
        </div>
      )}

      {error && (
        <div className="text-sm rounded px-3 py-2 bg-red-50 text-red-700">
          {(error as Error).message}
        </div>
      )}

      <button
        onClick={() => train()}
        disabled={isPending}
        className="mt-auto bg-blue-600 hover:bg-blue-700 disabled:bg-blue-300 text-white text-sm font-medium px-4 py-2 rounded transition-colors"
      >
        {isPending ? 'Training…' : 'Train Model'}
      </button>

      <p className="text-xs text-gray-400">
        Recommendations automatically use this model once trained.
      </p>
    </div>
  )
}

export function MLModelsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">ML Models</h1>
        <p className="text-gray-500 mt-1">
          Train models on historical trade outcomes to improve recommendation scoring.
        </p>
      </div>

      <div className="flex gap-6 flex-col sm:flex-row">
        <ModelCard
          title="Normal Strategies Model"
          description="Trained on signal_outcomes — predicts win probability for regular strategy signals."
          queryKey="normal-ml-status"
          fetchStatus={getNormalMLStatus}
          triggerTrain={trainNormalModel}
        />
        <ModelCard
          title="Special Strategies Model"
          description="Trained on special_backtest_trades — predicts win probability for special strategy signals."
          queryKey="special-ml-status"
          fetchStatus={getSpecialMLStatus}
          triggerTrain={trainSpecialModel}
        />
      </div>
    </div>
  )
}
