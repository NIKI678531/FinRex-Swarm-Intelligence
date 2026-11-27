<template>
  <div class="card">
    <h3>Trade Distributions</h3>
    <div v-if="!hasData" class="empty">No trade data available.</div>
    <div v-else class="row">
      <div class="col">
        <h4>Net PnL per Trade</h4>
        <EChart :option="pnlOption" height="240px" />
        <ul class="stats">
          <li><span>Mean</span><b>{{ fmt(stats.pnl?.mean) }}</b></li>
          <li><span>Median</span><b>{{ fmt(stats.pnl?.median) }}</b></li>
          <li><span>P25 / P75</span><b>{{ fmt(stats.pnl?.p25) }} / {{ fmt(stats.pnl?.p75) }}</b></li>
          <li><span>Min / Max</span><b>{{ fmt(stats.pnl?.min) }} / {{ fmt(stats.pnl?.max) }}</b></li>
        </ul>
      </div>
      <div class="col">
        <h4>Holding Period (bars)</h4>
        <EChart :option="durationOption" height="240px" />
        <ul class="stats">
          <li><span>Mean</span><b>{{ fmtInt(stats.duration?.mean) }}</b></li>
          <li><span>Median</span><b>{{ fmtInt(stats.duration?.median) }}</b></li>
          <li><span>P25 / P75</span><b>{{ fmtInt(stats.duration?.p25) }} / {{ fmtInt(stats.duration?.p75) }}</b></li>
          <li><span>Min / Max</span><b>{{ fmtInt(stats.duration?.min) }} / {{ fmtInt(stats.duration?.max) }}</b></li>
        </ul>
      </div>
      <div class="col side">
        <h4>By Side</h4>
        <EChart :option="sideOption" height="240px" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import EChart from '@/components/report/widgets/EChart.vue'

const props = defineProps({
  distributions: { type: Object, default: () => ({}) }
})

const hasData = computed(() => {
  const d = props.distributions || {}
  return (d.pnl_hist && d.pnl_hist.length) || (d.duration_hist && d.duration_hist.length)
})

const stats = computed(() => ({
  pnl: props.distributions?.pnl_stats || null,
  duration: props.distributions?.duration_stats || null
}))

function fmt (v) {
  if (v == null || isNaN(v)) return '-'
  return Number(v).toLocaleString(undefined, { maximumFractionDigits: 2 })
}
function fmtInt (v) {
  if (v == null || isNaN(v)) return '-'
  return Math.round(Number(v))
}

const pnlOption = computed(() => {
  const bins = props.distributions?.pnl_hist || []
  return histogramOption(bins, (b) => b.bin_low.toFixed(0), '#3a8dde', '#e54')
})
const durationOption = computed(() => {
  const bins = props.distributions?.duration_hist || []
  return histogramOption(bins, (b) => b.bin_low.toFixed(0), '#7a5fff', '#7a5fff')
})

function histogramOption (bins, labelFn, posColor, negColor) {
  return {
    grid: { top: 12, right: 8, bottom: 32, left: 40 },
    tooltip: {
      trigger: 'axis', axisPointer: { type: 'shadow' },
      formatter: (p) => {
        const b = bins[p[0].dataIndex]
        return `${b.bin_low.toFixed(2)} ~ ${b.bin_high.toFixed(2)}<br/>count: <b>${b.count}</b>`
      }
    },
    xAxis: {
      type: 'category',
      data: bins.map(labelFn),
      axisLabel: { fontSize: 10, rotate: 30 }
    },
    yAxis: { type: 'value', name: 'count' },
    series: [{
      type: 'bar',
      data: bins.map(b => ({
        value: b.count,
        itemStyle: { color: b.bin_high <= 0 ? negColor : posColor }
      })),
      barWidth: '85%'
    }]
  }
}

const sideOption = computed(() => {
  const by = props.distributions?.by_side || {}
  const entries = Object.entries(by)
  return {
    tooltip: { trigger: 'item' },
    legend: { bottom: 0, textStyle: { fontSize: 11 } },
    series: [{
      type: 'pie', radius: ['40%', '70%'], center: ['50%', '45%'],
      data: entries.map(([k, v]) => ({ name: k, value: v })),
      label: { fontSize: 11, formatter: '{b}: {c}' }
    }]
  }
})
</script>

<style scoped>
.card {
  border: 1px solid var(--c-border);
  border-radius: var(--r-md);
  background: var(--c-bg-soft);
  padding: var(--s-4);
  min-width: 0;
}
.card h3 {
  margin: 0 0 var(--s-3);
  font-size: 12px;
  font-family: var(--f-mono);
  letter-spacing: .12em;
  text-transform: uppercase;
  color: var(--c-text-muted);
}
.card h4 {
  margin: 0 0 8px;
  font-size: 11px;
  font-family: var(--f-mono);
  color: var(--c-text-subtle);
  letter-spacing: .08em;
}
.row {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: var(--s-4);
}
.col { min-width: 0; }
.stats { list-style: none; padding: 0; margin: 8px 0 0; font-size: 11px; }
.stats li { display: flex; justify-content: space-between; padding: 2px 0; color: var(--c-text-muted); }
.stats b { color: var(--c-text); font-family: var(--f-mono); }
.empty { padding: var(--s-5); text-align: center; color: var(--c-text-subtle); font-size: 13px; }

@media (max-width: 980px) {
  .row { grid-template-columns: 1fr; }
}
</style>
