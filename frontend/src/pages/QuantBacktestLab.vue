<template>
  <div class="quant-page">
    <header class="quant-page__bar">
      <button class="back" @click="$router.push('/')">&lt; {{ t('common.back') }}</button>
      <h1>{{ t('quant.backtest.title') }}</h1>
      <span class="status">{{ t('quant.backtest.status') }}</span>
    </header>

    <section class="control-row">
      <div class="control">
        <label>Symbol</label>
        <select v-model="form.symbol">
          <option v-for="s in symbols" :key="s.symbol" :value="s.symbol">{{ s.display || s.symbol }}</option>
        </select>
      </div>
      <div class="control">
        <label>Model</label>
        <select v-model="form.model_family">
          <option v-for="m in modelOptions" :key="m.value" :value="m.value">{{ m.label }}</option>
        </select>
      </div>
      <div class="control">
        <label>Start</label>
        <input type="date" v-model="form.start" />
      </div>
      <div class="control">
        <label>End</label>
        <input type="date" v-model="form.end" />
      </div>
      <div class="control">
        <label>Horizon (d)</label>
        <input type="number" min="1" max="20" v-model.number="form.horizon" />
      </div>
      <div class="control">
        <label>Initial Cash</label>
        <input type="number" min="100" v-model.number="form.initial_cash" />
      </div>
      <div class="control">
        <label>Swarm Source</label>
        <select v-model="form.swarm_source_mode">
          <option value="auto">Auto</option>
          <option value="fmp_only">FMP Only</option>
          <option value="oasis_only">OASIS Only</option>
        </select>
      </div>
      <div class="control" v-if="form.swarm_source_mode !== 'fmp_only'">
        <label>OASIS Sim ID</label>
        <input v-model.trim="form.oasis_simulation_id" placeholder="optional" />
      </div>
      <div class="control">
        <label>Fee (bps)</label>
        <input type="number" min="0" max="200" step="0.5" v-model.number="form.fee_bps" />
      </div>
      <div class="control">
        <label>Max Exposure</label>
        <input type="number" min="0" max="1" step="0.05" v-model.number="form.exposure" />
      </div>
      <div class="control">
        <label>Signal Threshold</label>
        <input type="number" min="0" max="1" step="0.01" v-model.number="form.signal_threshold" />
      </div>
      <label class="control checkbox-control">
        <span>Shorts</span>
        <input type="checkbox" v-model="form.allow_short" />
      </label>
      <div class="control">
        <label>Train Days</label>
        <input type="number" min="30" max="2000" step="10" v-model.number="form.train_days" />
      </div>
      <div class="control">
        <label>Test Days</label>
        <input type="number" min="10" max="730" step="5" v-model.number="form.test_days" />
      </div>
      <div class="control">
        <label>Step Days</label>
        <input type="number" min="5" max="365" step="5" v-model.number="form.step_days" />
      </div>
      <button class="primary" @click="runBacktest" :disabled="loading">
        <span v-if="loading">{{ t('common.loading') }}</span>
        <span v-else>{{ t('quant.backtest.runCTA') }}</span>
      </button>
    </section>

    <section v-if="error" class="error-banner">{{ error }}</section>

    <section v-if="result" class="results">
      <div class="quality-strip" :class="{warning: swarmQuality.constant_signal_warning}">
        <span>Market <b>{{ marketQuality.data_source || '-' }}</b></span>
        <span>Model <b>{{ modelFamilyLabel }}</b></span>
        <span>Price Engine <b>{{ priceModelQuality.engine || '-' }}</b></span>
        <span>Calib N <b>{{ priceModelQuality.calibration_sample_count ?? 0 }}</b></span>
        <span>Price MAE <b>{{ formatNum(priceModelQuality.mae, 2) }}</b></span>
        <span>Coverage <b>{{ formatPct(priceModelQuality.coverage_80) }}</b></span>
        <span>Market Cache <b>{{ yesNo(marketQuality.cache_hit) }}</b></span>
        <span>Market Rows <b>{{ marketQuality.rows ?? 0 }}</b></span>
        <span>Swarm Source <b>{{ swarmQuality.source_mode || '-' }}</b></span>
        <span>News <b>{{ newsEndpointLabel }}</b></span>
        <span>News Cache <b>{{ yesNo(swarmQuality.news_cache_hit) }}</b></span>
        <span>Coverage <b>{{ formatPct(swarmQuality.coverage_ratio) }}</b></span>
        <span>Effective N <b>{{ swarmQuality.effective_rows ?? 0 }}</b></span>
        <span>OASIS <b>{{ swarmQuality.oasis_rows ?? 0 }}</b></span>
        <span>FMP <b>{{ swarmQuality.fmp_rows ?? 0 }}</b></span>
        <span>Variants <b>{{ compactList(swarmQuality.news_symbol_variants) }}</b></span>
        <span v-if="swarmQuality.fallback_reason">Fallback <b>{{ swarmQuality.fallback_reason }}</b></span>
        <span v-if="swarmQuality.constant_signal_warning">Swarm data insufficient</span>
      </div>
      <div class="metrics-row">
        <div class="metric-card" v-for="(p, key) in metricCards" :key="key" :class="{highlight: key === 'hybrid'}">
          <div class="metric-card__head">{{ p.label }}</div>
          <ul>
            <li><span>Sharpe</span><b>{{ formatNum(p.data.sharpe) }}</b></li>
            <li><span>Sortino</span><b>{{ formatNum(p.data.sortino) }}</b></li>
            <li><span>Ann.Return</span><b>{{ formatPct(p.data.ann_return) }}</b></li>
            <li><span>Alpha</span><b>{{ formatPct(p.data.alpha) }}</b></li>
            <li><span>Beta</span><b>{{ formatNum(p.data.beta, 3) }}</b></li>
            <li><span>Ann.Vol</span><b>{{ formatPct(p.data.ann_vol) }}</b></li>
            <li><span>MaxDD</span><b>{{ formatPct(p.data.max_drawdown) }}</b></li>
            <li><span>Hit</span><b>{{ formatPct(p.data.hit_ratio) }}</b></li>
            <li><span>N</span><b>{{ p.data.n_periods }}</b></li>
            <li v-if="key === 'swarm'"><span>Effective N</span><b>{{ swarmQuality.effective_rows ?? 0 }}</b></li>
          </ul>
        </div>
      </div>

      <div class="chart-grid">
        <div class="chart-card chart-card--wide">
          <h3>Multi-Indicator Backtest View</h3>
          <QuantIndicatorBacktestChart :points="chartPoints" :trades="result.trades || []" :symbol="result.symbol" height="720px" />
        </div>
        <div class="chart-card summary-card">
          <h3>Summary</h3>
          <ul class="summary-list">
            <li><span>Run ID</span><b>{{ result.run_id }}</b></li>
            <li><span>Symbol</span><b>{{ result.symbol }}</b></li>
            <li><span>Model</span><b>{{ modelFamilyLabel }}</b></li>
            <li><span>Price Engine</span><b>{{ priceModelQuality.engine || '-' }}</b></li>
            <li><span>Calibration Samples</span><b>{{ priceModelQuality.calibration_sample_count ?? 0 }}</b></li>
            <li><span>Initial</span><b>{{ formatMoney(result.summary?.initial_cash) }}</b></li>
            <li><span>Final</span><b>{{ formatMoney(result.summary?.final_value) }}</b></li>
            <li><span>Return</span><b>{{ formatPct(result.summary?.total_return) }}</b></li>
            <li><span>Alpha</span><b>{{ formatPct(result.summary?.alpha) }}</b></li>
            <li><span>Beta</span><b>{{ formatNum(result.summary?.beta, 3) }}</b></li>
            <li><span>Ann.Vol</span><b>{{ formatPct(result.summary?.ann_vol) }}</b></li>
            <li><span>Calmar</span><b>{{ formatNum(result.summary?.calmar, 3) }}</b></li>
            <li><span>Profit Factor</span><b>{{ formatNum(result.summary?.profit_factor, 2) }}</b></li>
            <li><span>Exposure</span><b>{{ formatPct(result.summary?.exposure) }}</b></li>
            <li><span>Turnover Proxy</span><b>{{ formatPct(result.summary?.turnover_proxy) }}</b></li>
            <li><span>Trades</span><b>{{ result.summary?.num_trades || 0 }}</b></li>
            <li><span>Closed Trades</span><b>{{ result.summary?.closed_trades || 0 }}</b></li>
            <li><span>Avg Holding Days</span><b>{{ formatNum(result.summary?.avg_holding_days, 1) }}</b></li>
            <li><span>Closed P/L</span><b>{{ formatMoney(result.summary?.total_closed_pnl) }}</b></li>
            <li><span>IC mean</span><b>{{ formatNum(result.performance?.ic?.ic_mean) }}</b></li>
          </ul>
        </div>
        <div class="chart-card chart-card--wide">
          <h3>Trade Details</h3>
          <div v-if="!tradeRows.length" class="empty-table">No executed trades for this run.</div>
          <div v-else class="trade-table">
            <table>
              <thead>
                <tr>
                  <th>Status</th>
                  <th>Side</th>
                  <th>Entry</th>
                  <th>Exit / Mark</th>
                  <th class="num">Units</th>
                  <th class="num">Entry Px</th>
                  <th class="num">Exit Px</th>
                  <th class="num">Fees</th>
                  <th class="num">Gross P/L</th>
                  <th class="num">Net P/L</th>
                  <th class="num">Bars</th>
                  <th class="num">Entry Sig</th>
                  <th class="num">Entry pMeta</th>
                  <th class="num">Entry pSwarm</th>
                  <th class="num">Exit Sig</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(row, idx) in tradeRows" :key="idx">
                  <td><span class="trade-tag" :class="`trade-tag--${row.status || 'open'}`">{{ row.status || 'open' }}</span></td>
                  <td>{{ row.side || '-' }}</td>
                  <td>{{ shortDate(row.entry_ts) }}</td>
                  <td>{{ shortDate(row.exit_ts || row.mark_ts) }}</td>
                  <td class="num">{{ formatNum(row.units, 6) }}</td>
                  <td class="num">{{ formatMoney(row.entry_price) }}</td>
                  <td class="num">{{ formatMoney(row.exit_price || row.mark_price) }}</td>
                  <td class="num">{{ formatMoney((row.entry_fee || 0) + (row.exit_fee || 0)) }}</td>
                  <td class="num" :class="tone(row.gross_pnl ?? row.unrealized_pnl)">{{ formatMoney(row.gross_pnl ?? row.unrealized_pnl) }}</td>
                  <td class="num" :class="tone(row.net_pnl ?? row.unrealized_pnl)">{{ formatMoney(row.net_pnl ?? row.unrealized_pnl) }}</td>
                  <td class="num">{{ row.holding_bars ?? '-' }}</td>
                  <td class="num">{{ formatNum(row.entry_signal, 4) }}</td>
                  <td class="num">{{ formatNum(row.entry_p_meta, 4) }}</td>
                  <td class="num">{{ formatNum(row.entry_p_swarm, 4) }}</td>
                  <td class="num">{{ formatNum(row.exit_signal, 4) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <!-- ====== Professional analytics (additive — original cards untouched) ====== -->
      <section class="pro-section">
        <BacktestProMetricsBar :perf="hybridPerf" />
        <div class="pro-grid">
          <BacktestUnderwaterChart :series="proSeries.drawdown_series" />
          <BacktestRollingMetricsChart
            :rolling-sharpe="proSeries.rolling_sharpe"
            :rolling-vol="proSeries.rolling_vol"
          />
          <BacktestMonthlyHeatmap :rows="proSeries.monthly_returns" class="span-2" />
          <BacktestTradeDistribution :distributions="proDistributions" class="span-2" />
        </div>
      </section>
    </section>

    <section v-else class="empty-state">
      <p>{{ t('quant.backtest.heroDesc') }}</p>
      <div class="hero__chips">
        <span class="chip" v-for="s in symbols.slice(0, 6)" :key="s.symbol">{{ s.symbol }}</span>
      </div>
      <p class="muted">{{ t('quant.backtest.placeholderNote') }}</p>
    </section>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { quantApi } from '@/api/quant'
import QuantIndicatorBacktestChart from '@/components/backtest/QuantIndicatorBacktestChart.vue'
import BacktestProMetricsBar from '@/components/backtest/BacktestProMetricsBar.vue'
import BacktestUnderwaterChart from '@/components/backtest/BacktestUnderwaterChart.vue'
import BacktestRollingMetricsChart from '@/components/backtest/BacktestRollingMetricsChart.vue'
import BacktestMonthlyHeatmap from '@/components/backtest/BacktestMonthlyHeatmap.vue'
import BacktestTradeDistribution from '@/components/backtest/BacktestTradeDistribution.vue'

const { t } = useI18n()
const route = useRoute()
const symbols = ref([])
const result = ref(null)
const loading = ref(false)
const error = ref('')
const modelOptions = [
  { value: 'price_point_calibrated_ml', label: 'Price Forecast (Calibrated ML)' },
  { value: 'two_tower', label: 'Two-Tower Hybrid Alpha' },
  { value: 'financial_forecast', label: 'Legacy Financial Signal' }
]

const form = reactive({
  symbol: 'BTC-USDT',
  start: '',
  end: '',
  horizon: 5,
  initial_cash: 10000,
  swarm_source_mode: 'auto',
  oasis_simulation_id: '',
  sentiment_sources: ['fmp'],
  fee_bps: 5,
  exposure: 0.95,
  allow_short: true,
  signal_threshold: 0,
  train_days: 480,
  test_days: 120,
  step_days: 30,
  model_family: 'price_point_calibrated_ml'
})

const metricCards = computed(() => {
  if (!result.value) return {}
  const p = result.value.performance || {}
  return {
    market: { label: 'Market-Only', data: p.market_only || {} },
    swarm: { label: 'Swarm-Only', data: p.swarm_only || {} },
    hybrid: { label: 'Hybrid', data: p.hybrid || {} }
  }
})

const chartPoints = computed(() => {
  const points = result.value?.chart_points
  if (Array.isArray(points) && points.length) return points
  return buildLegacyChartPoints(result.value?.equity_curve || [])
})

const swarmQuality = computed(() => result.value?.data_quality?.swarm || {})
const marketQuality = computed(() => result.value?.data_quality?.market || {})
const priceModelQuality = computed(() => result.value?.data_quality?.price_forecast_model || {})
const modelFamilyLabel = computed(() => {
  const family = result.value?.config?.model_family || form.model_family
  return modelOptions.find(item => item.value === family)?.label || family || '-'
})
const newsEndpointLabel = computed(() => compactList(swarmQuality.value.news_endpoint_family))
const tradeRows = computed(() => {
  const rows = result.value?.trade_log
  if (Array.isArray(rows) && rows.length) return rows
  return []
})

const hybridPerf = computed(() => result.value?.performance?.hybrid || {})
const proSeries = computed(() => result.value?.pro_series || {
  drawdown_series: [], rolling_sharpe: [], rolling_vol: [], monthly_returns: []
})
const proDistributions = computed(() => result.value?.pro_distributions || {
  pnl_hist: [], duration_hist: [], by_side: {}
})

function defaultDates () {
  const end = new Date()
  const start = new Date(end.getTime() - 730 * 24 * 3600 * 1000)
  const fmt = (d) => d.toISOString().slice(0, 10)
  form.end = fmt(end)
  form.start = fmt(start)
}

async function loadSymbols () {
  try {
    const data = await quantApi.listSymbols()
    symbols.value = data.symbols || []
    if (symbols.value.length && !symbols.value.find(s => s.symbol === form.symbol)) {
      form.symbol = symbols.value[0].symbol
    }
  } catch (e) {
    symbols.value = [
      { symbol: 'BTC-USDT', display: 'BTC-USDT' },
      { symbol: 'ETH-USDT', display: 'ETH-USDT' },
      { symbol: 'AAPL', display: 'AAPL' },
      { symbol: '3033.HK', display: '3033.HK' },
      { symbol: '000300.SH', display: '000300.SH' }
    ]
  }
}

function applyPrefill () {
  const raw = sessionStorage.getItem('finrex_quant_backtest_prefill')
  const parsed = raw ? safeJson(raw) : null
  const queryModel = normalizeModelFamily(route.query.model_family || route.query.model)
  if (parsed) {
    const symbol = normalizeQuantSymbol(parsed.symbol || parsed.pair)
    if (symbol) form.symbol = symbol
    if (parsed.horizon_days || parsed.horizon) form.horizon = parseHorizonDays(parsed.horizon_days || parsed.horizon, form.horizon)
    if (parsed.oasis_simulation_id || parsed.simulation_id) form.oasis_simulation_id = parsed.oasis_simulation_id || parsed.simulation_id
    if (parsed.model_family || parsed.model_kind) form.model_family = normalizeModelFamily(parsed.model_family || parsed.model_kind) || form.model_family
  }
  if (queryModel) form.model_family = queryModel
}

async function runBacktest () {
  error.value = ''
  loading.value = true
  try {
    const payload = { ...form, sentiment_sources: ['fmp'] }
    if (!payload.oasis_simulation_id) delete payload.oasis_simulation_id
    result.value = await quantApi.createRun(payload)
  } catch (e) {
    error.value = e?.response?.data?.error || e.message || 'Backtest failed'
  } finally {
    loading.value = false
  }
}

function buildLegacyChartPoints (points) {
  return (points || []).map(p => {
    const close = p.price ?? p.close ?? p.value
    return {
      ts: p.ts,
      open: close,
      high: close,
      low: close,
      close,
      volume: null,
      cash: p.cash,
      value: p.value,
      position_side: p.position_side || 'flat',
      position_units: p.position_units || 0
    }
  })
}

function formatMoney (v) {
  if (v == null) return '-'
  return Number(v).toLocaleString(undefined, { maximumFractionDigits: 2 })
}
function formatPct (v) {
  if (v == null) return '-'
  return (Number(v) * 100).toFixed(2) + '%'
}
function formatNum (v, digits = 4) {
  if (v == null) return '-'
  return Number(v).toFixed(digits)
}
function yesNo (v) {
  return v == null ? '-' : (v ? 'Yes' : 'No')
}
function compactList (items) {
  if (!Array.isArray(items) || !items.length) return '-'
  const first = items.slice(0, 3).join(', ')
  return items.length > 3 ? `${first} +${items.length - 3}` : first
}
function shortDate (v) {
  return v ? String(v).replace('T', ' ').slice(0, 16) : '-'
}
function tone (v) {
  return Number(v || 0) >= 0 ? 'pos' : 'neg'
}

function safeJson (raw) {
  try { return JSON.parse(raw) } catch (_e) { return null }
}

function normalizeQuantSymbol (value) {
  const raw = String(value || '').trim().toUpperCase()
  if (!raw) return ''
  const aliases = {
    BTC: 'BTC-USDT',
    BTCUSD: 'BTC-USDT',
    BTCUSDT: 'BTC-USDT',
    'BTC-USD': 'BTC-USDT',
    ETH: 'ETH-USDT',
    ETHUSD: 'ETH-USDT',
    ETHUSDT: 'ETH-USDT',
    'ETH-USD': 'ETH-USDT'
  }
  const candidate = aliases[raw] || raw
  const exists = symbols.value.some(item => item.symbol === candidate)
  return exists ? candidate : candidate
}

function normalizeModelFamily (value) {
  const raw = String(value || '').trim().toLowerCase()
  if (['two_tower', 'dual_tower', 'hybrid_alpha', 'market_swarm', 'legacy'].includes(raw)) return 'two_tower'
  if (['financial_forecast', 'financial_sentiment'].includes(raw)) return 'financial_forecast'
  if ([
    'price_point_calibrated_ml',
    'price_point_ml',
    'calibrated_ml',
    'calibrated_price_ml',
    'price_point_calibrated',
    'price_forecast_ml',
    'price_forecast',
    'forecast'
  ].includes(raw)) return 'price_point_calibrated_ml'
  return ''
}

function parseHorizonDays (value, fallback) {
  const raw = String(value || '').trim().toLowerCase()
  const map = { '1d': 1, daily: 1, '5d': 5, '1w': 7, week: 7, '7d': 7, '2w': 14 }
  if (map[raw]) return map[raw]
  const parsed = Number(raw)
  return Number.isFinite(parsed) ? Math.max(1, Math.min(20, parsed)) : fallback
}

onMounted(() => {
  defaultDates()
  loadSymbols().then(applyPrefill)
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
  margin-left: auto; font-family: var(--f-mono); font-size: 11px;
  letter-spacing: .14em; color: var(--c-text-subtle);
}
.back {
  background: transparent; border: 1px solid var(--c-border);
  padding: 4px 10px; font-size: 12px; cursor: pointer; border-radius: 4px;
}
.control-row {
  display: flex; gap: var(--s-3); flex-wrap: wrap; align-items: flex-end;
  padding: var(--s-5) var(--s-6); border-bottom: 1px solid var(--c-border);
  background: var(--c-bg-soft);
}
.control { display: flex; flex-direction: column; gap: 4px; }
.control label {
  font-family: var(--f-mono); font-size: 10px;
  letter-spacing: .14em; text-transform: uppercase; color: var(--c-text-subtle);
}
.control select, .control input {
  padding: 6px 10px; border: 1px solid var(--c-border); border-radius: 4px;
  background: var(--c-bg); font-size: 13px; min-width: 140px;
}
.checkbox-control {
  min-height: 54px;
  justify-content: flex-end;
  align-items: center;
  color: var(--c-text-subtle);
  font-family: var(--f-mono);
  font-size: 10px;
  letter-spacing: .14em;
  text-transform: uppercase;
}
.checkbox-control input {
  min-width: auto;
  width: 18px;
  min-height: 18px;
}
.primary {
  padding: 10px 18px; background: var(--c-text); color: var(--c-bg);
  border: none; font-weight: 700; font-size: 13px;
  letter-spacing: .08em; cursor: pointer; border-radius: 4px;
}
.primary:disabled { opacity: .5; cursor: not-allowed; }
.error-banner {
  margin: var(--s-4) var(--s-6); padding: var(--s-3); border: 1px solid #e54;
  background: rgba(238, 85, 68, .08); color: #e54; font-size: 13px;
  border-radius: 4px;
}
.results, .empty-state { padding: var(--s-6); }
.quality-strip {
  display: flex; flex-wrap: wrap; gap: 10px 18px; align-items: center;
  margin-bottom: var(--s-4); padding: 10px 12px;
  border: 1px solid var(--c-border); border-radius: 4px; background: var(--c-bg-soft);
  font-size: 12px; color: var(--c-text-muted);
}
.quality-strip b { color: var(--c-text); font-family: var(--f-mono); margin-left: 4px; }
.quality-strip.warning { border-color: #e54; background: rgba(238, 85, 68, .08); color: #e54; }
.quality-strip.warning b { color: #e54; }
.metrics-row {
  display: grid; grid-template-columns: repeat(3, 1fr);
  gap: var(--s-4); margin-bottom: var(--s-5);
}
.metric-card {
  border: 1px solid var(--c-border); border-radius: var(--r-md);
  background: var(--c-bg-soft); padding: var(--s-4);
}
.metric-card.highlight {
  background: var(--c-text); color: var(--c-bg); border-color: var(--c-text);
}
.metric-card__head {
  font-family: var(--f-mono); font-size: 11px;
  letter-spacing: .14em; margin-bottom: var(--s-3);
  text-transform: uppercase;
}
.metric-card ul { list-style: none; padding: 0; margin: 0; }
.metric-card li {
  display: flex; justify-content: space-between;
  padding: 4px 0; font-size: 12px;
}
.metric-card li span { opacity: .7; }
.metric-card li b { font-family: var(--f-mono); }
.chart-grid {
  display: grid; grid-template-columns: minmax(0, 1fr) 340px;
  gap: var(--s-4);
}
.chart-card {
  min-width: 0;
  border: 1px solid var(--c-border); border-radius: var(--r-md);
  background: var(--c-bg-soft); padding: var(--s-4);
}
.chart-card--wide { grid-column: 1 / -1; }
.summary-card { grid-column: 1 / -1; max-width: 520px; }
.chart-card h3 {
  margin: 0 0 var(--s-3); font-size: 12px; font-family: var(--f-mono);
  letter-spacing: .12em; text-transform: uppercase; color: var(--c-text-muted);
}
.summary-list { list-style: none; padding: 0; margin: 0; }
.summary-list li {
  display: flex; justify-content: space-between; gap: var(--s-4);
  padding: 6px 0; border-bottom: 1px dashed var(--c-border);
  font-size: 13px;
}
.summary-list li:last-child { border-bottom: none; }
.summary-list span { color: var(--c-text-muted); }
.summary-list b { font-family: var(--f-mono); overflow-wrap: anywhere; text-align: right; }
.trade-table { overflow: auto; border: 1px solid var(--c-border); border-radius: 6px; background: var(--c-bg); }
.trade-table table { width: 100%; border-collapse: collapse; font-size: 12px; }
.trade-table th, .trade-table td { padding: 8px 10px; border-bottom: 1px solid var(--c-border); text-align: left; white-space: nowrap; }
.trade-table th { color: var(--c-text-muted); background: var(--c-bg-soft); font-weight: 800; }
.trade-table tr:last-child td { border-bottom: none; }
.num { text-align: right !important; font-variant-numeric: tabular-nums; }
.trade-tag { display: inline-flex; padding: 2px 8px; border-radius: 999px; background: #E5E7EB; color: #334155; font-size: 11px; font-weight: 800; }
.trade-tag--closed { background: #DCFCE7; color: #166534; }
.trade-tag--open { background: #E0E7FF; color: #3730A3; }
.pos { color: #16A34A; }
.neg { color: #DC2626; }
.empty-table { padding: var(--s-5); border: 1px dashed var(--c-border); border-radius: 6px; color: var(--c-text-subtle); text-align: center; font-size: 13px; }
.hero__chips { display: flex; gap: 8px; flex-wrap: wrap; margin: var(--s-4) 0; }
.chip {
  padding: 4px 10px; background: var(--c-bg-soft);
  border: 1px solid var(--c-border); font-family: var(--f-mono);
  font-size: 12px; border-radius: 4px;
}
.empty-state p { color: var(--c-text-muted); max-width: 720px; line-height: 1.7; }
.empty-state .muted { color: var(--c-text-subtle); font-size: 12px; }
.pro-section { margin-top: var(--s-5); display: flex; flex-direction: column; gap: var(--s-4); }
.pro-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--s-4);
}
.pro-grid .span-2 { grid-column: 1 / -1; }
@media (max-width: 900px) {
  .metrics-row, .chart-grid, .pro-grid { grid-template-columns: 1fr; }
  .summary-card { max-width: none; }
}
</style>
