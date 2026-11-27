<template>
  <div class="card">
    <h3>Monthly Returns Heatmap</h3>
    <EChart v-if="hasData" :option="option" height="320px" />
    <div v-else class="empty">No monthly returns data available.</div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import EChart from '@/components/report/widgets/EChart.vue'

const props = defineProps({
  rows: { type: Array, default: () => [] }
})

const hasData = computed(() => Array.isArray(props.rows) && props.rows.length > 0)

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

const option = computed(() => {
  const rows = props.rows || []
  if (!rows.length) return {}
  const years = Array.from(new Set(rows.map(r => r.year))).sort()
  const data = rows.map(r => [r.month - 1, years.indexOf(r.year), Number((r.return * 100).toFixed(2))])
  const values = rows.map(r => r.return * 100)
  const absMax = Math.max(Math.abs(Math.min(...values)), Math.abs(Math.max(...values)), 1)
  return {
    tooltip: {
      position: 'top',
      formatter: (p) => {
        const m = MONTHS[p.data[0]]
        const y = years[p.data[1]]
        return `${m} ${y}<br/><b>${p.data[2].toFixed(2)}%</b>`
      }
    },
    grid: { top: 20, right: 16, bottom: 24, left: 56, containLabel: true },
    xAxis: {
      type: 'category', data: MONTHS,
      splitArea: { show: true },
      axisLabel: { fontSize: 11 }
    },
    yAxis: {
      type: 'category', data: years.map(String),
      splitArea: { show: true },
      axisLabel: { fontSize: 11 }
    },
    visualMap: {
      min: -absMax, max: absMax, calculable: true, orient: 'horizontal',
      left: 'center', bottom: 0, itemHeight: 80, itemWidth: 12,
      inRange: { color: ['#e54', '#fffaf0', '#2ecc71'] }
    },
    series: [{
      name: 'Monthly Return', type: 'heatmap', data,
      label: {
        show: true, fontSize: 10,
        formatter: (p) => `${p.data[2].toFixed(1)}%`
      },
      emphasis: { itemStyle: { shadowBlur: 8, shadowColor: 'rgba(0,0,0,0.4)' } }
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
