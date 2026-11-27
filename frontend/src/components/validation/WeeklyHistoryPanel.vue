<template>
  <section class="weekly-history">
    <header><h3>Historical Weekly Markets</h3><span>{{ rows.length }} markets</span></header>
    <div v-if="!rows.length" class="empty">暂无 Polymarket 历史周度市场数据。</div>
    <div v-else class="history-grid">
      <article v-for="m in rows" :key="m.id || m.slug" class="history-card">
        <div class="hc-top"><strong>{{ shortQuestion(m.question) }}</strong><span>{{ date(m.end_date_utc) }}</span></div>
        <div class="hc-meta"><span>Vol {{ money(m.volume_usd) }}</span><span>Liq {{ money(m.liquidity_usd) }}</span></div>
        <div class="mini-outcomes">
          <span v-for="o in (m.outcomes || []).slice(0, 4)" :key="o.index">{{ o.label }} <b>{{ pct(o.yes_price) }}</b></span>
        </div>
      </article>
    </div>
  </section>
</template>

<script setup>
defineProps({ rows: { type: Array, default: () => [] } })

function shortQuestion (q) { return String(q || 'BTC weekly market').replace('What price will Bitcoin hit ', 'BTC ') }
function date (v) {
  const d = new Date(v)
  return Number.isNaN(d.getTime()) ? '—' : d.toISOString().slice(0, 10)
}
function pct (v) { return v == null || isNaN(v) ? '—' : (Number(v) * 100).toFixed(0) + '%' }
function money (v) { return v == null || isNaN(v) ? '—' : '$' + Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 1 }).format(Number(v)) }
</script>

<style scoped>
.weekly-history { background: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 6px; padding: 12px; color: #0F172A; }
header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
header h3 { margin: 0; font-size: 14px; color: #0F172A; }
header span { color: #94A3B8; font-size: 12px; }
.history-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
.history-card { border: 1px solid #EEF1F5; border-radius: 6px; padding: 10px; min-width: 0; background: #FFFFFF; }
.hc-top { display: flex; justify-content: space-between; gap: 10px; color: #0F172A; font-size: 12px; }
.hc-top strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.hc-top span, .hc-meta { color: #94A3B8; font-size: 11px; }
.hc-meta { display: flex; gap: 12px; margin: 7px 0; }
.mini-outcomes { display: flex; flex-wrap: wrap; gap: 5px; }
.mini-outcomes span { padding: 3px 6px; border-radius: 999px; background: #F8FAFC; border: 1px solid #EEF1F5; color: #475569; font-size: 10px; }
.mini-outcomes b { color: #111827; }
.empty { padding: 20px; text-align: center; color: #94A3B8; font-size: 13px; }
@media (max-width: 900px) { .history-grid { grid-template-columns: 1fr; } }
</style>
