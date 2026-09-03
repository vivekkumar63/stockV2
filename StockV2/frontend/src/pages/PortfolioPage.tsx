import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  exitPosition, getClosedPnl, getHoldings, getSellAlerts, getSpecialSellAlerts,
  manualEntry,
  type ClosedTrade, type Holding, type ManualEntryRequest, type SellAlert,
  type SpecialSellAlert,
} from '../api/portfolio'
import { getStrategies } from '../api/strategies'
import { getSpecialStrategies } from '../api/special'
import { inr } from '../utils/format'

export function PortfolioPage() {
  const queryClient = useQueryClient()
  const [exitPrices, setExitPrices] = useState<Record<string, string>>({})
  const [showManualBuy, setShowManualBuy] = useState(false)

  const { data: holdings = [], isLoading: loadingHoldings, isError: holdingsError } = useQuery({
    queryKey: ['portfolio', 'holdings'],
    queryFn: getHoldings,
  })

  const { data: pnlData, isLoading: loadingPnl, isError: pnlError } = useQuery({
    queryKey: ['portfolio', 'pnl'],
    queryFn: getClosedPnl,
  })

  const { data: sellAlerts = [] } = useQuery({
    queryKey: ['portfolio', 'sell-alerts'],
    queryFn: getSellAlerts,
    refetchInterval: 5 * 60 * 1000,
  })

  const { data: specialAlerts = [] } = useQuery({
    queryKey: ['portfolio', 'special-sell-alerts'],
    queryFn: getSpecialSellAlerts,
    refetchInterval: 5 * 60 * 1000,
  })

  const exitMut = useMutation({
    mutationFn: ({ symbol, price }: { symbol: string; price: number }) =>
      exitPosition(symbol, price, 'manual'),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['portfolio'] }),
    onError: (err) => console.error('Failed to exit position:', err),
  })

  return (
    <div className="space-y-8">
      <h1 className="text-2xl font-bold text-gray-800">Portfolio</h1>

      {/* Special strategy sell alerts */}
      {specialAlerts.length > 0 && (
        <section>
          <div className="flex items-center gap-2 mb-3">
            <span className="text-base font-semibold text-orange-700">Special Strategy Sell Signals</span>
            <span className="text-xs bg-orange-100 text-orange-700 border border-orange-300 rounded-full px-2 py-0.5 font-bold">
              {specialAlerts.length}
            </span>
          </div>
          <div className="space-y-2">
            {specialAlerts.map((a, i) => (
              <SpecialSellAlertCard key={i} alert={a} />
            ))}
          </div>
        </section>
      )}

      {/* Regular sell alerts */}
      {sellAlerts.length > 0 && (
        <section>
          <div className="flex items-center gap-2 mb-3">
            <span className="text-base font-semibold text-red-700">Sell Signals for Your Holdings</span>
            <span className="text-xs bg-red-100 text-red-700 border border-red-300 rounded-full px-2 py-0.5 font-bold">
              {sellAlerts.length}
            </span>
          </div>
          <div className="space-y-2">
            {sellAlerts.map((a, i) => (
              <SellAlertCard key={i} alert={a} />
            ))}
          </div>
        </section>
      )}

      {/* Open Positions */}
      <section>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-semibold text-gray-700">Open Positions</h2>
          <button
            onClick={() => setShowManualBuy(true)}
            className="px-3 py-1.5 bg-green-600 text-white text-sm rounded-lg hover:bg-green-700 font-medium"
          >
            + Manual Buy
          </button>
        </div>
        {loadingHoldings ? (
          <p className="text-gray-400">Loading…</p>
        ) : holdingsError ? (
          <p className="text-red-600 text-sm">Failed to load holdings.</p>
        ) : holdings.length === 0 ? (
          <p className="text-gray-500 py-4">No open positions.</p>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-gray-200">
            <table className="w-full text-sm">
              <thead className="bg-gray-100 text-gray-600 text-left">
                <tr>
                  <th scope="col" className="px-4 py-2">Symbol</th>
                  <th scope="col" className="px-4 py-2">Strategy</th>
                  <th scope="col" className="px-4 py-2">Qty</th>
                  <th scope="col" className="px-4 py-2">Avg Price</th>
                  <th scope="col" className="px-4 py-2">Invested</th>
                  <th scope="col" className="px-4 py-2">Stop Loss</th>
                  <th scope="col" className="px-4 py-2">Target</th>
                  <th scope="col" className="px-4 py-2">Exit Price</th>
                  <th scope="col" className="px-4 py-2" />
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-100">
                {holdings.map((h) => (
                  <HoldingRow
                    key={h.id}
                    holding={h}
                    exitPrice={exitPrices[h.symbol] ?? ''}
                    onPriceChange={(v) => setExitPrices((p) => ({ ...p, [h.symbol]: v }))}
                    onExit={() =>
                      exitMut.mutate({ symbol: h.symbol, price: Number(exitPrices[h.symbol]) })
                    }
                    exiting={exitMut.isPending && exitMut.variables?.symbol === h.symbol}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
        {exitMut.isError && (
          <p className="text-red-600 text-sm mt-2">
            Failed to exit position: {String(exitMut.error)}
          </p>
        )}
      </section>

      {/* Closed P&L */}
      <section>
        <h2 className="text-lg font-semibold text-gray-700 mb-3">Closed P&L</h2>
        {loadingPnl ? (
          <p className="text-gray-400">Loading…</p>
        ) : pnlError ? (
          <p className="text-red-600 text-sm">Failed to load P&L data.</p>
        ) : pnlData ? (
          <>
            <p className="text-sm text-gray-500 mb-3">
              Total:{' '}
              <span className={pnlData.total_pnl >= 0 ? 'text-green-600 font-semibold' : 'text-red-600 font-semibold'}>
                {inr(pnlData.total_pnl)}
              </span>
            </p>
            {pnlData.closed_trades.length === 0 ? (
              <p className="text-gray-500">No closed trades yet.</p>
            ) : (
              <div className="overflow-x-auto rounded-lg border border-gray-200">
                <table className="w-full text-sm">
                  <thead className="bg-gray-100 text-gray-600 text-left">
                    <tr>
                      <th scope="col" className="px-4 py-2">Symbol</th>
                      <th scope="col" className="px-4 py-2">Date</th>
                      <th scope="col" className="px-4 py-2">Qty</th>
                      <th scope="col" className="px-4 py-2">Sell ₹</th>
                      <th scope="col" className="px-4 py-2">Buy Avg ₹</th>
                      <th scope="col" className="px-4 py-2">P&L</th>
                      <th scope="col" className="px-4 py-2">P&L %</th>
                    </tr>
                  </thead>
                  <tbody className="bg-white divide-y divide-gray-100">
                    {pnlData.closed_trades.map((t, i) => (
                      <ClosedTradeRow key={i} trade={t} />
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        ) : null}
      </section>

      {showManualBuy && (
        <ManualBuyModal
          onClose={() => setShowManualBuy(false)}
          onSuccess={() => {
            setShowManualBuy(false)
            queryClient.invalidateQueries({ queryKey: ['portfolio'] })
          }}
        />
      )}
    </div>
  )
}

function HoldingRow({
  holding: h, exitPrice, onPriceChange, onExit, exiting,
}: {
  holding: Holding
  exitPrice: string
  onPriceChange: (v: string) => void
  onExit: () => void
  exiting: boolean
}) {
  const strategyLabel = h.special_strategy_name ?? null
  const isManual = h.entry_source === 'manual'

  return (
    <tr className="hover:bg-gray-50">
      <td className="px-4 py-2 font-semibold">
        {h.symbol}
        {isManual && (
          <span className="ml-1.5 text-xs bg-gray-100 text-gray-500 border border-gray-200 rounded px-1 py-0.5">manual</span>
        )}
      </td>
      <td className="px-4 py-2 text-xs text-gray-500 max-w-[150px]">
        {strategyLabel ? (
          <span className="px-1.5 py-0.5 rounded bg-purple-100 text-purple-700 font-medium truncate block" title={strategyLabel}>
            ⭐ {strategyLabel}
          </span>
        ) : '—'}
      </td>
      <td className="px-4 py-2">{h.quantity}</td>
      <td className="px-4 py-2">{inr(h.avg_buy_price)}</td>
      <td className="px-4 py-2">{inr(h.invested_value)}</td>
      <td className="px-4 py-2 text-red-600">{h.stop_loss_price != null ? inr(h.stop_loss_price) : '—'}</td>
      <td className="px-4 py-2 text-green-600">{h.target_1_price != null ? inr(h.target_1_price) : '—'}</td>
      <td className="px-4 py-2">
        <input
          type="number"
          placeholder="exit price"
          className="w-28 border border-gray-300 rounded px-2 py-1 text-xs"
          value={exitPrice}
          onChange={(e) => onPriceChange(e.target.value)}
        />
      </td>
      <td className="px-4 py-2">
        <button
          onClick={onExit}
          disabled={!exitPrice || isNaN(Number(exitPrice)) || Number(exitPrice) <= 0 || exiting}
          aria-label={`Exit ${h.symbol}`}
          className="px-3 py-1 bg-red-600 text-white text-xs rounded hover:bg-red-700 disabled:opacity-50"
        >
          Exit
        </button>
      </td>
    </tr>
  )
}

function SellAlertCard({ alert: a }: { alert: SellAlert }) {
  const conf = a.confidence_score != null ? Math.round(a.confidence_score * 100) : null
  const pnlPct = a.price_at_signal && a.avg_buy_price
    ? ((a.price_at_signal - a.avg_buy_price) / a.avg_buy_price * 100)
    : null

  let conditions: string[] = []
  try {
    const r = JSON.parse(a.reasoning_json ?? '{}')
    conditions = r.conditions_met ?? []
  } catch { /* ignore */ }

  return (
    <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-3 flex flex-wrap gap-x-6 gap-y-1 items-start">
      <div className="min-w-[80px]">
        <div className="font-bold text-red-700 text-base">{a.symbol}</div>
        <div className="text-xs text-gray-500">{a.signal_date}</div>
      </div>
      <div className="flex-1 min-w-[160px]">
        <div className="text-sm font-medium text-gray-700 truncate" title={a.strategy_name}>
          {a.strategy_name}
        </div>
        {conditions.length > 0 && (
          <div className="text-xs text-gray-500 mt-0.5 line-clamp-1">
            {conditions.slice(0, 2).join(' · ')}
          </div>
        )}
      </div>
      <div className="flex gap-4 text-sm flex-wrap">
        {conf != null && (
          <span className="text-red-600 font-semibold">{conf}% confidence</span>
        )}
        <span className="text-gray-600">
          Signal ₹{a.price_at_signal.toLocaleString('en-IN', { maximumFractionDigits: 0 })}
        </span>
        {pnlPct != null && (
          <span className={pnlPct >= 0 ? 'text-green-600 font-semibold' : 'text-red-600 font-semibold'}>
            {pnlPct >= 0 ? '+' : ''}{pnlPct.toFixed(1)}% vs avg
          </span>
        )}
      </div>
    </div>
  )
}

function SpecialSellAlertCard({ alert: a }: { alert: SpecialSellAlert }) {
  const pnlPct = a.current_price && a.avg_buy_price
    ? ((a.current_price - a.avg_buy_price) / a.avg_buy_price * 100)
    : null

  return (
    <div className="bg-orange-50 border border-orange-200 rounded-lg px-4 py-3 flex flex-wrap gap-x-6 gap-y-1 items-start">
      <div className="min-w-[80px]">
        <div className="font-bold text-orange-700 text-base">{a.symbol}</div>
        <div className="text-xs text-orange-600">Special strategy exit signal</div>
      </div>
      <div className="flex-1 min-w-[160px]">
        <div className="text-sm font-medium text-gray-700">
          ⭐ {a.strategy_name}
        </div>
        <div className="text-xs text-gray-500 mt-0.5">Sell signal fired — consider exiting</div>
      </div>
      <div className="flex gap-4 text-sm flex-wrap">
        {a.current_price != null && (
          <span className="text-gray-600">
            Current ₹{a.current_price.toLocaleString('en-IN', { maximumFractionDigits: 0 })}
          </span>
        )}
        {pnlPct != null && (
          <span className={pnlPct >= 0 ? 'text-green-600 font-semibold' : 'text-red-600 font-semibold'}>
            {pnlPct >= 0 ? '+' : ''}{pnlPct.toFixed(1)}% vs avg
          </span>
        )}
      </div>
    </div>
  )
}

function ClosedTradeRow({ trade: t }: { trade: ClosedTrade }) {
  const pos = (t.pnl ?? 0) >= 0
  return (
    <tr className="hover:bg-gray-50">
      <td className="px-4 py-2 font-semibold">{t.symbol}</td>
      <td className="px-4 py-2 text-gray-500">{t.trade_date}</td>
      <td className="px-4 py-2">{t.quantity}</td>
      <td className="px-4 py-2">{inr(t.price)}</td>
      <td className="px-4 py-2">{t.buy_avg != null ? inr(t.buy_avg) : '—'}</td>
      <td className={`px-4 py-2 font-semibold ${pos ? 'text-green-600' : 'text-red-600'}`}>
        {t.pnl != null ? inr(t.pnl) : '—'}
      </td>
      <td className={`px-4 py-2 ${pos ? 'text-green-600' : 'text-red-600'}`}>
        {t.pnl_pct != null ? `${t.pnl_pct.toFixed(2)}%` : '—'}
      </td>
    </tr>
  )
}

function ManualBuyModal({ onClose, onSuccess }: { onClose: () => void; onSuccess: () => void }) {
  const [form, setForm] = useState({
    symbol: '',
    quantity: '',
    price: '',
    stop_loss: '',
    target: '',
    strategy_type: 'none' as 'none' | 'regular' | 'special',
    strategy_id: '',
    special_strategy_id: '',
  })
  const [error, setError] = useState<string | null>(null)

  const { data: regularStrategies = [] } = useQuery({
    queryKey: ['strategies'],
    queryFn: getStrategies,
  })

  const { data: specialStrategies = [] } = useQuery({
    queryKey: ['special', 'strategies'],
    queryFn: getSpecialStrategies,
  })

  const mut = useMutation({
    mutationFn: (req: ManualEntryRequest) => manualEntry(req),
    onSuccess: () => onSuccess(),
    onError: (err) => setError(String(err)),
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    const qty = parseInt(form.quantity)
    const price = parseFloat(form.price)
    const sl = parseFloat(form.stop_loss)
    const tgt = parseFloat(form.target)

    if (!form.symbol.trim()) return setError('Symbol is required')
    if (!qty || qty <= 0) return setError('Quantity must be > 0')
    if (!price || price <= 0) return setError('Price must be > 0')
    if (!sl || sl <= 0) return setError('Stop loss must be > 0')
    if (!tgt || tgt <= 0) return setError('Target must be > 0')
    if (sl >= price) return setError('Stop loss must be below entry price')
    if (tgt <= price) return setError('Target must be above entry price')

    const req: ManualEntryRequest = {
      symbol: form.symbol.trim().toUpperCase(),
      quantity: qty,
      price,
      stop_loss: sl,
      target: tgt,
    }
    if (form.strategy_type === 'regular' && form.strategy_id) {
      req.strategy_id = parseInt(form.strategy_id)
    }
    if (form.strategy_type === 'special' && form.special_strategy_id) {
      req.special_strategy_id = parseInt(form.special_strategy_id)
    }
    mut.mutate(req)
  }

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }))

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-md p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-800">Manual Buy Entry</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl leading-none">&times;</button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs font-medium text-gray-600 block mb-1">Symbol *</label>
              <input
                type="text"
                placeholder="e.g. RELIANCE"
                value={form.symbol}
                onChange={set('symbol')}
                className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm uppercase"
                required
              />
            </div>
            <div>
              <label className="text-xs font-medium text-gray-600 block mb-1">Quantity *</label>
              <input
                type="number"
                min="1"
                placeholder="10"
                value={form.quantity}
                onChange={set('quantity')}
                className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm"
                required
              />
            </div>
            <div>
              <label className="text-xs font-medium text-gray-600 block mb-1">Buy Price ₹ *</label>
              <input
                type="number"
                step="0.01"
                min="0"
                placeholder="1500.00"
                value={form.price}
                onChange={set('price')}
                className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm"
                required
              />
            </div>
            <div>
              <label className="text-xs font-medium text-gray-600 block mb-1">Stop Loss ₹ *</label>
              <input
                type="number"
                step="0.01"
                min="0"
                placeholder="1395.00"
                value={form.stop_loss}
                onChange={set('stop_loss')}
                className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm"
                required
              />
            </div>
            <div className="col-span-2">
              <label className="text-xs font-medium text-gray-600 block mb-1">Target ₹ *</label>
              <input
                type="number"
                step="0.01"
                min="0"
                placeholder="1725.00"
                value={form.target}
                onChange={set('target')}
                className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm"
                required
              />
            </div>
          </div>

          <div>
            <label className="text-xs font-medium text-gray-600 block mb-1">Strategy (optional)</label>
            <select
              value={form.strategy_type}
              onChange={set('strategy_type')}
              className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm"
            >
              <option value="none">No strategy</option>
              <option value="regular">Regular strategy</option>
              <option value="special">Special strategy</option>
            </select>
          </div>

          {form.strategy_type === 'regular' && (
            <div>
              <label className="text-xs font-medium text-gray-600 block mb-1">Select Regular Strategy</label>
              <select
                value={form.strategy_id}
                onChange={set('strategy_id')}
                className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm"
              >
                <option value="">— pick strategy —</option>
                {regularStrategies.map((s) => (
                  <option key={s.id} value={s.id}>{s.name}</option>
                ))}
              </select>
            </div>
          )}

          {form.strategy_type === 'special' && (
            <div>
              <label className="text-xs font-medium text-gray-600 block mb-1">
                Select Special Strategy
                <span className="ml-1 text-gray-400 font-normal">(sell signal tracked automatically)</span>
              </label>
              <select
                value={form.special_strategy_id}
                onChange={set('special_strategy_id')}
                className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm"
              >
                <option value="">— pick strategy —</option>
                {specialStrategies.map((s) => (
                  <option key={s.id} value={s.id}>{s.name}</option>
                ))}
              </select>
              {form.special_strategy_id && (
                <p className="text-xs text-purple-600 mt-1">
                  You'll receive a Telegram alert when this strategy fires a sell signal for your position.
                </p>
              )}
            </div>
          )}

          {error && (
            <p className="text-red-600 text-sm">{error}</p>
          )}

          <div className="flex gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 px-4 py-2 border border-gray-300 rounded-lg text-sm text-gray-600 hover:bg-gray-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={mut.isPending}
              className="flex-1 px-4 py-2 bg-green-600 text-white rounded-lg text-sm font-medium hover:bg-green-700 disabled:opacity-50"
            >
              {mut.isPending ? 'Adding…' : 'Add Position'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
