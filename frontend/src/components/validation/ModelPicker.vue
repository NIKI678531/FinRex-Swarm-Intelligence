<template>
  <div class="model-picker">
    <label :for="id">Prediction model</label>
    <div class="select-wrap">
      <select :id="id" :value="modelValue" :disabled="loading || !items.length" @change="onChange">
        <option v-for="m in items" :key="m.key" :value="m.key">{{ labelFor(m) }}</option>
      </select>
      <span class="chevron" aria-hidden="true">▾</span>
    </div>
    <p v-if="activeModel" class="desc">{{ descFor(activeModel) }}</p>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

const props = defineProps({
  modelValue: { type: String, default: null },
  items: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false }
})
const emit = defineEmits(['update:modelValue', 'change'])

const id = `model-picker-${Math.random().toString(36).slice(2, 8)}`
let locale = { value: 'zh' }
try { ({ locale } = useI18n()) } catch (e) { /* i18n optional */ }
const isZh = computed(() => String(locale.value || 'zh').toLowerCase().startsWith('zh'))

const activeModel = computed(() => props.items.find(m => m.key === props.modelValue) || props.items[0] || null)

function labelFor (m) { return isZh.value ? (m.label_zh || m.label_en || m.key) : (m.label_en || m.label_zh || m.key) }
function descFor (m) { return isZh.value ? (m.description_zh || m.description_en || '') : (m.description_en || m.description_zh || '') }
function onChange (e) {
  emit('update:modelValue', e.target.value)
  emit('change', e.target.value)
}
</script>

<style scoped>
.model-picker { display: flex; flex-direction: column; gap: 6px; min-width: 220px; }
.model-picker > label { color: #94A3B8; font-size: 11px; text-transform: uppercase; letter-spacing: .04em; }
.select-wrap { position: relative; }
select { width: 100%; appearance: none; border: 1px solid #D1D9E0; border-radius: 6px; background: #FFFFFF; color: #0F172A; font-size: 13px; font-weight: 700; padding: 8px 30px 8px 10px; cursor: pointer; }
select:disabled { opacity: 0.6; cursor: not-allowed; }
select:focus { outline: none; border-color: #111827; }
.chevron { position: absolute; right: 10px; top: 50%; transform: translateY(-50%); color: #64748B; font-size: 11px; pointer-events: none; }
.desc { margin: 0; color: #64748B; font-size: 12px; line-height: 1.5; }
</style>
