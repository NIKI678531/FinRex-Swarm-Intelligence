<template>
  <div class="model-debug">
    <div class="debug-grid">
      <div class="debug-cell">
        <span>Forecast Head</span>
        <strong>{{ debug.forecast_head || 'weighted_live_score' }}</strong>
      </div>
      <div class="debug-cell">
        <span>Active Model</span>
        <strong>{{ debug.model_kind || strategy.model_kind || 'weighted' }}</strong>
      </div>
      <div class="debug-cell">
        <span>P(up)</span>
        <strong>{{ pct(debug.p_up) }}</strong>
      </div>
      <div class="debug-cell">
        <span>Confidence</span>
        <strong>{{ pct(debug.confidence) }}</strong>
      </div>
      <div class="debug-cell">
        <span>Bias / Day</span>
        <strong>{{ signedPct(payload.bias_per_day) }}</strong>
      </div>
      <div class="debug-cell">
        <span>Sigma Multiplier</span>
        <strong>{{ number(payload.sigma_adjustment?.multiplier, 2) }}</strong>
      </div>
      <div class="debug-cell">
        <span>OASIS Coverage</span>
        <strong>{{ coverageLabel }}</strong>
      </div>
      <div class="debug-cell">
        <span>Ablation</span>
        <strong>{{ debug.ablation_mode || strategy.ablation_mode || 'market_text_oasis' }}</strong>
      </div>
    </div>

    <div class="factor-strip" v-if="topFactors.length">
      <div class="factor-title">Top Feature Contributions</div>
      <div class="factor-row" v-for="f in topFactors" :key="f.key">
        <span>{{ f.key }}</span>
        <strong :class="f.value >= 0 ? 'pos' : 'neg'">{{ number(f.value, 4) }}</strong>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({ forecast: { type: Object, default: null } })

const payload = computed(() => props.forecast?.payload || {})
const debug = computed(() => payload.value.model_debug || {})
const strategy = computed(() => payload.value.strategy_cfg || {})
const coverage = computed(() => debug.value.oasis_coverage || {})
const coverageLabel = computed(() => {
  if (!coverage.value.available) return 'neutral / no stream'
  return `${coverage.value.covered_days || 0} days, ${coverage.value.action_count || 0} actions`
})
const topFactors = computed(() => Object.entries(debug.value.feature_contribution || {})
  .map(([key, value]) => ({ key, value: Number(value) || 0 }))
  .sort((a, b) => Math.abs(b.value) - Math.abs(a.value))
  .slice(0, 8))

function number (v, digits = 2) {
  if (v == null || isNaN(v)) return '—'
  return Number(v).toFixed(digits)
}
function pct (v) {
  if (v == null || isNaN(v)) return '—'
  return `${(Number(v) * 100).toFixed(2)}%`
}
function signedPct (v) {
  if (v == null || isNaN(v)) return '—'
  const n = Number(v) * 100
  return `${n >= 0 ? '+' : ''}${n.toFixed(3)}%`
}
</script>

<style scoped>
.model-debug { display: flex; flex-direction: column; gap: 12px; color: #0F172A; }
.debug-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; }
.debug-cell { padding: 10px 11px; border: 1px solid #E5E7EB; border-radius: 6px; background: #F8FAFC; }
.debug-cell span { display: block; color: #64748B; font-size: 10px; font-weight: 800; letter-spacing: 0.04em; text-transform: uppercase; }
.debug-cell strong { display: block; margin-top: 5px; color: #0F172A; font-size: 12px; overflow-wrap: anywhere; }
.factor-strip { border: 1px solid #E5E7EB; border-radius: 6px; overflow: hidden; }
.factor-title { padding: 8px 10px; background: #F8FAFC; color: #334155; font-size: 12px; font-weight: 800; }
.factor-row { display: flex; justify-content: space-between; gap: 10px; padding: 7px 10px; border-top: 1px solid #EEF1F5; font-size: 12px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.factor-row span { color: #475569; }
.pos { color: #16A34A; }
.neg { color: #DC2626; }
@media (max-width: 900px) { .debug-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 560px) { .debug-grid { grid-template-columns: 1fr; } }
</style>
