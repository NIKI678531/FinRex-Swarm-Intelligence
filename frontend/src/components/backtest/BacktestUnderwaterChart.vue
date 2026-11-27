<template>
  <div class="card">
    <h3>Underwater Plot (Drawdown)</h3>
    <EChart v-if="hasData" :option="option" height="300px" />
    <div v-else class="empty">No drawdown data available.</div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import EChart from '@/components/report/widgets/EChart.vue'

const props = defineProps({
  series: { type: Array, default: () => [] }
})

const hasData = computed(() => Array.isArray(props.series) && props.series.length > 0)

const option = computed(() => {
  const data = (props.series || []).map(p => [p.ts, p.drawdown * 100])
  const minDD = data.length ? Math.min(...data.map(d => d[1])) : 0
  return {
    grid: { top: 20, right: 24, bottom: 36, left: 56 },
    tooltip: {
      trigger: 'axis',
      valueFormatter: (v) => (v == null ? '-' : `${v.toFixed(2)}%`)
    },
    xAxis: { type: 'time' },
    yAxis: {
      type: 'value',
      name: 'Drawdown (%)',
      max: 0,
      min: Math.floor(minDD * 1.1),
      axisLabel: { formatter: '{value}%' }
    },
    series: [{
      type: 'line',
      name: 'Drawdown',
      data,
      symbol: 'none',
      smooth: false,
      lineStyle: { width: 1, color: '#e54' },
      areaStyle: { color: 'rgba(238, 85, 68, 0.25)' }
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
.empty { padding: var(--s-5); text-align: center; color: var(--c-text-subtle); font-size: 13px; }
</style>
