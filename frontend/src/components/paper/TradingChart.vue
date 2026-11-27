<template>
  <div class="tv-chart">
    <div ref="containerRef" class="tv-chart__canvas"></div>
    <a
      class="tv-chart__attr"
      href="https://www.tradingview.com/lightweight-charts/"
      target="_blank"
      rel="noopener"
    >Charts by TradingView</a>
    <div v-if="!candles.length" class="tv-chart__empty">{{ emptyText }}</div>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import {
  createChart,
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
  ColorType,
  CrosshairMode,
  LineStyle,
  createSeriesMarkers
} from 'lightweight-charts'

const props = defineProps({
  candles: { type: Array, default: () => [] },
  markers: { type: Array, default: () => [] },
  priceLines: { type: Array, default: () => [] },
  emptyText: { type: String, default: 'No data' },
  smaPeriod: { type: Number, default: 20 }
})

const containerRef = ref(null)
let chart = null
let candleSeries = null
let volumeSeries = null
let smaSeries = null
let markersApi = null
let priceLineHandles = []
let ro = null

const cssVar = (name, fallback) => {
  if (typeof window === 'undefined') return fallback
  const v = getComputedStyle(document.documentElement).getPropertyValue(name)
  return v ? v.trim() : fallback
}

function buildChart () {
  if (!containerRef.value) return
  const textColor = cssVar('--c-text', '#222')
  const borderColor = cssVar('--c-border', '#e2e2e2')
  chart = createChart(containerRef.value, {
    autoSize: true,
    layout: {
      background: { type: ColorType.Solid, color: 'transparent' },
      textColor,
      fontFamily: cssVar('--f-mono', 'monospace')
    },
    grid: {
      vertLines: { color: borderColor, style: LineStyle.Dotted },
      horzLines: { color: borderColor, style: LineStyle.Dotted }
    },
    crosshair: { mode: CrosshairMode.Normal },
    rightPriceScale: { borderColor },
    timeScale: { borderColor, timeVisible: true, secondsVisible: false }
  })

  candleSeries = chart.addSeries(CandlestickSeries, {
    upColor: '#16a34a',
    downColor: '#dc2626',
    borderUpColor: '#16a34a',
    borderDownColor: '#dc2626',
    wickUpColor: '#16a34a',
    wickDownColor: '#dc2626'
  })

  volumeSeries = chart.addSeries(HistogramSeries, {
    priceFormat: { type: 'volume' },
    priceScaleId: '',
    color: 'rgba(120,120,140,.35)'
  })
  volumeSeries.priceScale().applyOptions({
    scaleMargins: { top: 0.82, bottom: 0 }
  })

  smaSeries = chart.addSeries(LineSeries, {
    color: '#2563eb',
    lineWidth: 1,
    priceLineVisible: false,
    lastValueVisible: false
  })

  markersApi = createSeriesMarkers(candleSeries, [])
  render()
}

function computeSma (candles, period) {
  if (candles.length < period) return []
  const out = []
  let sum = 0
  for (let i = 0; i < candles.length; i++) {
    sum += candles[i].close
    if (i >= period) sum -= candles[i - period].close
    if (i >= period - 1) out.push({ time: candles[i].time, value: sum / period })
  }
  return out
}

function render () {
  if (!chart || !candleSeries) return
  const candles = props.candles || []
  candleSeries.setData(candles.map(c => ({
    time: c.time, open: c.open, high: c.high, low: c.low, close: c.close
  })))
  volumeSeries.setData(candles.map(c => ({
    time: c.time,
    value: c.volume || 0,
    color: c.close >= c.open ? 'rgba(22,163,74,.35)' : 'rgba(220,38,38,.35)'
  })))
  smaSeries.setData(computeSma(candles, props.smaPeriod))

  if (markersApi) {
    markersApi.setMarkers((props.markers || []).slice().sort((a, b) => a.time - b.time))
  }

  priceLineHandles.forEach(h => { try { candleSeries.removePriceLine(h) } catch (e) { /* ignore */ } })
  priceLineHandles = (props.priceLines || []).map(pl => candleSeries.createPriceLine({
    price: pl.price,
    color: pl.color || '#888',
    lineWidth: 1,
    lineStyle: pl.dashed ? LineStyle.Dashed : LineStyle.Solid,
    axisLabelVisible: true,
    title: pl.title || ''
  }))

  if (candles.length) chart.timeScale().fitContent()
}

onMounted(async () => {
  await nextTick()
  buildChart()
  ro = new ResizeObserver(() => { if (chart) chart.applyOptions({}) })
  if (containerRef.value) ro.observe(containerRef.value)
})

onBeforeUnmount(() => {
  if (ro) ro.disconnect()
  if (chart) { chart.remove(); chart = null }
})

watch(() => props.candles, render, { deep: false })
watch(() => props.markers, () => { if (markersApi) markersApi.setMarkers((props.markers || []).slice().sort((a, b) => a.time - b.time)) }, { deep: false })
watch(() => props.priceLines, render, { deep: false })
</script>

<style scoped>
.tv-chart { position: relative; width: 100%; height: 100%; min-height: 320px; }
.tv-chart__canvas { width: 100%; height: 100%; }
.tv-chart__attr {
  position: absolute; left: 8px; bottom: 6px; z-index: 3;
  font-size: 10px; color: var(--c-text-subtle); text-decoration: none;
  opacity: .6;
}
.tv-chart__attr:hover { opacity: 1; }
.tv-chart__empty {
  position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
  color: var(--c-text-subtle); font-size: 13px; font-family: var(--f-mono);
}
</style>
