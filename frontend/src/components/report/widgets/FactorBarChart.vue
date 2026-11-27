<template>
  <div class="factor-bars">
    <EChart v-if="bars.length" :option="option" :height="height" />
    <div v-else class="empty">暂无因子数据</div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import EChart from './EChart.vue'
import { buildFactorBars } from './financialFactorAdapter'

const props = defineProps({
  financialContext: { type: Object, default: () => ({}) },
  height: { type: String, default: '260px' },
})

const bars = computed(() => buildFactorBars(props.financialContext))

const option = computed(() => ({
  grid: { left: 80, right: 90, top: 16, bottom: 24 },
  tooltip: {
    trigger: 'axis',
    axisPointer: { type: 'shadow' },
    formatter: (params) => {
      const p = params[0]
      const b = bars.value[p.dataIndex]
      if (!b) return ''
      return `<b>${b.label}</b><br/>` +
             `得分: ${b.score >= 0 ? '+' : ''}${b.score.toFixed(3)}<br/>` +
             `权重: ${(b.weight * 100).toFixed(1)}%<br/>` +
             `贡献: ${b.contribution >= 0 ? '+' : ''}${b.contribution.toFixed(3)}`
    },
  },
  xAxis: {
    type: 'value',
    min: -1, max: 1,
    axisLabel: { fontSize: 11, color: '#94A3B8' },
    splitLine: { lineStyle: { color: '#F1F5F9' } },
  },
  yAxis: {
    type: 'category',
    data: bars.value.map(b => b.label),
    axisLabel: { fontSize: 12, color: '#475569' },
    axisLine: { show: false },
    axisTick: { show: false },
  },
  series: [{
    type: 'bar',
    barWidth: 18,
    data: bars.value.map(b => ({
      value: b.score,
      itemStyle: { color: b.color, borderRadius: [0, 4, 4, 0] },
    })),
    label: {
      show: true,
      position: 'right',
      formatter: (p) => {
        const b = bars.value[p.dataIndex]
        return `权重 ${(b.weight * 100).toFixed(0)}%`
      },
      color: '#64748B',
      fontSize: 11,
    },
  }],
}))
</script>

<style scoped>
.factor-bars { width: 100%; }
.empty { padding: 24px; color: #94A3B8; text-align: center; font-size: 13px; }
</style>
