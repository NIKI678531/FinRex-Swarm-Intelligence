<template>
  <EChart v-if="hasData" :option="option" :height="height" preserve-data-zoom />
  <div v-else class="empty">No chart data for this run.</div>
</template>

<script setup>
import { computed } from 'vue'
import EChart from '@/components/report/widgets/EChart.vue'

const props = defineProps({
  points: { type: Array, default: () => [] },
  trades: { type: Array, default: () => [] },
  symbol: { type: String, default: '' },
  height: { type: String, default: '720px' }
})

const rows = computed(() => props.points || [])
const hasData = computed(() => rows.value.length > 0)
const dates = computed(() => rows.value.map(p => p.ts))

const buyMarkers = computed(() => entryMarkers('buy'))
const sellMarkers = computed(() => entryMarkers('sell'))
const positiveTrades = computed(() => closedTrades().filter(t => Number(t.pnl) >= 0).map(t => [t.ts, round(t.pnl)]))
const negativeTrades = computed(() => closedTrades().filter(t => Number(t.pnl) < 0).map(t => [t.ts, round(t.pnl)]))

const option = computed(() => {
  const close = rows.value.map(p => n(p.close))
  const volume = rows.value.map((p, idx) => ({
    value: n(p.volume),
    itemStyle: { color: Number(p.close) >= Number(p.open ?? rows.value[idx - 1]?.close) ? 'rgba(156,163,175,.56)' : 'rgba(244,63,94,.48)' }
  }))

  return {
    backgroundColor: '#FFFFFF',
    animation: false,
    axisPointer: {
      link: [{ xAxisIndex: [0, 1, 2, 3, 4, 5] }],
      label: { backgroundColor: '#111827', color: '#FFFFFF', fontSize: 10 }
    },
    legend: {
      top: 4,
      left: 68,
      itemWidth: 16,
      itemHeight: 8,
      textStyle: { color: '#334155', fontSize: 11 },
      data: ['cash', 'value', 'Positive', 'Negative', 'Close', 'Volume', 'buy', 'sell', 'EMA 9', 'EMA 12', 'EMA 26', 'K', 'D', 'J', 'Highest 9', 'Lowest 9', 'macd', 'signal', 'histo']
    },
    grid: [
      { left: 68, right: 66, top: 34, height: 46 },
      { left: 68, right: 66, top: 88, height: 52 },
      { left: 68, right: 66, top: 150, height: 286 },
      { left: 68, right: 66, top: 448, height: 58 },
      { left: 68, right: 66, top: 514, height: 58 },
      { left: 68, right: 66, top: 580, height: 88 }
    ],
    tooltip: {
      trigger: 'axis',
      confine: true,
      transitionDuration: 0,
      backgroundColor: '#FFFFFF',
      borderColor: '#CBD5E1',
      textStyle: { color: '#0F172A', fontSize: 12 },
      extraCssText: 'box-shadow: 0 12px 28px rgba(15,23,42,.16); border-radius: 6px;',
      formatter: tooltipFormatter
    },
    dataZoom: [
      { type: 'inside', xAxisIndex: [0, 1, 2, 3, 4, 5], filterMode: 'filter' },
      { type: 'slider', xAxisIndex: [0, 1, 2, 3, 4, 5], bottom: 12, height: 22, borderColor: '#CBD5E1', fillerColor: 'rgba(17,24,39,.14)', handleStyle: { color: '#111827' }, textStyle: { color: '#64748B' } }
    ],
    xAxis: makeXAxes(),
    yAxis: [
      valueAxis(0, 'Broker', v => compact(v)),
      valueAxis(1, 'P/L', v => compact(v)),
      valueAxis(2, props.symbol || 'Price', v => price(v), 'right'),
      { type: 'value', gridIndex: 2, show: false, scale: true },
      valueAxis(3, 'KDJ', v => Number(v).toFixed(0), 'right'),
      valueAxis(4, 'Range', v => price(v), 'right'),
      valueAxis(5, 'MACD', v => compact(v), 'right')
    ],
    series: [
      line('cash', 0, 0, rows.value.map(p => n(p.cash)), '#F43F5E', 1.4),
      line('value', 0, 0, rows.value.map(p => n(p.value)), '#2563EB', 1.4),
      scatter('Positive', 1, 1, positiveTrades.value, '#0B43FF', 'circle', 11),
      scatter('Negative', 1, 1, negativeTrades.value, '#FF1717', 'circle', 11),
      line('Close', 2, 2, close, '#111827', 1.8),
      { name: 'Volume', type: 'bar', xAxisIndex: 2, yAxisIndex: 3, data: volume, barWidth: '58%', itemStyle: { opacity: 0.78 }, z: 1 },
      scatter('buy', 2, 2, buyMarkers.value, '#00E51B', 'triangle', 14, 0),
      scatter('sell', 2, 2, sellMarkers.value, '#FF1717', 'triangle', 14, 180),
      line('EMA 9', 2, 2, rows.value.map(p => n(p.ema_9)), '#16A34A', 1.4),
      line('EMA 12', 2, 2, rows.value.map(p => n(p.ema_12)), '#F43F5E', 1.4),
      line('EMA 26', 2, 2, rows.value.map(p => n(p.ema_26)), '#0B43FF', 1.4),
      line('K', 3, 4, rows.value.map(p => n(p.kdj_k)), '#2563EB', 1.2, kdjMarkLine()),
      line('D', 3, 4, rows.value.map(p => n(p.kdj_d)), '#F43F5E', 1.2),
      line('J', 3, 4, rows.value.map(p => n(p.kdj_j)), '#D97706', 1.2),
      line('Highest 9', 4, 5, rows.value.map(p => n(p.highest_9)), '#F43F5E', 1.5),
      line('Lowest 9', 4, 5, rows.value.map(p => n(p.lowest_9)), '#16A34A', 1.5),
      { name: 'histo', type: 'bar', xAxisIndex: 5, yAxisIndex: 6, data: rows.value.map(p => ({ value: n(p.macd_hist), itemStyle: { color: Number(p.macd_hist) >= 0 ? 'rgba(22,163,74,.68)' : 'rgba(244,63,94,.68)' } })), barWidth: '58%' },
      line('macd', 5, 6, rows.value.map(p => n(p.macd)), '#F43F5E', 1.4, zeroMarkLine()),
      line('signal', 5, 6, rows.value.map(p => n(p.macd_signal)), '#0B43FF', 1.3, undefined, 'dashed')
    ]
  }
})

function makeXAxes () {
  return [0, 1, 2, 3, 4, 5].map(i => ({
    type: 'category',
    gridIndex: i,
    data: dates.value,
    boundaryGap: false,
    axisLine: { lineStyle: { color: '#94A3B8' } },
    axisTick: { show: false },
    axisLabel: { show: i === 5, color: '#64748B', fontSize: 10, formatter: formatDate },
    splitLine: { show: true, lineStyle: { color: '#E5E7EB' } }
  }))
}

function valueAxis (gridIndex, name, formatter, position = 'right') {
  return {
    type: 'value',
    gridIndex,
    name,
    scale: true,
    position,
    nameTextStyle: { color: '#64748B', fontSize: 10 },
    axisLabel: { color: '#334155', fontSize: 10, formatter },
    splitLine: { lineStyle: { color: '#D1D5DB' } }
  }
}

function line (name, xAxisIndex, yAxisIndex, data, color, width, markLine, type = 'solid') {
  return {
    name,
    type: 'line',
    xAxisIndex,
    yAxisIndex,
    data,
    symbol: 'none',
    connectNulls: false,
    lineStyle: { color, width, type },
    itemStyle: { color },
    markLine
  }
}

function scatter (name, xAxisIndex, yAxisIndex, data, color, symbol, symbolSize, symbolRotate = 0) {
  return {
    name,
    type: 'scatter',
    xAxisIndex,
    yAxisIndex,
    data,
    symbol,
    symbolSize,
    symbolRotate,
    itemStyle: { color },
    z: 8
  }
}

function closedTrades () {
  return (props.trades || []).filter(t => t.kind && t.kind !== 'entry' && t.ts)
}

function entryMarkers (side) {
  return (props.trades || [])
    .filter(t => t.kind === 'entry' && t.side === side && t.ts)
    .map(t => [t.ts, n(t.price)])
}

function kdjMarkLine () {
  return {
    silent: true,
    symbol: 'none',
    label: { color: '#64748B', fontSize: 10 },
    lineStyle: { color: '#94A3B8', type: 'dashed', width: 1 },
    data: [{ yAxis: 80, label: { formatter: '80' } }, { yAxis: 20, label: { formatter: '20' } }]
  }
}

function zeroMarkLine () {
  return {
    silent: true,
    symbol: 'none',
    label: { show: false },
    lineStyle: { color: '#64748B', type: 'dotted', width: 1 },
    data: [{ yAxis: 0 }]
  }
}

function tooltipFormatter (params) {
  const items = Array.isArray(params) ? params : [params]
  const title = formatDateTime(items[0]?.axisValue)
  const lines = items
    .filter(item => item?.value != null)
    .map(item => {
      const value = Array.isArray(item.value) ? item.value[1] : item.value
      return `<div><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${item.color};margin-right:6px"></span>${item.seriesName}: <b>${tooltipValue(item.seriesName, value)}</b></div>`
    })
  return `<div class="q-tooltip"><div class="q-tooltip__time">${title}</div>${lines.join('')}</div>`
}

function tooltipValue (name, value) {
  if (value == null || Number.isNaN(Number(value))) return '-'
  if (['cash', 'value', 'Close', 'EMA 9', 'EMA 12', 'EMA 26', 'Highest 9', 'Lowest 9'].includes(name)) return price(value)
  if (['Positive', 'Negative'].includes(name)) return Number(value).toLocaleString('en-US', { maximumFractionDigits: 2 })
  return Number(value).toFixed(4)
}

function n (value) {
  const out = Number(value)
  return Number.isFinite(out) ? out : null
}

function round (value) {
  const out = n(value)
  return out == null ? null : Number(out.toFixed(4))
}

function price (value) {
  if (value == null || Number.isNaN(Number(value))) return '-'
  return Number(value).toLocaleString('en-US', { maximumFractionDigits: 2 })
}

function compact (value) {
  if (value == null || Number.isNaN(Number(value))) return '-'
  return Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 2 }).format(Number(value))
}

function formatDate (value) {
  if (!value) return ''
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return String(value).slice(0, 10)
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}-${String(d.getUTCDate()).padStart(2, '0')}`
}

function formatDateTime (value) {
  if (!value) return ''
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return String(value)
  return `${formatDate(value)} ${String(d.getUTCHours()).padStart(2, '0')}:${String(d.getUTCMinutes()).padStart(2, '0')} UTC`
}
</script>

<style scoped>
.empty {
  min-height: 420px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px dashed #CBD5E1;
  border-radius: 6px;
  color: #94A3B8;
  font-size: 13px;
}
:deep(.q-tooltip) { min-width: 190px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; line-height: 1.7; }
:deep(.q-tooltip__time) { margin-bottom: 6px; color: #64748B; font-size: 11px; }
</style>
