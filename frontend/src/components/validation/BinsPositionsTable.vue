<template>
  <div class="bins-positions">
    <div v-if="!rows.length" class="empty">No paper bets yet. Positive edge is required before opening a simulated position.</div>
    <table v-else class="bp-table">
      <thead>
        <tr>
          <th>Cycle</th>
          <th>Status</th>
          <th>Price Bin</th>
          <th class="num">Model P</th>
          <th class="num">Market P</th>
          <th class="num">Edge</th>
          <th class="num">Kelly</th>
          <th class="num">Stake</th>
          <th class="num">EV</th>
          <th class="num">PnL</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="r in rows" :key="r.id" :class="rowClass(r)">
          <td>{{ r.cycle_id || '-' }}</td>
          <td>
            <span v-if="r.is_hit === true" class="tag tag--win">Hit</span>
            <span v-else-if="r.is_hit === false" class="tag tag--lose">Miss</span>
            <span v-else class="tag tag--open">Open</span>
          </td>
          <td class="mono">{{ formatRange(r) }}</td>
          <td class="num">{{ pct(r.model_prob) }}</td>
          <td class="num">{{ pct(r.market_prob ?? r.baseline_prob) }}</td>
          <td class="num" :class="r.edge > 0 ? 'pos' : 'neg'">{{ pct(r.edge, true) }}</td>
          <td class="num">{{ pct(r.kelly_fraction_raw) }}</td>
          <td class="num">{{ money(r.stake) }}</td>
          <td class="num" :class="(r.expected_value ?? 0) >= 0 ? 'pos' : 'neg'">{{ money(r.expected_value) }}</td>
          <td class="num" :class="(r.realized_pnl ?? 0) >= 0 ? 'pos' : 'neg'">{{ r.realized_pnl != null ? money(r.realized_pnl) : '-' }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup>
defineProps({ rows: { type: Array, default: () => [] } })
function formatRange (r) {
  const lo = r.bin_range?.[0], hi = r.bin_range?.[1]
  if (lo == null) return `< $${money(hi)}`
  if (hi == null) return `> $${money(lo)}`
  return `$${money(lo)} - $${money(hi)}`
}
function money (v) { return v == null || isNaN(v) ? '-' : Number(v).toLocaleString('en-US', { maximumFractionDigits: 2 }) }
function pct (v, signed = false) {
  if (v == null || isNaN(v)) return '-'
  const n = (Number(v) * 100).toFixed(2)
  return signed && Number(v) > 0 ? `+${n}%` : `${n}%`
}
function rowClass (r) { return r.is_hit === true ? 'row--win' : r.is_hit === false ? 'row--lose' : '' }
</script>

<style scoped>
.bins-positions { color: #0F172A; overflow: auto; }
.empty { padding: 32px; text-align: center; color: #94A3B8; font-size: 13px; }
.bp-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.bp-table th, .bp-table td { padding: 8px 10px; border-bottom: 1px solid #EEF1F5; text-align: left; white-space: nowrap; }
.bp-table th { color: #64748B; font-weight: 700; background: #F8FAFC; }
.bp-table .num { text-align: right; font-variant-numeric: tabular-nums; }
.bp-table .mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.row--win { background: rgba(34, 197, 94, 0.05); }
.row--lose { background: rgba(239, 68, 68, 0.04); }
.tag { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 11px; font-weight: 700; }
.tag--win { background: #DCFCE7; color: #166534; }
.tag--lose { background: #FEE2E2; color: #991B1B; }
.tag--open { background: #E0E7FF; color: #3730A3; }
.pos { color: #16A34A; }
.neg { color: #DC2626; }
</style>
