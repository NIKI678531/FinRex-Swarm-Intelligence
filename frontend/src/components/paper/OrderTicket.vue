<template>
  <div class="ticket">
    <div class="ticket__head">
      <div class="ticket__sym">
        <strong>{{ symbol }}</strong>
        <span class="ticket__last" :class="lastClass">{{ lastPrice != null ? fmt(lastPrice) : '—' }}</span>
      </div>
      <span v-if="stale" class="ticket__stale">{{ t('quant.paperTrading.staleTag') }}</span>
    </div>

    <!-- Order type tabs -->
    <div class="seg">
      <button
        v-for="ot in orderTypes"
        :key="ot.value"
        :class="['seg__btn', { active: form.order_type === ot.value }]"
        @click="form.order_type = ot.value"
      >{{ ot.label }}</button>
    </div>

    <!-- Quantity -->
    <label class="fld">
      <span class="fld__lbl">{{ t('quant.paperTrading.qty') }}</span>
      <span class="stepper">
        <button @click="bump(-stepQty)" type="button">−</button>
        <input type="number" v-model.number="form.qty" min="0" :step="stepQty" />
        <button @click="bump(stepQty)" type="button">+</button>
      </span>
    </label>

    <!-- Buying power -->
    <div v-if="cash != null" class="buypower">
      <span>{{ t('quant.paperTrading.buyingPower') }} <b>{{ fmt(cash) }}</b></span>
      <button v-if="maxBuyQty" class="maxbtn" type="button" @click="setMax">{{ t('quant.paperTrading.max') }}</button>
    </div>

    <!-- Conditional price inputs -->
    <label v-if="needLimit" class="fld">
      <span class="fld__lbl">{{ t('quant.paperTrading.limitPrice') }}</span>
      <input type="number" v-model.number="form.limit_price" step="0.01" />
    </label>
    <label v-if="needStop" class="fld">
      <span class="fld__lbl">{{ t('quant.paperTrading.stopPrice') }}</span>
      <input type="number" v-model.number="form.stop_price" step="0.01" />
    </label>
    <div v-if="form.order_type === 'trailing_stop'" class="fld-row">
      <label class="fld">
        <span class="fld__lbl">{{ t('quant.paperTrading.trailAmt') }}</span>
        <input type="number" v-model.number="form.trail_amount" step="0.01" placeholder="—" />
      </label>
      <label class="fld">
        <span class="fld__lbl">{{ t('quant.paperTrading.trailPct') }}</span>
        <input type="number" v-model.number="form.trail_percent" step="0.1" placeholder="—" />
      </label>
    </div>

    <!-- Bracket TP / SL (for market/limit entries) -->
    <div v-if="bracketAllowed" class="bracket">
      <label class="chk">
        <input type="checkbox" v-model="form.useTp" />
        <span>{{ t('quant.paperTrading.takeProfit') }}</span>
      </label>
      <div v-if="form.useTp" class="bracket__row">
        <input type="number" v-model.number="form.take_profit" step="0.01" />
        <span class="pnl" :class="tpPnl >= 0 ? 'pos' : 'neg'">{{ pnlText(tpPnl) }}</span>
      </div>

      <label class="chk">
        <input type="checkbox" v-model="form.useSl" />
        <span>{{ t('quant.paperTrading.stopLoss') }}</span>
      </label>
      <div v-if="form.useSl" class="bracket__row">
        <input type="number" v-model.number="form.stop_loss" step="0.01" />
        <span class="pnl" :class="slPnl >= 0 ? 'pos' : 'neg'">{{ pnlText(slPnl) }}</span>
      </div>
      <p v-if="form.useTp && form.useSl" class="oco-hint">{{ t('quant.paperTrading.ocoHint') }}</p>
    </div>

    <label class="chk reduce" v-if="positionQty">
      <input type="checkbox" v-model="form.reduce_only" />
      <span>{{ t('quant.paperTrading.reduceOnly') }}</span>
    </label>

    <!-- Est. notional -->
    <div class="notional">
      <span>{{ t('quant.paperTrading.estNotional') }}</span>
      <b>{{ estNotional != null ? fmt(estNotional) : '—' }}</b>
    </div>
    <p v-if="exceedsCash" class="cash-warn">{{ t('quant.paperTrading.insufficientCashHint') }}</p>

    <!-- Buy / Sell -->
    <div class="actions">
      <button class="act buy" :disabled="busy || !canSubmit || exceedsCash" @click="submit('buy')">
        {{ t('quant.paperTrading.buy') }}
      </button>
      <button class="act sell" :disabled="busy || !canSubmit" @click="submit('sell')">
        {{ t('quant.paperTrading.sell') }}
      </button>
    </div>
  </div>
</template>

<script setup>
import { reactive, computed } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const props = defineProps({
  symbol: { type: String, default: '' },
  lastPrice: { type: Number, default: null },
  stale: { type: Boolean, default: false },
  positionQty: { type: Number, default: 0 },
  cash: { type: Number, default: null },
  busy: { type: Boolean, default: false }
})
const emit = defineEmits(['submit'])

const orderTypes = computed(() => [
  { value: 'market', label: t('quant.paperTrading.typeMarket') },
  { value: 'limit', label: t('quant.paperTrading.typeLimit') },
  { value: 'stop', label: t('quant.paperTrading.typeStop') },
  { value: 'stop_limit', label: t('quant.paperTrading.typeStopLimit') },
  { value: 'trailing_stop', label: t('quant.paperTrading.typeTrailing') }
])

const form = reactive({
  order_type: 'market',
  qty: 0.01,
  limit_price: null,
  stop_price: null,
  trail_amount: null,
  trail_percent: null,
  useTp: false,
  useSl: false,
  take_profit: null,
  stop_loss: null,
  reduce_only: false
})

const needLimit = computed(() => ['limit', 'stop_limit'].includes(form.order_type))
const needStop = computed(() => ['stop', 'stop_limit'].includes(form.order_type))
const bracketAllowed = computed(() => ['market', 'limit'].includes(form.order_type))
const stepQty = computed(() => (props.lastPrice && props.lastPrice > 1000 ? 0.001 : (props.lastPrice && props.lastPrice > 50 ? 0.1 : 1)))

const refPrice = computed(() => {
  if (needLimit.value && form.limit_price) return form.limit_price
  if (needStop.value && form.stop_price) return form.stop_price
  return props.lastPrice
})
const estNotional = computed(() => (refPrice.value && form.qty ? refPrice.value * form.qty : null))

// Leave a small headroom so a market order is not rejected by minor price drift
// between the displayed quote and the fill price.
const BUY_BUFFER = 0.005
const maxBuyQty = computed(() => {
  if (!refPrice.value || props.cash == null || props.cash <= 0) return null
  const raw = props.cash / (refPrice.value * (1 + BUY_BUFFER))
  const aligned = Math.floor(raw / stepQty.value) * stepQty.value
  return aligned > 0 ? Number(aligned.toFixed(6)) : null
})
const exceedsCash = computed(() =>
  props.cash != null && estNotional.value != null && estNotional.value > props.cash
)

function setMax () {
  if (maxBuyQty.value && maxBuyQty.value > 0) form.qty = maxBuyQty.value
}

const tpPnl = computed(() => (form.take_profit && refPrice.value ? (form.take_profit - refPrice.value) * form.qty : 0))
const slPnl = computed(() => (form.stop_loss && refPrice.value ? (form.stop_loss - refPrice.value) * form.qty : 0))

const lastClass = computed(() => '')

const canSubmit = computed(() => {
  if (!form.qty || form.qty <= 0) return false
  if (needLimit.value && !form.limit_price) return false
  if (needStop.value && !form.stop_price) return false
  if (form.order_type === 'trailing_stop' && !form.trail_amount && !form.trail_percent) return false
  return true
})

function bump (d) {
  const next = Number(((form.qty || 0) + d).toFixed(6))
  form.qty = next > 0 ? next : 0
}

function fmt (v) {
  if (v == null || isNaN(v)) return '—'
  return Number(v).toLocaleString(undefined, { maximumFractionDigits: 4 })
}
function pnlText (v) {
  const s = v >= 0 ? '+' : ''
  return `${s}${Number(v).toLocaleString(undefined, { maximumFractionDigits: 2 })}`
}

function submit (side) {
  const payload = {
    side,
    order_type: form.order_type,
    qty: form.qty,
    reduce_only: form.reduce_only
  }
  if (needLimit.value) payload.limit_price = form.limit_price
  if (needStop.value) payload.stop_price = form.stop_price
  if (form.order_type === 'trailing_stop') {
    if (form.trail_amount) payload.trail_amount = form.trail_amount
    if (form.trail_percent) payload.trail_percent = form.trail_percent
  }
  if (bracketAllowed.value) {
    if (form.useTp && form.take_profit) payload.take_profit = form.take_profit
    if (form.useSl && form.stop_loss) payload.stop_loss = form.stop_loss
  }
  emit('submit', payload)
}
</script>

<style scoped>
.ticket {
  display: flex; flex-direction: column; gap: var(--s-3);
}
.ticket__head { display: flex; align-items: center; justify-content: space-between; }
.ticket__sym { display: flex; align-items: baseline; gap: 8px; }
.ticket__sym strong { font-size: 15px; }
.ticket__last { font-family: var(--f-mono); font-size: 14px; }
.ticket__stale {
  font-size: 10px; font-family: var(--f-mono); letter-spacing: .1em;
  background: rgba(234,179,8,.16); color: #b58100; padding: 2px 6px; border-radius: 4px;
}
.seg { display: grid; grid-template-columns: repeat(5, 1fr); gap: 4px; }
.seg__btn {
  padding: 6px 4px; font-size: 11px; border: 1px solid var(--c-border);
  background: var(--c-bg); cursor: pointer; border-radius: 4px;
  font-family: var(--f-mono); letter-spacing: .04em;
}
.seg__btn.active { background: var(--c-text); color: var(--c-bg); border-color: var(--c-text); }
.fld { display: flex; flex-direction: column; gap: 4px; }
.fld-row { display: grid; grid-template-columns: 1fr 1fr; gap: var(--s-2); }
.fld__lbl {
  font-family: var(--f-mono); font-size: 10px; letter-spacing: .12em;
  text-transform: uppercase; color: var(--c-text-subtle);
}
.fld input, .bracket__row input {
  padding: 7px 10px; border: 1px solid var(--c-border); border-radius: 4px;
  background: var(--c-bg); font-size: 13px; width: 100%; font-family: var(--f-mono);
}
.stepper { display: grid; grid-template-columns: 34px 1fr 34px; gap: 4px; }
.stepper button {
  border: 1px solid var(--c-border); background: var(--c-bg); cursor: pointer;
  font-size: 16px; border-radius: 4px; line-height: 1;
}
.stepper input { text-align: center; }
.bracket { display: flex; flex-direction: column; gap: 6px; padding: var(--s-2) 0; border-top: 1px dashed var(--c-border); }
.bracket__row { display: grid; grid-template-columns: 1fr auto; gap: 8px; align-items: center; }
.chk { display: flex; align-items: center; gap: 6px; font-size: 12px; cursor: pointer; }
.chk input { width: 15px; height: 15px; }
.reduce { margin-top: -4px; }
.pnl { font-family: var(--f-mono); font-size: 12px; min-width: 70px; text-align: right; }
.pos { color: #16a34a; }
.neg { color: #dc2626; }
.oco-hint { font-size: 11px; color: var(--c-text-subtle); margin: 2px 0 0; }
.notional { display: flex; justify-content: space-between; font-size: 12px; color: var(--c-text-muted); }
.notional b { font-family: var(--f-mono); color: var(--c-text); }
.buypower { display: flex; align-items: center; justify-content: space-between; font-size: 12px; color: var(--c-text-muted); margin-top: -2px; }
.buypower b { font-family: var(--f-mono); color: var(--c-text); }
.maxbtn { padding: 2px 8px; font-size: 11px; border: 1px solid var(--c-border); border-radius: 4px; background: var(--c-bg-soft); color: var(--c-text); cursor: pointer; }
.maxbtn:hover { border-color: var(--c-accent, #2563eb); color: var(--c-accent, #2563eb); }
.cash-warn { font-size: 11px; color: #dc2626; margin: 2px 0 0; }
.actions { display: grid; grid-template-columns: 1fr 1fr; gap: var(--s-3); margin-top: var(--s-2); }
.act {
  padding: 12px; border: none; border-radius: 6px; font-weight: 700;
  font-size: 14px; letter-spacing: .06em; cursor: pointer; color: #fff;
}
.act.buy { background: #16a34a; }
.act.sell { background: #dc2626; }
.act:disabled { opacity: .45; cursor: not-allowed; }
</style>
