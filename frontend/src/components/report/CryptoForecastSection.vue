<template>
  <section id="s2-crypto" class="crypto-section">
    <header class="section-head">
      <div>
        <span class="kicker">{{ forecastKicker }}</span>
        <h2>{{ forecastTitle }}</h2>
        <p>{{ forecastSubtitle }}</p>
      </div>
      <button type="button" class="refresh-btn" :disabled="loading" @click="loadForecast">
        {{ loading ? '读取中…' : '刷新' }}
      </button>
    </header>

    <!-- 上下文胶囊行 -->
    <div v-if="hasForecast" class="chip-row">
      <span class="chip"><b>交易所</b> {{ exchangeLabel }}</span>
      <span class="chip"><b>标的</b> {{ symbolLabel }}</span>
      <span class="chip"><b>Bar 周期</b> {{ barPeriod }}</span>
      <span class="chip"><b>覆盖窗口</b> {{ priceRangeLabel }}（{{ priceSpark.data.length }} 根）</span>
      <span class="chip"><b>情绪模型</b> {{ sentimentModel }}</span>
    </div>

    <div v-if="loading" class="state-card">正在读取价格预测结果…</div>
    <div v-else-if="error" class="state-card error">{{ error }}</div>
    <div v-else-if="!hasForecast" class="state-card">
      当前 Unified Report 暂无结构化价格预测。请确认本次报告选择了股票或虚拟货币标的，例如 BTC 或 3033.HK。
    </div>

    <article v-else class="forecast-card" :class="directionClass">
      <!-- Row 1: KPI -->
      <div class="kpi-row">
        <div class="kpi-main">
          <span class="asset-label">{{ symbolLabel }} · {{ horizon }}</span>
          <strong class="dir-label" :class="'glow-' + directionKey">
            <span class="dir-icon">{{ directionIcon }}</span> {{ directionLabel }}
          </strong>
          <em>{{ probabilityLabel }} · {{ confidenceLabel }} · 综合分 {{ formatScore(composite) }}</em>
        </div>
        <div class="kpi-stats">
          <div class="stat" :class="'bar-' + directionKey">
            <span>综合分</span>
            <strong :style="{ color: compositeColor }">{{ formatScore(composite) }}</strong>
          </div>
          <div v-if="targetRange" class="stat" :class="'bar-' + directionKey">
            <span>目标区间</span>
            <strong class="mono">{{ targetRange }}</strong>
          </div>
          <div class="stat precise-stat">
            <span>预估/参考价格 · {{ preciseModeLabel }}</span>
            <strong class="mono">
              {{ preciseForecast ? fmtNum(preciseForecast.predicted_price) : '等待数据' }}
              <em v-if="preciseForecast" class="precise-band">[{{ fmtNum(preciseForecast.p10) }} – {{ fmtNum(preciseForecast.p90) }}]</em>
            </strong>
            <small v-if="preciseWarning" class="precise-warning">{{ preciseWarning }}</small>
          </div>
          <div class="stat" :class="'bar-' + directionKey">
            <span>状态</span>
            <strong>{{ status }}</strong>
          </div>
        </div>
        <div class="kpi-gauge">
          <EChart :option="probabilityGaugeOption" height="150px" />
          <div class="kpi-quality">
            <span>行情 {{ dataQuality.market_rows || 0 }}</span>
            <span>舆情 {{ dataQuality.sentiment_count || 0 }}</span>
            <span>新闻 {{ dataQuality.news ? '✓' : '—' }}</span>
            <span>衍生品 {{ dataQuality.derivatives ? '✓' : '—' }}</span>
          </div>
        </div>
      </div>

      <!-- Row 2: Pro Charts (3 等分) -->
      <div class="chart-row">
        <div class="chart-col">
          <EChart v-if="priceSpark.data.length" :option="priceProOption" height="240px" />
          <div v-else class="chart-empty">无价格序列</div>
        </div>
        <div class="chart-col">
          <EChart v-if="sentimentSpark.data.length" :option="sentimentProOption" height="240px" />
          <div v-else class="chart-empty">无情绪时序</div>
        </div>
        <div class="chart-col">
          <FactorBarChart :financial-context="financialContext" height="240px" />
        </div>
      </div>

      <!-- Row 3: Drivers + risks -->
      <div class="evidence-row">
        <div class="drivers-col">
          <h3>关键依据</h3>
          <ul v-if="topDrivers.length" class="driver-list">
            <li v-for="(d, i) in topDrivers" :key="i" :class="driverClass(d)">
              <b>{{ d.tag }}</b>
              <span class="driver-title">
                {{ d.title }}
                <span class="score-bar" :style="{ width: Math.min(100, Math.abs(d.compound) * 100) + '%' }"></span>
              </span>
              <em v-if="d.site">{{ d.site }}</em>
            </li>
          </ul>
          <p v-else class="muted">暂无 driver 数据</p>
        </div>
        <div class="risks-col">
          <h3>⚠ 风险与边界</h3>
          <ul v-if="riskCaveats.length" class="risk-list">
            <li v-for="(r, i) in riskCaveats" :key="i">{{ r }}</li>
          </ul>
          <p v-else class="muted">无风险注释</p>
        </div>
      </div>

      <p v-if="rationale" class="rationale">{{ rationale }}</p>
    </article>
  </section>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { getReport, getReportBySimulation } from '@/api/report'
import EChart from './widgets/EChart.vue'
import FactorBarChart from './widgets/FactorBarChart.vue'
import {
  buildPriceSparkline,
  buildSentimentSparkline,
  extractComposite,
} from './widgets/financialFactorAdapter'

const props = defineProps({
  reportId: { type: String, required: true },
  simulationId: { type: String, default: '' }
})

const loading = ref(false)
const error = ref('')
const report = ref(null)

const financialContext = computed(() => report.value?.financial_context || {})
const forecast = computed(() => financialContext.value?.forecast || {})
const cryptoForecast = computed(() => forecast.value?.crypto_forecast || null)
const hasForecast = computed(() => !!cryptoForecast.value || (forecast.value?.factors && Object.keys(forecast.value.factors).length))
const dataQuality = computed(() => cryptoForecast.value?.data_quality || financialContext.value?.data_quality || {})
const observed = computed(() => financialContext.value?.observed || {})
const inferred = computed(() => financialContext.value?.inferred || {})
const priceFacts = computed(() => observed.value?.price_facts || {})

const targetAsset = computed(() => financialContext.value?.target_asset || {})
const assetType = computed(() => String(targetAsset.value?.type || (cryptoForecast.value ? 'crypto' : 'asset')).toLowerCase())
const forecastKicker = computed(() => assetType.value === 'crypto' ? 'PRICE FORECAST · CRYPTO' : 'PRICE FORECAST')
const forecastTitle = computed(() => {
  const symbol = cryptoForecast.value?.symbol || targetAsset.value?.symbol
  if (symbol) return `${symbol} 价格预测`
  return '事件市场反应预测'
})
const forecastSubtitle = computed(() => {
  const symbol = cryptoForecast.value?.symbol || targetAsset.value?.symbol || '目标资产'
  const horizonLabel = cryptoForecast.value?.horizon || forecast.value?.horizon || '1w'
  return `基于 Step1 已选 FMP/Binance 种子、真实评论、行情技术因子与衍生品数据，展示 ${symbol} ${horizonLabel} 方向、目标区间和参考价格点。`
})

const symbolLabel = computed(() => {
  const cf = cryptoForecast.value
  if (cf?.symbol) return `${cf.symbol}${cf.pair ? ' · ' + cf.pair : ''}`
  const ta = targetAsset.value
  return ta?.symbol ? `${ta.symbol}${ta.market ? ' · ' + ta.market : ''}` : '事件级（无标的）'
})
const exchangeLabel = computed(() => {
  return cryptoForecast.value?.exchange || financialContext.value?.target_asset?.market || 'Binance'
})
const barPeriod = computed(() => {
  return cryptoForecast.value?.bar || cryptoForecast.value?.timeframe || observed.value?.bar || '1d'
})
const sentimentModel = computed(() => inferred.value?.sentiment_model || 'VADER')

const direction = computed(() => String(cryptoForecast.value?.direction || forecast.value?.direction || 'neutral').toLowerCase())
const directionKey = computed(() => {
  if (['bullish', 'up'].includes(direction.value)) return 'up'
  if (['bearish', 'down'].includes(direction.value)) return 'down'
  return 'neutral'
})
const directionClass = computed(() => `dir-${directionKey.value}`)
const directionLabel = computed(() => ({ bullish: '看涨', up: '看涨', bearish: '看跌', down: '看跌', neutral: '中性' }[direction.value] || direction.value))
const directionIcon = computed(() => {
  if (['bullish', 'up'].includes(direction.value)) return '▲'
  if (['bearish', 'down'].includes(direction.value)) return '▼'
  return '◆'
})
const probability = computed(() => {
  const p = cryptoForecast.value?.probability ?? forecast.value?.probability
  return (p == null || Number.isNaN(Number(p))) ? null : Number(p)
})
const probabilityLabel = computed(() => probability.value == null ? '-' : `${(probability.value * 100).toFixed(1)}%`)
const confidenceLabel = computed(() => {
  const c = String(cryptoForecast.value?.confidence || forecast.value?.confidence || 'low').toLowerCase()
  return { low: '低置信度', medium: '中置信度', high: '高置信度' }[c] || c
})
const horizon = computed(() => cryptoForecast.value?.horizon || forecast.value?.horizon || '1w')
const status = computed(() => cryptoForecast.value?.status || 'ok')
const rationale = computed(() => cryptoForecast.value?.rationale || forecast.value?.rationale || '')

const composite = computed(() => extractComposite(financialContext.value))
const compositeColor = computed(() => {
  const v = composite.value
  if (v > 0.05) return '#26A269'
  if (v < -0.05) return '#C0392B'
  return '#64748B'
})

const rawTargetRange = computed(() => cryptoForecast.value?.target_price_range || forecast.value?.target_price_range || null)
const targetRangeObject = computed(() => {
  const r = rawTargetRange.value
  if (!r) return null
  if (Array.isArray(r) && r.length >= 2) {
    return {
      low: r[0],
      high: r[1],
      mid: r.length >= 3 ? r[2] : null,
    }
  }
  if (typeof r === 'object') return r
  return null
})
const targetRange = computed(() => {
  const r = rawTargetRange.value
  const obj = targetRangeObject.value
  if (!r) return ''
  if (obj && obj.low != null && obj.high != null) {
    const mid = obj.mid != null ? ` / mid ${fmtNum(obj.mid)}` : ''
    return `${fmtNum(obj.low)} ~ ${fmtNum(obj.high)}${mid}`
  }
  return String(r)
})

const preciseForecast = computed(() => {
  const existing = cryptoForecast.value?.precise_forecast || forecast.value?.precise_forecast
  if (existing) return existing
  const r = targetRangeObject.value
  if (r?.mid == null || r?.low == null || r?.high == null) return null
  return {
    predicted_price: r.mid,
    p10: r.low,
    p50: r.mid,
    p90: r.high,
    p_up: null,
    expected_return: null,
    mode: 'target_point',
    source: 'frontend_target_range_fallback',
    warning: '本报告未保存 Kronos/Chronos-Bolt 输出，当前使用目标区间 mid 作为参考价格点。',
  }
})
const preciseModeLabel = computed(() => {
  const raw = preciseForecast.value?.mode || 'foundation/fallback'
  const mode = String(raw).toLowerCase()
  if (mode === 'kronos+chronos') return 'Kronos + Chronos-Bolt · kronos+chronos'
  if (mode === 'kronos_only') return 'Kronos · kronos_only'
  if (mode === 'chronos_only') return 'Chronos-Bolt · chronos_only'
  return raw
})
const preciseWarning = computed(() => preciseForecast.value?.warning || '')

const priceSpark = computed(() => buildPriceSparkline(financialContext.value))
const sentimentSpark = computed(() => buildSentimentSparkline(financialContext.value))

const priceRangeLabel = computed(() => {
  const lbls = priceSpark.value.labels
  if (!lbls.length) return '—'
  return `${lbls[0]} → ${lbls[lbls.length - 1]}`
})

const dirColor = computed(() => directionKey.value === 'up' ? '#26A269' : directionKey.value === 'down' ? '#C0392B' : '#6366F1')

// ===== ECharts options =====

const probabilityGaugeOption = computed(() => {
  const v = probability.value == null ? 0 : probability.value * 100
  const color = dirColor.value
  return {
    series: [{
      type: 'gauge',
      startAngle: 180,
      endAngle: 0,
      min: 0,
      max: 100,
      radius: '100%',
      center: ['50%', '72%'],
      splitNumber: 5,
      progress: { show: true, width: 14, itemStyle: { color } },
      pointer: { show: false },
      axisLine: { lineStyle: { width: 14, color: [[1, '#E5E7EB']] } },
      axisTick: { show: false },
      splitLine: { length: 6, lineStyle: { width: 1, color: '#CBD5E1' } },
      axisLabel: { distance: -18, fontSize: 9, color: '#94A3B8' },
      anchor: { show: false },
      title: { show: false },
      detail: {
        valueAnimation: true,
        offsetCenter: [0, '-12%'],
        fontSize: 24,
        fontWeight: 'bold',
        color,
        formatter: (val) => probability.value == null ? '—' : `${val.toFixed(1)}%`,
      },
      data: [{ value: v, name: '概率' }],
    }],
  }
})

const priceProOption = computed(() => {
  const ma20 = priceFacts.value?.ma20
  const ma60 = priceFacts.value?.ma60
  const markLines = []
  if (ma20 != null) markLines.push({ yAxis: ma20, name: 'MA20', lineStyle: { color: '#F59E0B', type: 'dashed', width: 1.2 }, label: { formatter: 'MA20', color: '#F59E0B', fontSize: 10, position: 'insideEndTop' } })
  if (ma60 != null) markLines.push({ yAxis: ma60, name: 'MA60', lineStyle: { color: '#6366F1', type: 'dashed', width: 1.2 }, label: { formatter: 'MA60', color: '#6366F1', fontSize: 10, position: 'insideEndBottom' } })
  return {
    title: {
      text: `${symbolLabel.value} · ${barPeriod.value}`,
      subtext: `数据源: ${exchangeLabel.value} OHLCV (${priceRangeLabel.value})`,
      textStyle: { fontSize: 12, color: '#111', fontWeight: 700 },
      subtextStyle: { fontSize: 10, color: '#94A3B8' },
      left: 0, top: 0,
    },
    grid: { left: 56, right: 16, top: 56, bottom: 50 },
    tooltip: { trigger: 'axis', axisPointer: { type: 'cross', label: { show: true, backgroundColor: '#475569' } } },
    xAxis: {
      type: 'category',
      data: priceSpark.value.labels,
      name: '日期',
      nameLocation: 'middle',
      nameGap: 28,
      nameTextStyle: { color: '#94A3B8', fontSize: 10 },
      axisLabel: { fontSize: 9, color: '#94A3B8', rotate: 30 },
    },
    yAxis: {
      type: 'value',
      scale: true,
      name: '价格 (USD)',
      nameLocation: 'middle',
      nameGap: 44,
      nameTextStyle: { color: '#94A3B8', fontSize: 10 },
      axisLabel: { fontSize: 9, color: '#94A3B8' },
      splitLine: { lineStyle: { color: '#F1F5F9' } },
    },
    dataZoom: [{ type: 'inside' }],
    series: [{
      name: 'close',
      type: 'line',
      smooth: true,
      symbol: 'none',
      data: priceSpark.value.data,
      lineStyle: { color: '#0EA5E9', width: 2 },
      areaStyle: { color: 'rgba(14,165,233,.12)' },
      markLine: markLines.length ? { silent: true, symbol: 'none', data: markLines } : undefined,
      markPoint: priceSpark.value.data.length ? {
        symbol: 'pin', symbolSize: 32,
        label: { fontSize: 9, color: '#FFF' },
        data: [{ type: 'max', itemStyle: { color: '#26A269' } }, { type: 'min', itemStyle: { color: '#C0392B' } }],
      } : undefined,
    }],
  }
})

const sentimentProOption = computed(() => ({
  title: {
    text: '情绪 compound 时序',
    subtext: `模型: ${sentimentModel.value} · ${observed.value?.real_news?.length || 0} 条新闻 + ${observed.value?.real_comments?.length || 0} 条评论`,
    textStyle: { fontSize: 12, color: '#111', fontWeight: 700 },
    subtextStyle: { fontSize: 10, color: '#94A3B8' },
    left: 0, top: 0,
  },
  grid: { left: 56, right: 16, top: 56, bottom: 50 },
  tooltip: { trigger: 'axis', axisPointer: { type: 'cross', label: { show: true, backgroundColor: '#475569' } } },
  xAxis: {
    type: 'category',
    data: sentimentSpark.value.labels,
    name: '时间窗口',
    nameLocation: 'middle',
    nameGap: 28,
    nameTextStyle: { color: '#94A3B8', fontSize: 10 },
    axisLabel: { fontSize: 9, color: '#94A3B8', rotate: 30 },
  },
  yAxis: {
    type: 'value',
    min: -1, max: 1,
    name: '情绪复合分',
    nameLocation: 'middle',
    nameGap: 38,
    nameTextStyle: { color: '#94A3B8', fontSize: 10 },
    axisLabel: { fontSize: 9, color: '#94A3B8' },
    splitLine: { lineStyle: { color: '#F1F5F9' } },
  },
  series: [{
    name: 'compound',
    type: 'line',
    smooth: true,
    symbol: 'circle',
    symbolSize: 4,
    data: sentimentSpark.value.data,
    lineStyle: { color: '#6366F1', width: 2 },
    areaStyle: { color: 'rgba(99,102,241,.18)' },
    markArea: {
      silent: true,
      itemStyle: { opacity: 0.15 },
      data: [
        [{ yAxis: 0.1, itemStyle: { color: '#26A269' } }, { yAxis: 1 }],
        [{ yAxis: -1, itemStyle: { color: '#C0392B' } }, { yAxis: -0.1 }],
      ],
    },
    markLine: { silent: true, symbol: 'none', data: [{ yAxis: 0, lineStyle: { color: '#94A3B8', type: 'dashed' } }] },
    markPoint: sentimentSpark.value.data.length ? {
      symbol: 'pin', symbolSize: 30,
      label: { fontSize: 9, color: '#FFF' },
      data: [{ type: 'max', itemStyle: { color: '#26A269' } }, { type: 'min', itemStyle: { color: '#C0392B' } }],
    } : undefined,
  }],
}))

const topDrivers = computed(() => {
  const list = cryptoForecast.value?.evidence?.drivers || financialContext.value?.inferred?.drivers || []
  return list.slice(0, 4).map(d => ({
    tag: (d.label || d.type || 'signal').slice(0, 12),
    title: d.title || d.label || 'market signal',
    site: d.site || d.source || '',
    compound: Number(d.compound ?? 0),
  }))
})

const riskCaveats = computed(() => {
  const r = forecast.value?.risk_caveats || cryptoForecast.value?.risk_caveats || []
  return Array.isArray(r) ? r.slice(0, 4) : []
})

function driverClass (d) {
  if (d.compound > 0.1) return 'pos'
  if (d.compound < -0.1) return 'neg'
  return 'neu'
}

function formatScore (v) {
  if (v == null || Number.isNaN(Number(v))) return '-'
  const n = Number(v)
  return `${n >= 0 ? '+' : ''}${n.toFixed(2)}`
}

function fmtNum (v) {
  if (v == null || Number.isNaN(Number(v))) return '-'
  return Number(v).toLocaleString(undefined, { maximumFractionDigits: 4 })
}

async function loadForecast () {
  if (!props.reportId) return
  loading.value = true
  error.value = ''
  report.value = null
  try {
    const current = await getReport(props.reportId)
    const currentReport = current.data
    if (currentReport?.report_type === 'financial') {
      report.value = currentReport
      return
    }
    const simulationId = props.simulationId || currentReport?.simulation_id
    if (!simulationId) { report.value = currentReport; return }
    try {
      const fin = await getReportBySimulation(simulationId, 'financial')
      report.value = fin.data
    } catch (err) {
      report.value = currentReport
    }
  } catch (err) {
    error.value = err.message || '价格预测暂不可用。'
  } finally {
    loading.value = false
  }
}

onMounted(loadForecast)
watch(() => [props.reportId, props.simulationId], loadForecast)
</script>

<style scoped>
.crypto-section { padding: var(--s-6) 0; scroll-margin-top: 80px; }
.section-head { display: flex; justify-content: space-between; align-items: flex-start; gap: var(--s-4); margin-bottom: var(--s-3); }
.kicker { color: var(--c-accent); font-size: var(--fs-12); font-weight: 700; letter-spacing: .14em; }
.section-head h2 { margin: 4px 0; color: var(--c-text); font-size: var(--fs-22); }
.section-head p { margin: 0; color: var(--c-text-muted); font-size: var(--fs-13); }
.refresh-btn { border: 1px solid var(--c-border-strong); border-radius: var(--r-sm); background: var(--c-bg); color: var(--c-text); padding: 8px 12px; font-weight: 700; cursor: pointer; }
.refresh-btn:disabled { opacity: .55; cursor: not-allowed; }

/* 上下文胶囊行 */
.chip-row { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: var(--s-4); padding: 10px 12px; background: rgba(99,102,241,.04); border: 1px solid rgba(99,102,241,.15); border-radius: var(--r-md); }
.chip { font-size: 11px; color: var(--c-text-muted); background: #FFF; padding: 4px 10px; border-radius: 999px; border: 1px solid rgba(23,32,51,.08); font-family: var(--f-mono, monospace); }
.chip b { color: var(--c-accent); font-weight: 700; margin-right: 4px; }

.state-card { padding: var(--s-5); color: var(--c-text-muted); border: 1px dashed var(--c-border-strong); border-radius: var(--r-md); background: var(--c-bg-soft); }
.state-card.error { border-color: #FCA5A5; color: #991B1B; background: #FFF7F7; }

/* 玻璃质感 forecast card */
.forecast-card { border: 1px solid var(--c-border); border-radius: var(--r-lg); padding: var(--s-5); display: grid; gap: var(--s-4); background: linear-gradient(135deg, var(--c-bg) 0%, rgba(99,102,241,.04) 100%); box-shadow: 0 4px 20px rgba(15,23,42,.06); }
.forecast-card.dir-up { border-color: #26A269; background: linear-gradient(135deg, #F1FAF5 0%, rgba(38,162,105,.06) 100%); }
.forecast-card.dir-down { border-color: #C0392B; background: linear-gradient(135deg, #FFF6F5 0%, rgba(192,57,43,.06) 100%); }
.forecast-card.dir-neutral { border-color: #94A3B8; background: linear-gradient(135deg, #F8FAFC 0%, rgba(99,102,241,.04) 100%); }

.kpi-row { display: grid; grid-template-columns: 1.2fr 1.6fr 1fr; gap: var(--s-4); align-items: center; }
.kpi-main .asset-label { display: block; color: var(--c-text-muted); font-size: var(--fs-13); margin-bottom: 4px; font-family: var(--f-mono, monospace); }
.dir-label { display: block; color: var(--c-text); font-size: 36px; line-height: 1.1; font-weight: 700; }
.dir-label.glow-up { color: #166534; text-shadow: 0 0 12px rgba(38,162,105,.35); }
.dir-label.glow-down { color: #991B1B; text-shadow: 0 0 12px rgba(192,57,43,.35); }
.dir-label.glow-neutral { color: #475569; text-shadow: 0 0 12px rgba(99,102,241,.25); }
.dir-icon { margin-right: 6px; }
.kpi-main em { display: block; margin-top: 8px; color: var(--c-text-muted); font-size: var(--fs-13); font-style: normal; }

.kpi-stats { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }
.stat { padding: 10px 12px 10px 14px; background: rgba(255,255,255,.85); border: 1px solid rgba(23,32,51,.08); border-radius: var(--r-md); border-left: 3px solid #94A3B8; font-variant-numeric: tabular-nums; }
.stat.bar-up { border-left-color: #26A269; }
.stat.bar-down { border-left-color: #C0392B; }
.stat.bar-neutral { border-left-color: #6366F1; }
.stat span { display: block; color: var(--c-text-muted); font-size: 11px; letter-spacing: .04em; text-transform: uppercase; margin-bottom: 4px; }
.stat strong { color: var(--c-text); font-size: 16px; font-variant-numeric: tabular-nums; }
.stat .mono { font-family: var(--f-mono, monospace); font-size: 13px; }
.stat.precise-stat { border-left-color: #4078c0; background: rgba(64,120,192,0.08); }
.stat.precise-stat .precise-band { display: block; font-style: normal; font-size: 11px; color: #4078c0; font-weight: 500; margin-top: 2px; }
.stat.precise-stat .precise-warning { display: block; margin-top: 5px; color: #64748B; font-size: 10px; line-height: 1.35; }

.kpi-gauge { display: flex; flex-direction: column; align-items: center; padding: 6px; background: rgba(255,255,255,.6); border-radius: var(--r-md); border: 1px dashed rgba(23,32,51,.08); }
.kpi-quality { display: flex; flex-wrap: wrap; gap: 4px 10px; padding: 4px 6px 0; color: var(--c-text-muted); font-size: 10px; font-family: var(--f-mono, monospace); justify-content: center; }

.chart-row { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: var(--s-4); align-items: stretch; }
.chart-col { background: rgba(255,255,255,.85); border-radius: var(--r-md); border: 1px solid rgba(23,32,51,.08); padding: 10px; min-height: 240px; }
.chart-empty { display: flex; align-items: center; justify-content: center; height: 100%; min-height: 220px; color: var(--c-text-muted); font-size: var(--fs-13); }

.evidence-row { display: grid; grid-template-columns: 1.2fr 1fr; gap: var(--s-4); }
.drivers-col h3, .risks-col h3 { margin: 0 0 8px; color: var(--c-text); font-size: var(--fs-14); }
.driver-list, .risk-list { margin: 0; padding: 0; list-style: none; display: grid; gap: 6px; }
.driver-list li { display: grid; grid-template-columns: 80px 1fr auto; gap: 8px; align-items: center; padding: 6px 8px; border-radius: 6px; background: rgba(255,255,255,.7); border-left: 3px solid #94A3B8; font-size: var(--fs-12); color: var(--c-text); position: relative; }
.driver-list li.pos { border-left-color: #26A269; }
.driver-list li.neg { border-left-color: #C0392B; }
.driver-list b { color: var(--c-accent); font-family: var(--f-mono, monospace); font-size: 11px; text-transform: uppercase; }
.driver-list em { color: var(--c-text-muted); font-style: normal; font-size: 11px; }
.driver-title { color: var(--c-text); position: relative; padding-bottom: 4px; }
.score-bar { display: block; position: absolute; left: 0; bottom: 0; height: 2px; background: currentColor; opacity: 0.35; max-width: 100%; transition: width .3s; }
.driver-list li.pos .score-bar { background: #26A269; }
.driver-list li.neg .score-bar { background: #C0392B; }
.risk-list li { padding: 8px 10px; border-left: 3px solid #C0392B; background: #FFF6F5; border-radius: 4px; font-size: var(--fs-12); color: #7F1D1D; box-shadow: inset 0 1px 0 rgba(255,255,255,.6); }
.muted { color: var(--c-text-muted); font-size: var(--fs-12); margin: 4px 0; }
.rationale { margin: 0; color: var(--c-text-muted); font-size: var(--fs-13); line-height: var(--lh-relaxed); padding: 10px 12px; background: rgba(255,255,255,.5); border-radius: var(--r-md); border-left: 3px solid var(--c-accent); }

@media (max-width: 1100px) {
  .chart-row { grid-template-columns: 1fr 1fr; }
  .chart-col:last-child { grid-column: 1 / -1; }
}
@media (max-width: 980px) {
  .kpi-row, .chart-row, .evidence-row { grid-template-columns: 1fr; }
  .chart-col:last-child { grid-column: auto; }
}
@media (max-width: 600px) {
  .kpi-stats { grid-template-columns: 1fr; }
  .driver-list li { grid-template-columns: 1fr; }
}
</style>
