<template>
  <div class="card">
    <h3>Rolling Risk (90D Sharpe &amp; Volatility)</h3>
    <EChart v-if="hasData" :option="option" height="300px" />
    <div v-else class="empty">No rolling metrics available (need ≥ window length of data).</div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import EChart from '@/components/report/widgets/EChart.vue'

const props = defineProps({
  rollingSharpe: { type: Array, default: () => [] },
  rollingVol: { type: Array, default: () => [] }
})

const hasData = computed(() =>
  (Array.isArray(props.rollingSharpe) && props.rollingSharpe.length > 0) ||
  (Array.isArray(props.rollingVol) && props.rollingVol.length > 0)
)

const option = computed(() => ({
  grid: { top: 40, right: 56, bottom: 36, left: 56 },
  legend: { top: 4, textStyle: { fontSize: 11 } },
  tooltip: { trigger: 'axis' },
  xAxis: { type: 'time' },
  yAxis: [
    { type: 'value', name: 'Sharpe', position: 'left' },
    {
      type: 'value',
      name: 'Vol (ann.)',
      position: 'right',
      axisLabel: { formatter: (v) => (v * 100).toFixed(0) + '%' }
    }
  ],
  series: [
    {
      type: 'line', name: 'Rolling Sharpe (90D)', yAxisIndex: 0,
      data: (props.rollingSharpe || []).map(p => [p.ts, p.value]),
      symbol: 'none', smooth: true,
      lineStyle: { width: 1.5, color: '#3a8dde' }
    },
    {
      type: 'line', name: 'Rolling Vol (90D)', yAxisIndex: 1,
      data: (props.rollingVol || []).map(p => [p.ts, p.value]),
      symbol: 'none', smooth: true,
      lineStyle: { width: 1.5, color: '#e8a93b', type: 'dashed' }
    }
  ]
}))
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
.empty { padding: var(--s-5); text-align: center; color: var(--c-text-subtle); font-size: 13px; }
</style>
