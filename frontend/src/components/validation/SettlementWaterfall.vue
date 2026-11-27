<template>
  <EChart v-if="points.length" :option="option" height="260px" />
  <div v-else class="empty">No settled weekly bets yet.</div>
</template>

<script setup>
import { computed } from 'vue'
import EChart from '@/components/report/widgets/EChart.vue'
const props = defineProps({ positions: { type: Array, default: () => [] } })
const points = computed(() => (props.positions || []).filter(p => p.realized_pnl != null).slice().reverse())
const option = computed(() => ({
  backgroundColor: '#FFFFFF',
  grid: { left: 56, right: 20, top: 24, bottom: 42 },
  tooltip: { trigger: 'axis' },
  xAxis: { type: 'category', data: points.value.map(p => p.cycle_id || p.id), axisLabel: { color: '#64748B' } },
  yAxis: { type: 'value', name: 'PnL ($)', axisLabel: { color: '#64748B' }, splitLine: { lineStyle: { color: '#EEF2F7' } } },
  series: [{ type: 'bar', name: 'Realized PnL', data: points.value.map(p => p.realized_pnl), itemStyle: { color: p => Number(p.value || 0) >= 0 ? '#16A34A' : '#DC2626' }, barMaxWidth: 34 }]
}))
</script>

<style scoped>
.empty { padding: 28px; text-align: center; color: #94A3B8; font-size: 13px; }
</style>
