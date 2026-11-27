<template>
  <div class="factor-radar">
    <EChart v-if="hasData" :option="option" :height="height" />
    <div v-else class="empty">暂无因子数据</div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import EChart from './EChart.vue'
import { buildFactorRadar } from './financialFactorAdapter'

const props = defineProps({
  financialContext: { type: Object, default: () => ({}) },
  height: { type: String, default: '280px' },
})

const data = computed(() => buildFactorRadar(props.financialContext))
const hasData = computed(() => data.value.indicator.length > 0)

const option = computed(() => ({
  tooltip: { trigger: 'item' },
  legend: { bottom: 0, textStyle: { fontSize: 11 } },
  radar: {
    indicator: data.value.indicator,
    radius: '62%',
    splitNumber: 4,
    axisName: { color: '#475569', fontSize: 11 },
    splitLine: { lineStyle: { color: '#E5E7EB' } },
    splitArea: { areaStyle: { color: ['rgba(99,102,241,0.04)', 'rgba(99,102,241,0.02)'] } },
  },
  series: [{
    type: 'radar',
    emphasis: { focus: 'series' },
    data: [
      {
        name: data.value.series[0].name,
        value: data.value.series[0].value,
        areaStyle: { color: 'rgba(99,102,241,0.25)' },
        lineStyle: { color: '#6366F1', width: 2 },
        itemStyle: { color: '#6366F1' },
      },
      {
        name: data.value.series[1].name,
        value: data.value.series[1].value,
        areaStyle: { color: 'rgba(14,165,233,0.18)' },
        lineStyle: { color: '#0EA5E9', width: 2, type: 'dashed' },
        itemStyle: { color: '#0EA5E9' },
      },
    ],
  }],
}))
</script>

<style scoped>
.factor-radar { width: 100%; }
.empty { padding: 24px; color: #94A3B8; text-align: center; font-size: 13px; }
</style>
