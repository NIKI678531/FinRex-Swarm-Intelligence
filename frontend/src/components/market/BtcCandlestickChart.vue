<template>
  <div class="chart-shell">
    <EChart v-if="rows.length" :option="option" :height="height" preserve-data-zoom />
    <div v-else class="empty">暂无 BTC K 线数据</div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import EChart from '@/components/report/widgets/EChart.vue'

const props = defineProps({
  rows: { type: Array, default: () => [] },
  bins: { type: Array, default: () => [] },
  forecast: { type: Object, default: null },
  predictions: { type: Array, default: () => [] },
  height: { type: String, default: '420px' },
  dark: { type: Boolean, default: false }
})

const rows = computed(() => props.rows || [])
const dates = computed(() => rows.value.map(r => r.ts))
const candles = computed(() => rows.value.map(r => [r.open, r.close, r.low, r.high]))
const volume = computed(() => rows.value.map(r => r.volume || 0))
const closeByDate = computed(() => {
  const map = new Map()
  rows.value.forEach(r => map.set(String(r.ts).slice(0, 10), r.close))
  return map
})

const predictionMarkers = computed(() => (props.predictions || []).slice(-240).map(p => {
  const d = String(p.ts || '').slice(0, 10)
  const close = closeByDate.value.get(d) || p.realized_close
  if (!close) return null
  return {
    name: p.hit === true ? 'Hit' : p.hit === false ? 'Miss' : 'Prediction',
    coord: [p.ts, close],
    value: p.predicted_prob_up,
    itemStyle: { color: p.hit === false ? '#F6465D' : '#0ECB81' }
  }
}).filter(Boolean))

// Price range used to clamp open-ended bins ( "< X" / "> Y" ) to the chart.
const priceDomain = computed(() => {
  const lows = rows.value.map(r => Number(r.low)).filter(n => !Number.isNaN(n))
  const highs = rows.value.map(r => Number(r.high)).filter(n => !Number.isNaN(n))
  let lo = lows.length ? Math.min(...lows) : 0
  let hi = highs.length ? Math.max(...highs) : 0
  const f = props.forecast?.payload || props.forecast || {}
  ;[f.expected_price, f.median_price].forEach(v => { if (v) { lo = Math.min(lo, v); hi = Math.max(hi, v) } })
  for (const b of props.bins || []) {
    if (b.low != null) { lo = Math.min(lo, Number(b.low)) }
    if (b.high != null) { hi = Math.max(hi, Number(b.high)) }
  }
  const pad = (hi - lo) * 0.04 || hi * 0.02
  return { lo: lo - pad, hi: hi + pad }
})

const topBinIndex = computed(() => {
  let best = -1; let bestP = -1
  ;(props.bins || []).forEach((b, i) => { const p = Number(b.prob || 0); if (p > bestP) { bestP = p; best = i } })
  return best
})

// Forecast bins are drawn as soft horizontal bands (not a forest of dashed
// lines). Each band carries a single probability label on the LEFT so it never
// collides with the right-hand price axis.
const markAreas = computed(() => {
  const bins = props.bins || []
  if (!bins.length) return []
  const { lo, hi } = priceDomain.value
  return bins.map((b, i) => {
    const isTop = i === topBinIndex.value
    const yLow = b.low != null ? Number(b.low) : lo
    const yHigh = b.high != null ? Number(b.high) : hi
    const prob = b.prob != null ? `${(Number(b.prob) * 100).toFixed(0)}%` : ''
    const fill = isTop ? 'rgba(37,99,235,0.10)' : (i % 2 ? 'rgba(100,116,139,0.045)' : 'rgba(100,116,139,0.085)')
    return [
      {
        yAxis: yLow,
        itemStyle: { color: fill },
        label: {
          show: Boolean(prob),
          position: 'insideTopLeft',
          formatter: prob,
          color: isTop ? '#1D4ED8' : '#64748B',
          fontSize: 10,
          fontWeight: isTop ? 700 : 500,
          padding: [3, 4, 0, 6]
        }
      },
      { yAxis: yHigh }
    ]
  })
})

const markLines = computed(() => {
  const lines = []
  const forecast = props.forecast?.payload || props.forecast || {}
  if (forecast.expected_price) lines.push(line(forecast.expected_price, '预期', '#2563EB'))
  if (forecast.median_price) lines.push(line(forecast.median_price, '中位', '#9333EA'))
  return lines
})

function line (price, name, color, type = 'dashed') {
  return {
    yAxis: Number(price),
    lineStyle: { color, type, width: 1.4 },
    label: {
      show: true,
      position: 'insideStartTop',
      formatter: `${name} ${formatPrice(price, 0)}`,
      color,
      fontSize: 10,
      fontWeight: 600,
      backgroundColor: 'rgba(255,255,255,0.82)',
      padding: [2, 5],
      borderRadius: 3
    }
  }
}

function formatDateLabel (value) {
  if (!value) return ''
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return String(value).slice(0, 16)
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}-${String(d.getUTCDate()).padStart(2, '0')}`
}

function formatTimeLabel (value) {
  if (!value) return ''
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return String(value)
  const date = `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}-${String(d.getUTCDate()).padStart(2, '0')}`
  const time = `${String(d.getUTCHours()).padStart(2, '0')}:${String(d.getUTCMinutes()).padStart(2, '0')}`
  return `${date} ${time} UTC`
}

function formatPrice (value, digits = 2) {
  if (value == null || Number.isNaN(Number(value))) return '-'
  return Number(value).toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits })
}

function formatCompact (value) {
  if (value == null || Number.isNaN(Number(value))) return '-'
  return Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 2 }).format(Number(value))
}

function tooltipFormatter (params) {
  const list = Array.isArray(params) ? params : [params]
  const candle = list.find(p => p.seriesType === 'candlestick')
  if (!candle) return ''
  const idx = candle.dataIndex
  const row = rows.value[idx] || {}
  const up = Number(row.close) >= Number(row.open)
  const color = up ? '#0ECB81' : '#F6465D'
  return `
    <div class="k-tooltip">
      <div class="k-tooltip__time">${formatTimeLabel(row.ts || candle.axisValue)}</div>
      <div class="k-tooltip__grid">
        <span>Open</span><strong>${formatPrice(row.open)}</strong>
        <span>High</span><strong>${formatPrice(row.high)}</strong>
        <span>Low</span><strong>${formatPrice(row.low)}</strong>
        <span>Close</span><strong style="color:${color}">${formatPrice(row.close)}</strong>
        <span>Volume</span><strong>${formatCompact(row.volume)}</strong>
      </div>
    </div>
  `
}

const option = computed(() => {
  const dark = props.dark
  const text = dark ? '#A7B1BC' : '#64748B'
  const border = dark ? '#2B3139' : '#CBD5E1'
  const gridLine = dark ? '#1F2937' : '#EEF2F7'
  const sliderBg = dark ? '#111827' : '#F8FAFC'
  return {
    backgroundColor: dark ? '#0B0F14' : '#FFFFFF',
    animation: false,
    axisPointer: {
      link: [{ xAxisIndex: [0, 1] }],
      snap: true,
      label: { show: true, backgroundColor: dark ? '#2B3139' : '#111827', color: '#FFFFFF', fontSize: 11 }
    },
    grid: [
      { left: 64, right: 28, top: 42, height: '62%' },
      { left: 64, right: 28, bottom: 48, height: '16%' }
    ],
    tooltip: {
      trigger: 'axis',
      confine: true,
      transitionDuration: 0,
      axisPointer: { type: 'cross', crossStyle: { color: dark ? '#7B8794' : '#64748B', type: 'dashed' } },
      backgroundColor: dark ? '#181A20' : '#FFFFFF',
      borderColor: dark ? '#2B3139' : '#E5E7EB',
      textStyle: { color: dark ? '#E5E7EB' : '#0F172A' },
      extraCssText: 'box-shadow: 0 12px 32px rgba(0,0,0,.22); border-radius: 8px;',
      formatter: tooltipFormatter
    },
    toolbox: {
      right: 20,
      top: 6,
      itemSize: 14,
      iconStyle: { borderColor: text },
      emphasis: { iconStyle: { borderColor: '#F3BA2F' } },
      feature: { dataZoom: { yAxisIndex: false }, restore: {} }
    },
    dataZoom: [
      { type: 'inside', xAxisIndex: [0, 1], filterMode: 'filter', zoomOnMouseWheel: true, moveOnMouseMove: true, moveOnMouseWheel: false },
      {
        type: 'slider', xAxisIndex: [0, 1], bottom: 12, height: 24, borderColor: border,
        backgroundColor: sliderBg, fillerColor: dark ? 'rgba(243,186,47,.22)' : 'rgba(17,24,39,.14)',
        handleStyle: { color: dark ? '#F3BA2F' : '#111827', borderColor: dark ? '#F3BA2F' : '#111827' },
        textStyle: { color: text }
      }
    ],
    xAxis: [
      { type: 'category', data: dates.value, boundaryGap: false, axisLine: { lineStyle: { color: border } }, axisLabel: { color: text, fontSize: 10, formatter: formatDateLabel }, axisPointer: { label: { formatter: p => formatTimeLabel(p.value) } } },
      { type: 'category', data: dates.value, gridIndex: 1, boundaryGap: false, axisLabel: { show: false }, axisLine: { lineStyle: { color: border } }, axisPointer: { label: { formatter: p => formatTimeLabel(p.value) } } }
    ],
    yAxis: [
      { type: 'value', scale: true, position: 'right', axisLabel: { color: text, formatter: v => formatPrice(v, 0) }, axisPointer: { label: { formatter: p => `$${formatPrice(p.value)}` } }, splitLine: { lineStyle: { color: gridLine } } },
      { type: 'value', gridIndex: 1, position: 'right', axisLabel: { color: text, fontSize: 10, formatter: formatCompact }, splitLine: { show: false } }
    ],
    series: [
      {
        name: 'BTCUSDT', type: 'candlestick', data: candles.value,
        itemStyle: { color: '#0ECB81', color0: '#F6465D', borderColor: '#0ECB81', borderColor0: '#F6465D' },
        markArea: markAreas.value.length ? { silent: true, data: markAreas.value } : undefined,
        markLine: markLines.value.length ? { silent: true, symbol: 'none', data: markLines.value } : undefined,
        markPoint: predictionMarkers.value.length ? { symbol: 'circle', symbolSize: 9, data: predictionMarkers.value } : undefined
      },
      { name: 'Volume', type: 'bar', xAxisIndex: 1, yAxisIndex: 1, data: volume.value, itemStyle: { color: dark ? '#2B3139' : '#CBD5E1' } }
    ]
  }
})
</script>

<style scoped>
.chart-shell { min-width: 0; }
.empty { min-height: 320px; display: flex; align-items: center; justify-content: center; color: #94A3B8; border: 1px dashed #CBD5E1; border-radius: 8px; }
:deep(.k-tooltip) { min-width: 170px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
:deep(.k-tooltip__time) { margin-bottom: 8px; color: #A7B1BC; font-size: 11px; }
:deep(.k-tooltip__grid) { display: grid; grid-template-columns: auto auto; gap: 5px 14px; align-items: center; }
:deep(.k-tooltip__grid span) { color: #7B8794; font-size: 11px; }
:deep(.k-tooltip__grid strong) { text-align: right; font-size: 12px; font-weight: 700; color: inherit; }
</style>
