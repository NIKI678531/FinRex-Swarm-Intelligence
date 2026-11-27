<template>
  <section class="outcome-board">
    <header>
      <div><h3>BTC Weekly Outcomes</h3><span>{{ market?.question || 'FinRex probability bins' }}</span></div>
      <a v-if="market?.raw_url" :href="market.raw_url" target="_blank" rel="noopener">Polymarket</a>
    </header>
    <div class="outcome-list">
      <div v-for="row in mergedRows" :key="row.key" class="outcome-row" :class="{ top: row.isTop, unmatched: row.polyYes == null && hasMarket }">
        <div class="range">
          <strong>{{ row.label }}</strong>
          <span v-if="row.isTop">highest FinRex probability</span>
          <span v-else-if="row.polyYes == null && hasMarket" class="warn">no Polymarket match</span>
        </div>
        <div class="prob-cell"><span>FinRex</span><strong>{{ pct(row.finrexProb) }}</strong></div>
        <div class="prob-cell"><span>Reach (path)</span><strong>{{ pct(row.hitProb) }}</strong></div>
        <div class="prob-cell"><span>Polymarket Yes</span><strong>{{ pct(row.polyYes) }}</strong></div>
        <div class="prob-cell" :class="tone(row.edge)"><span>Edge</span><strong>{{ signedPct(row.edge) }}</strong></div>
        <div class="prob-cell"><span>Volume</span><strong>{{ money(row.volume) }}</strong></div>
      </div>
    </div>
    <p v-if="!market" class="source-note">Polymarket odds unavailable; displaying FinRex bins only.</p>
  </section>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  bins: { type: Array, default: () => [] },
  market: { type: Object, default: null }
})

const mergedRows = computed(() => {
  const bins = props.bins || []
  const outcomes = props.market?.outcomes || []
  const topProb = Math.max(...bins.map(b => Number(b.prob || 0)), 0)
  return bins.map((bin, idx) => {
    const outcome = matchOutcome(bin, outcomes)
    const finrexProb = Number(bin.prob || 0)
    const polyYes = outcome?.yes_price == null ? null : Number(outcome.yes_price)
    return {
      key: `${idx}-${bin.label || ''}`,
      label: bin.label || formatRange(bin),
      finrexProb,
      hitProb: bin.hit_prob == null ? null : Number(bin.hit_prob),
      polyYes,
      edge: polyYes == null ? null : finrexProb - polyYes,
      volume: outcome?.volume_usd || props.market?.volume_usd || null,
      liquidity: outcome?.liquidity_usd || props.market?.liquidity_usd || null,
      isTop: finrexProb === topProb && topProb > 0
    }
  })
})

const hasMarket = computed(() => Boolean((props.market?.outcomes || []).length))

// Scale-free matching: pick the Polymarket outcome whose price range overlaps
// the local bin the most (intersection-over-union). Avoids the old fixed
// $100 tolerance that never matched at BTC ~ $100k.
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
  const interLow = Math.max(al, bl)
  const interHigh = Math.min(ah, bh)
  const inter = Math.max(0, interHigh - interLow)
  if (inter <= 0) return 0
  const union = Math.max(ah, bh) - Math.min(al, bl)
  if (!isFinite(union) || union <= 0) return inter > 0 ? 1 : 0
  return inter / union
}
function formatRange (b) {
  if (b.low == null) return `< $${num(b.high, 0)}`
  if (b.high == null) return `> $${num(b.low, 0)}`
  return `$${num(b.low, 0)} - $${num(b.high, 0)}`
}
function pct (v) { return v == null || isNaN(v) ? '—' : (Number(v) * 100).toFixed(1) + '%' }
function signedPct (v) { return v == null || isNaN(v) ? '—' : `${v > 0 ? '+' : ''}${(Number(v) * 100).toFixed(1)}pp` }
function money (v) { return v == null || isNaN(v) ? '—' : '$' + Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 1 }).format(Number(v)) }
function num (v, d = 0) { return v == null || isNaN(v) ? '—' : Number(v).toLocaleString('en-US', { maximumFractionDigits: d }) }
function tone (v) { return v == null ? '' : v >= 0 ? 'pos' : 'neg' }
</script>

<style scoped>
.outcome-board { background: #fff; border: 1px solid #E5E7EB; border-radius: 6px; overflow: hidden; color: #0F172A; }
header { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; padding: 12px 14px; border-bottom: 1px solid #EEF1F5; background: #FFFFFF; }
header h3 { margin: 0 0 4px; font-size: 14px; color: #0F172A; }
header span { color: #64748B; font-size: 12px; }
header a { color: #2563EB; font-size: 12px; text-decoration: none; font-weight: 800; }
.outcome-list { display: flex; flex-direction: column; }
.outcome-row { display: grid; grid-template-columns: minmax(150px, 1.45fr) repeat(5, minmax(70px, 1fr)); gap: 10px; padding: 10px 12px; border-bottom: 1px solid #F1F5F9; align-items: center; }
.outcome-row.top { background: #F8FAFC; box-shadow: inset 3px 0 #111827; }
.outcome-row.unmatched { opacity: 0.5; }
.range strong { display: block; color: #0F172A; font-size: 13px; }
.range span, .prob-cell span { display: block; color: #94A3B8; font-size: 10px; text-transform: uppercase; letter-spacing: .04em; }
.range span.warn { color: #D97706; text-transform: none; letter-spacing: 0; }
.prob-cell strong { color: #0F172A; font-size: 13px; font-variant-numeric: tabular-nums; }
.prob-cell.pos strong { color: #16A34A; }
.prob-cell.neg strong { color: #DC2626; }
.source-note { margin: 0; padding: 10px 14px; color: #94A3B8; font-size: 12px; }
@media (max-width: 980px) { .outcome-row { grid-template-columns: 1fr 1fr 1fr; } }
</style>
