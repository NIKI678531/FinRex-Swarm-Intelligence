<template>
  <div class="mini-spark">
    <div class="spark-head">
      <span class="spark-label">{{ label }}</span>
      <strong v-if="latestText" class="spark-latest" :style="{ color: latestColor }">{{ latestText }}</strong>
    </div>
    <EChart v-if="data && data.length" :option="option" :height="height" />
    <div v-else class="empty">无数据</div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import EChart from './EChart.vue'

const props = defineProps({
  label: { type: String, default: '' },
  data: { type: Array, default: () => [] },
  labels: { type: Array, default: () => [] },
  color: { type: String, default: '#6366F1' },
  height: { type: String, default: '80px' },
  format: { type: Function, default: null }, // (v) => string
  showLatest: { type: Boolean, default: true },
})

const latestText = computed(() => {
  if (!props.showLatest || !props.data?.length) return ''
  const v = props.data[props.data.length - 1]
  if (v == null) return ''
  if (props.format) return props.format(v)
  return Number(v).toFixed(2)
})

const latestColor = computed(() => {
  if (!props.data?.length || props.data.length < 2) return props.color
  const last = props.data[props.data.length - 1]
  const first = props.data[0]
  if (last > first) return '#26A269'
  if (last < first) return '#C0392B'
  return '#64748B'
})

const option = computed(() => ({
  grid: { left: 0, right: 0, top: 4, bottom: 4 },
  xAxis: { type: 'category', show: false, data: props.labels.length ? props.labels : props.data.map((_, i) => i) },
  yAxis: { type: 'value', show: false, scale: true },
  tooltip: {
    trigger: 'axis',
    formatter: (params) => {
      const p = params[0]
      const v = p.value
      const lbl = props.format ? props.format(v) : Number(v).toFixed(3)
      return `${p.axisValueLabel || ''}<br/><b>${lbl}</b>`
    },
  },
  series: [{
    type: 'line',
    data: props.data,
    smooth: true,
    symbol: 'none',
    lineStyle: { color: props.color, width: 1.6 },
    areaStyle: { color: props.color, opacity: 0.12 },
  }],
}))
</script>

<style scoped>
.mini-spark { padding: 8px 10px; border: 1px solid #E5E7EB; border-radius: 8px; background: #FFF; }
.spark-head { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 4px; }
.spark-label { font-size: 11px; color: #64748B; letter-spacing: .04em; text-transform: uppercase; }
.spark-latest { font-size: 13px; font-weight: 700; }
.empty { font-size: 11px; color: #94A3B8; padding: 8px 0; text-align: center; }
</style>
