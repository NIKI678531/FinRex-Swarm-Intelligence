<template>
  <div class="quant-page">
    <header class="quant-page__bar">
      <button class="back" @click="$router.push('/')">← {{ t('common.back') }}</button>
      <h1>{{ t('quant.paperTrading.title') }}</h1>
      <span class="status">{{ t('quant.paperTrading.status') }}</span>
      <div class="account-info" v-if="account">
        <span class="kicker">ACCOUNT</span>
        <strong>{{ account.name }}</strong>
        <span class="muted">
          {{ t('quant.paperTrading.equity') }} {{ formatMoney(account.total_equity) }} ·
          {{ t('quant.paperTrading.cash') }} {{ formatMoney(account.cash) }} ·
          {{ t('quant.paperTrading.return') }}
          <b :class="account.cumulative_return >= 0 ? 'positive' : 'negative'">{{ formatPct(account.cumulative_return) }}</b>
        </span>
        <button class="ghost" @click="switchAccount">{{ t('quant.paperTrading.switchAccount') }}</button>
      </div>
    </header>

    <!-- Account creation / selection -->
    <section class="control-row" v-if="!account">
      <div class="control">
        <label>{{ t('quant.paperTrading.accountName') }}</label>
        <input v-model="newAccount.name" placeholder="My Paper Account" />
      </div>
      <div class="control">
        <label>{{ t('quant.paperTrading.initialCash') }}</label>
        <input type="number" v-model.number="newAccount.initial_cash" />
      </div>
      <div class="control">
        <label>{{ t('quant.paperTrading.currency') }}</label>
        <select v-model="newAccount.ccy">
          <option>USD</option><option>USDT</option><option>HKD</option><option>CNY</option>
        </select>
      </div>
      <button class="primary" @click="createAccount" :disabled="loading">
        {{ t('quant.paperTrading.openAccountCTA') }}
      </button>
      <div class="account-list" v-if="accounts.length">
        <span class="muted">{{ t('quant.paperTrading.existing') }}:</span>
        <span v-for="a in accounts" :key="a.account_id" class="account-chip">
          <button class="ghost" @click="loadAccount(a.account_id)">
            {{ a.name }} · {{ a.account_id.slice(0, 12) }}
          </button>
          <button class="chip-x" :title="t('quant.paperTrading.deleteAccount')"
                  @click.stop="deleteAccount(a)">×</button>
        </span>
      </div>
    </section>

    <section v-if="error" class="error-banner">{{ error }}</section>

    <!-- Trading workspace -->
    <section v-if="account" class="ws">
      <!-- Left: watchlist -->
      <aside class="ws__watchlist">
        <input class="wl-search" v-model="symbolSearch" :placeholder="t('quant.paperTrading.searchSymbol')" />
        <div class="wl-filter">
          <button v-for="c in classFilters" :key="c"
                  :class="['wl-chip', { active: classFilter === c }]"
                  @click="classFilter = c">
            {{ c === 'all' ? t('quant.paperTrading.classFilterAll') : t('quant.paperTrading.class.' + c) }}
          </button>
        </div>
        <div v-for="grp in groupedSymbols" :key="grp.key" class="wl-group">
          <div class="wl-group__title">{{ t('quant.paperTrading.class.' + grp.key) }}</div>
          <ul>
            <li v-for="s in grp.items" :key="s.symbol"
                :class="{ active: selectedSymbol === s.symbol }"
                @click="selectSymbol(s.symbol)">
              <div class="wl-item__name">
                <strong>{{ s.symbol }}</strong>
                <small>{{ s.display }}</small>
              </div>
              <span class="px" :class="quoteStale[s.symbol] ? 'stale' : ''">
                {{ quotes[s.symbol] != null ? formatNum(quotes[s.symbol]) : '—' }}
              </span>
            </li>
          </ul>
        </div>
      </aside>

      <!-- Center: chart + tabs -->
      <div class="ws__main">
        <div class="chart-card">
          <div class="chart-toolbar">
            <div class="chart-title">
              <strong>{{ selectedSymbol }}</strong>
              <span class="muted">{{ selectedMeta?.display }}</span>
              <span v-if="lastQuote != null" class="chart-last">{{ formatNum(lastQuote) }}</span>
              <span v-if="quoteStale[selectedSymbol]" class="stale-tag">{{ t('quant.paperTrading.staleTag') }}</span>
            </div>
            <div class="chart-segs">
              <div class="tf-seg">
                <button v-for="r in ranges" :key="r.value"
                        :class="['tf-btn', { active: rangeKey === r.value }]"
                        @click="setRange(r.value)">{{ r.label }}</button>
              </div>
              <div class="tf-seg">
                <button v-for="tf in timeframes" :key="tf.value"
                        :class="['tf-btn', { active: timeframe === tf.value }]"
                        @click="setTimeframe(tf.value)">{{ tf.label }}</button>
              </div>
            </div>
          </div>
          <div class="chart-host">
            <TradingChart
              :candles="candles"
              :markers="chartMarkers"
              :price-lines="chartPriceLines"
              :empty-text="chartLoading ? t('common.loading') : t('quant.paperTrading.noData')"
            />
          </div>
        </div>

        <div class="tabs-card">
          <nav class="tabs">
            <button v-for="tb in tabs" :key="tb.value"
                    :class="['tab', { active: activeTab === tb.value }]"
                    @click="activeTab = tb.value">
              {{ tb.label }}<span v-if="tb.count" class="badge">{{ tb.count }}</span>
            </button>
          </nav>

          <!-- Positions -->
          <div v-show="activeTab === 'positions'" class="tab-body">
            <table class="data-table">
              <thead>
                <tr>
                  <th>{{ t('quant.paperTrading.symbol') }}</th><th>{{ t('quant.paperTrading.qty') }}</th>
                  <th>{{ t('quant.paperTrading.avg') }}</th><th>{{ t('quant.paperTrading.last') }}</th>
                  <th>{{ t('quant.paperTrading.marketValue') }}</th><th>{{ t('quant.paperTrading.pnl') }}</th><th></th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="p in account.positions" :key="p.symbol" @click="selectSymbol(p.symbol)" class="rowlink">
                  <td>{{ p.symbol }}</td>
                  <td>{{ formatNum(p.qty) }}</td>
                  <td>{{ formatNum(p.avg_price) }}</td>
                  <td>{{ formatNum(p.last_price) }}</td>
                  <td>{{ formatMoney(p.market_value) }}</td>
                  <td :class="p.unrealized_pnl >= 0 ? 'positive' : 'negative'">{{ formatMoney(p.unrealized_pnl) }}</td>
                  <td><button class="mini" @click.stop="quickClose(p)">{{ t('quant.paperTrading.close') }}</button></td>
                </tr>
                <tr v-if="!account.positions?.length"><td colspan="7" class="muted center">{{ t('quant.paperTrading.noPositions') }}</td></tr>
              </tbody>
            </table>
          </div>

          <!-- Pending -->
          <div v-show="activeTab === 'pending'" class="tab-body">
            <table class="data-table">
              <thead>
                <tr>
                  <th>{{ t('quant.paperTrading.time') }}</th><th>{{ t('quant.paperTrading.symbol') }}</th>
                  <th>{{ t('quant.paperTrading.side') }}</th><th>{{ t('quant.paperTrading.type') }}</th>
                  <th>{{ t('quant.paperTrading.qty') }}</th><th>{{ t('quant.paperTrading.price') }}</th><th></th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="o in pendingOrders" :key="o.order_id">
                  <td>{{ shortTs(o.ts) }}</td>
                  <td>{{ o.symbol }}</td>
                  <td :class="o.side === 'buy' ? 'positive' : 'negative'">{{ o.side }}</td>
                  <td>{{ orderTypeLabel(o.order_type) }}</td>
                  <td>{{ formatNum(o.qty) }}</td>
                  <td>{{ formatNum(o.stop_price || o.limit_price || o.price) }}</td>
                  <td><button class="mini danger" @click="cancelOrder(o)">{{ t('quant.paperTrading.cancel') }}</button></td>
                </tr>
                <tr v-if="!pendingOrders.length"><td colspan="7" class="muted center">{{ t('quant.paperTrading.noPending') }}</td></tr>
              </tbody>
            </table>
          </div>

          <!-- History -->
          <div v-show="activeTab === 'history'" class="tab-body">
            <table class="data-table">
              <thead>
                <tr>
                  <th>{{ t('quant.paperTrading.time') }}</th><th>{{ t('quant.paperTrading.symbol') }}</th>
                  <th>{{ t('quant.paperTrading.side') }}</th><th>{{ t('quant.paperTrading.type') }}</th>
                  <th>{{ t('quant.paperTrading.qty') }}</th><th>{{ t('quant.paperTrading.price') }}</th><th>{{ t('quant.paperTrading.statusCol') }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="o in historyOrders" :key="o.order_id">
                  <td>{{ shortTs(o.ts) }}</td>
                  <td>{{ o.symbol }}</td>
                  <td :class="o.side === 'buy' ? 'positive' : 'negative'">{{ o.side }}</td>
                  <td>{{ orderTypeLabel(o.order_type) }}</td>
                  <td>{{ formatNum(o.qty) }}</td>
                  <td>{{ formatNum(o.price) }}</td>
                  <td>{{ o.status }}</td>
                </tr>
                <tr v-if="!historyOrders.length"><td colspan="7" class="muted center">{{ t('quant.paperTrading.noHistory') }}</td></tr>
              </tbody>
            </table>
          </div>

          <!-- Auto trader -->
          <div v-show="activeTab === 'auto'" class="tab-body">
            <div class="strategy-box">
              <div class="strategy-box__head">
                <strong>{{ t('quant.paperTrading.strategyTitle') }}</strong>
                <span class="muted">{{ t('quant.paperTrading.strategyEngine') }}</span>
              </div>
              <p class="muted small-note">{{ t('quant.paperTrading.strategyDesc') }}</p>
              <ul class="strategy-rules" v-if="autoConfig">
                <li>{{ t('quant.paperTrading.ruleScore') }} <b>{{ autoConfig.score_threshold }}</b></li>
                <li>{{ t('quant.paperTrading.ruleConfidence') }} <b>{{ autoConfig.min_confidence }}</b></li>
                <li>{{ t('quant.paperTrading.ruleMaxPos') }} <b>{{ (autoConfig.max_position_pct * 100).toFixed(0) }}%</b></li>
                <li>{{ t('quant.paperTrading.ruleCashReserve') }} <b>{{ (autoConfig.cash_reserve_pct * 100).toFixed(0) }}%</b></li>
              </ul>
            </div>
            <div class="auto-controls">
              <div class="control grow">
                <label>{{ t('quant.paperTrading.watchlistOverride') }}</label>
                <input v-model="auto.watchlistText" placeholder="BTC-USDT,ETH-USDT,AAPL" />
              </div>
              <button class="primary" @click="runAutoTrade" :disabled="auto.running">
                {{ auto.running ? t('quant.paperTrading.running') : t('quant.paperTrading.runCycle') }}
              </button>
            </div>
            <div v-if="auto.running || auto.progress" class="progress">
              <div class="progress__bar"><div class="progress__fill" :style="{ width: progressPct + '%' }"></div></div>
              <span class="progress__txt">
                {{ auto.progress ? `${auto.progress.done}/${auto.progress.total}` : '' }}
                {{ auto.progress?.symbol ? '· ' + auto.progress.symbol : '' }}
              </span>
            </div>
            <div class="auto-result" v-if="auto.lastResult">
              <div class="auto-summary">
                <span>{{ t('quant.paperTrading.executed') }} <b>{{ auto.lastResult.executed }}</b></span>
                <span>{{ t('quant.paperTrading.pendingFilled') }} <b>{{ auto.lastResult.pending_filled }}</b></span>
                <span class="muted">{{ shortTs(auto.lastResult.ts) }}</span>
              </div>
              <table class="data-table small">
                <thead>
                  <tr>
                    <th>{{ t('quant.paperTrading.symbol') }}</th><th>{{ t('quant.paperTrading.statusCol') }}</th>
                    <th>{{ t('quant.paperTrading.side') }}</th><th>{{ t('quant.paperTrading.qty') }}</th>
                    <th>Score</th><th>Conf</th><th>{{ t('quant.paperTrading.reason') }}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(d, i) in auto.lastResult.decisions" :key="i" :class="{ executed: d.status === 'executed' }">
                    <td>{{ d.symbol }}</td>
                    <td>{{ d.status }}</td>
                    <td :class="d.side === 'buy' ? 'positive' : (d.side === 'sell' ? 'negative' : '')">{{ d.side || '—' }}</td>
                    <td>{{ d.qty ? formatNum(d.qty) : '—' }}</td>
                    <td>{{ d.score != null ? Number(d.score).toFixed(3) : '—' }}</td>
                    <td>{{ d.confidence != null ? Number(d.confidence).toFixed(2) : '—' }}</td>
                    <td class="muted">{{ d.reason }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>

      <!-- Right: order ticket + signal -->
      <aside class="ws__ticket">
        <div class="ticket-card">
          <OrderTicket
            :symbol="selectedSymbol"
            :last-price="lastQuote"
            :stale="!!quoteStale[selectedSymbol]"
            :position-qty="selectedPositionQty"
            :cash="account ? account.cash : null"
            :busy="loading"
            @submit="onTicketSubmit"
          />
        </div>
        <div class="signal-card" v-if="signal">
          <h4>{{ t('quant.paperTrading.signal') }}</h4>
          <div class="signal-row">
            <span class="muted">{{ t('quant.paperTrading.direction') }}</span>
            <b :class="signalClass">{{ signal.direction || signal.action || '—' }}</b>
          </div>
          <div class="signal-row" v-if="signal.score != null">
            <span class="muted">Score</span><b>{{ Number(signal.score).toFixed(3) }}</b>
          </div>
          <div class="signal-row" v-if="signal.confidence != null">
            <span class="muted">{{ t('quant.paperTrading.confidence') }}</span><b>{{ Number(signal.confidence).toFixed(2) }}</b>
          </div>
        </div>

        <!-- Model & strategy panel -->
        <div class="model-card">
          <h4>{{ t('quant.paperTrading.modelPanelTitle') }}</h4>
          <p class="model-desc">{{ t('quant.paperTrading.modelPanelDesc') }}</p>
          <div class="model-sources">
            <div class="model-src-head">{{ t('quant.paperTrading.activeSources') }}</div>
            <div v-for="src in signalSources" :key="src.name" class="model-src">
              <div class="model-src__top">
                <strong>{{ modelLabel(src.name) }}</strong>
                <span v-if="src.direction" class="src-dir" :class="dirClass(src.direction)">{{ src.direction }}</span>
              </div>
              <small class="muted">{{ modelDesc(src.name) }}</small>
              <div class="model-src__metrics" v-if="src.score != null || src.confidence != null">
                <span v-if="src.score != null">Score <b>{{ Number(src.score).toFixed(3) }}</b></span>
                <span v-if="src.confidence != null">Conf <b>{{ Number(src.confidence).toFixed(2) }}</b></span>
              </div>
            </div>
            <div v-if="!signalSources.length" class="muted small-note">{{ t('quant.paperTrading.noSources') }}</div>
          </div>
          <div class="model-fusion">
            <div class="model-src-head">{{ t('quant.paperTrading.fusionTitle') }}</div>
            <p class="muted small-note">{{ t('quant.paperTrading.fusionDesc') }}</p>
          </div>
          <details class="model-catalog">
            <summary>{{ t('quant.paperTrading.backtestModels') }}</summary>
            <div v-for="m in MODEL_CATALOG" :key="m.key" class="catalog-row">
              <strong>{{ m.label }}</strong>
              <small class="muted">{{ m.desc }}</small>
            </div>
          </details>
        </div>
      </aside>
    </section>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onBeforeUnmount } from 'vue'
import { useI18n } from 'vue-i18n'
import { paperTradingApi } from '@/api/paperTrading'
import TradingChart from '@/components/paper/TradingChart.vue'
import OrderTicket from '@/components/paper/OrderTicket.vue'

const { t } = useI18n()

const symbols = ref([])
const accounts = ref([])
const account = ref(null)
const orders = ref([])
const quotes = reactive({})
const quoteStale = reactive({})
const loading = ref(false)
const error = ref('')

const selectedSymbol = ref('BTC-USDT')
const symbolSearch = ref('')
const classFilter = ref('all')
const timeframe = ref('1d')
const rangeKey = ref('1y')
const candles = ref([])
const chartLoading = ref(false)
const signal = ref(null)
const activeTab = ref('positions')
const autoConfig = ref(null)

const newAccount = reactive({ name: 'My Paper Account', initial_cash: 100000, ccy: 'USD' })

const auto = reactive({ running: false, watchlistText: '', lastResult: null, progress: null })
let autoPollTimer = null
let quoteTimer = null

const timeframes = [
  { value: '1d', label: '1D' },
  { value: '4h', label: '4H' },
  { value: '1h', label: '1H' }
]
const ranges = [
  { value: '1m', label: '1M' },
  { value: '3m', label: '3M' },
  { value: '6m', label: '6M' },
  { value: '1y', label: '1Y' },
  { value: '2y', label: '2Y' },
  { value: '5y', label: '5Y' }
]
const RANGE_DAYS = { '1m': 30, '3m': 90, '6m': 180, '1y': 365, '2y': 730, '5y': 1825 }
const CLASS_ORDER = ['crypto', 'us_stock', 'hk_etf', 'hk_stock', 'a_stock']
const classFilters = ['all', ...CLASS_ORDER]

// Human-readable labels for the models / signal sources driving paper trading.
const MODEL_LABELS = {
  quant_pipeline: 'Quant Pipeline',
  stock_forecast: 'Stock Forecaster',
  crypto_forecast: 'Crypto Forecaster'
}
const MODEL_DESCS = {
  quant_pipeline: 'Kronos + Chronos-Bolt 价格点预测 + Two-Tower 元模型（上次回测信号）',
  stock_forecast: '技术面 55% · 情绪 30% · OASIS 群体 8% · 量能 7%',
  crypto_forecast: '链上 / 技术 / 情绪复合方向概率'
}
const MODEL_CATALOG = [
  { key: 'price_point_calibrated_ml', label: 'Price-Point Calibrated ML', desc: 'Kronos（精确价格）+ Chronos-Bolt（稳健区间）基础集成 + 残差/分位校准' },
  { key: 'two_tower', label: 'Two-Tower Walk-Forward', desc: 'Market Tower（量价技术）+ Swarm Tower（8 个 OASIS 行为因子）+ Meta-Model 融合' },
  { key: 'financial_forecast', label: 'Financial Forecast', desc: '可解释复合：技术 55% · 情绪 30% · OASIS 8% · 量能 7%' }
]

const tabs = computed(() => [
  { value: 'positions', label: t('quant.paperTrading.tabPositions'), count: account.value?.positions?.length || 0 },
  { value: 'pending', label: t('quant.paperTrading.tabPending'), count: pendingOrders.value.length },
  { value: 'history', label: t('quant.paperTrading.tabHistory') },
  { value: 'auto', label: t('quant.paperTrading.tabAuto') }
])

const selectedMeta = computed(() => symbols.value.find(s => s.symbol === selectedSymbol.value) || null)
const lastQuote = computed(() => quotes[selectedSymbol.value] ?? null)

const filteredSymbols = computed(() => {
  const q = symbolSearch.value.trim().toLowerCase()
  let list = symbols.value
  if (classFilter.value !== 'all') {
    list = list.filter(s => (s.asset_class || 'other') === classFilter.value)
  }
  if (!q) return list
  return list.filter(s =>
    s.symbol.toLowerCase().includes(q) || (s.display || '').toLowerCase().includes(q))
})
const groupedSymbols = computed(() => {
  const map = {}
  for (const s of filteredSymbols.value) {
    const k = s.asset_class || 'other'
    ;(map[k] = map[k] || []).push(s)
  }
  const keys = Object.keys(map).sort((a, b) => {
    const ia = CLASS_ORDER.indexOf(a); const ib = CLASS_ORDER.indexOf(b)
    return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib)
  })
  return keys.map(k => ({ key: k, items: map[k] }))
})

const pendingOrders = computed(() => orders.value.filter(o => o.status === 'pending'))
const historyOrders = computed(() => orders.value.filter(o => o.status !== 'pending'))

const selectedPosition = computed(() => (account.value?.positions || []).find(p => p.symbol === selectedSymbol.value) || null)
const selectedPositionQty = computed(() => selectedPosition.value?.qty || 0)

const progressPct = computed(() => {
  if (!auto.progress || !auto.progress.total) return auto.running ? 8 : 0
  return Math.round((auto.progress.done / auto.progress.total) * 100)
})

const signalClass = computed(() => {
  const d = String(signal.value?.direction || signal.value?.action || '').toLowerCase()
  if (d.includes('buy') || d.includes('long')) return 'positive'
  if (d.includes('sell') || d.includes('short')) return 'negative'
  return ''
})

const signalSources = computed(() => {
  const src = signal.value?.sources
  return Array.isArray(src) ? src : []
})

function modelLabel (name) { return MODEL_LABELS[name] || name }
function modelDesc (name) { return MODEL_DESCS[name] || '' }
function dirClass (dir) {
  const d = String(dir || '').toLowerCase()
  if (d.includes('up') || d.includes('buy') || d.includes('long')) return 'positive'
  if (d.includes('down') || d.includes('sell') || d.includes('short')) return 'negative'
  return ''
}

// Chart overlays
const chartPriceLines = computed(() => {
  const lines = []
  const pos = selectedPosition.value
  if (pos && pos.avg_price) {
    lines.push({ price: pos.avg_price, color: '#2563eb', dashed: true, title: t('quant.paperTrading.avgLine') })
  }
  for (const o of pendingOrders.value) {
    if (o.symbol !== selectedSymbol.value) continue
    const px = o.stop_price || o.limit_price
    if (!px) continue
    lines.push({ price: px, color: o.side === 'buy' ? '#16a34a' : '#dc2626', dashed: true, title: orderTypeLabel(o.order_type) })
  }
  return lines
})
const chartMarkers = computed(() => {
  return historyOrders.value
    .filter(o => o.symbol === selectedSymbol.value && o.status === 'filled')
    .map(o => ({
      time: Math.floor(new Date(o.ts).getTime() / 1000),
      position: o.side === 'buy' ? 'belowBar' : 'aboveBar',
      color: o.side === 'buy' ? '#16a34a' : '#dc2626',
      shape: o.side === 'buy' ? 'arrowUp' : 'arrowDown',
      text: (o.side === 'buy' ? 'B ' : 'S ') + formatNum(o.qty)
    }))
})

async function loadSymbols () {
  try {
    const data = await paperTradingApi.listSymbols()
    symbols.value = data.symbols || []
  } catch (e) {
    symbols.value = [
      { symbol: 'BTC-USDT', display: 'Bitcoin / USDT', asset_class: 'crypto' },
      { symbol: 'ETH-USDT', display: 'Ethereum / USDT', asset_class: 'crypto' },
      { symbol: 'AAPL', display: 'Apple Inc.', asset_class: 'us_stock' },
      { symbol: '3033.HK', display: 'HS Tech ETF', asset_class: 'hk_etf' },
      { symbol: '000300.SH', display: 'CSI 300', asset_class: 'a_stock' }
    ]
  }
  if (symbols.value.length && !symbols.value.find(s => s.symbol === selectedSymbol.value)) {
    selectedSymbol.value = symbols.value[0].symbol
  }
}

async function loadAccountList () {
  try {
    const data = await paperTradingApi.listAccounts()
    accounts.value = data.accounts || []
  } catch (e) { /* ignore */ }
}

async function createAccount () {
  error.value = ''
  loading.value = true
  try {
    const doc = await paperTradingApi.createAccount({ ...newAccount })
    await loadAccount(doc.account_id)
  } catch (e) {
    error.value = e?.response?.data?.error || e.message
  } finally {
    loading.value = false
  }
}

async function loadAccount (id) {
  loading.value = true
  error.value = ''
  try {
    account.value = await paperTradingApi.getAccount(id)
    await refreshOrders()
    await refreshQuotes()
    await loadChart()
    await loadSignal()
    startQuotePolling()
  } catch (e) {
    error.value = e?.response?.data?.error || e.message
  } finally {
    loading.value = false
  }
}

function switchAccount () {
  stopQuotePolling()
  account.value = null
  loadAccountList()
}

async function deleteAccount (a) {
  const ok = window.confirm(t('quant.paperTrading.confirmDelete', { name: a.name }))
  if (!ok) return
  try {
    await paperTradingApi.deleteAccount(a.account_id)
    if (account.value && account.value.account_id === a.account_id) {
      switchAccount()
    }
    await loadAccountList()
  } catch (e) {
    error.value = e?.response?.data?.error || e.message
  }
}

async function loadAutoConfig () {
  try {
    autoConfig.value = await paperTradingApi.autoTradeConfig()
  } catch (e) { /* ignore */ }
}

async function refreshOrders () {
  if (!account.value) return
  try {
    const data = await paperTradingApi.listOrders(account.value.account_id)
    orders.value = (data.orders || []).slice().reverse()
  } catch (e) { /* ignore */ }
}

async function refreshQuotes () {
  const targets = symbols.value.slice(0, 12)
  await Promise.all(targets.map(async (s) => {
    try {
      const q = await paperTradingApi.quote(s.symbol)
      if (q.price != null) quotes[s.symbol] = q.price
      quoteStale[s.symbol] = !!q.stale
    } catch (e) { /* ignore */ }
  }))
}

async function loadChart () {
  chartLoading.value = true
  try {
    const days = RANGE_DAYS[rangeKey.value] || 365
    const data = await paperTradingApi.ohlcv(selectedSymbol.value, { tf: timeframe.value, days })
    candles.value = data.candles || []
  } catch (e) {
    candles.value = []
  } finally {
    chartLoading.value = false
  }
}

async function loadSignal () {
  try {
    signal.value = await paperTradingApi.fusedSignal(selectedSymbol.value)
  } catch (e) {
    signal.value = null
  }
}

function selectSymbol (sym) {
  if (selectedSymbol.value === sym) return
  selectedSymbol.value = sym
  loadChart()
  loadSignal()
  if (quotes[sym] == null) {
    paperTradingApi.quote(sym).then(q => {
      if (q.price != null) quotes[sym] = q.price
      quoteStale[sym] = !!q.stale
    }).catch(() => {})
  }
}

function setTimeframe (tf) {
  if (timeframe.value === tf) return
  timeframe.value = tf
  loadChart()
}

function setRange (r) {
  if (rangeKey.value === r) return
  rangeKey.value = r
  loadChart()
}

async function onTicketSubmit (payload) {
  if (!account.value) return
  error.value = ''
  loading.value = true
  try {
    await paperTradingApi.placeOrder(account.value.account_id, { symbol: selectedSymbol.value, ...payload })
    await loadAccount(account.value.account_id)
  } catch (e) {
    error.value = e?.response?.data?.error || e.message
  } finally {
    loading.value = false
  }
}

async function quickClose (pos) {
  if (!account.value || !pos.qty) return
  error.value = ''
  loading.value = true
  try {
    await paperTradingApi.placeOrder(account.value.account_id, {
      symbol: pos.symbol,
      side: pos.qty > 0 ? 'sell' : 'buy',
      qty: Math.abs(pos.qty),
      order_type: 'market',
      reduce_only: true
    })
    await loadAccount(account.value.account_id)
  } catch (e) {
    error.value = e?.response?.data?.error || e.message
  } finally {
    loading.value = false
  }
}

async function cancelOrder (o) {
  if (!account.value) return
  error.value = ''
  try {
    await paperTradingApi.cancelOrder(account.value.account_id, o.order_id)
    await refreshOrders()
  } catch (e) {
    error.value = e?.response?.data?.error || e.message
  }
}

async function runAutoTrade () {
  if (!account.value || auto.running) return
  error.value = ''
  auto.running = true
  auto.progress = null
  try {
    const payload = {}
    const wl = auto.watchlistText.trim()
    if (wl) payload.watchlist = wl.split(',').map(s => s.trim()).filter(Boolean)
    const { task_id } = await paperTradingApi.startAutoTrade(account.value.account_id, payload)
    pollAutoTask(task_id)
  } catch (e) {
    error.value = e?.response?.data?.error || e.message
    auto.running = false
  }
}

function pollAutoTask (taskId) {
  stopAutoPoll()
  autoPollTimer = setInterval(async () => {
    try {
      const task = await paperTradingApi.pollAutoTask(taskId)
      auto.progress = { done: task.done || 0, total: task.total || 0, symbol: task.current_symbol }
      if (task.status === 'done') {
        auto.lastResult = task.result || auto.lastResult
        finishAuto()
      } else if (task.status === 'error') {
        error.value = task.error || 'auto-trade failed'
        auto.lastResult = task.result || auto.lastResult
        finishAuto()
      }
    } catch (e) {
      error.value = e?.response?.data?.error || e.message
      finishAuto()
    }
  }, 1200)
}

function finishAuto () {
  stopAutoPoll()
  auto.running = false
  if (account.value) loadAccount(account.value.account_id)
}

function stopAutoPoll () {
  if (autoPollTimer) { clearInterval(autoPollTimer); autoPollTimer = null }
}

function startQuotePolling () {
  stopQuotePolling()
  quoteTimer = setInterval(() => { if (account.value) refreshQuotes() }, 20000)
}
function stopQuotePolling () {
  if (quoteTimer) { clearInterval(quoteTimer); quoteTimer = null }
}

function orderTypeLabel (ot) {
  const map = {
    market: t('quant.paperTrading.typeMarket'),
    limit: t('quant.paperTrading.typeLimit'),
    stop: t('quant.paperTrading.typeStop'),
    stop_limit: t('quant.paperTrading.typeStopLimit'),
    trailing_stop: t('quant.paperTrading.typeTrailing'),
    oco: 'OCO'
  }
  return map[ot] || ot
}

function shortTs (ts) { return String(ts || '').slice(0, 19).replace('T', ' ') }
function formatMoney (v) {
  if (v == null) return '-'
  return Number(v).toLocaleString(undefined, { maximumFractionDigits: 2 })
}
function formatPct (v) {
  if (v == null) return '-'
  return (Number(v) * 100).toFixed(2) + '%'
}
function formatNum (v) {
  if (v == null || isNaN(v)) return '-'
  return Number(v).toFixed(4)
}

onMounted(async () => {
  await loadSymbols()
  await loadAccountList()
  loadAutoConfig()
})

onBeforeUnmount(() => {
  stopAutoPoll()
  stopQuotePolling()
})
</script>

<style scoped>
.quant-page { min-height: 100vh; background: var(--c-bg); color: var(--c-text); }
.quant-page__bar {
  display: flex; align-items: center; gap: var(--s-4);
  padding: var(--s-4) var(--s-6); border-bottom: 1px solid var(--c-border);
  background: var(--c-bg-soft);
}
.quant-page__bar h1 { font-size: 16px; margin: 0; font-weight: 700; }
.quant-page__bar .status {
  font-family: var(--f-mono); font-size: 11px; letter-spacing: .14em; color: var(--c-text-subtle);
}
.account-info { margin-left: auto; display: flex; gap: 10px; align-items: center; font-size: 13px; }
.account-info .kicker {
  font-family: var(--f-mono); font-size: 10px; letter-spacing: .14em;
  background: var(--c-text); color: var(--c-bg); padding: 2px 6px;
}
.muted { color: var(--c-text-subtle); font-size: 12px; }
.back { background: transparent; border: 1px solid var(--c-border); padding: 4px 10px; font-size: 12px; cursor: pointer; border-radius: 4px; }
.control-row {
  display: flex; gap: var(--s-3); flex-wrap: wrap; align-items: flex-end;
  padding: var(--s-5) var(--s-6); border-bottom: 1px solid var(--c-border); background: var(--c-bg-soft);
}
.control { display: flex; flex-direction: column; gap: 4px; }
.control.grow { flex: 1; }
.control label { font-family: var(--f-mono); font-size: 10px; letter-spacing: .14em; text-transform: uppercase; color: var(--c-text-subtle); }
.control select, .control input { padding: 6px 10px; border: 1px solid var(--c-border); border-radius: 4px; background: var(--c-bg); font-size: 13px; min-width: 140px; }
.primary { padding: 10px 18px; background: var(--c-text); color: var(--c-bg); border: none; font-weight: 700; font-size: 13px; letter-spacing: .08em; cursor: pointer; border-radius: 4px; }
.primary:disabled { opacity: .5; cursor: not-allowed; }
.ghost { padding: 6px 10px; background: transparent; border: 1px solid var(--c-border); font-size: 12px; cursor: pointer; border-radius: 4px; }
.account-list { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.account-chip { display: inline-flex; align-items: center; }
.account-chip .ghost { border-top-right-radius: 0; border-bottom-right-radius: 0; }
.chip-x { padding: 6px 8px; background: transparent; border: 1px solid var(--c-border); border-left: none; border-top-right-radius: 4px; border-bottom-right-radius: 4px; font-size: 13px; line-height: 1; color: #dc2626; cursor: pointer; }
.chip-x:hover { background: rgba(220,38,38,.08); }
.error-banner { margin: var(--s-4) var(--s-6); padding: var(--s-3); border: 1px solid #e54; background: rgba(238, 85, 68, .08); color: #e54; font-size: 13px; border-radius: 4px; }
.positive { color: #16a34a; }
.negative { color: #dc2626; }

/* Workspace */
.ws { display: grid; grid-template-columns: 240px 1fr 320px; gap: var(--s-4); padding: var(--s-4) var(--s-5); align-items: start; }

/* Watchlist */
.ws__watchlist { border: 1px solid var(--c-border); border-radius: var(--r-md); background: var(--c-bg-soft); padding: var(--s-3); position: sticky; top: var(--s-4); }
.wl-search { width: 100%; padding: 7px 10px; border: 1px solid var(--c-border); border-radius: 4px; background: var(--c-bg); font-size: 13px; margin-bottom: var(--s-3); }
.wl-filter { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: var(--s-3); }
.wl-chip { padding: 3px 8px; font-size: 11px; border: 1px solid var(--c-border); background: var(--c-bg); cursor: pointer; border-radius: 12px; color: var(--c-text-muted); }
.wl-chip.active { background: var(--c-text); color: var(--c-bg); border-color: var(--c-text); }
.wl-group { margin-bottom: var(--s-3); }
.wl-group__title { font-family: var(--f-mono); font-size: 10px; letter-spacing: .12em; text-transform: uppercase; color: var(--c-text-muted); margin-bottom: 4px; }
.wl-group ul { list-style: none; padding: 0; margin: 0; }
.wl-group li { display: flex; justify-content: space-between; align-items: center; padding: 7px 8px; cursor: pointer; border-radius: 4px; font-size: 13px; }
.wl-group li:hover { background: var(--c-bg); }
.wl-group li.active { background: var(--c-text); color: var(--c-bg); }
.wl-item__name strong { display: block; font-size: 13px; }
.wl-item__name small { display: block; opacity: .7; font-size: 11px; }
.px { font-family: var(--f-mono); font-size: 12px; }
.px.stale { color: #b58100; }

/* Main */
.ws__main { display: flex; flex-direction: column; gap: var(--s-4); min-width: 0; }
.chart-card, .tabs-card { border: 1px solid var(--c-border); border-radius: var(--r-md); background: var(--c-bg-soft); }
.chart-toolbar { display: flex; align-items: center; justify-content: space-between; padding: var(--s-3) var(--s-4); border-bottom: 1px solid var(--c-border); }
.chart-title { display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap; }
.chart-title strong { font-size: 15px; }
.chart-last { font-family: var(--f-mono); font-size: 14px; }
.stale-tag { font-size: 10px; font-family: var(--f-mono); background: rgba(234,179,8,.16); color: #b58100; padding: 2px 6px; border-radius: 4px; }
.tf-seg { display: flex; gap: 4px; }
.chart-segs { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.tf-btn { padding: 4px 10px; font-size: 11px; font-family: var(--f-mono); border: 1px solid var(--c-border); background: var(--c-bg); cursor: pointer; border-radius: 4px; }
.tf-btn.active { background: var(--c-text); color: var(--c-bg); border-color: var(--c-text); }
.chart-host { height: 420px; padding: var(--s-2); }

/* Tabs */
.tabs { display: flex; gap: 2px; border-bottom: 1px solid var(--c-border); padding: 0 var(--s-3); }
.tab { padding: 10px 14px; font-size: 13px; background: transparent; border: none; border-bottom: 2px solid transparent; cursor: pointer; color: var(--c-text-muted); }
.tab.active { color: var(--c-text); border-bottom-color: var(--c-text); font-weight: 600; }
.badge { display: inline-block; margin-left: 6px; font-size: 10px; font-family: var(--f-mono); background: var(--c-border); color: var(--c-text); padding: 1px 5px; border-radius: 8px; }
.tab-body { padding: var(--s-4); }
.data-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.data-table th, .data-table td { text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--c-border); }
.data-table th { font-family: var(--f-mono); font-size: 11px; letter-spacing: .12em; color: var(--c-text-subtle); }
.data-table .center { text-align: center; }
.data-table .rowlink { cursor: pointer; }
.data-table .rowlink:hover { background: var(--c-bg); }
.data-table.small th, .data-table.small td { padding: 4px 6px; font-size: 12px; }
.data-table tr.executed { background: rgba(34,119,238,.06); }
.mini { padding: 3px 8px; font-size: 11px; border: 1px solid var(--c-border); background: var(--c-bg); cursor: pointer; border-radius: 4px; }
.mini.danger { color: #dc2626; border-color: #dc262644; }

/* Auto */
.auto-controls { display: flex; gap: var(--s-3); align-items: flex-end; margin-bottom: var(--s-3); }
.progress { display: flex; align-items: center; gap: var(--s-3); margin-bottom: var(--s-3); }
.progress__bar { flex: 1; height: 6px; background: var(--c-border); border-radius: 3px; overflow: hidden; }
.progress__fill { height: 100%; background: #2563eb; transition: width .3s ease; }
.progress__txt { font-family: var(--f-mono); font-size: 12px; color: var(--c-text-muted); white-space: nowrap; }
.auto-summary { display: flex; gap: var(--s-4); align-items: center; margin-bottom: var(--s-2); font-size: 13px; }
.auto-summary b { font-family: var(--f-mono); color: var(--c-text); }

/* Ticket */
.ws__ticket { display: flex; flex-direction: column; gap: var(--s-4); position: sticky; top: var(--s-4); }
.ticket-card, .signal-card { border: 1px solid var(--c-border); border-radius: var(--r-md); background: var(--c-bg-soft); padding: var(--s-4); }
.signal-card h4 { margin: 0 0 var(--s-3); font-size: 12px; font-family: var(--f-mono); letter-spacing: .12em; text-transform: uppercase; color: var(--c-text-muted); }
.signal-row { display: flex; justify-content: space-between; font-size: 13px; padding: 3px 0; }
.signal-row b { font-family: var(--f-mono); }

/* Model & strategy panel */
.model-card { border: 1px solid var(--c-border); border-radius: var(--r-md); background: var(--c-bg-soft); padding: var(--s-4); }
.model-card h4 { margin: 0 0 6px; font-size: 12px; font-family: var(--f-mono); letter-spacing: .12em; text-transform: uppercase; color: var(--c-text-muted); }
.model-desc { margin: 0 0 var(--s-3); font-size: 12px; color: var(--c-text-muted); line-height: 1.5; }
.model-src-head { font-family: var(--f-mono); font-size: 10px; letter-spacing: .12em; text-transform: uppercase; color: var(--c-text-subtle); margin-bottom: 6px; }
.model-src { padding: 8px; border: 1px solid var(--c-border); border-radius: 6px; background: var(--c-bg); margin-bottom: 8px; }
.model-src__top { display: flex; justify-content: space-between; align-items: center; gap: 6px; }
.model-src__top strong { font-size: 13px; }
.src-dir { font-family: var(--f-mono); font-size: 10px; padding: 1px 6px; border-radius: 4px; background: var(--c-border); }
.model-src__metrics { display: flex; gap: 12px; margin-top: 4px; font-size: 12px; }
.model-src__metrics b { font-family: var(--f-mono); }
.small-note { font-size: 12px; line-height: 1.5; }
.model-fusion { margin-top: var(--s-3); }
.model-catalog { margin-top: var(--s-3); border-top: 1px solid var(--c-border); padding-top: var(--s-3); }
.model-catalog summary { cursor: pointer; font-size: 12px; font-family: var(--f-mono); letter-spacing: .08em; color: var(--c-text-muted); }
.catalog-row { padding: 6px 0; border-bottom: 1px dashed var(--c-border); }
.catalog-row strong { display: block; font-size: 12px; }
.catalog-row small { display: block; font-size: 11px; }

/* Strategy box (auto tab) */
.strategy-box { border: 1px solid var(--c-border); border-radius: 6px; background: var(--c-bg); padding: var(--s-3); margin-bottom: var(--s-3); }
.strategy-box__head { display: flex; align-items: baseline; gap: 8px; }
.strategy-box__head strong { font-size: 13px; }
.strategy-rules { display: flex; flex-wrap: wrap; gap: 6px 18px; list-style: none; padding: 8px 0 0; margin: 0; font-size: 12px; }
.strategy-rules b { font-family: var(--f-mono); }

@media (max-width: 1100px) {
  .ws { grid-template-columns: 1fr; }
  .ws__watchlist, .ws__ticket { position: static; }
}
</style>
