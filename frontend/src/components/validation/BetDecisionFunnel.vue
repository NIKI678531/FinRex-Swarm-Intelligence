<template>
  <div class="funnel">
    <div v-if="!active.length" class="empty">No positive-edge paper bets in this cycle.</div>
    <div v-for="p in active" :key="p.id" class="row">
      <strong>{{ p.bin_label || `Bin ${p.bin_index}` }}</strong>
      <div class="steps">
        <span>Model {{ pct(p.model_prob) }}</span>
        <span>Market {{ pct(p.market_prob ?? p.baseline_prob) }}</span>
        <span :class="tone(p.edge)">Edge {{ signedPct(p.edge) }}</span>
        <span>Kelly {{ pct(p.kelly_fraction_raw) }}</span>
        <span>Final {{ money(p.stake) }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
const props = defineProps({ positions: { type: Array, default: () => [] } })
const active = computed(() => (props.positions || []).filter(p => Number(p.stake || 0) > 0).slice(0, 8))
function pct (v) { return v == null || isNaN(v) ? '-' : (Number(v) * 100).toFixed(2) + '%' }
function signedPct (v) { return v == null || isNaN(v) ? '-' : `${Number(v) >= 0 ? '+' : ''}${(Number(v) * 100).toFixed(2)}pp` }
function money (v) { return v == null || isNaN(v) ? '-' : '$' + Number(v).toLocaleString('en-US', { maximumFractionDigits: 2 }) }
function tone (v) { return Number(v || 0) >= 0 ? 'pos' : 'neg' }
</script>

<style scoped>
.funnel { display: flex; flex-direction: column; gap: 8px; color: #0F172A; }
.row { padding: 10px; border: 1px solid #EEF1F5; border-radius: 6px; background: #F8FAFC; }
.row strong { display: block; margin-bottom: 7px; font-size: 13px; }
.steps { display: flex; gap: 6px; flex-wrap: wrap; }
.steps span { padding: 5px 7px; border-radius: 5px; background: #FFFFFF; border: 1px solid #E5E7EB; font-size: 12px; }
.pos { color: #16A34A; }
.neg { color: #DC2626; }
.empty { padding: 24px; text-align: center; color: #94A3B8; font-size: 13px; }
</style>
