<template>
  <section class="ticker-strip">
    <div class="ticker-main">
      <span class="pair">BTC/USDT</span>
      <strong :class="changeClass">{{ money(ticker?.last, 2) }}</strong>
      <span :class="changeClass">{{ pct(ticker?.change_pct_24h, true) }}</span>
    </div>
    <div class="ticker-cell"><span>24h High</span><strong>{{ money(ticker?.high_24h, 2) }}</strong></div>
    <div class="ticker-cell"><span>24h Low</span><strong>{{ money(ticker?.low_24h, 2) }}</strong></div>
    <div class="ticker-cell"><span>24h Volume</span><strong>{{ number(ticker?.volume_24h, 2) }} BTC</strong></div>
    <div class="ticker-cell"><span>Quote Volume</span><strong>{{ compact(ticker?.quote_volume_24h) }}</strong></div>
    <div class="ticker-cell"><span>Updated</span><strong>{{ timeLabel }}</strong></div>
  </section>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({ ticker: { type: Object, default: null } })

const changeClass = computed(() => (props.ticker?.change_pct_24h || 0) >= 0 ? 'pos' : 'neg')
const timeLabel = computed(() => {
  if (!props.ticker?.ts) return '—'
  const d = new Date(props.ticker.ts)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })
})

function money (v, digits = 0) {
  if (v == null || isNaN(v)) return '—'
  return '$' + Number(v).toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits })
}
function number (v, digits = 0) {
  if (v == null || isNaN(v)) return '—'
  return Number(v).toLocaleString('en-US', { maximumFractionDigits: digits })
}
function compact (v) {
  if (v == null || isNaN(v)) return '—'
  return '$' + Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 2 }).format(Number(v))
}
function pct (v, signed = false) {
  if (v == null || isNaN(v)) return '—'
  const n = Number(v) * 100
  return `${signed && n > 0 ? '+' : ''}${n.toFixed(2)}%`
}
</script>

<style scoped>
.ticker-strip { display: grid; grid-template-columns: 1.4fr repeat(5, minmax(0, 1fr)); gap: 1px; border: 1px solid #E5E7EB; background: #E5E7EB; color: #0F172A; }
.ticker-main, .ticker-cell { min-width: 0; padding: 10px 12px; background: #FFFFFF; }
.ticker-main { display: flex; align-items: baseline; gap: 10px; }
.pair { color: #111827; font-size: 13px; font-weight: 800; }
.ticker-main strong { font-size: 21px; font-variant-numeric: tabular-nums; }
.ticker-cell span { display: block; color: #94A3B8; font-size: 11px; margin-bottom: 4px; }
.ticker-cell strong { display: block; color: #0F172A; font-size: 12px; font-variant-numeric: tabular-nums; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pos { color: #0ECB81 !important; }
.neg { color: #F6465D !important; }
@media (max-width: 1000px) { .ticker-strip { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
</style>
