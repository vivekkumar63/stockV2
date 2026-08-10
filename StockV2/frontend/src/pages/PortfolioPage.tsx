import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { exitPosition, getClosedPnl, getHoldings, type ClosedTrade, type Holding } from '../api/portfolio'
import { inr } from '../utils/format'

export function PortfolioPage() {
  const queryClient = useQueryClient()
  const [exitPrices, setExitPrices] = useState<Record<string, string>>({})

  const { data: holdings = [], isLoading: loadingHoldings, isError: holdingsError } = useQuery({
    queryKey: ['portfolio', 'holdings'],
    queryFn: getHoldings,
  })

  const { data: pnlData, isLoading: loadingPnl } = useQuery({
    queryKey: ['portfolio', 'pnl'],
    queryFn: getClosedPnl,
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
      {!loadingPnl && pnlData && (
        <section>
          <h2 className="text-lg font-semibold text-gray-700 mb-3">
            Closed P&L —{' '}
            <span className={pnlData.total_pnl >= 0 ? 'text-green-600' : 'text-red-600'}>
              {inr(pnlData.total_pnl)}
            </span>
          </h2>
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
        </section>
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
          disabled={!exitPrice || exiting}
          aria-label={`Exit ${h.symbol}`}
          className="px-3 py-1 bg-red-600 text-white text-xs rounded hover:bg-red-700 disabled:opacity-50"
        >
          Exit
        </button>
      </td>
    </tr>
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
