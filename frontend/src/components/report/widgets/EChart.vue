<template>
  <div ref="el" class="ec-chart" :style="{ height }"></div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import * as echarts from 'echarts'
import { finrexTheme } from '@/assets/echarts-theme-finrex'

if (typeof window !== 'undefined' && !window.__finrex_theme_registered__) {
  echarts.registerTheme('finrex', finrexTheme)
  window.__finrex_theme_registered__ = true
}

const props = defineProps({
  option: { type: Object, required: true },
  height: { type: String, default: '320px' },
  preserveDataZoom: { type: Boolean, default: false }
})

const el = ref(null)
let inst = null
let ro   = null

function render () {
  if (!el.value) return
  if (!inst) inst = echarts.init(el.value, 'finrex')
  const option = props.preserveDataZoom ? withCurrentDataZoom(props.option) : props.option
  inst.setOption(option, true)
}

function withCurrentDataZoom (option) {
  if (!inst) return option
  const current = inst.getOption()?.dataZoom || []
  if (!current.length || !Array.isArray(option?.dataZoom)) return option
  return {
    ...option,
    dataZoom: option.dataZoom.map((zoom, idx) => {
      const prev = current[idx]
      if (!prev) return zoom
      const keep = {}
      for (const key of ['start', 'end', 'startValue', 'endValue']) {
        if (prev[key] !== undefined && prev[key] !== null) keep[key] = prev[key]
      }
      return { ...zoom, ...keep }
    })
  }
}

onMounted(async () => {
  await nextTick()
  render()
  ro = new ResizeObserver(() => inst && inst.resize())
  ro.observe(el.value)
})

watch(() => props.option, render, { deep: true })

onBeforeUnmount(() => {
  if (ro && el.value) ro.unobserve(el.value)
  if (inst) { inst.dispose(); inst = null }
})
</script>

<style scoped>
.ec-chart { width: 100%; }
</style>
