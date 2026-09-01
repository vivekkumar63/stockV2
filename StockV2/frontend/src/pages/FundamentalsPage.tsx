import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getAllFundamentals, getFundamentalsHistory, type FundamentalsRow } from '../api/fundamentals'

// ─── formatters ──────────────────────────────────────────────────────────────

function fmtNum(v: number | null, dec = 2): string {
  if (v == null) return '—'
  return v.toFixed(dec)
}

function fmtCr(v: number | null): string {
  if (v == null) return '—'
  const cr = v / 1e7
  const abs = Math.abs(cr)
  if (abs >= 1e5) return `${(cr / 1e5).toFixed(2)}L Cr`
  if (abs >= 1000) return `${(cr / 1000).toFixed(1)}K Cr`
  return `${cr.toFixed(0)} Cr`
}

function fmtPct(v: number | null): string {
  if (v == null) return '—'
  return `${(v * 100).toFixed(2)}%`
}

// ─── column definitions ───────────────────────────────────────────────────────

type ColKey = keyof FundamentalsRow

const COLUMNS: { key: ColKey; label: string; right: boolean; fmt: (r: FundamentalsRow) => string }[] = [
  { key: 'symbol',         label: 'Symbol',       right: false, fmt: r => r.symbol ?? '—' },
  { key: 'pe_ratio',       label: 'P/E',           right: true,  fmt: r => fmtNum(r.pe_ratio) },
  { key: 'pb_ratio',       label: 'P/B',           right: true,  fmt: r => fmtNum(r.pb_ratio) },
  { key: 'eps',            label: 'EPS',           right: true,  fmt: r => fmtNum(r.eps) },
  { key: 'revenue',        label: 'Revenue',       right: true,  fmt: r => fmtCr(r.revenue) },
  { key: 'net_profit',     label: 'Net Profit',    right: true,  fmt: r => fmtCr(r.net_profit) },
  { key: 'debt_equity',    label: 'D/E',           right: true,  fmt: r => fmtNum(r.debt_equity) },
  { key: 'roe',            label: 'ROE',           right: true,  fmt: r => fmtPct(r.roe) },
  { key: 'dividend_yield', label: 'Div Yield',     right: true,  fmt: r => fmtPct(r.dividend_yield) },
  { key: 'data_as_of',     label: 'As Of',         right: false, fmt: r => r.data_as_of ?? '—' },
]

// ─── sort helper ─────────────────────────────────────────────────────────────

type SortDir = 'asc' | 'desc'

function sortRows(rows: FundamentalsRow[], key: ColKey, dir: SortDir): FundamentalsRow[] {
  return [...rows].sort((a, b) => {
    const av = a[key]
    const bv = b[key]
    if (av == null && bv == null) return 0
    if (av == null) return 1
    if (bv == null) return -1
    if (typeof av === 'string' && typeof bv === 'string') {
      return dir === 'asc' ? av.localeCompare(bv) : bv.localeCompare(av)
    }
    return dir === 'asc' ? (av as number) - (bv as number) : (bv as number) - (av as number)
  })
}

// ─── SortTh ───────────────────────────────────────────────────────────────────

function SortTh({
  col, sortKey, sortDir, onSort,
}: {
  col: typeof COLUMNS[number]
  sortKey: ColKey
  sortDir: SortDir
  onSort: (k: ColKey) => void
}) {
  const active = sortKey === col.key
  return (
    <th
      onClick={() => onSort(col.key)}
      className={`px-3 py-2.5 font-medium text-gray-600 cursor-pointer select-none whitespace-nowrap
        border-b border-gray-200 hover:bg-gray-100 transition-colors
        ${col.right ? 'text-right' : 'text-left'}`}
    >
      {col.label}
      {active ? (
        <span className="ml-1 text-blue-500 text-xs">{sortDir === 'asc' ? '▲' : '▼'}</span>
      ) : (
        <span className="ml-1 text-gray-300 text-xs">⇅</span>
      )}
    </th>
  )
}

// ─── AllStocksTab ─────────────────────────────────────────────────────────────

function AllStocksTab({ data }: { data: FundamentalsRow[] }) {
  const [sortKey, setSortKey] = useState<ColKey>('symbol')
  const [sortDir, setSortDir] = useState<SortDir>('asc')
  const [filter, setFilter] = useState('')

  const rows = useMemo(() => {
    const filtered = filter
      ? data.filter(r => r.symbol?.toUpperCase().includes(filter.toUpperCase()))
      : data
    return sortRows(filtered, sortKey, sortDir)
  }, [data, sortKey, sortDir, filter])

  const handleSort = (key: ColKey) => {
    if (sortKey === key) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortKey(key); setSortDir('asc') }
  }

  if (!data.length) {
    return (
      <p className="text-sm text-gray-400">
        No fundamentals data yet. Run a refresh from the ML Models page.
      </p>
    )
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        <input
          type="text"
          placeholder="Filter symbol…"
          value={filter}
          onChange={e => setFilter(e.target.value)}
          className="border border-gray-300 rounded px-3 py-1.5 text-sm w-52 focus:outline-none focus:ring-1 focus:ring-blue-400"
        />
        <span className="text-xs text-gray-400">
          {rows.length}{filter ? ` of ${data.length}` : ''} stocks
        </span>
      </div>

      <div className="overflow-x-auto rounded-lg border border-gray-200 shadow-sm">
        <table className="min-w-full text-sm">
          <thead className="bg-gray-50">
            <tr>
              {COLUMNS.map(col => (
                <SortTh key={col.key} col={col} sortKey={sortKey} sortDir={sortDir} onSort={handleSort} />
              ))}
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-100">
            {rows.map(row => (
              <tr key={row.symbol} className="hover:bg-blue-50 transition-colors">
                {COLUMNS.map(col => (
                  <td
                    key={col.key}
                    className={`px-3 py-2 whitespace-nowrap text-gray-700
                      ${col.right ? 'text-right font-mono' : ''}
                      ${col.key === 'symbol' ? 'font-semibold text-gray-900' : ''}`}
                  >
                    {col.fmt(row)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ─── MetricCard ───────────────────────────────────────────────────────────────

function MetricCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4 shadow-sm">
      <p className="text-xs text-gray-500 mb-1">{label}</p>
      <p className="text-xl font-bold text-gray-900 font-mono">{value}</p>
      {sub && <p className="text-xs text-gray-400 mt-0.5">{sub}</p>}
    </div>
  )
}

// ─── StockDetailTab ───────────────────────────────────────────────────────────

function StockDetailTab({ symbols }: { symbols: string[] }) {
  const [symbol, setSymbol] = useState('')

  const { data: history, isLoading, isFetching } = useQuery({
    queryKey: ['fundamentals-history', symbol],
    queryFn: () => getFundamentalsHistory(symbol),
    enabled: !!symbol,
    staleTime: 5 * 60 * 1000,
  })

  const latest = history?.[0]

  return (
    <div className="space-y-6">
      {/* Symbol picker */}
      <div className="flex items-center gap-3">
        <select
          value={symbol}
          onChange={e => setSymbol(e.target.value)}
          className="border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-blue-400 min-w-[220px]"
        >
          <option value="">— Select a stock —</option>
          {symbols.map(s => <option key={s} value={s}>{s}</option>)}
        </select>
        {isFetching && <span className="text-xs text-gray-400">Loading…</span>}
      </div>

      {/* Latest metrics */}
      {latest && (
        <>
          <div>
            <p className="text-xs text-gray-400 mb-2">
              Latest snapshot — {latest.data_as_of ?? 'unknown date'}
            </p>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <MetricCard label="P/E Ratio"      value={fmtNum(latest.pe_ratio)}    sub="trailing" />
              <MetricCard label="P/B Ratio"      value={fmtNum(latest.pb_ratio)} />
              <MetricCard label="EPS"            value={fmtNum(latest.eps)}          sub="trailing" />
              <MetricCard label="ROE"            value={fmtPct(latest.roe)}          sub="return on equity" />
              <MetricCard label="Revenue"        value={fmtCr(latest.revenue)} />
              <MetricCard label="Net Profit"     value={fmtCr(latest.net_profit)} />
              <MetricCard label="Debt / Equity"  value={fmtNum(latest.debt_equity)} />
              <MetricCard label="Dividend Yield" value={fmtPct(latest.dividend_yield)} />
            </div>
          </div>

          {/* History table */}
          <div>
            <h3 className="text-sm font-semibold text-gray-700 mb-2">
              Snapshot History
              <span className="ml-2 text-gray-400 font-normal">({history!.length} records)</span>
            </h3>
            <div className="overflow-x-auto rounded-lg border border-gray-200 shadow-sm">
              <table className="min-w-full text-sm">
                <thead className="bg-gray-50">
                  <tr>
                    {['Date', 'P/E', 'P/B', 'EPS', 'Revenue', 'Net Profit', 'D/E', 'ROE', 'Div Yield'].map(h => (
                      <th key={h} className="px-3 py-2.5 text-left font-medium text-gray-600 border-b border-gray-200 whitespace-nowrap">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-100">
                  {history!.map((row, i) => (
                    <tr key={i} className={`hover:bg-gray-50 ${i === 0 ? 'bg-blue-50' : ''}`}>
                      <td className="px-3 py-2 font-semibold text-gray-900 whitespace-nowrap">{row.data_as_of ?? '—'}</td>
                      <td className="px-3 py-2 font-mono text-right text-gray-700">{fmtNum(row.pe_ratio)}</td>
                      <td className="px-3 py-2 font-mono text-right text-gray-700">{fmtNum(row.pb_ratio)}</td>
                      <td className="px-3 py-2 font-mono text-right text-gray-700">{fmtNum(row.eps)}</td>
                      <td className="px-3 py-2 font-mono text-right text-gray-700">{fmtCr(row.revenue)}</td>
                      <td className="px-3 py-2 font-mono text-right text-gray-700">{fmtCr(row.net_profit)}</td>
                      <td className="px-3 py-2 font-mono text-right text-gray-700">{fmtNum(row.debt_equity)}</td>
                      <td className="px-3 py-2 font-mono text-right text-gray-700">{fmtPct(row.roe)}</td>
                      <td className="px-3 py-2 font-mono text-right text-gray-700">{fmtPct(row.dividend_yield)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {symbol && !isLoading && !latest && (
        <p className="text-sm text-gray-400">No data found for {symbol}.</p>
      )}
    </div>
  )
}

// ─── FundamentalsPage ─────────────────────────────────────────────────────────

export function FundamentalsPage() {
  const [tab, setTab] = useState<'all' | 'detail'>('all')

  const { data: allData, isLoading } = useQuery({
    queryKey: ['fundamentals-all'],
    queryFn: getAllFundamentals,
    staleTime: 5 * 60 * 1000,
  })

  const symbols = useMemo(
    () => (allData ?? []).map(r => r.symbol!).sort(),
    [allData],
  )

  const tabClass = (t: 'all' | 'detail') =>
    `px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
      tab === t
        ? 'border-blue-600 text-blue-600'
        : 'border-transparent text-gray-500 hover:text-gray-700'
    }`

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Fundamentals</h1>
        <p className="text-gray-500 mt-1">
          P/E, ROE, revenue and other financial metrics — collected via yfinance and used as ML features.
        </p>
      </div>

      <div className="flex border-b border-gray-200">
        <button className={tabClass('all')} onClick={() => setTab('all')}>
          All Stocks
          {allData && <span className="ml-1.5 text-xs text-gray-400">{allData.length}</span>}
        </button>
        <button className={tabClass('detail')} onClick={() => setTab('detail')}>Stock Detail</button>
      </div>

      {isLoading ? (
        <p className="text-sm text-gray-400">Loading…</p>
      ) : tab === 'all' ? (
        <AllStocksTab data={allData ?? []} />
      ) : (
        <StockDetailTab symbols={symbols} />
      )}
    </div>
  )
}
