import { useEffect, useRef } from 'react'
import {
  createChart,
  ColorType,
  CrosshairMode,
  LineStyle,
  CandlestickSeries,
  type IChartApi,
} from 'lightweight-charts'
import type { ZoneBand, ChartSetupLines, OhlcvBar } from '../api/zones'

interface PriceChartProps {
  ohlcv: OhlcvBar[]
  demandBands?: ZoneBand[]
  supplyBands?: ZoneBand[]
  longSetup?: ChartSetupLines
  shortSetup?: ChartSetupLines
  height?: number
}

export function PriceChart({
  ohlcv,
  demandBands = [],
  supplyBands = [],
  longSetup,
  shortSetup,
  height = 400,
}: PriceChartProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef     = useRef<IChartApi | null>(null)

  useEffect(() => {
    if (!containerRef.current || ohlcv.length === 0) return

    const chart = createChart(containerRef.current, {
      width:  containerRef.current.clientWidth,
      height,
      layout: {
        background: { type: ColorType.Solid, color: '#0f172a' },
        textColor:  '#94a3b8',
      },
      grid: {
        vertLines: { color: '#1e293b' },
        horzLines: { color: '#1e293b' },
      },
      crosshair: { mode: CrosshairMode.Normal },
      timeScale: { borderColor: '#334155', timeVisible: true },
      rightPriceScale: { borderColor: '#334155' },
    })
    chartRef.current = chart

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor:      '#22c55e',
      downColor:    '#ef4444',
      borderVisible: false,
      wickUpColor:   '#22c55e',
      wickDownColor: '#ef4444',
    })

    candleSeries.setData(
      ohlcv.map(d => ({
        time:  d.date as any,
        open:  d.open,
        high:  d.high,
        low:   d.low,
        close: d.close,
      }))
    )

    // Demand zone bands (green)
    for (const z of demandBands) {
      candleSeries.createPriceLine({
        price:             z.low,
        color:             'rgba(34, 197, 94, 0.4)',
        lineWidth:         1,
        lineStyle:         LineStyle.Solid,
        axisLabelVisible:  false,
      })
      candleSeries.createPriceLine({
        price:             z.high,
        color:             'rgba(34, 197, 94, 0.7)',
        lineWidth:         2,
        lineStyle:         LineStyle.Solid,
        axisLabelVisible:  true,
        title:             `D${z.strength}${z.source === 'vwap' ? ' VWAP' : ''}`,
      })
    }

    // Supply zone bands (red)
    for (const z of supplyBands) {
      candleSeries.createPriceLine({
        price:             z.low,
        color:             'rgba(239, 68, 68, 0.7)',
        lineWidth:         2,
        lineStyle:         LineStyle.Solid,
        axisLabelVisible:  true,
        title:             `S${z.strength}${z.source === 'vwap' ? ' VWAP' : ''}`,
      })
      candleSeries.createPriceLine({
        price:             z.high,
        color:             'rgba(239, 68, 68, 0.4)',
        lineWidth:         1,
        lineStyle:         LineStyle.Solid,
        axisLabelVisible:  false,
      })
    }

    // Setup lines (long)
    if (longSetup) {
      candleSeries.createPriceLine({ price: longSetup.entry,    color: '#3b82f6', lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: 'Entry' })
      candleSeries.createPriceLine({ price: longSetup.stop_loss, color: '#ef4444', lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: 'SL' })
      if (longSetup.target != null) {
        candleSeries.createPriceLine({ price: longSetup.target, color: '#22c55e', lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: 'T2' })
      }
    }

    chart.timeScale().fitContent()

    // Resize observer
    const ro = new ResizeObserver(() => {
      if (containerRef.current) chart.applyOptions({ width: containerRef.current.clientWidth })
    })
    ro.observe(containerRef.current)

    return () => {
      ro.disconnect()
      chart.remove()
      chartRef.current = null
    }
  }, [ohlcv, demandBands, supplyBands, longSetup, shortSetup, height])

  return <div ref={containerRef} style={{ height }} />
}
