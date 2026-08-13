import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { exitPosition, getClosedPnl, getHoldings, getSellAlerts, type ClosedTrade, type Holding, type SellAlert } from '../api/portfolio'
import { inr } from '../utils/format'

export function PortfolioPage() {
  const queryClient = useQueryClient()
  const [exitPrices, setExitPrices] = useState<Record<string, string>>({})

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

  const exitMut = useMutation({
    mutationFn: ({ symbol, price }: { symbol: string; price: number }) =>
      exitPosition(symbol, price, 'manual'),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['portfolio'] }),
    onError: (err) => console.error('Failed to exit position:', err),
  })

  return (
    <div className="space-y-8">
      <h1 className="text-2xl font-bold text-gray-800">Portfolio</h1>

      {/* Sell Alerts */}
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
        <h2 className="text-lg font-semibold text-gray-700 mb-3">Open Positions</h2>
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
  return (
    <tr className="hover:bg-gray-50">
      <td className="px-4 py-2 font-semibold">{h.symbol}</td>
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
