import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { MLModelStatus, MLTrainResult, ComputeOutcomesResult, BackfillStatus } from '../api/ml'
import type { SpecialPrecomputeStatus } from '../api/special'
import {
  getNormalMLStatus,
  getSpecialMLStatus,
  trainNormalModel,
  trainSpecialModel,
  computeSignalOutcomes,
  triggerBackfill,
  getBackfillStatus,
  refreshFundamentals,
  getFundamentalsCount,
} from '../api/ml'
import { triggerSpecialPrecompute, getSpecialPrecomputeStatus, getSpecialTrainingDataStatus } from '../api/special'

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
              {status.models_total != null
                ? `${status.models_trained ?? 0}/${status.models_total} strategies trained`
                : status.exists ? 'Trained' : 'Not Trained'}
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

function NormalModelCard() {
  const qc = useQueryClient()

  const { mutate: startBackfill, isPending: isStarting } = useMutation({
    mutationFn: () => triggerBackfill(90),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['backfill-status'] }),
  })

  const { data: bfStatus } = useQuery<BackfillStatus>({
    queryKey: ['backfill-status'],
    queryFn: getBackfillStatus,
    refetchInterval: (query) => query.state.data?.is_running ? 3000 : false,
  })

  const { mutate: computeOutcomes, isPending: isComputing, data: computeResult } =
    useMutation<ComputeOutcomesResult>({
      mutationFn: computeSignalOutcomes,
      onSuccess: () => qc.invalidateQueries({ queryKey: ['normal-ml-status'] }),
    })

  const isRunning = bfStatus?.is_running ?? false
  const hasBackfillDone = (bfStatus?.signals_saved ?? 0) > 0 && !isRunning

  return (
    <div className="flex flex-col gap-3 flex-1">
      {/* Step 1 — Backfill */}
      <div className="bg-white rounded-lg shadow p-4 space-y-2">
        <p className="text-sm font-medium text-gray-700">Step 1 — Backfill Historical Signals</p>
        <p className="text-xs text-gray-400">
          Replays all strategies over 90 days of price history to seed the signal database.
          Only needed once on a fresh deployment.
        </p>
        {isRunning && bfStatus && (
          <div className="space-y-1">
            <div className="flex justify-between text-xs text-blue-700">
              <span>Processing symbols…</span>
              <span>{bfStatus.done} / {bfStatus.total}</span>
            </div>
            <div className="w-full bg-gray-200 rounded-full h-1.5">
              <div
                className="bg-blue-500 h-1.5 rounded-full transition-all"
                style={{ width: bfStatus.total ? `${(bfStatus.done / bfStatus.total) * 100}%` : '0%' }}
              />
            </div>
            <p className="text-xs text-gray-400">{bfStatus.signals_saved} signals saved so far</p>
          </div>
        )}
        {hasBackfillDone && (
          <p className="text-xs text-green-700">
            Done — {bfStatus!.signals_saved} signals saved, {bfStatus!.outcomes_labelled} outcomes labelled
          </p>
        )}
        {bfStatus?.error && (
          <p className="text-xs text-red-600">{bfStatus.error}</p>
        )}
        <button
          onClick={() => startBackfill()}
          disabled={isStarting || isRunning}
          className="bg-gray-700 hover:bg-gray-800 disabled:bg-gray-400 text-white text-xs font-medium px-3 py-1.5 rounded transition-colors"
        >
          {isRunning ? 'Running…' : 'Backfill Signals'}
        </button>
      </div>

      {/* Step 2 — Compute Outcomes */}
      <div className="bg-white rounded-lg shadow p-4 flex items-center justify-between gap-4">
        <div>
          <p className="text-sm font-medium text-gray-700">Step 2 — Compute Outcomes</p>
          <p className="text-xs text-gray-400 mt-0.5">
            Labels signals ≥15 days old as profitable/not. Run after backfill or daily.
          </p>
          {computeResult && (
            <p className="text-xs mt-1 text-green-700">
              +{computeResult.new_outcomes_recorded} new &nbsp;·&nbsp; {computeResult.total_labelled_outcomes} total
              {computeResult.ready_to_train ? ' — ready to train ✓' : ' — need 50 to train'}
            </p>
          )}
        </div>
        <button
          onClick={() => computeOutcomes()}
          disabled={isComputing || isRunning}
          className="flex-shrink-0 bg-gray-600 hover:bg-gray-700 disabled:bg-gray-400 text-white text-sm font-medium px-4 py-2 rounded transition-colors"
        >
          {isComputing ? 'Computing…' : 'Compute Outcomes'}
        </button>
      </div>

      {/* Step 3 — Train */}
      <ModelCard
        title="Normal Strategies Model"
        description="Step 3 — Train on labelled outcomes to predict win probability for strategy signals."
        queryKey="normal-ml-status"
        fetchStatus={getNormalMLStatus}
        triggerTrain={trainNormalModel}
      />
    </div>
  )
}

function SpecialModelCard() {
  const qc = useQueryClient()

  const { mutate: startPrecompute, isPending: isStarting } = useMutation({
    mutationFn: () => triggerSpecialPrecompute(false),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['special-precompute-status'] }),
  })

  const { data: pcStatus } = useQuery<SpecialPrecomputeStatus>({
    queryKey: ['special-precompute-status'],
    queryFn: getSpecialPrecomputeStatus,
    refetchInterval: (query) => query.state.data?.is_running ? 3000 : false,
  })

  const { data: tdStatus, refetch: recheckTd, isFetching: isFetchingTd } = useQuery({
    queryKey: ['special-training-data-status'],
    queryFn: getSpecialTrainingDataStatus,
  })

  const isRunning = pcStatus?.is_running ?? false
  const hasDone = (pcStatus?.symbols_computed ?? 0) > 0 && !isRunning

  return (
    <div className="flex flex-col gap-3 flex-1">
      {/* Step 1 — Precompute */}
      <div className="bg-white rounded-lg shadow p-4 space-y-2">
        <p className="text-sm font-medium text-gray-700">Step 1 — Run Precompute</p>
        <p className="text-xs text-gray-400">
          Runs backtests for all special strategies across all symbols to populate trade history.
          Only needed once on a fresh deployment.
        </p>
        {isRunning && pcStatus && (
          <div className="space-y-1">
            <div className="flex justify-between text-xs text-blue-700">
              <span>{pcStatus.phase || 'Processing…'}</span>
              <span>{pcStatus.done} / {pcStatus.total}</span>
            </div>
            <div className="w-full bg-gray-200 rounded-full h-1.5">
              <div
                className="bg-blue-500 h-1.5 rounded-full transition-all"
                style={{ width: `${pcStatus.pct_done ?? 0}%` }}
              />
            </div>
            <p className="text-xs text-gray-400">{pcStatus.symbols_computed} symbols computed</p>
          </div>
        )}
        {hasDone && (
          <p className="text-xs text-green-700">
            Done — {pcStatus!.symbols_computed} symbols computed
          </p>
        )}
        {pcStatus?.error && (
          <p className="text-xs text-red-600">{pcStatus.error}</p>
        )}
        <button
          onClick={() => startPrecompute()}
          disabled={isStarting || isRunning}
          className="bg-gray-700 hover:bg-gray-800 disabled:bg-gray-400 text-white text-xs font-medium px-3 py-1.5 rounded transition-colors"
        >
          {isRunning ? 'Running…' : 'Run Precompute'}
        </button>
      </div>

      {/* Step 2 — Check training data */}
      <div className="bg-white rounded-lg shadow p-4 flex items-center justify-between gap-4">
        <div>
          <p className="text-sm font-medium text-gray-700">Step 2 — Check Training Data</p>
          <p className="text-xs text-gray-400 mt-0.5">
            Counts labelled backtest trades available for training.
          </p>
          {tdStatus && (
            <p className="text-xs mt-1 text-green-700">
              {tdStatus.total_labelled_trades} trades available
              {tdStatus.ready_to_train
                ? ' — ready to train ✓'
                : ` — need ${tdStatus.min_required} to train`}
            </p>
          )}
        </div>
        <button
          onClick={() => recheckTd()}
          disabled={isFetchingTd || isRunning}
          className="flex-shrink-0 bg-gray-600 hover:bg-gray-700 disabled:bg-gray-400 text-white text-sm font-medium px-4 py-2 rounded transition-colors"
        >
          {isFetchingTd ? 'Checking…' : 'Check'}
        </button>
      </div>

      {/* Step 3 — Train */}
      <ModelCard
        title="Special Strategies Model"
        description="Step 3 — Train on backtest trades to predict win probability for special strategy signals."
        queryKey="special-ml-status"
        fetchStatus={getSpecialMLStatus}
        triggerTrain={trainSpecialModel}
      />
    </div>
  )
}

function FundamentalsPanel() {
  const qc = useQueryClient()
  const { data: countData, isLoading } = useQuery({
    queryKey: ['fundamentals-count'],
    queryFn: getFundamentalsCount,
  })
  const { mutate: refresh, isPending, isSuccess } = useMutation({
    mutationFn: refreshFundamentals,
    onSuccess: () => setTimeout(() => qc.invalidateQueries({ queryKey: ['fundamentals-count'] }), 3000),
  })

  const count = countData?.count ?? 0

  return (
    <div className={`rounded-lg border p-4 flex items-center justify-between gap-4 ${count === 0 ? 'bg-amber-50 border-amber-200' : 'bg-white border-gray-200'}`}>
      <div>
        <p className="text-sm font-medium text-gray-800">Fundamentals Data</p>
        <p className="text-xs text-gray-500 mt-0.5">
          P/E, ROE, debt/equity, revenue — used as ML features once collected.
          Fetched from yfinance (~500 symbols, takes 5–10 min).
        </p>
        {!isLoading && (
          <p className={`text-xs mt-1 font-medium ${count === 0 ? 'text-amber-700' : 'text-green-700'}`}>
            {count === 0
              ? 'No data yet — run a refresh to populate'
              : `${count} symbols have fundamentals data`}
          </p>
        )}
        {isSuccess && (
          <p className="text-xs mt-1 text-blue-600">Refresh started in background — count will update shortly</p>
        )}
      </div>
      <button
        onClick={() => refresh()}
        disabled={isPending}
        className="flex-shrink-0 bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-300 text-white text-sm font-medium px-4 py-2 rounded transition-colors"
      >
        {isPending ? 'Starting…' : 'Refresh Fundamentals'}
      </button>
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

      <FundamentalsPanel />

      <div className="flex gap-6 flex-col sm:flex-row">
        <NormalModelCard />
        <SpecialModelCard />
      </div>
    </div>
  )
}
