import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  getConfluenceScan,
  type ConfluenceBreakout,
  type ConfluenceNearBreakout,
} from '../api/confluence'

// ── Helpers ──────────────────────────────────────────────────────────────────

function ScoreBar({ value, label, color }: { value: number; label: string; color: string }) {
  const pct = Math.round(value * 100)
  return (
    <div className="flex items-center gap-2">
      <span className="text-[10px] text-gray-500 w-24 shrink-0">{label}</span>
      <div className="flex-1 h-2 bg-gray-100 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-[11px] font-semibold text-gray-700 w-8 text-right">{pct}%</span>
    </div>
  )
}

function combinedBadge(score: number) {
  const pct = Math.round(score * 100)
  const cls =
    score >= 0.70 ? 'bg-green-500 text-white' :
    score >= 0.55 ? 'bg-yellow-400 text-gray-800' :
    'bg-gray-200 text-gray-600'
  return (
    <span className={`inline-flex items-center justify-center w-12 h-12 rounded-full text-sm font-bold shadow-sm ${cls}`}>
      {pct}%
    </span>
  )
}

function mlBadge(value: number, label: string) {
  const pct = Math.round(value * 100)
  const cls =
    value >= 0.70 ? 'bg-green-100 text-green-700' :
    value >= 0.55 ? 'bg-yellow-100 text-yellow-700' :
    'bg-gray-100 text-gray-500'
  return (
    <span className={`text-[10px] px-2 py-0.5 rounded font-semibold ${cls}`}>{label} {pct}%</span>
  )
}

const STRUCTURE_CLS: Record<string, string> = {
  bullish:  'bg-green-100 text-green-700',
  bearish:  'bg-red-100 text-red-600',
  sideways: 'bg-gray-100 text-gray-500',
}

// ── Breakout card ─────────────────────────────────────────────────────────────

function BreakoutCard({ sig }: { sig: ConfluenceBreakout }) {
  const [open, setOpen] = useState(false)

  return (
    <div className={`rounded-xl border shadow-sm overflow-hidden transition-all ${open ? 'border-blue-300' : 'border-gray-200'}`}>
      {/* Card header */}
      <div
        className={`flex items-center gap-4 px-5 py-4 cursor-pointer ${open ? 'bg-blue-50' : 'bg-white hover:bg-gray-50'}`}
        onClick={() => setOpen(v => !v)}
      >
        {/* Combined score circle */}
        <div className="shrink-0">{combinedBadge(sig.combined_score)}</div>

        {/* Symbol + badges */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-bold text-gray-900 text-base">{sig.symbol}</span>
            <span className={`text-[10px] px-2 py-0.5 rounded capitalize font-medium ${STRUCTURE_CLS[sig.market_structure] ?? 'bg-gray-100 text-gray-500'}`}>
              {sig.market_structure}
            </span>
            {sig.candle_signal !== 'NONE' && (
              <span className="text-[10px] px-2 py-0.5 rounded bg-purple-100 text-purple-700 font-medium">
                {sig.candle_signal.replace('_', ' ')}
              </span>
            )}
            <span className="text-[10px] px-2 py-0.5 rounded bg-blue-100 text-blue-700 font-bold">
              🚀 +{sig.breakout_pct.toFixed(1)}% above resist.
            </span>
          </div>
          <div className="flex gap-3 mt-1.5 flex-wrap">
            {mlBadge(sig.zone_ml_confidence,       'Zone')}
            {mlBadge(sig.breakout_ml_probability,  'Breakout')}
          </div>
        </div>

        {/* Right stats */}
        <div className="text-right shrink-0 space-y-1">
          <div className="text-base font-semibold text-gray-800">
            ₹{sig.current_price.toLocaleString('en-IN', { maximumFractionDigits: 0 })}
          </div>
          <div className="text-[11px] text-gray-400">
            Resist. ₹{sig.resistance.toLocaleString('en-IN', { maximumFractionDigits: 0 })}
          </div>
          <div className="flex gap-2 justify-end text-[11px]">
            <span className={`font-medium ${sig.volume_ratio >= 2 ? 'text-green-600' : sig.volume_ratio >= 1.5 ? 'text-yellow-600' : 'text-gray-500'}`}>
              Vol {sig.volume_ratio.toFixed(1)}×
            </span>
            <span className={sig.rsi > 65 ? 'text-orange-500' : sig.rsi > 55 ? 'text-green-600' : 'text-gray-500'}>
              RSI {sig.rsi.toFixed(0)}
            </span>
            <span className={`font-bold ${
              sig.conviction_score === 6 ? 'text-green-600' :
              sig.conviction_score === 5 ? 'text-blue-600' : 'text-gray-600'}`}>
              {sig.conviction_score}/6
            </span>
          </div>
        </div>

        <span className="text-gray-400 text-lg shrink-0">{open ? '▲' : '▼'}</span>
      </div>

      {/* Expanded detail */}
      {open && (
        <div className="bg-white border-t border-blue-100 px-5 py-4 space-y-4">
          {/* Score bars */}
          <div className="space-y-2 max-w-sm">
            <ScoreBar value={sig.combined_score}          label="Combined"     color="bg-blue-500" />
            <ScoreBar value={sig.zone_ml_confidence}      label="Zone ML"      color="bg-indigo-400" />
            <ScoreBar value={sig.breakout_ml_probability} label="Breakout ML"  color="bg-emerald-400" />
          </div>

          <div className="grid grid-cols-2 gap-6 text-xs">
            {/* Signals */}
            <div>
              <div className="font-semibold text-gray-600 mb-1">Signals Met ({sig.signals_met.length}/6)</div>
              {sig.signals_met.map(s => <div key={s} className="text-green-700">✅ {s}</div>)}
              {sig.signals_failed.map(s => <div key={s} className="text-red-400">✗ {s}</div>)}
            </div>

            {/* Additional metrics */}
            <div>
              <div className="font-semibold text-gray-600 mb-1">Metrics</div>
              <div className="space-y-0.5 text-gray-600">
                <div>EMA50 slope: <span className={sig.ema50_slope_pct > 0 ? 'text-green-600 font-medium' : 'text-red-500'}>{sig.ema50_slope_pct?.toFixed(2)}%</span></div>
                <div>Body ratio: {sig.body_ratio != null ? (sig.body_ratio * 100).toFixed(0) : '—'}%</div>
                <div>Range/ATR: {sig.range_atr_ratio?.toFixed(2)}×</div>
                <div>Zone score: {sig.zone_score}/100</div>
              </div>
            </div>
          </div>

          {/* Zone setup */}
          {sig.long_setup && (
            <div className="bg-green-50 rounded-lg p-3 text-xs">
              <div className="font-semibold text-green-800 mb-2">Long Setup (score: {sig.long_setup.score}/100)</div>
              <div className="grid grid-cols-3 gap-2 text-gray-700">
                <div><span className="text-gray-500">Entry</span><br />₹{sig.long_setup.ideal_entry?.toFixed(0)}</div>
                <div><span className="text-gray-500">Stop</span><br /><span className="text-red-500">₹{sig.long_setup.stop_loss?.toFixed(0)}</span></div>
                <div><span className="text-gray-500">T1 ({sig.long_setup.t1_rr?.toFixed(1)}R)</span><br /><span className="text-green-600">₹{sig.long_setup.t1?.toFixed(0)}</span></div>
                {sig.long_setup.t2 && (
                  <div><span className="text-gray-500">T2 ({sig.long_setup.t2_rr?.toFixed(1)}R)</span><br /><span className="text-green-700 font-semibold">₹{sig.long_setup.t2?.toFixed(0)}</span></div>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Near-breakout row ─────────────────────────────────────────────────────────

function NearBreakoutRow({ sig }: { sig: ConfluenceNearBreakout }) {
  const [open, setOpen] = useState(false)
  const distAbs = Math.abs(sig.dist_to_resistance).toFixed(1)

  return (
    <div>
      <div
        className={`grid px-4 py-3 text-xs border-b border-gray-100 hover:bg-gray-50 cursor-pointer items-center ${open ? 'bg-amber-50' : ''}`}
        style={{ gridTemplateColumns: '1fr 90px 80px 80px 65px 55px 65px 55px' }}
        onClick={() => setOpen(v => !v)}
      >
        <div>
          <span className="font-semibold text-gray-800">{sig.symbol}</span>
          <span className={`ml-2 text-[10px] px-1.5 py-0.5 rounded capitalize ${STRUCTURE_CLS[sig.market_structure] ?? 'bg-gray-100 text-gray-500'}`}>
            {sig.market_structure}
          </span>
        </div>
        <span className="text-right">₹{sig.current_price.toLocaleString('en-IN', { maximumFractionDigits: 0 })}</span>
        <span className="text-right text-gray-500">₹{sig.resistance.toLocaleString('en-IN', { maximumFractionDigits: 0 })}</span>
        <span className="text-right text-amber-600 font-semibold">{distAbs}% below</span>
        <span className={`text-right ${sig.volume_ratio >= 1.5 ? 'text-green-600' : 'text-gray-500'}`}>
          {sig.volume_ratio.toFixed(1)}×
        </span>
        <span className={`text-right ${sig.rsi > 55 ? 'text-green-600' : 'text-gray-500'}`}>
          {sig.rsi.toFixed(0)}
        </span>
        <div className="flex justify-center">
          {mlBadge(sig.zone_ml_confidence, 'Zone')}
        </div>
        <div className="flex justify-center">
          <span className={`text-[10px] font-bold px-2 py-0.5 rounded ${
            sig.combined_score >= 0.60 ? 'bg-green-100 text-green-700' :
            sig.combined_score >= 0.45 ? 'bg-yellow-100 text-yellow-700' :
            'bg-gray-100 text-gray-500'
          }`}>{Math.round(sig.combined_score * 100)}%</span>
        </div>
      </div>

      {open && (
        <div className="bg-amber-50 px-6 py-3 border-b border-amber-100 text-xs space-y-3">
          <div className="flex gap-8 flex-wrap">
            <div>
              <div className="font-semibold text-gray-600 mb-1">Zone ML Confidence</div>
              <ScoreBar value={sig.zone_ml_confidence} label="" color="bg-indigo-400" />
            </div>
            <div>
              <div className="font-semibold text-gray-600 mb-1">Metrics</div>
              <div className="text-gray-600 space-y-0.5">
                <div>EMA50 slope: <span className={sig.ema50_slope_pct > 0 ? 'text-green-600' : 'text-red-500'}>{sig.ema50_slope_pct?.toFixed(2)}%</span></div>
                <div>Zone score: {sig.zone_score}/100</div>
              </div>
            </div>
            {sig.long_setup && (
              <div className="bg-white rounded p-2 text-xs shadow-sm">
                <div className="font-semibold text-green-700 mb-1">Long Setup ({sig.long_setup.score}/100)</div>
                <div className="space-y-0.5 text-gray-600">
                  <div>Entry: ₹{sig.long_setup.ideal_entry?.toFixed(0)}</div>
                  <div>Stop: <span className="text-red-500">₹{sig.long_setup.stop_loss?.toFixed(0)}</span></div>
                  <div>T1 ({sig.long_setup.t1_rr?.toFixed(1)}R): <span className="text-green-600">₹{sig.long_setup.t1?.toFixed(0)}</span></div>
                  {sig.long_setup.t2 && (
                    <div>T2 ({sig.long_setup.t2_rr?.toFixed(1)}R): <span className="text-green-700 font-semibold">₹{sig.long_setup.t2?.toFixed(0)}</span></div>
                  )}
                </div>
              </div>
            )}
            {sig.demand_zones?.length > 0 && (
              <div>
                <div className="font-semibold text-gray-600 mb-1">Demand Zones</div>
                {sig.demand_zones.slice(0, 3).map((z, i) => (
                  <div key={i} className="text-gray-600">
                    ₹{z.low?.toFixed(0)}–{z.high?.toFixed(0)}
                    <span className={`ml-1 text-[10px] ${z.freshness === 'fresh' ? 'text-green-600' : z.freshness === 'tested' ? 'text-yellow-600' : 'text-gray-400'}`}>
                      {z.freshness}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export function ConfluencePage() {
  const queryClient = useQueryClient()

  const query = useQuery({
    queryKey: ['confluence-scan'],
    queryFn:  getConfluenceScan,
    staleTime: 5 * 60 * 1000,
  })

  const breakouts   = query.data?.breakouts   ?? []
  const nearBreakout = query.data?.near_breakout ?? []

  return (
    <div className="max-w-5xl mx-auto">
      {/* Page header */}
      <div className="flex items-center gap-4 mb-6">
        <div>
          <h1 className="text-xl font-bold text-gray-900">Confluence Scanner</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            Zone quality + breakout momentum — stocks where both signals align
          </p>
        </div>
        <button
          onClick={() => queryClient.invalidateQueries({ queryKey: ['confluence-scan'] })}
          disabled={query.isFetching}
          className="ml-auto px-5 py-2 bg-blue-600 text-white text-sm rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50 shadow-sm"
        >
          {query.isFetching ? 'Scanning…' : 'Scan Now'}
        </button>
      </div>

      {/* Score legend */}
      <div className="bg-blue-50 border border-blue-100 rounded-xl px-5 py-3 mb-6 text-xs text-blue-800">
        <span className="font-semibold">Combined Score</span> = 35% breakout ML probability + 35% zone ML confidence + 20% conviction signals + 10% volume surge.
        <span className="ml-2 font-semibold">Watching</span> = within 3% below resistance with strong zone backing.
      </div>

      {query.isLoading && (
        <div className="text-center py-20 text-gray-400">Scanning for confluence setups…</div>
      )}

      {query.isError && (
        <div className="text-center py-20 text-red-400 text-sm">
          Scan failed. Ensure zone precompute has run today.
        </div>
      )}

      {/* Breaking Out section */}
      {!query.isLoading && (
        <section className="mb-8">
          <div className="flex items-center gap-3 mb-3">
            <h2 className="text-base font-bold text-gray-800">Breaking Out Now</h2>
            <span className="text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full font-medium">
              {breakouts.length} stocks
            </span>
            <span className="text-xs text-gray-400">Zone-backed breakouts · ranked by combined score</span>
          </div>

          {breakouts.length === 0 ? (
            <div className="text-center py-10 text-gray-400 text-sm bg-white rounded-xl border border-gray-200">
              No confluence breakouts today.
              {!query.isLoading && query.data && ' Run zone precompute if data is stale.'}
            </div>
          ) : (
            <div className="space-y-3">
              {breakouts.map(sig => <BreakoutCard key={sig.symbol} sig={sig} />)}
            </div>
          )}
        </section>
      )}

      {/* Near Breakout section */}
      {!query.isLoading && (
        <section>
          <div className="flex items-center gap-3 mb-3">
            <h2 className="text-base font-bold text-gray-800">Watching</h2>
            <span className="text-xs bg-amber-100 text-amber-700 px-2 py-0.5 rounded-full font-medium">
              {nearBreakout.length} stocks
            </span>
            <span className="text-xs text-gray-400">Within 3% below resistance · strong zone · potential breakout</span>
          </div>

          {nearBreakout.length === 0 ? (
            <div className="text-center py-10 text-gray-400 text-sm bg-white rounded-xl border border-gray-200">
              No stocks in the watchlist zone today.
            </div>
          ) : (
            <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
              <div className="grid px-4 py-2 text-[10px] font-bold text-gray-500 uppercase bg-gray-50 border-b"
                style={{ gridTemplateColumns: '1fr 90px 80px 80px 65px 55px 65px 55px' }}>
                <span>Symbol</span>
                <span className="text-right">Price</span>
                <span className="text-right">Resistance</span>
                <span className="text-right">Distance</span>
                <span className="text-right">Vol×</span>
                <span className="text-right">RSI</span>
                <span className="text-center">Zone ML</span>
                <span className="text-center">Score</span>
              </div>
              {nearBreakout.map(sig => <NearBreakoutRow key={sig.symbol} sig={sig} />)}
            </div>
          )}
        </section>
      )}
    </div>
  )
}
