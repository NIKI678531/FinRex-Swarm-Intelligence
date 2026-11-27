<template>
  <div class="bins-panel">
    <EChart v-if="series.length" :option="option" height="280px" />
    <div v-else class="empty">暂无预测数据，点击"运行 Snapshot"。</div>
    <div v-if="latestForecast" class="meta">
      <span>预期价格 <strong>${{ formatNum(latestForecast.expected_price) }}</strong></span>
      <span>中位数 <strong>${{ formatNum(latestForecast.median_price) }}</strong></span>
      <span>样本路径 <strong>{{ latestForecast.n_paths }}</strong></span>
      <span>每日漂移 bias <strong>{{ (latestForecast.payload?.bias_per_day * 100 || 0).toFixed(3) }}%</strong></span>
      <span>Sigma x <strong>{{ sigmaMultiplier }}</strong></span>
      <span>Model edge <strong>{{ modelEdge }}</strong></span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import EChart from '@/components/report/widgets/EChart.vue'

const props = defineProps({
  bins: { type: Array, default: () => [] },          // [{index, low, high, label, prob, count}]
  baselineProb: { type: Number, default: null },     // 1/n
  latestForecast: { type: Object, default: null }
})

const series = computed(() => props.bins || [])
const modelDebug = computed(() => props.latestForecast?.payload?.model_debug || {})
const sigmaMultiplier = computed(() => {
  const v = props.latestForecast?.payload?.sigma_adjustment?.multiplier
  return v == null || isNaN(v) ? '—' : Number(v).toFixed(2)
})
const modelEdge = computed(() => {
  const p = modelDebug.value?.p_up
  if (p == null || isNaN(p)) return '—'
  return `${((p - 0.5) * 100).toFixed(2)}pp`
})

function formatRange (b) {
  if (b.low == null) return `< $${formatNum(b.high)}`
  if (b.high == null) return `> $${formatNum(b.low)}`
  return `$${formatNum(b.low)} – $${formatNum(b.high)}`
}
function formatNum (v, digits = 0) {
  if (v == null || isNaN(v)) return '—'
  return Number(v).toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits })
}

const option = computed(() => {
  const bins = series.value
  const labels = bins.map(b => b.label || formatRange(b))
  const probs = bins.map(b => +(b.prob * 100).toFixed(2))
  const baseline = props.baselineProb != null ? +(props.baselineProb * 100).toFixed(2) : null
  const baselineSeries = baseline != null ? bins.map(() => baseline) : null
  return {
    backgroundColor: '#FFFFFF',
    grid: { top: 20, right: 16, bottom: 56, left: 56 },
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#FFFFFF',
      borderColor: '#E5E7EB',
      textStyle: { color: '#0F172A' },
      formatter: (params) => {
        const b = bins[params[0].dataIndex]
        const range = formatRange(b)
        const lines = [`<strong>${b.label || range}</strong>`, `区间: ${range}`]
        params.forEach(p => lines.push(`${p.marker} ${p.seriesName}: ${p.value}%`))
        lines.push(`样本: ${b.count}`)
        return lines.join('<br/>')
      }
    },
    legend: { data: baseline != null ? ['模型概率', '均匀基线 1/n'] : ['模型概率'], textStyle: { color: '#64748B' } },
    xAxis: {
      type: 'category', data: labels,
      axisLine: { lineStyle: { color: '#CBD5E1' } },
      axisLabel: { rotate: 25, fontSize: 11, color: '#64748B' }
    },
    yAxis: {
      type: 'value', name: '概率 %', max: Math.max(40, Math.ceil(Math.max(...probs, baseline || 0) / 5) * 5 + 5),
      nameTextStyle: { color: '#64748B' },
      axisLabel: { color: '#64748B' },
      splitLine: { lineStyle: { color: '#EEF2F7' } }
    },
    series: [
      {
        type: 'bar', name: '模型概率', data: probs, barMaxWidth: 48,
        itemStyle: {
          color: (p) => probs[p.dataIndex] > (baseline || 0) ? '#111827' : '#94A3B8'
        },
        label: { show: true, position: 'top', formatter: '{c}%', fontSize: 11, color: '#0F172A' }
      },
      ...(baselineSeries ? [{
        type: 'line', name: '均匀基线 1/n', data: baselineSeries,
        lineStyle: { type: 'dashed', color: '#F59E0B' },
        symbol: 'none', smooth: false
      }] : [])
    ]
  }
})
</script>

<style scoped>
.bins-panel { display: flex; flex-direction: column; gap: 12px; color: #0F172A; }
.meta { display: flex; gap: 10px; flex-wrap: wrap; font-size: 12px; color: #64748B; }
.meta span { padding: 7px 9px; border: 1px solid #EEF1F5; border-radius: 6px; background: #F8FAFC; }
.meta strong { color: #0F172A; }
.empty { padding: 32px; text-align: center; color: #94A3B8; font-size: 13px; }
</style>
