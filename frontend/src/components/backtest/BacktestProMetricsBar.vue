<template>
  <div class="pro-bar" v-if="hasData">
    <div class="pro-bar__title">Professional Risk &amp; Return Metrics</div>
    <div class="pro-bar__grid">
      <div class="cell" v-for="m in items" :key="m.key" :class="`tone-${m.tone}`">
        <div class="cell__label">{{ m.label }}</div>
        <div class="cell__value">{{ m.value }}</div>
        <div class="cell__hint" v-if="m.hint">{{ m.hint }}</div>
      </div>
    </div>
  </div>
  <div v-else class="empty">No professional metrics available — run a backtest first.</div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  perf: { type: Object, default: () => ({}) }
})

const hasData = computed(() => props.perf && Object.keys(props.perf).some(k => k.startsWith('pro_')))

function fmtPct (v, digits = 2) {
  if (v == null || isNaN(v)) return '-'
  return (Number(v) * 100).toFixed(digits) + '%'
}
function fmtNum (v, digits = 3) {
  if (v == null || isNaN(v) || !isFinite(v)) return '-'
  return Number(v).toFixed(digits)
}
function fmtInt (v) {
  if (v == null || isNaN(v)) return '-'
  return Math.round(Number(v))
}
function toneFor (key, val) {
  if (val == null) return 'neutral'
  if (key === 'pro_sortino' || key === 'pro_calmar' || key === 'pro_omega' || key === 'pro_prob_sharpe') {
    return val >= 1 ? 'good' : val >= 0 ? 'neutral' : 'bad'
  }
  if (key === 'pro_max_dd' || key === 'pro_var_95' || key === 'pro_cvar_95') {
    return val <= -0.2 ? 'bad' : val <= -0.05 ? 'warn' : 'neutral'
  }
  if (key === 'pro_kelly') return val > 0 ? 'good' : 'bad'
  return 'neutral'
}

const items = computed(() => {
  const p = props.perf || {}
  const defs = [
    { key: 'pro_sortino',          label: 'Sortino',       fmt: 'num',  digits: 2 },
    { key: 'pro_calmar',           label: 'Calmar',        fmt: 'num',  digits: 2 },
    { key: 'pro_omega',            label: 'Omega',         fmt: 'num',  digits: 2 },
    { key: 'pro_tail_ratio',       label: 'Tail Ratio',    fmt: 'num',  digits: 2 },
    { key: 'pro_prob_sharpe',      label: 'Prob. Sharpe',  fmt: 'pct',  digits: 1, hint: 'P(SR>0)' },
    { key: 'pro_max_dd_duration',  label: 'MaxDD Days',    fmt: 'int' },
    { key: 'pro_ulcer_index',      label: 'Ulcer Idx',     fmt: 'num',  digits: 3 },
    { key: 'pro_payoff_ratio',     label: 'Payoff',        fmt: 'num',  digits: 2 },
    { key: 'pro_profit_factor',    label: 'Profit Factor', fmt: 'num',  digits: 2 },
    { key: 'pro_kelly',            label: 'Kelly',         fmt: 'pct',  digits: 1 },
    { key: 'pro_var_95',           label: 'VaR 95',        fmt: 'pct',  digits: 2 },
    { key: 'pro_cvar_95',          label: 'CVaR 95',       fmt: 'pct',  digits: 2 },
    { key: 'pro_skew',             label: 'Skew',          fmt: 'num',  digits: 2 },
    { key: 'pro_kurtosis',         label: 'Kurtosis',      fmt: 'num',  digits: 2 }
  ]
  return defs.map(d => {
    const raw = p[d.key]
    let value = '-'
    if (d.fmt === 'pct') value = fmtPct(raw, d.digits)
    else if (d.fmt === 'int') value = fmtInt(raw)
    else value = fmtNum(raw, d.digits)
    return { ...d, value, tone: toneFor(d.key, raw) }
  })
})
</script>

<style scoped>
.pro-bar {
  margin-top: var(--s-4);
  border: 1px solid var(--c-border);
  border-radius: var(--r-md);
  background: var(--c-bg-soft);
  padding: var(--s-4);
}
.pro-bar__title {
  font-family: var(--f-mono);
  font-size: 11px;
  letter-spacing: .14em;
  text-transform: uppercase;
  color: var(--c-text-muted);
  margin-bottom: var(--s-3);
}
.pro-bar__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: var(--s-3);
}
.cell {
  border: 1px solid var(--c-border);
  border-radius: var(--r-sm);
  padding: 10px 12px;
  background: var(--c-bg);
}
.cell__label {
  font-family: var(--f-mono);
  font-size: 10px;
  letter-spacing: .12em;
  text-transform: uppercase;
  color: var(--c-text-subtle);
}
.cell__value {
  font-family: var(--f-mono);
  font-size: 16px;
  font-weight: 700;
  margin-top: 4px;
  color: var(--c-text);
}
.cell__hint { font-size: 10px; color: var(--c-text-subtle); margin-top: 2px; }
.tone-good .cell__value { color: #2ecc71; }
.tone-bad .cell__value { color: #e54; }
.tone-warn .cell__value { color: #e8a93b; }
.empty { padding: var(--s-5); text-align: center; color: var(--c-text-subtle); font-size: 13px; }
</style>
