<template>
  <div class="decision-summary">
    <div class="cell headline">
      <span class="k">Model</span>
      <strong class="v">{{ modelLabel }}</strong>
      <small v-if="modelMeta?.warning" class="warn">{{ modelMeta.warning }}</small>
      <small v-else class="muted">{{ outputKindLabel }}</small>
    </div>
    <div class="cell">
      <span class="k">Top bin</span>
      <strong class="v">{{ topBin?.label || '—' }}</strong>
      <small class="muted">FinRex {{ pct(topBin?.prob) }}</small>
    </div>
    <div class="cell">
      <span class="k">Best edge vs market</span>
      <strong class="v" :class="tone(bestEdge)">{{ signedPct(bestEdge) }}</strong>
      <small class="muted">{{ bestEdgeBin?.label || 'no qualifying bin' }}</small>
    </div>
    <div class="cell">
      <span class="k">Recommended stake</span>
      <strong class="v">{{ money(totalStake) }}</strong>
      <small class="muted">{{ betCount }} bin(s) · {{ pct(stakePct) }} of book</small>
    </div>
    <div class="cell">
      <span class="k">Expected value</span>
      <strong class="v" :class="tone(totalEv)">{{ money(totalEv) }}</strong>
      <small class="muted">sum of open paper bets</small>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  bins: { type: Array, default: () => [] },
  positions: { type: Array, default: () => [] },
  modelMeta: { type: Object, default: null },
  cash: { type: Number, default: null }
})

const modelLabel = computed(() => props.modelMeta?.label_zh || props.modelMeta?.label || props.modelMeta?.model_family || '—')
const outputKindLabel = computed(() => {
  const k = props.modelMeta?.output_kind
  if (k === 'price_dist') return 'price distribution'
  if (k === 'direction') return 'directional signal'
  return ''
})
const topBin = computed(() => {
  const bins = props.bins || []
  if (!bins.length) return null
  return bins.reduce((a, b) => (Number(b.prob || 0) > Number(a.prob || 0) ? b : a), bins[0])
})
const openBets = computed(() => (props.positions || []).filter(p => Number(p.stake || 0) > 0 && p.is_hit == null))
const betCount = computed(() => openBets.value.length)
const totalStake = computed(() => openBets.value.reduce((s, p) => s + Number(p.stake || 0), 0))
const totalEv = computed(() => openBets.value.reduce((s, p) => s + Number(p.expected_value || 0), 0))
const stakePct = computed(() => (props.cash ? totalStake.value / props.cash : null))
const bestEdgeBin = computed(() => {
  const withMarket = openBets.value.filter(p => p.edge_vs_market != null)
  if (!withMarket.length) return null
  return withMarket.reduce((a, b) => (Number(b.edge_vs_market) > Number(a.edge_vs_market) ? b : a))
})
const bestEdge = computed(() => (bestEdgeBin.value ? Number(bestEdgeBin.value.edge_vs_market) : null))

function pct (v) { return v == null || isNaN(v) ? '—' : (Number(v) * 100).toFixed(1) + '%' }
function signedPct (v) { return v == null || isNaN(v) ? '—' : `${Number(v) >= 0 ? '+' : ''}${(Number(v) * 100).toFixed(1)}pp` }
function money (v) { return v == null || isNaN(v) ? '—' : '$' + Number(v).toLocaleString('en-US', { maximumFractionDigits: 2 }) }
function tone (v) { return v == null ? '' : Number(v) >= 0 ? 'pos' : 'neg' }
</script>

<style scoped>
.decision-summary { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 1px; background: #E5E7EB; border: 1px solid #E5E7EB; border-radius: 8px; overflow: hidden; }
.cell { background: #FFFFFF; padding: 12px 14px; display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.cell.headline { background: #0F172A; }
.cell.headline .k { color: #94A3B8; }
.cell.headline .v { color: #FFFFFF; }
.k { color: #94A3B8; font-size: 11px; text-transform: uppercase; letter-spacing: .04em; }
.v { color: #0F172A; font-size: 17px; font-variant-numeric: tabular-nums; line-height: 1.1; }
small { font-size: 11px; }
.muted { color: #94A3B8; }
.warn { color: #D97706; }
.pos { color: #16A34A; }
.neg { color: #DC2626; }
@media (max-width: 1180px) { .decision-summary { grid-template-columns: repeat(2, 1fr); } }
</style>
