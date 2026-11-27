<template>
  <div class="data-source-badge" :class="statusClass" :title="title">
    <span class="dot" />
    <span class="label">{{ label }}</span>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  // 'live' | 'stale' | 'down' | 'unknown'
  status: { type: String, default: 'unknown' },
  label: { type: String, default: 'Source' },
  detail: { type: String, default: '' }
})

const statusClass = computed(() => `is-${props.status || 'unknown'}`)
const title = computed(() => props.detail || props.status)
</script>

<style scoped>
.data-source-badge { display: inline-flex; align-items: center; gap: 6px; padding: 3px 8px; border-radius: 999px; border: 1px solid #E5E7EB; background: #FFFFFF; font-size: 11px; font-weight: 700; color: #475569; }
.dot { width: 7px; height: 7px; border-radius: 50%; background: #94A3B8; }
.is-live .dot { background: #16A34A; }
.is-live { color: #166534; border-color: #BBF7D0; background: #F0FDF4; }
.is-stale .dot { background: #F59E0B; }
.is-stale { color: #92400E; border-color: #FDE68A; background: #FFFBEB; }
.is-down .dot { background: #DC2626; }
.is-down { color: #991B1B; border-color: #FECACA; background: #FEF2F2; }
</style>
