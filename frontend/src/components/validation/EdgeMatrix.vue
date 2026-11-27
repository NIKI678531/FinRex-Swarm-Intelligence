<template>
  <div class="edge-matrix">
    <table>
      <thead><tr><th>Bin</th><th class="num">FinRex P</th><th class="num">Reach</th><th class="num">Market P</th><th class="num">Edge</th><th class="num">Stake</th><th class="num">EV</th></tr></thead>
      <tbody>
        <tr v-for="r in rows" :key="r.key" :class="{ unmatched: r.marketUnmatched }">
          <td>{{ r.label }}</td>
          <td class="num">{{ pct(r.modelProb) }}</td>
          <td class="num">{{ pct(r.hitProb) }}</td>
          <td class="num">{{ pct(r.marketProb) }}</td>
          <td class="num" :class="tone(r.edge)">{{ signedPct(r.edge) }}</td>
          <td class="num">{{ money(r.stake) }}</td>
          <td class="num" :class="tone(r.expectedValue)">{{ money(r.expectedValue) }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup>
import { computed } from 'vue'
const props = defineProps({
  bins: { type: Array, default: () => [] },
  positions: { type: Array, default: () => [] },
  market: { type: Object, default: null },
  baselineProb: { type: Number, default: null }
})
const rows = computed(() => (props.bins || []).map((b, idx) => {
  const pos = (props.positions || []).find(p => Number(p.bin_index) === Number(b.index ?? idx))
  const marketOutcome = matchOutcome(b, props.market?.outcomes || [])
  const hasMarket = Boolean((props.market?.outcomes || []).length)
  const marketYes = marketOutcome?.yes_price ?? pos?.market_prob ?? null
  const marketProb = marketYes ?? props.baselineProb
  const modelProb = Number(b.prob || pos?.model_prob || 0)
  return {
    key: idx,
    label: b.label || pos?.bin_label || marketOutcome?.label || `Bin ${idx + 1}`,
    modelProb,
    hitProb: b.hit_prob == null ? null : Number(b.hit_prob),
    marketProb,
    marketUnmatched: hasMarket && marketYes == null,
    edge: modelProb - Number(marketProb || 0),
    stake: pos?.stake,
    expectedValue: pos?.expected_value
  }
}))
// Scale-free interval-overlap matching (replaces fixed $100 tolerance).
function matchOutcome (bin, outcomes) {
  if (!outcomes.length) return null
  let best = null
  let bestIoU = 0
  for (const o of outcomes) {
    const iou = intervalIoU(o.low, o.high, bin.low, bin.high)
    if (iou > bestIoU) { bestIoU = iou; best = o }
  }
  return bestIoU >= 0.4 ? best : null
}
function intervalIoU (aLow, aHigh, bLow, bHigh) {
  const BIG = 1e12
  const al = aLow == null ? -BIG : Number(aLow)
  const ah = aHigh == null ? BIG : Number(aHigh)
  const bl = bLow == null ? -BIG : Number(bLow)
  const bh = bHigh == null ? BIG : Number(bHigh)
  const inter = Math.max(0, Math.min(ah, bh) - Math.max(al, bl))
  if (inter <= 0) return 0
  const union = Math.max(ah, bh) - Math.min(al, bl)
  if (!isFinite(union) || union <= 0) return 1
  return inter / union
}
function pct (v) { return v == null || isNaN(v) ? '-' : (Number(v) * 100).toFixed(1) + '%' }
function signedPct (v) { return v == null || isNaN(v) ? '-' : `${Number(v) >= 0 ? '+' : ''}${(Number(v) * 100).toFixed(1)}pp` }
function money (v) { return v == null || isNaN(v) ? '-' : '$' + Number(v).toLocaleString('en-US', { maximumFractionDigits: 2 }) }
function tone (v) { return Number(v || 0) >= 0 ? 'pos' : 'neg' }
</script>

<style scoped>
.edge-matrix { overflow: auto; color: #0F172A; }
table { width: 100%; border-collapse: collapse; font-size: 12px; }
th, td { padding: 8px 10px; border-bottom: 1px solid #EEF1F5; text-align: left; white-space: nowrap; }
th { color: #64748B; background: #F8FAFC; }
.num { text-align: right; font-variant-numeric: tabular-nums; }
.unmatched { opacity: 0.45; }
.pos { color: #16A34A; }
.neg { color: #DC2626; }
</style>
