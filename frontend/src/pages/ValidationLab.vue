<template>
  <div class="validation-lab finrex-v2">
    <HomeNavbar>
      <LanguageSwitcher />
      <UiButton variant="link" size="sm" @click="$router.push('/')">返回首页</UiButton>
      <UiButton variant="link" size="sm" @click="$router.push('/quant/backtest')">回测实验室</UiButton>
    </HomeNavbar>

    <MarketTickerStrip :ticker="ticker" />

    <header class="desk-head">
      <div>
        <UiBadge tone="warning" dot>BTC Weekly Forecast · Polymarket Overlay</UiBadge>
        <h1>本周比特币会涨到哪个价位？</h1>
        <p>选择一个预测模型，FinRex 给出本周收盘价的概率分布，并与真实 Polymarket 赔率逐档对比，找出有正向 edge 的区间进行内部模拟下注。</p>
      </div>
      <div class="cycle-card" :class="cycleStatusClass">
        <div><span>Cycle</span><strong>{{ cycle?.cycle_id || '—' }}</strong></div>
        <div><span>Range</span><strong>{{ formatRange(cycle?.anchor_utc, cycle?.resolve_utc) }}</strong></div>
        <div><span>Resolve In</span><strong>{{ countdown }}</strong></div>
        <div><span>Anchor Spot</span><strong>${{ formatNum(cycle?.spot_at_anchor) }}</strong></div>
      </div>
    </header>

    <!-- 1) Controls: pick a model, run, see data freshness -->
    <section class="control-band">
      <div class="control-left">
        <ModelPicker v-model="selectedModel" :items="models" :loading="modelsLoading" @change="onModelChange" />
        <div class="control-actions">
          <UiButton size="sm" :loading="snapshotting" @click="runSnapshot(true)">运行 Snapshot 并下注</UiButton>
          <UiButton size="sm" variant="ghost" :loading="snapshotting" @click="runSnapshot(false)">仅刷新预测</UiButton>
        </div>
      </div>
      <div class="source-row">
        <DataSourceBadge status="live" label="Binance K线" :detail="`${ohlcvRows.length} candles`" />
        <DataSourceBadge :status="polymarketStatus" label="Polymarket" :detail="polymarketDetail" />
      </div>
    </section>

    <!-- 2) The answer: one-line decision summary -->
    <DecisionSummaryBar class="summary-bar" :bins="forecastBins" :positions="currentCyclePositions" :model-meta="modelMeta" :cash="kpi?.equity" />

    <!-- 3) The evidence: price chart + model-vs-market distribution -->
    <section class="desk-main">
      <main class="chart-zone">
        <div class="panel-head">
          <div><h3>BTCUSDT K线 · 概率区间叠加</h3><span>Binance public REST · {{ chartInterval }} · {{ lookback }} · {{ ohlcvRows.length }} candles</span></div>
          <div class="segmented">
            <button :class="{active: lookback === '7d'}" @click="setLookback('7d')">7D</button>
            <button :class="{active: lookback === '60d'}" @click="setLookback('60d')">2M</button>
            <button :class="{active: lookback === '1y'}" @click="setLookback('1y')">1Y</button>
          </div>
        </div>
        <BtcCandlestickChart
          :rows="ohlcvRows"
          :bins="forecastBins"
          :forecast="cycle?.latest_forecast"
          height="540px"
        />
      </main>

      <aside class="right-rail">
        <OutcomeBoard :bins="forecastBins" :market="polymarket.current" />
      </aside>
    </section>

    <!-- 4) Drill-down tabs: progressive disclosure of diagnostics -->
    <nav class="vl-tabs">
      <button v-for="t in tabs" :key="t.key" :class="{ active: activeTab === t.key }" @click="activeTab = t.key">{{ t.label }}</button>
    </nav>

    <section class="tab-content">
      <div v-show="activeTab === 'forecast'" class="tab-grid">
        <section class="desk-panel">
          <div class="panel-head compact"><div><h3>概率分布</h3><span>模型每档概率 vs 均匀基线 1/n</span></div></div>
          <BinsForecastPanel :bins="forecastBins" :baseline-prob="baselineProb" :latest-forecast="cycle?.latest_forecast" />
        </section>
        <section class="desk-panel" v-if="cycle?.latest_forecast">
          <div class="panel-head compact"><div><h3>模型内部信号</h3><span>当前模型的预测过程与参数</span></div></div>
          <ValidationModelDebugPanel :forecast="cycle.latest_forecast" />
        </section>
      </div>

      <div v-show="activeTab === 'edge'" class="tab-grid">
        <section class="desk-panel">
          <div class="panel-head compact"><div><h3>Edge Matrix</h3><span>FinRex 概率 vs 市场隐含概率，逐档 edge</span></div></div>
          <EdgeMatrix :bins="forecastBins" :positions="currentCyclePositions" :market="polymarket.current" :baseline-prob="baselineProb" />
        </section>
        <section class="desk-panel">
          <div class="panel-head compact"><div><h3>下注决策漏斗</h3><span>正 edge → Kelly 仓位 → 上限 → 最终模拟下注</span></div></div>
          <BetDecisionFunnel :positions="currentCyclePositions" />
        </section>
      </div>

      <div v-show="activeTab === 'positions'" class="tab-grid one">
        <section class="desk-panel">
          <div class="panel-head compact">
            <div><h3>Paper Betting 持仓</h3><span>内部模拟下注记录，不连接钱包</span></div>
            <div class="segmented">
              <button :class="{active: posFilter === 'all'}" @click="posFilter = 'all'">All</button>
              <button :class="{active: posFilter === 'open'}" @click="posFilter = 'open'">Open</button>
              <button :class="{active: posFilter === 'settled'}" @click="posFilter = 'settled'">Settled</button>
            </div>
          </div>
          <BinsPositionsTable :rows="filteredPositions" />
        </section>
      </div>

      <div v-show="activeTab === 'performance'" class="tab-grid">
        <section class="desk-panel kpis" v-if="kpi">
          <div><span>Equity</span><strong>${{ formatNum(kpi.equity) }}</strong></div>
          <div><span>Realized PnL</span><strong :class="kpi.realized_pnl >= 0 ? 'pos' : 'neg'">${{ formatNum(kpi.realized_pnl) }}</strong></div>
          <div><span>Settled Cycles</span><strong>{{ kpi.n_settled_cycles }} / {{ kpi.n_cycles }}</strong></div>
          <div><span>Win Rate</span><strong>{{ kpi.win_rate != null ? (kpi.win_rate * 100).toFixed(1) + '%' : '—' }}</strong></div>
          <div><span>Brier</span><strong>{{ kpi.multi_class_brier != null ? kpi.multi_class_brier.toFixed(4) : '—' }}</strong></div>
        </section>
        <section class="desk-panel">
          <div class="panel-head compact"><div><h3>验证净值曲线</h3><span>按结算周累计</span></div></div>
          <EChart v-if="equityCurve.length" :option="equityOption" height="280px" />
          <div v-else class="empty">暂无已结算周期。</div>
        </section>
        <section class="desk-panel">
          <div class="panel-head compact"><div><h3>结算瀑布</h3><span>每个已结算周注的实现盈亏</span></div></div>
          <SettlementWaterfall :positions="filteredPositions" />
        </section>
        <section class="desk-panel">
          <div class="panel-head compact"><div><h3>分置信度胜率</h3><span>已结算样本按模型概率分桶</span></div></div>
          <ConfidenceBuckets :buckets="kpi?.confidence_buckets || []" />
        </section>
      </div>

      <div v-show="activeTab === 'polymarket'" class="tab-grid one">
        <WeeklyHistoryPanel :rows="polymarket.history" />
      </div>
    </section>

    <footer class="vl-foot">FinRex 只读展示 Polymarket 赔率，不持有 USDC，不提交订单，不构成投资建议。</footer>

    <transition name="toast-fade">
      <div v-if="toast" class="vl-toast" :class="`is-${toast.tone}`">{{ toast.text }}</div>
    </transition>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import HomeNavbar from '@/components/home/HomeNavbar.vue'
import LanguageSwitcher from '@/components/LanguageSwitcher.vue'
import { UiBadge, UiButton } from '@/components/ui'
import EChart from '@/components/report/widgets/EChart.vue'
import BinsForecastPanel from '@/components/validation/BinsForecastPanel.vue'
import BinsPositionsTable from '@/components/validation/BinsPositionsTable.vue'
import BetDecisionFunnel from '@/components/validation/BetDecisionFunnel.vue'
import ConfidenceBuckets from '@/components/validation/ConfidenceBuckets.vue'
import EdgeMatrix from '@/components/validation/EdgeMatrix.vue'
import OutcomeBoard from '@/components/validation/OutcomeBoard.vue'
import SettlementWaterfall from '@/components/validation/SettlementWaterfall.vue'
import ValidationModelDebugPanel from '@/components/validation/ValidationModelDebugPanel.vue'
import WeeklyHistoryPanel from '@/components/validation/WeeklyHistoryPanel.vue'
import ModelPicker from '@/components/validation/ModelPicker.vue'
import DecisionSummaryBar from '@/components/validation/DecisionSummaryBar.vue'
import DataSourceBadge from '@/components/validation/DataSourceBadge.vue'
import MarketTickerStrip from '@/components/market/MarketTickerStrip.vue'
import BtcCandlestickChart from '@/components/market/BtcCandlestickChart.vue'
import { validationApi } from '@/api/validation'
import { marketApi } from '@/api/market'

const cycle = ref(null)
const kpi = ref(null)
const allPositions = ref([])
const equityCurve = ref([])
const ticker = ref(null)
const ohlcvRows = ref([])
const polymarket = ref({ current: null, history: [], source_status: {} })
const snapshotting = ref(false)
const posFilter = ref('all')
const lookback = ref('1y')
const tickTimer = ref(null)
const marketTimer = ref(null)
const appTimer = ref(null)
const polyTimer = ref(null)
const models = ref([])
const modelsLoading = ref(false)
const selectedModel = ref(null)
const toast = ref(null)
let toastTimer = null
const activeTab = ref('forecast')
const tabs = [
  { key: 'forecast', label: '概率分布' },
  { key: 'edge', label: 'Edge & 下注' },
  { key: 'positions', label: '持仓记录' },
  { key: 'performance', label: '绩效与结算' },
  { key: 'polymarket', label: 'Polymarket 历史' }
]

const chartInterval = computed(() => {
  if (lookback.value === '7d') return '1h'
  if (lookback.value === '60d') return '4h'
  return '1d'
})
const forecastBins = computed(() => {
  if (cycle.value?.latest_forecast?.bins_probs) return cycle.value.latest_forecast.bins_probs
  if (cycle.value?.bins) return cycle.value.bins.map(b => ({ ...b, prob: 0, count: 0 }))
  return []
})
const baselineProb = computed(() => forecastBins.value.length ? 1 / forecastBins.value.length : null)
const modelMeta = computed(() => {
  const fc = cycle.value?.latest_forecast
  return fc?.payload?.model_meta || fc?.model_meta || null
})
const polymarketStatus = computed(() => {
  const st = polymarket.value?.source_status || {}
  if (st.ok === false || st.status === 'down') return 'down'
  if (st.stale || st.status === 'stale') return 'stale'
  return polymarket.value?.current?.outcomes?.length ? 'live' : 'down'
})
const polymarketDetail = computed(() => {
  const n = polymarket.value?.current?.outcomes?.length || 0
  return n ? `${n} outcomes` : 'odds unavailable'
})
const filteredPositions = computed(() => {
  if (posFilter.value === 'all') return allPositions.value
  if (posFilter.value === 'open') return allPositions.value.filter(p => p.is_hit == null)
  return allPositions.value.filter(p => p.is_hit != null)
})
const currentCyclePositions = computed(() => {
  const cid = cycle.value?.cycle_id
  const cycleRows = cycle.value?.positions || []
  if (!cid) return cycleRows
  const rows = allPositions.value.filter(p => p.cycle_id === cid)
  return rows.length ? rows : cycleRows
})
const cycleStatusClass = computed(() => {
  if (!cycle.value) return 'loading'
  if (cycle.value.status === 'settled') return 'settled'
  const ttr = cycle.value.time_to_resolve_seconds || 0
  return ttr <= 0 ? 'closing' : 'open'
})
const countdown = computed(() => {
  if (!cycle.value) return '—'
  const s = Math.max(0, cycle.value.time_to_resolve_seconds || 0)
  const d = Math.floor(s / 86400)
  const h = Math.floor((s % 86400) / 3600)
  const m = Math.floor((s % 3600) / 60)
  return `${d}d ${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`
})
const equityOption = computed(() => ({
  backgroundColor: '#FFFFFF',
  grid: { top: 20, right: 20, bottom: 36, left: 64 },
  tooltip: { trigger: 'axis', backgroundColor: '#FFFFFF', borderColor: '#E5E7EB', textStyle: { color: '#0F172A' } },
  xAxis: { type: 'time', axisLine: { lineStyle: { color: '#CBD5E1' } }, axisLabel: { color: '#64748B' } },
  yAxis: { type: 'value', name: 'Equity (USD)', scale: true, nameTextStyle: { color: '#64748B' }, axisLabel: { color: '#64748B' }, splitLine: { lineStyle: { color: '#EEF2F7' } } },
  series: [{ type: 'line', smooth: true, name: 'FinRex Weekly', data: equityCurve.value.map(p => [p.ts, p.equity]), lineStyle: { width: 2, color: '#111827' }, areaStyle: { opacity: 0.1, color: '#111827' } }]
}))

async function loadAppData () {
  try {
    const [cyc, k, pos, eq] = await Promise.all([
      validationApi.cycleCurrent('BTC'), validationApi.kpi('BTC'), validationApi.positions('BTC', 'all'), validationApi.equityCurve('BTC')
    ])
    cycle.value = cyc
    kpi.value = k
    allPositions.value = pos?.items || []
    equityCurve.value = eq?.points || []
  } catch (err) { console.warn('validation load failed', err) }
}
async function loadMarketData () {
  try {
    const [tk, klines] = await Promise.all([
      marketApi.btcTicker(), marketApi.btcOhlcv({ interval: chartInterval.value, lookback: lookback.value })
    ])
    ticker.value = tk
    ohlcvRows.value = klines?.rows || []
  } catch (err) { console.warn('market load failed', err) }
}
async function loadPolymarket () {
  try { polymarket.value = await validationApi.polymarketWeekly({ mode: 'history', limit: 10 }) } catch (err) { console.warn('polymarket load failed', err) }
}
async function loadModels () {
  modelsLoading.value = true
  try {
    const data = await validationApi.models()
    models.value = data?.items || []
    if (!selectedModel.value) {
      const fromForecast = cycle.value?.latest_forecast?.model_family
      selectedModel.value = fromForecast || models.value[0]?.key || null
    }
  } catch (err) { console.warn('models load failed', err) } finally { modelsLoading.value = false }
}
function onModelChange () { /* selection applied on next snapshot run */ }
function showToast (text, tone = 'info') {
  toast.value = { text, tone }
  if (toastTimer) clearTimeout(toastTimer)
  toastTimer = setTimeout(() => { toast.value = null }, 4000)
}
async function runSnapshot (placeBets) {
  snapshotting.value = true
  try {
    cycle.value = await validationApi.snapshot({ symbol: 'BTC', place_bets: placeBets, model_family: selectedModel.value })
    await loadAppData()
    showToast(placeBets ? 'Snapshot 完成并已下注' : '预测已刷新', 'success')
  } catch (err) { showToast('Snapshot 失败：' + (err?.message || err), 'error') } finally { snapshotting.value = false }
}
async function setLookback (value) {
  lookback.value = value
  await loadMarketData()
}
function formatNum (v, digits = 2) { return v == null || isNaN(v) ? '—' : Number(v).toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits }) }
function formatRange (a, b) {
  if (!a || !b) return '—'
  const fa = new Date(a), fb = new Date(b)
  return `${fa.toISOString().slice(5, 10)} - ${fb.toISOString().slice(5, 10)} UTC`
}

onMounted(async () => {
  await Promise.all([loadAppData(), loadMarketData(), loadPolymarket()])
  await loadModels()
  tickTimer.value = setInterval(() => {
    if (cycle.value?.time_to_resolve_seconds != null) cycle.value.time_to_resolve_seconds = Math.max(0, cycle.value.time_to_resolve_seconds - 1)
  }, 1000)
  marketTimer.value = setInterval(loadMarketData, 5000)
  appTimer.value = setInterval(loadAppData, 60000)
  polyTimer.value = setInterval(() => { if (!document.hidden) loadPolymarket() }, 60000)
  document.addEventListener('visibilitychange', onVisibilityChange)
})
function onVisibilityChange () { if (!document.hidden) { loadPolymarket(); loadAppData() } }
onBeforeUnmount(() => {
  if (tickTimer.value) clearInterval(tickTimer.value)
  if (marketTimer.value) clearInterval(marketTimer.value)
  if (appTimer.value) clearInterval(appTimer.value)
  if (polyTimer.value) clearInterval(polyTimer.value)
  if (toastTimer) clearTimeout(toastTimer)
  document.removeEventListener('visibilitychange', onVisibilityChange)
})
</script>

<style scoped>
.validation-lab { min-height: 100vh; background: #F3F5F7; color: #0F172A; }
.desk-head { display: grid; grid-template-columns: minmax(0, 1fr) 380px; gap: 18px; padding: 18px 24px; background: #FFFFFF; border-bottom: 1px solid #E5E7EB; }
.desk-head h1 { margin: 8px 0 6px; font-size: 28px; line-height: 1.05; color: #0F172A; letter-spacing: 0; }
.desk-head p { margin: 0; color: #64748B; font-size: 14px; max-width: 860px; line-height: 1.55; }
.control-band { display: flex; justify-content: space-between; align-items: flex-end; gap: 16px; flex-wrap: wrap; padding: 14px 16px 0; max-width: 1760px; margin: 0 auto; }
.control-left { display: flex; align-items: flex-end; gap: 12px; flex-wrap: wrap; }
.control-actions { display: flex; gap: 8px; }
.source-row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.summary-bar { display: block; max-width: 1760px; margin: 12px auto 0; padding: 0 16px; }
.cycle-card { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; border: 1px solid #E5E7EB; border-left: 3px solid #111827; border-radius: 6px; padding: 12px; background: #FFFFFF; }
.cycle-card.open { border-left-color: #16A34A; }
.cycle-card.closing { border-left-color: #F59E0B; }
.cycle-card.settled { border-left-color: #64748B; }
.cycle-card span { display: block; color: #94A3B8; font-size: 11px; }
.cycle-card strong { display: block; margin-top: 3px; color: #0F172A; font-size: 12px; font-variant-numeric: tabular-nums; }
.desk-grid { display: grid; grid-template-columns: minmax(0, 1fr) 430px; gap: 12px; padding: 12px 16px 0; max-width: 1760px; margin: 0 auto; }
.desk-main { display: grid; grid-template-columns: minmax(0, 1fr) 430px; gap: 12px; padding: 12px 16px 0; max-width: 1760px; margin: 0 auto; align-items: start; }
.chart-zone, .desk-panel { background: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 6px; padding: 12px; min-width: 0; }
.chart-zone { padding-bottom: 4px; }
.right-rail { display: flex; flex-direction: column; gap: 12px; min-width: 0; }
.panel-head { display: flex; justify-content: space-between; gap: 12px; align-items: center; min-height: 34px; margin-bottom: 10px; }
.panel-head.compact { margin-bottom: 10px; }
.panel-head h3 { margin: 0 0 3px; color: #0F172A; font-size: 14px; font-weight: 800; }
.panel-head span { color: #94A3B8; font-size: 12px; }
.segmented { display: inline-flex; gap: 2px; padding: 3px; border: 1px solid #E5E7EB; border-radius: 6px; background: #F8FAFC; flex: none; }
.segmented button { border: none; background: transparent; min-width: 44px; padding: 6px 10px; border-radius: 4px; cursor: pointer; color: #64748B; font-size: 12px; font-weight: 700; }
.segmented button.active { background: #111827; color: #FFFFFF; }
.kpis { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 10px; }
.kpis div { padding: 10px 12px; border: 1px solid #EEF1F5; border-radius: 6px; background: #FFFFFF; }
.kpis span { color: #94A3B8; font-size: 11px; }
.kpis strong { display: block; margin-top: 4px; color: #0F172A; font-size: 18px; font-variant-numeric: tabular-nums; }
.pos { color: #16A34A; }
.neg { color: #DC2626; }
.empty { padding: 28px; text-align: center; color: #94A3B8; font-size: 13px; }
.vl-tabs { display: flex; gap: 4px; flex-wrap: wrap; max-width: 1760px; margin: 18px auto 0; padding: 0 16px; border-bottom: 1px solid #E5E7EB; }
.vl-tabs button { border: none; background: transparent; padding: 10px 16px; cursor: pointer; color: #64748B; font-size: 13px; font-weight: 700; border-bottom: 2px solid transparent; margin-bottom: -1px; }
.vl-tabs button:hover { color: #0F172A; }
.vl-tabs button.active { color: #0F172A; border-bottom-color: #111827; }
.tab-content { max-width: 1760px; margin: 0 auto; padding: 12px 16px 0; }
.tab-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; align-items: start; }
.tab-grid.one { grid-template-columns: 1fr; }
.tab-grid .kpis { grid-column: 1 / -1; }
.vl-foot { padding: 14px 28px; border-top: 1px solid #E5E7EB; color: #94A3B8; text-align: center; font-size: 12px; background: #FFFFFF; }
.vl-toast { position: fixed; right: 20px; bottom: 20px; z-index: 50; padding: 12px 16px; border-radius: 8px; font-size: 13px; font-weight: 700; color: #FFFFFF; box-shadow: 0 8px 24px rgba(15, 23, 42, .18); }
.vl-toast.is-success { background: #16A34A; }
.vl-toast.is-error { background: #DC2626; }
.vl-toast.is-info { background: #0F172A; }
.toast-fade-enter-active, .toast-fade-leave-active { transition: opacity .25s ease, transform .25s ease; }
.toast-fade-enter-from, .toast-fade-leave-to { opacity: 0; transform: translateY(8px); }
@media (max-width: 1180px) {
  .desk-head, .desk-main { grid-template-columns: 1fr; }
  .tab-grid { grid-template-columns: 1fr; }
  .kpis { grid-template-columns: repeat(2, 1fr); }
}
</style>
