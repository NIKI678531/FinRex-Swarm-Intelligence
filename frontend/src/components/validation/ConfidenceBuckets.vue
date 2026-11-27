<template>
  <EChart v-if="buckets.length" :option="option" height="260px" />
  <div v-else class="empty">No settled confidence buckets yet.</div>
</template>

<script setup>
import { computed } from 'vue'
import EChart from '@/components/report/widgets/EChart.vue'
const props = defineProps({ buckets: { type: Array, default: () => [] } })
const option = computed(() => ({
  backgroundColor: '#FFFFFF',
  grid: { left: 54, right: 54, top: 34, bottom: 44 },
  tooltip: { trigger: 'axis' },
  legend: { top: 0, data: ['Win Rate', 'Samples'], textStyle: { color: '#64748B' } },
  xAxis: { type: 'category', data: props.buckets.map(b => `${(b.bucket_low * 100).toFixed(0)}-${(b.bucket_high * 100).toFixed(0)}%`), axisLabel: { color: '#64748B' } },
  yAxis: [
    { type: 'value', min: 0, max: 1, name: 'Win Rate', axisLabel: { color: '#64748B', formatter: v => `${Math.round(v * 100)}%` }, splitLine: { lineStyle: { color: '#EEF2F7' } } },
    { type: 'value', name: 'Samples', axisLabel: { color: '#64748B' }, splitLine: { show: false } }
  ],
  series: [
    { name: 'Win Rate', type: 'line', yAxisIndex: 0, data: props.buckets.map(b => b.win_rate), smooth: true, itemStyle: { color: '#2563EB' } },
    { name: 'Samples', type: 'bar', yAxisIndex: 1, data: props.buckets.map(b => b.n), barMaxWidth: 30, itemStyle: { color: '#94A3B8' } }
  ]
}))
</script>

<style scoped>
.empty { padding: 28px; text-align: center; color: #94A3B8; font-size: 13px; }
</style>
