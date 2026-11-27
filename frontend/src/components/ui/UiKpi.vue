<template>
  <div class="ui-kpi">
    <div class="ui-kpi__label">{{ label }}</div>
    <div class="ui-kpi__value">{{ display }}</div>
    <div v-if="delta !== null && delta !== undefined" class="ui-kpi__delta" :class="trendClass">
      <span class="ui-kpi__arrow">{{ trend === 'up' ? '↑' : trend === 'down' ? '↓' : '·' }}</span>
      <span>{{ delta }}</span>
    </div>
    <div v-if="hint" class="ui-kpi__hint">{{ hint }}</div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  label: { type: String, required: true },
  value: { type: [String, Number], required: true },
  delta: { type: [String, Number], default: null },
  trend: { type: String, default: 'flat' }, // up | down | flat
  hint:  { type: String, default: '' }
})

const display = computed(() => {
  if (typeof props.value === 'number') {
    if (Math.abs(props.value) >= 10000) return `${(props.value / 1000).toFixed(1)}k`
    return props.value.toLocaleString()
  }
  return props.value
})

const trendClass = computed(() => `is-${props.trend}`)
</script>

<style scoped>
.ui-kpi {
  display: flex; flex-direction: column; gap: 4px;
  padding: var(--s-4) var(--s-5);
  background: var(--c-bg);
  border: 1px solid var(--c-border);
  border-radius: var(--r-lg);
  min-height: 96px;
}
.ui-kpi__label {
  font-size: var(--fs-12);
  color: var(--c-text-muted);
  letter-spacing: .04em;
  text-transform: uppercase;
}
.ui-kpi__value {
  font-family: var(--f-mono);
  font-size: var(--fs-28);
  font-weight: 600;
  color: var(--c-text);
  line-height: 1.1;
}
.ui-kpi__delta {
  display: inline-flex; align-items: center; gap: 4px;
  font-size: var(--fs-13); font-weight: 500;
}
.ui-kpi__delta.is-up    { color: var(--c-bull); }
.ui-kpi__delta.is-down  { color: var(--c-bear); }
.ui-kpi__delta.is-flat  { color: var(--c-text-subtle); }
.ui-kpi__hint { font-size: var(--fs-12); color: var(--c-text-subtle); }
</style>
