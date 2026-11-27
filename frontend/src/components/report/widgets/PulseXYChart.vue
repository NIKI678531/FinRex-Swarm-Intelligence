<template>
  <div class="pulse-xy">
    <EChart v-if="hasPulses" :option="option" :height="height" />
    <div v-else class="pulse-empty">
      <strong>暂无动态脉冲</strong>
      <span>OASIS action stream 还没有足够的声量峰值，或当前报告只有静态 fallback 数据。</span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import EChart from './EChart.vue'

const props = defineProps({
  pulses: { type: Array, default: () => [] },
  height: { type: String, default: '300px' }
})

const hasPulses = computed(() => normalized.value.length > 0)

const normalized = computed(() => {
  const pulses = props.pulses || []
  return pulses
    .map((pulse, index) => {
      const x = numeric(pulse.x, numeric(pulse.simulated_hour, numeric(pulse.round, index + 1)))
      const y = Math.max(0, Math.min(1, numeric(pulse.y, numeric(pulse.intensity, 0.5))))
      const volume = Math.max(0, numeric(pulse.volume, 0))
      return {
        ...pulse,
        x,
        y,
        volume,
        layer: pulse.layer || pulse.source_layer || 'inferred',
        title: pulse.title || `Pulse ${index + 1}`
      }
    })
    .filter(pulse => Number.isFinite(pulse.x) && Number.isFinite(pulse.y))
})

const maxVolume = computed(() => Math.max(...normalized.value.map(p => p.volume), 1))

const option = computed(() => {
  const data = normalized.value.map(pulse => ({
    value: [pulse.x, pulse.y, pulse.volume],
    name: pulse.title,
    pulse
  }))

  return {
    tooltip: {
      trigger: 'item',
      formatter: (params) => {
        const p = params.data.pulse
        const time = p.t ? `<br/>时间: ${formatTime(p.t)}` : ''
        const round = p.round !== undefined && p.round !== null ? `<br/>Round: ${p.round}` : ''
        const hour = p.simulated_hour !== undefined && p.simulated_hour !== null ? `<br/>Sim hour: ${p.simulated_hour}` : ''
        const scores = p.model_scores || {}
        return [
          `<strong>${escapeHtml(p.title)}</strong>`,
          time,
          round,
          hour,
          `<br/>Signal: ${escapeHtml(displayLayer(p.layer))}`,
          `<br/>Volume: ${p.volume || 0}`,
          `<br/>Intensity: ${Math.round((p.y || 0) * 100)}%`,
          scores.burst_state ? `<br/>Burst: ${escapeHtml(scores.burst_state)}` : '',
          p.summary ? `<br/><span>${escapeHtml(p.summary)}</span>` : ''
        ].join('')
      }
    },
    grid: { left: 54, right: 28, top: 28, bottom: 48 },
    xAxis: {
      type: 'value',
      name: 'Round / Sim Hour',
      nameLocation: 'middle',
      nameGap: 30,
      splitLine: { lineStyle: { type: 'dashed' } }
    },
    yAxis: {
      type: 'value',
      name: 'Heat / Risk',
      min: 0,
      max: 1,
      splitLine: { lineStyle: { type: 'dashed' } }
    },
    series: [{
      type: 'scatter',
      data,
      symbolSize: (value) => 10 + Math.sqrt((value[2] || 0) / maxVolume.value) * 34,
      itemStyle: {
        color: (params) => layerColor(params.data.pulse.layer),
        opacity: 0.78,
        borderColor: '#fff',
        borderWidth: 1
      },
      label: {
        show: true,
        formatter: (params) => trim(params.data.name, 12),
        position: 'top',
        color: '#64748B',
        fontSize: 11
      }
    }]
  }
})

function numeric(value, fallback) {
  const number = Number(value)
  return Number.isFinite(number) ? number : fallback
}

function layerColor(layer) {
  return { observed: '#1B3A8B', inferred: '#64748B', simulated: '#D89A00', Observed: '#1B3A8B', Inferred: '#64748B', Simulated: '#D89A00' }[layer] || '#64748B'
}

function displayLayer(layer) {
  return {
    observed: 'Direct',
    inferred: 'Derived',
    simulated: 'Scenario',
    Observed: 'Direct',
    Inferred: 'Derived',
    Simulated: 'Scenario'
  }[layer] || 'Derived'
}

function trim(text, limit) {
  const value = String(text || '')
  return value.length > limit ? value.slice(0, limit) + '...' : value
}

function formatTime(iso) {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return `${date.getMonth() + 1}/${date.getDate()} ${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`
}

function escapeHtml(value) {
  return String(value || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}
</script>

<style scoped>
.pulse-xy { width: 100%; min-height: 220px; }
.pulse-empty {
  min-height: 260px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  border-radius: var(--r-md);
  background: var(--c-bg-soft);
  color: var(--c-text-muted);
  text-align: center;
  padding: var(--s-4);
}
.pulse-empty strong { color: var(--c-text); font-size: var(--fs-15); }
.pulse-empty span { max-width: 420px; font-size: var(--fs-12); line-height: var(--lh-relaxed); }
</style>
