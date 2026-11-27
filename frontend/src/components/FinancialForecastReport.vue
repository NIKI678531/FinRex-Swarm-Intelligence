<template>
  <div class="fin-report">
    <div v-if="loading" class="fin-status">
      <span class="spinner"></span>
      正在加载金融强预测报告...
    </div>
    <div v-else-if="error" class="fin-status error">{{ error }}</div>
    <div v-else-if="!report" class="fin-status muted">暂无金融强预测报告</div>

    <div v-else class="fin-content">
      <!-- ============ Header ============ -->
      <header class="fin-header">
        <div class="fin-meta">
          <span class="fin-tag">Financial OIF Forecast</span>
          <span class="fin-id">ID: {{ report.report_id }}</span>
          <span class="fin-mode">{{ modeLabel }}</span>
          <span v-for="(q, i) in qualityBadges" :key="i" class="fin-badge">{{ q }}</span>
        </div>
        <h1 class="fin-title">{{ report.outline?.title || '金融强预测报告' }}</h1>
        <p class="fin-sub">{{ report.outline?.summary || '' }}</p>
      </header>

      <!-- ============ Section A · Forecast Summary ============ -->
      <DashboardCard title="A · Forecast Summary" subtitle="最终方向、概率与权重雷达">
        <div class="summary-grid">
          <div class="summary-main" :class="forecastDirectionClass">
            <div class="sm-asset">{{ targetLabel }}</div>
            <div class="sm-direction">
              <span class="dir-icon">{{ directionIcon }}</span>
              {{ directionLabel }}
            </div>
            <div class="sm-meta">
              <span><b>{{ probabilityPct }}</b> 概率</span>
              <span><b>{{ confidenceLabel }}</b> 置信度</span>
              <span><b>{{ horizonLabel }}</b> 时间窗</span>
            </div>
            <div v-if="targetPriceRange" class="sm-range">
              <span>目标区间</span>
              <strong>{{ targetPriceRange }}</strong>
            </div>
            <div class="sm-composite">
              <span>综合分</span>
              <strong :style="{ color: compositeColor }">{{ formatScore(composite) }}</strong>
            </div>
            <div v-if="preciseForecast" class="sm-precise" :class="{ 'is-fallback': !isFoundationPrecise }">
              <div class="sm-precise-head">
                <span class="precise-tag">{{ preciseModelLabel }} · {{ preciseModeLabel }}</span>
                <span v-if="preciseAgreementPct" class="precise-agree">模型一致度 {{ preciseAgreementPct }}</span>
              </div>
              <div class="sm-precise-row">
                <span>{{ precisePriceLabel }}</span>
                <strong>{{ formatNumber(preciseForecast.predicted_price) }}</strong>
              </div>
              <div class="sm-precise-row">
                <span>p10 — p90</span>
                <strong>{{ formatNumber(preciseForecast.p10) }} ~ {{ formatNumber(preciseForecast.p90) }}</strong>
              </div>
              <div class="sm-precise-row" v-if="preciseExpectedReturnPct">
                <span>预期回报</span>
                <strong>{{ preciseExpectedReturnPct }}</strong>
              </div>
              <div class="sm-precise-row" v-if="preciseForecast.warning">
                <span>状态</span>
                <strong class="precise-warning">{{ preciseForecast.warning }}</strong>
              </div>
            </div>
          </div>
          <div class="summary-radar">
            <FactorRadar :financial-context="financialContext" height="280px" />
          </div>
        </div>
      </DashboardCard>

      <!-- ============ Section B · Model Tuning & Backtest ============ -->
      <DashboardCard title="B · Model Tuning & Backtest" subtitle="只作为 Backtest 参数预填；Promote 后才进入 Validation active config">
        <div class="tuning-shell">
          <div class="tuning-main">
            <div class="tuning-row tuning-row--top">
              <label>
                <span>Model Kind</span>
                <select v-model="tuning.modelKind">
                  <option value="weighted">Weighted Sigmoid</option>
                  <option value="multimodal_v1">Multimodal v1</option>
                </select>
              </label>
              <label>
                <span>Horizon</span>
                <select v-model="tuning.horizon">
                  <option value="1d">1d direction</option>
                  <option value="7d">7d direction</option>
                </select>
              </label>
              <label>
                <span>Ablation</span>
                <select v-model="tuning.ablationMode">
                  <option value="market_only">Market only</option>
                  <option value="market_text">Market + Text</option>
                  <option value="market_text_oasis">Market + Text + OASIS</option>
                </select>
              </label>
              <label>
                <span>Decision Threshold</span>
                <input v-model.number="tuning.decisionThreshold" type="number" min="0.5" max="0.95" step="0.01" />
              </label>
            </div>

            <label class="tuning-oasis">
              <span>OASIS Simulation ID</span>
              <input v-model.trim="tuning.oasisSimulationId" placeholder="可选；为空则 OASIS 历史因子按 neutral 处理" />
            </label>

            <div class="weight-sliders">
              <div v-for="group in tuningWeightGroups" :key="group.name" class="slider-group">
                <div class="slider-group-head">
                  <strong>{{ group.name }}</strong>
                  <span>{{ group.hint }}</span>
                </div>
                <label v-for="item in group.items" :key="item.key" class="slider-line">
                  <div class="slider-label">
                    <span>{{ item.label }}</span>
                    <strong :class="weightTone(tuning.weights[item.key])">{{ formatWeight(tuning.weights[item.key]) }}</strong>
                  </div>
                  <input
                    v-model.number="tuning.weights[item.key]"
                    type="range"
                    :min="item.min ?? -0.5"
                    :max="item.max ?? 0.6"
                    step="0.01"
                  />
                </label>
              </div>
            </div>
          </div>

          <aside class="tuning-side">
            <div class="tuning-source">
              <span>当前参数来源</span>
              <strong>{{ activeWeightSetLabel }}</strong>
              <em v-if="tuningLoadError">{{ tuningLoadError }}</em>
            </div>
            <div class="tuning-kv">
              <span>Symbol</span><strong>{{ targetSymbol }}</strong>
              <span>Interval</span><strong>1d</strong>
              <span>Report</span><strong class="mono">{{ props.reportId || report?.report_id || '-' }}</strong>
            </div>
            <div class="tuning-actions">
              <button type="button" class="btn-secondary" @click="resetTuningToDefaults">恢复默认权重</button>
              <button type="button" class="btn-primary" @click="goBacktest">进入回测</button>
            </div>
            <p class="tuning-note">滑动条只影响即将进入 Backtest 的预填参数；完成回测并 Promote 后，Validation 才会读取新的 active config。</p>
          </aside>
        </div>
      </DashboardCard>

      <!-- ============ Section C · Factor Pipeline (CORE) ============ -->
      <DashboardCard
        title="C · Factor Pipeline"
        subtitle="原始数据 → 因子打分 → 加权融合 → 最终方向"
        accent
      >
        <FactorFlowSankey :financial-context="financialContext" height="320px" />
        <div class="pipeline-foot">
          <FactorBarChart :financial-context="financialContext" height="240px" />
        </div>
      </DashboardCard>

      <!-- ============ Section D · Observed Layer ============ -->
      <DashboardCard title="D · Observed · 真实行情与新闻" subtitle="OHLCV / 真实新闻 / 真实评论">
        <div class="panel-note">
          <div class="pn-row">
            <span class="pn-tag">面板说明</span>
            <span>当前展示的是 <b>{{ targetLabel }}</b> 的{{ hasOhlcv ? ' K 线（蜡烛图）' : '价格摘要' }}面板，数据来自交易所原始 OHLCV，过去 <b>{{ candleData.dates.length }}</b> 根 bar，时间范围 <b>{{ ohlcvRangeLabel }}</b>。</span>
          </div>
          <div class="pn-row">
            <span class="pn-tag">用途</span>
            <span>该原始行情用于计算 <code>MA20 / MA60 / RSI14 / return_5d / volatility_30d</code> 等技术因子，供 D 章情绪推断与 F 章预测使用。</span>
          </div>
          <div class="pn-row">
            <span class="pn-tag">坐标轴</span>
            <span>X 轴 = 日期（从左到右时间递增）；Y 轴 = 价格 (USD)；蜡烛实体 <span class="col-up">绿色</span> 表示当根上涨、<span class="col-down">红色</span> 表示下跌。</span>
          </div>
        </div>
        <div class="observed-grid">
          <div class="observed-chart">
            <EChart v-if="hasOhlcv" :option="candleOption" height="280px" />
            <div v-else class="placeholder">
              <div v-if="priceFacts.last_close != null" class="ph-row">
                <span>最新收盘 last_close</span>
                <strong>{{ formatNumber(priceFacts.last_close) }}</strong>
              </div>
              <div v-if="priceFacts.ma20 != null" class="ph-row">
                <span>MA20</span><strong>{{ formatNumber(priceFacts.ma20) }}</strong>
              </div>
              <div v-if="priceFacts.ma60 != null" class="ph-row">
                <span>MA60</span><strong>{{ formatNumber(priceFacts.ma60) }}</strong>
              </div>
              <div v-if="priceFacts.rsi14 != null" class="ph-row">
                <span>RSI14</span><strong>{{ formatNumber(priceFacts.rsi14) }}</strong>
              </div>
              <div v-if="priceFacts.return_5d != null" class="ph-row">
                <span>5d return</span><strong>{{ formatPct(priceFacts.return_5d) }}</strong>
              </div>
              <div v-else class="placeholder-empty">无 OHLCV 数据</div>
            </div>
          </div>
          <div class="observed-side">
            <MiniSparkline label="价格 close" :data="priceSpark.data" :labels="priceSpark.labels" color="#0EA5E9" height="60px" />
            <div class="kv-grid">
              <div><span>RSI14</span><strong>{{ formatNumber(priceFacts.rsi14) }}</strong></div>
              <div><span>5d return</span><strong>{{ formatPct(priceFacts.return_5d) }}</strong></div>
              <div><span>30d vol</span><strong>{{ formatPct(priceFacts.volatility_30d) }}</strong></div>
              <div><span>MA20/60</span><strong class="mono">{{ formatNumber(priceFacts.ma20) }}/{{ formatNumber(priceFacts.ma60) }}</strong></div>
            </div>
          </div>
        </div>

        <div class="sub-note">来源：真实社媒 + 新闻聚合，未经 LLM 改写，作为 D 章 sentiment_index 计算输入。</div>
        <div class="news-comments">
          <div class="news-col">
            <h4>真实新闻 ({{ realNews.length }})</h4>
            <ul v-if="realNews.length" class="news-list">
              <li v-for="(n, i) in realNews.slice(0, 5)" :key="i">
                <a v-if="n.url" :href="n.url" target="_blank" rel="noopener">{{ n.title || n.headline || '(无标题)' }}</a>
                <span v-else>{{ n.title || n.headline || '(无标题)' }}</span>
                <em v-if="n.site">{{ n.site }}</em>
              </li>
            </ul>
            <p v-else class="muted">无</p>
          </div>
          <div class="comments-col">
            <h4>真实评论 ({{ realComments.length }})</h4>
            <blockquote v-for="(c, i) in realComments.slice(0, 3)" :key="i">
              {{ c.text || c.body || c.content || '' }}
              <cite v-if="c.author || c.source">— {{ c.author || c.source }}</cite>
            </blockquote>
            <p v-if="!realComments.length" class="muted">无</p>
          </div>
        </div>
      </DashboardCard>

      <!-- ============ Section E · Inferred Layer ============ -->
      <DashboardCard title="E · Inferred · 情绪与驱动" subtitle="sentiment / drivers / divergence signals">
        <div class="panel-note">
          <div class="pn-row">
            <span class="pn-tag">情绪指标</span>
            <span>采用 <b>{{ inferred.sentiment_model || 'VADER / FinBERT' }}</b> 模型对 C 章真实新闻 + 用户评论计算 <code>compound</code> 复合分，范围 <b>[-1, +1]</b>：&gt;0 看多 / &lt;0 看空 / ≈0 中性。当前 sentiment_index = <b :style="{ color: scoreColor(inferred.sentiment_index) }">{{ formatScore(inferred.sentiment_index) }}</b>。</span>
          </div>
          <div class="pn-row">
            <span class="pn-tag">坐标轴</span>
            <span>X 轴 = 时间窗口（按发布时间或滚动窗口聚合）；Y 轴 = compound 复合分；浅绿色带 = 多头区 (&gt;+0.1)、浅红色带 = 空头区 (&lt;-0.1)。</span>
          </div>
          <div class="pn-row">
            <span class="pn-tag">背离</span>
            <span>价格走势与情绪走势出现顶/底背离时，divergence_signals 会被触发，作为反转风险注释提示，请重点关注下方告警条。</span>
          </div>
        </div>
        <div class="inferred-grid">
          <div class="senti-chart">
            <EChart v-if="hasSentimentTimeline" :option="sentimentOption" height="220px" />
            <div v-else class="placeholder-empty">无情绪时序</div>
            <div class="senti-meta">
              <span>sentiment_index <b>{{ formatScore(inferred.sentiment_index) }}</b></span>
              <span v-if="inferred.sentiment_model">model <b>{{ inferred.sentiment_model }}</b></span>
            </div>
          </div>
          <div class="drivers-table">
            <h4>主导驱动 ({{ drivers.length }})</h4>
            <table v-if="drivers.length">
              <thead><tr><th>标题</th><th>来源</th><th>compound</th></tr></thead>
              <tbody>
                <tr v-for="(d, i) in drivers.slice(0, 8)" :key="i">
                  <td><span :class="driverClass(d)">{{ d.title || d.label || '(无)' }}</span></td>
                  <td class="muted">{{ d.site || '' }}</td>
                  <td class="mono" :style="{ color: driverColor(d) }">{{ d.compound != null ? Number(d.compound).toFixed(3) : '-' }}</td>
                </tr>
              </tbody>
            </table>
            <p v-else class="muted">无</p>
          </div>
        </div>
        <div v-if="divergences.length" class="divergence-row">
          <span class="div-label">⚠ 背离信号</span>
          <span v-for="(d, i) in divergences" :key="i" class="div-tag">{{ d }}</span>
        </div>
      </DashboardCard>

      <!-- ============ Section F · Simulated Layer ============ -->
      <DashboardCard
        title="F · Simulated · OASIS 推演"
        subtitle="oasis_pulses / agent_scenarios（来自 OASIS 多 Agent 模拟，仅推演，不可作为现实依据）"
      >
        <div v-if="sortedPulses.length" class="pulses">
          <h4>脉冲累计冲击 (按 timestamp 升序，{{ sortedPulses.length }} 条)</h4>
          <EChart :option="pulseShiftOption" height="220px" />
          <ul class="pulse-list">
            <li v-for="(p, i) in sortedPulses.slice(0, 8)" :key="i">
              <span class="p-time">{{ p.time || p.timestamp || `t${i+1}` }}</span>
              <span class="p-name">{{ p.name || p.event || p.label || 'pulse' }}</span>
              <em v-if="p.sentiment_shift != null" :style="{ color: scoreColor(p.sentiment_shift) }">
                Δ {{ formatScore(p.sentiment_shift) }}
              </em>
            </li>
          </ul>
        </div>
        <div v-if="agentScenarios.length" class="scenarios">
          <h4>Agent 行为推演 ({{ agentScenarios.length }})</h4>
          <div v-if="agentRoleSummary.length" class="role-badges">
            <span v-for="(b, i) in agentRoleSummary" :key="i" class="role-badge" :class="b.cls">
              {{ b.label }} × {{ b.count }}
            </span>
          </div>
          <div class="scenario-grid">
            <div v-for="(s, i) in agentScenarios.slice(0, 6)" :key="i" class="scenario-card">
              <strong>{{ s.role || s.name || s.persona || `Agent ${i+1}` }}</strong>
              <p>{{ s.action || s.behavior || s.text || s.description || '' }}</p>
            </div>
          </div>
        </div>
        <p v-if="!sortedPulses.length && !agentScenarios.length" class="muted">无模拟数据</p>
        <div class="sim-footnote">⚠ 以上数据均来自 OASIS 多 Agent 模拟推演，仅作为情景假设，不代表真实市场行为或可执行交易建议。</div>
      </DashboardCard>

      <!-- ============ Section G · Risk & Strategy ============ -->
      <DashboardCard title="G · Risk & Strategy Notes" subtitle="风险注释与所用量化策略说明">
        <div class="rs-grid">
          <div>
            <h4>风险与边界</h4>
            <ul v-if="riskCaveats.length" class="risk-list">
              <li v-for="(r, i) in riskCaveats" :key="i">{{ r }}</li>
            </ul>
            <p v-else class="muted">无</p>
          </div>
          <div>
            <h4>策略说明</h4>
            <ul class="strategy-list">
              <li v-for="(s, i) in strategyNotes" :key="i">
                <b>{{ s.name }}</b>
                <span>{{ s.desc }}</span>
              </li>
            </ul>
            <p v-if="rationale" class="rationale-box">{{ rationale }}</p>
          </div>
        </div>
      </DashboardCard>

      <!-- ============ Section H · Original OIF Report (collapsible) ============ -->
      <DashboardCard
        title="H · Original OIF Report"
        subtitle="完整四章金融预测报告原文"
        collapsible
        :default-collapsed="true"
      >
        <div class="fin-sections">
          <section
            v-for="(sec, idx) in sections"
            :key="idx"
            class="fin-section"
            :class="{ collapsed: collapsed.has(idx) }"
          >
            <div class="fin-section-head" @click="toggleCollapse(idx)">
              <span class="num">{{ String(idx + 1).padStart(2, '0') }}</span>
              <h3>{{ sec.title }}</h3>
              <span class="chev">{{ collapsed.has(idx) ? '+' : '−' }}</span>
            </div>
            <div v-show="!collapsed.has(idx)" class="fin-section-body markdown-body" v-html="renderMd(sec.content)"></div>
          </section>
        </div>
      </DashboardCard>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { getReport } from '@/api/report'
import EChart from './report/widgets/EChart.vue'
import FactorRadar from './report/widgets/FactorRadar.vue'
import FactorBarChart from './report/widgets/FactorBarChart.vue'
import FactorFlowSankey from './report/widgets/FactorFlowSankey.vue'
import MiniSparkline from './report/widgets/MiniSparkline.vue'
import DashboardCard from './report/widgets/DashboardCard.vue'
import {
  buildPriceSparkline,
  buildCandlestick,
  extractComposite,
} from './report/widgets/financialFactorAdapter'

const props = defineProps({
  reportId: { type: String, default: '' },
  simulationId: { type: String, default: '' }
})

const router = useRouter()

const loading = ref(false)
const error = ref('')
const report = ref(null)
const collapsed = ref(new Set())

const DEFAULT_TUNING_WEIGHTS = {
  sentiment_finbert: 0.30,
  sentiment_emotion: 0.10,
  news_volume: 0.10,
  social_volume: 0.10,
  price_momentum: 0.25,
  volatility: 0.15,
  oasis_sentiment: 0.12,
  oasis_pulse_score: 0.10,
  oasis_risk_intensity: -0.12,
  oasis_volume_z: 0.06,
  oasis_velocity_z: 0.06,
  oasis_consensus: 0.08,
  oasis_disagreement: -0.08,
  oasis_cross_platform_spread: 0.05,
  oasis_fomo_score: 0.06,
  oasis_panic_score: -0.08
}

const tuningWeightGroups = [
  {
    name: 'Market Factors',
    hint: '价格趋势与波动率',
    items: [
      { key: 'price_momentum', label: 'Price momentum', min: -0.3, max: 0.6 },
      { key: 'volatility', label: 'Volatility', min: -0.4, max: 0.4 }
    ]
  },
  {
    name: 'Text Sentiment Factors',
    hint: '新闻、评论、声量',
    items: [
      { key: 'sentiment_finbert', label: 'FinBERT sentiment', min: -0.3, max: 0.6 },
      { key: 'sentiment_emotion', label: 'Emotion sentiment', min: -0.3, max: 0.4 },
      { key: 'news_volume', label: 'News volume', min: -0.2, max: 0.4 },
      { key: 'social_volume', label: 'Social volume', min: -0.2, max: 0.4 }
    ]
  },
  {
    name: 'OASIS Crowd Factors',
    hint: '群体推演、风险扩散、FOMO/Panic',
    items: [
      { key: 'oasis_sentiment', label: 'OASIS sentiment', min: -0.3, max: 0.5 },
      { key: 'oasis_pulse_score', label: 'Pulse score', min: -0.3, max: 0.5 },
      { key: 'oasis_risk_intensity', label: 'Risk intensity', min: -0.5, max: 0.2 },
      { key: 'oasis_volume_z', label: 'Volume z-score', min: -0.2, max: 0.3 },
      { key: 'oasis_velocity_z', label: 'Velocity z-score', min: -0.2, max: 0.3 },
      { key: 'oasis_consensus', label: 'Consensus', min: -0.2, max: 0.4 },
      { key: 'oasis_disagreement', label: 'Disagreement', min: -0.4, max: 0.2 },
      { key: 'oasis_cross_platform_spread', label: 'Cross-platform spread', min: -0.2, max: 0.3 },
      { key: 'oasis_fomo_score', label: 'FOMO score', min: -0.2, max: 0.4 },
      { key: 'oasis_panic_score', label: 'Panic score', min: -0.5, max: 0.2 }
    ]
  }
]

const tuning = reactive({
  modelKind: 'multimodal_v1',
  horizon: '1d',
  ablationMode: 'market_text_oasis',
  decisionThreshold: 0.55,
  oasisSimulationId: '',
  weights: { ...DEFAULT_TUNING_WEIGHTS }
})
const activeWeightSet = ref(null)
const tuningLoadError = ref('')

const financialContext = computed(() => report.value?.financial_context || {})
const observed = computed(() => financialContext.value?.observed || {})
const inferred = computed(() => financialContext.value?.inferred || {})
const simulated = computed(() => financialContext.value?.simulated || {})
const forecast = computed(() => financialContext.value?.forecast || {})

const priceFacts = computed(() => observed.value?.price_facts || {})
const realNews = computed(() => observed.value?.real_news || [])
const realComments = computed(() => observed.value?.real_comments || [])
const drivers = computed(() => inferred.value?.drivers || [])
const divergences = computed(() => {
  const d = inferred.value?.divergence_signals || []
  return Array.isArray(d) ? d : []
})
const oasisPulses = computed(() => simulated.value?.oasis_pulses || [])
const agentScenarios = computed(() => simulated.value?.agent_scenarios || [])

const targetLabel = computed(() => {
  const ta = financialContext.value?.target_asset
  if (!ta || !ta.symbol) return '事件级（无标的）'
  return `${ta.symbol}${ta.market ? ' · ' + ta.market : ''}${ta.type ? ' · ' + ta.type : ''}`
})
const targetSymbol = computed(() => {
  const ta = financialContext.value?.target_asset || {}
  const fallback = forecast.value?.stock_forecast?.symbol || forecast.value?.crypto_forecast?.symbol || ''
  const raw = ta.symbol || fallback
  return raw ? String(raw).trim().toUpperCase() : 'UNKNOWN'
})
const modeLabel = computed(() => {
  const m = financialContext.value?.mode
  return m === 'asset' ? 'Asset Mode' : (m === 'event' ? 'Event Mode' : 'Mode —')
})

const directionLabel = computed(() => ({ up: '上涨', down: '下跌', bullish: '看多', bearish: '看空', neutral: '中性' }[(forecast.value.direction || 'neutral').toLowerCase()] || forecast.value.direction))
const directionIcon = computed(() => {
  const d = (forecast.value.direction || 'neutral').toLowerCase()
  if (['up', 'bullish'].includes(d)) return '▲'
  if (['down', 'bearish'].includes(d)) return '▼'
  return '◆'
})
const forecastDirectionClass = computed(() => {
  const d = (forecast.value.direction || 'neutral').toLowerCase()
  if (['up', 'bullish'].includes(d)) return 'dir-up'
  if (['down', 'bearish'].includes(d)) return 'dir-down'
  return 'dir-neutral'
})
const probabilityPct = computed(() => {
  const p = forecast.value.probability
  return p == null ? '—' : (p * 100).toFixed(1) + '%'
})
const confidenceLabel = computed(() => ({ low: '低', medium: '中', high: '高' }[(forecast.value.confidence || 'medium').toLowerCase()] || forecast.value.confidence))
const horizonLabel = computed(() => forecast.value.horizon || '—')
const targetPriceRange = computed(() => {
  const r = forecast.value.target_price_range
  if (!r) return ''
  if (Array.isArray(r) && r.length === 2) return `${formatNumber(r[0])} ~ ${formatNumber(r[1])}`
  if (typeof r === 'object' && r.low != null && r.high != null) {
    const mid = r.mid != null ? ` / mid ${formatNumber(r.mid)}` : ''
    return `${formatNumber(r.low)} ~ ${formatNumber(r.high)}${mid}`
  }
  return String(r)
})
const riskCaveats = computed(() => Array.isArray(forecast.value.risk_caveats) ? forecast.value.risk_caveats : [])
const rationale = computed(() => forecast.value?.rationale || '')

const preciseForecast = computed(() => {
  const existing = forecast.value?.precise_forecast
  return existing || null
})
const preciseModeLabel = computed(() => preciseForecast.value?.mode || 'foundation')
const isFoundationPrecise = computed(() => ['kronos+chronos', 'kronos_only', 'chronos_only'].includes(String(preciseModeLabel.value).toLowerCase()))
const preciseModelLabel = computed(() => {
  const mode = String(preciseModeLabel.value).toLowerCase()
  if (mode === 'kronos+chronos') return 'Kronos + Chronos-Bolt'
  if (mode === 'kronos_only') return 'Kronos'
  if (mode === 'chronos_only') return 'Chronos-Bolt'
  return '参考价格点'
})
const precisePriceLabel = computed(() => isFoundationPrecise.value ? '模型预测价格' : '参考价格')
const preciseExpectedReturnPct = computed(() => {
  const v = preciseForecast.value?.expected_return
  return v == null ? null : (v * 100).toFixed(2) + '%'
})
const preciseAgreementPct = computed(() => {
  const v = preciseForecast.value?.cross_model_agreement
  return v == null ? null : (v * 100).toFixed(0) + '%'
})

const composite = computed(() => extractComposite(financialContext.value))
const compositeColor = computed(() => {
  const v = composite.value
  if (v > 0.05) return '#26A269'
  if (v < -0.05) return '#C0392B'
  return '#64748B'
})

const qualityBadges = computed(() => {
  const dq = financialContext.value?.data_quality || {}
  const out = []
  if (dq.market_rows != null) out.push(`market ${dq.market_rows}`)
  if (dq.sentiment_count != null) out.push(`senti ${dq.sentiment_count}`)
  if (dq.news != null) out.push(`news ${dq.news ? '✓' : '—'}`)
  if (dq.derivatives != null) out.push(`deriv ${dq.derivatives ? '✓' : '—'}`)
  return out
})

const activeWeightSetLabel = computed(() => {
  if (activeWeightSet.value?.name) return activeWeightSet.value.name
  return `Built-in defaults for ${targetSymbol.value}`
})

const priceSpark = computed(() => buildPriceSparkline(financialContext.value))
const candleData = computed(() => buildCandlestick(financialContext.value))
const hasOhlcv = computed(() => candleData.value.data.length >= 5)
const hasSentimentTimeline = computed(() => (inferred.value?.sentiment_timeline || []).length > 0)

const candleOption = computed(() => {
  const ma20 = priceFacts.value?.ma20
  const ma60 = priceFacts.value?.ma60
  const markLines = []
  if (ma20 != null) markLines.push({ yAxis: ma20, name: 'MA20', lineStyle: { color: '#F59E0B', type: 'dashed', width: 1.2 }, label: { formatter: 'MA20', color: '#F59E0B', position: 'insideEndTop', fontSize: 10 } })
  if (ma60 != null) markLines.push({ yAxis: ma60, name: 'MA60', lineStyle: { color: '#6366F1', type: 'dashed', width: 1.2 }, label: { formatter: 'MA60', color: '#6366F1', position: 'insideEndBottom', fontSize: 10 } })
  return {
    grid: { left: 60, right: 24, top: 32, bottom: 56 },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross', label: { show: true, backgroundColor: '#475569' } },
    },
    legend: { data: ['K 线'], top: 4, left: 'center', textStyle: { color: '#64748B', fontSize: 11 } },
    xAxis: {
      type: 'category',
      data: candleData.value.dates,
      name: '日期',
      nameLocation: 'middle',
      nameGap: 32,
      nameTextStyle: { color: '#94A3B8', fontSize: 11 },
      axisLabel: { fontSize: 10, color: '#94A3B8', rotate: 30 },
    },
    yAxis: {
      type: 'value',
      scale: true,
      name: '价格 (USD)',
      nameLocation: 'middle',
      nameGap: 48,
      nameTextStyle: { color: '#94A3B8', fontSize: 11 },
      axisLabel: { fontSize: 10, color: '#94A3B8' },
      splitLine: { lineStyle: { color: '#F1F5F9' } },
    },
    dataZoom: [{ type: 'inside' }],
    series: [{
      name: 'K 线',
      type: 'candlestick',
      data: candleData.value.data,
      itemStyle: {
        color: '#26A269', color0: '#C0392B',
        borderColor: '#26A269', borderColor0: '#C0392B',
      },
      markLine: markLines.length ? { silent: true, symbol: 'none', data: markLines } : undefined,
    }],
  }
})

const sentimentOption = computed(() => {
  const tl = inferred.value?.sentiment_timeline || []
  const data = tl.map(p => Number(p.score ?? p.compound ?? p.value ?? 0))
  return {
    grid: { left: 60, right: 24, top: 24, bottom: 56 },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross', label: { show: true, backgroundColor: '#475569' } },
    },
    xAxis: {
      type: 'category',
      data: tl.map(p => p.date || p.window || p.timestamp || ''),
      name: '时间窗口',
      nameLocation: 'middle',
      nameGap: 32,
      nameTextStyle: { color: '#94A3B8', fontSize: 11 },
      axisLabel: { fontSize: 10, color: '#94A3B8', rotate: 30 },
    },
    yAxis: {
      type: 'value',
      min: -1, max: 1,
      name: '情绪复合分 compound',
      nameLocation: 'middle',
      nameGap: 44,
      nameTextStyle: { color: '#94A3B8', fontSize: 11 },
      axisLabel: { fontSize: 10, color: '#94A3B8' },
      splitLine: { lineStyle: { color: '#F1F5F9' } },
    },
    series: [{
      name: 'compound',
      type: 'line',
      smooth: true,
      symbol: 'circle',
      symbolSize: 5,
      data,
      lineStyle: { color: '#6366F1', width: 2 },
      areaStyle: { color: 'rgba(99,102,241,.18)' },
      markArea: {
        silent: true,
        itemStyle: { opacity: 0.18 },
        data: [
          [{ yAxis: 0.1, itemStyle: { color: '#26A269' } }, { yAxis: 1 }],
          [{ yAxis: -1, itemStyle: { color: '#C0392B' } }, { yAxis: -0.1 }],
        ],
      },
      markLine: {
        silent: true,
        symbol: 'none',
        data: [{
          yAxis: 0,
          lineStyle: { color: '#94A3B8', type: 'dashed' },
          label: { formatter: '中性阈值 0', color: '#94A3B8', fontSize: 10, position: 'insideEndTop' },
        }],
      },
      markPoint: data.length ? {
        symbol: 'pin',
        symbolSize: 38,
        label: { fontSize: 10, color: '#FFF' },
        data: [
          { type: 'max', name: 'Max', itemStyle: { color: '#26A269' } },
          { type: 'min', name: 'Min', itemStyle: { color: '#C0392B' } },
          { name: 'Latest', xAxis: data.length - 1, yAxis: data[data.length - 1], itemStyle: { color: '#6366F1' } },
        ],
      } : undefined,
    }],
  }
})

const strategyNotes = computed(() => [
  { name: '技术-情绪复合因子', desc: '价格趋势/RSI/MA20-60 与新闻情绪 compound 加权融合，捕捉量价-舆情共振。' },
  { name: 'OASIS 模拟脉冲推演', desc: '基于多 Agent 模拟脉冲事件，计算 sentiment_shift，用于评估事件冲击的边际方向。' },
  { name: '加权融合 → 方向裁决', desc: 'composite > 0.15 判看涨；< -0.15 判看跌；中间区间为中性。confidence 由数据完整度自动评级。' },
  { name: '背离信号检测', desc: '当价格与情绪走势出现顶部/底部背离时触发警告，作为反转风险的注释。' },
])

// ===== 补充 computed: ohlcv 时间范围 / pulse 排序 / pulse 冲击图 / role 汇总 =====
const ohlcvRangeLabel = computed(() => {
  const dates = candleData.value.dates
  if (!dates.length) return '—'
  return `${dates[0]} → ${dates[dates.length - 1]}`
})

const sortedPulses = computed(() => {
  const list = oasisPulses.value || []
  const ts = (p) => {
    const v = p.time || p.timestamp || p.t || ''
    const n = new Date(v).getTime()
    return Number.isNaN(n) ? 0 : n
  }
  return [...list].sort((a, b) => ts(a) - ts(b))
})

const pulseShiftOption = computed(() => {
  const list = sortedPulses.value
  return {
    grid: { left: 60, right: 24, top: 16, bottom: 56 },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    xAxis: {
      type: 'category',
      data: list.map((p, i) => p.name || p.event || p.label || `pulse ${i + 1}`),
      name: '脉冲事件（按时间升序）',
      nameLocation: 'middle',
      nameGap: 36,
      nameTextStyle: { color: '#94A3B8', fontSize: 11 },
      axisLabel: { fontSize: 10, color: '#94A3B8', rotate: 25, interval: 0 },
    },
    yAxis: {
      type: 'value',
      name: 'Δ sentiment_shift',
      nameLocation: 'middle',
      nameGap: 44,
      nameTextStyle: { color: '#94A3B8', fontSize: 11 },
      axisLabel: { fontSize: 10, color: '#94A3B8' },
      splitLine: { lineStyle: { color: '#F1F5F9' } },
    },
    series: [{
      type: 'bar',
      barWidth: 18,
      data: list.map(p => {
        const v = Number(p.sentiment_shift ?? 0)
        return { value: v, itemStyle: { color: v > 0.05 ? '#26A269' : v < -0.05 ? '#C0392B' : '#94A3B8', borderRadius: [3, 3, 0, 0] } }
      }),
      markLine: { silent: true, symbol: 'none', data: [{ yAxis: 0, lineStyle: { color: '#94A3B8', type: 'dashed' } }] },
    }],
  }
})

const agentRoleSummary = computed(() => {
  const list = agentScenarios.value || []
  if (!list.length) return []
  const buckets = { buy: 0, sell: 0, hold: 0, other: 0 }
  for (const s of list) {
    const k = String(s.action || s.behavior || s.role || '').toLowerCase()
    if (k.includes('buy') || k.includes('long') || k.includes('买')) buckets.buy += 1
    else if (k.includes('sell') || k.includes('short') || k.includes('卖')) buckets.sell += 1
    else if (k.includes('hold') || k.includes('wait') || k.includes('观望') || k.includes('持')) buckets.hold += 1
    else buckets.other += 1
  }
  const out = []
  if (buckets.buy) out.push({ label: 'Buy', count: buckets.buy, cls: 'rb-buy' })
  if (buckets.sell) out.push({ label: 'Sell', count: buckets.sell, cls: 'rb-sell' })
  if (buckets.hold) out.push({ label: 'Hold', count: buckets.hold, cls: 'rb-hold' })
  if (buckets.other) out.push({ label: 'Other', count: buckets.other, cls: 'rb-other' })
  return out
})

const sections = computed(() => report.value?.outline?.sections || [])

function toggleCollapse (idx) {
  const next = new Set(collapsed.value)
  if (next.has(idx)) next.delete(idx); else next.add(idx)
  collapsed.value = next
}

function escapeHtml (s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;')
}
function inlineMd (text) {
  let s = escapeHtml(text)
  s = s.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
  s = s.replace(/(^|[^*])\*([^*]+)\*/g, '$1<em>$2</em>')
  s = s.replace(/`([^`]+)`/g, '<code>$1</code>')
  return s
}
function renderMd (text) {
  if (!text) return ''
  const lines = String(text).split(/\r?\n/)
  const out = []
  let inUl = false, inOl = false
  for (let raw of lines) {
    const line = raw.trimEnd()
    if (/^\s*$/.test(line)) {
      if (inUl) { out.push('</ul>'); inUl = false }
      if (inOl) { out.push('</ol>'); inOl = false }
      continue
    }
    let m
    if ((m = line.match(/^(#{1,6})\s+(.*)$/))) {
      if (inUl) { out.push('</ul>'); inUl = false }
      if (inOl) { out.push('</ol>'); inOl = false }
      out.push(`<h${m[1].length}>${inlineMd(m[2])}</h${m[1].length}>`)
      continue
    }
    if ((m = line.match(/^\s*[-*+]\s+(.*)$/))) {
      if (!inUl) { if (inOl) { out.push('</ol>'); inOl = false } out.push('<ul>'); inUl = true }
      out.push(`<li>${inlineMd(m[1])}</li>`); continue
    }
    if ((m = line.match(/^\s*\d+\.\s+(.*)$/))) {
      if (!inOl) { if (inUl) { out.push('</ul>'); inUl = false } out.push('<ol>'); inOl = true }
      out.push(`<li>${inlineMd(m[1])}</li>`); continue
    }
    if (inUl) { out.push('</ul>'); inUl = false }
    if (inOl) { out.push('</ol>'); inOl = false }
    out.push(`<p>${inlineMd(line)}</p>`)
  }
  if (inUl) out.push('</ul>')
  if (inOl) out.push('</ol>')
  return out.join('\n')
}

function formatNumber (v) {
  if (v == null || Number.isNaN(Number(v))) return '-'
  return Number(v).toLocaleString(undefined, { maximumFractionDigits: 4 })
}
function formatScore (v) {
  if (v == null || Number.isNaN(Number(v))) return '-'
  const n = Number(v)
  return `${n >= 0 ? '+' : ''}${n.toFixed(2)}`
}
function formatPct (v) {
  if (v == null || Number.isNaN(Number(v))) return '-'
  return `${(Number(v) * 100).toFixed(2)}%`
}
function scoreColor (v) {
  const n = Number(v)
  if (n > 0.05) return '#26A269'
  if (n < -0.05) return '#C0392B'
  return '#64748B'
}
function driverClass (d) {
  const c = Number(d.compound ?? 0)
  return c > 0.1 ? 'pos' : c < -0.1 ? 'neg' : 'neu'
}
function driverColor (d) { return scoreColor(d.compound) }

function clampNumber (v, fallback = 0) {
  const n = Number(v)
  return Number.isFinite(n) ? n : fallback
}

function applyTuningWeights (weights = {}) {
  Object.assign(tuning.weights, DEFAULT_TUNING_WEIGHTS, weights || {})
}

function resetTuningToDefaults () {
  activeWeightSet.value = null
  tuningLoadError.value = ''
  tuning.modelKind = 'multimodal_v1'
  tuning.horizon = '1d'
  tuning.ablationMode = 'market_text_oasis'
  tuning.decisionThreshold = 0.55
  tuning.oasisSimulationId = props.simulationId || ''
  applyTuningWeights()
}

function formatWeight (v) {
  const n = clampNumber(v)
  return `${n >= 0 ? '+' : ''}${n.toFixed(2)}`
}

function weightTone (v) {
  const n = clampNumber(v)
  if (n > 0.001) return 'pos'
  if (n < -0.001) return 'neg'
  return 'neu'
}

function sanitizedWeights () {
  const out = {}
  for (const [key, val] of Object.entries({ ...DEFAULT_TUNING_WEIGHTS, ...tuning.weights })) {
    out[key] = Number(clampNumber(val).toFixed(4))
  }
  return out
}

async function loadActiveTuningConfig () {
  tuningLoadError.value = ''
  tuning.oasisSimulationId = props.simulationId || ''
  activeWeightSet.value = null
  applyTuningWeights()
}

function goBacktest () {
  const oasisId = (tuning.oasisSimulationId || '').trim()
  const strategyCfg = {
    model_kind: tuning.modelKind,
    horizon: tuning.horizon,
    ablation_mode: tuning.ablationMode,
    decision_threshold: clampNumber(tuning.decisionThreshold, 0.55)
  }
  if (oasisId) strategyCfg.oasis_simulation_id = oasisId

  const payload = {
    source: 'financial_report',
    report_id: props.reportId || report.value?.report_id || '',
    simulation_id: props.simulationId || report.value?.simulation_id || '',
    symbol: normalizeQuantSymbol(targetSymbol.value),
    pair: normalizeQuantSymbol(targetSymbol.value),
    interval: '1d',
    model_family: 'price_point_calibrated_ml',
    model_kind: tuning.modelKind,
    horizon: tuning.horizon,
    ablation_mode: tuning.ablationMode,
    oasis_simulation_id: oasisId || null,
    factor_weights: sanitizedWeights(),
    strategy_cfg: strategyCfg
  }
  sessionStorage.setItem('finrex_quant_backtest_prefill', JSON.stringify(payload))
  router.push({
    name: 'QuantBacktestLab',
    query: { prefill: 'financial', report_id: payload.report_id }
  })
}

function normalizeQuantSymbol (value) {
  const raw = String(value || '').trim().toUpperCase()
  if (raw === 'BTC' || raw === 'BTCUSD' || raw === 'BTCUSDT' || raw === 'BTC-USD') return 'BTC-USDT'
  if (raw === 'ETH' || raw === 'ETHUSD' || raw === 'ETHUSDT' || raw === 'ETH-USD') return 'ETH-USDT'
  return raw
}

async function load () {
  if (!props.reportId) { report.value = null; return }
  loading.value = true
  error.value = ''
  try {
    const res = await getReport(props.reportId)
    if (res.success) report.value = res.data
    else error.value = res.error || '加载失败'
  } catch (e) {
    error.value = e.message || String(e)
  } finally {
    loading.value = false
  }
}

async function loadReportAndTuning () {
  await load()
  await loadActiveTuningConfig()
}

watch(() => props.reportId, loadReportAndTuning)
watch(() => props.simulationId, (id) => {
  if (!activeWeightSet.value) tuning.oasisSimulationId = id || ''
})
onMounted(loadReportAndTuning)
</script>

<style scoped>
.fin-report {
  height: 100%;
  overflow: auto;
  padding: 20px;
  background: #F8FAFC;
  font-family: 'Space Grotesk', 'Noto Sans SC', system-ui, sans-serif;
  color: #111;
}
.fin-status { padding: 32px; text-align: center; color: #666; }
.fin-status.error { color: #c0392b; }
.fin-status.muted { color: #999; }
.spinner { display: inline-block; width: 14px; height: 14px; border: 2px solid #ddd; border-top-color: #111; border-radius: 50%; animation: spin .8s linear infinite; margin-right: 8px; vertical-align: middle; }
@keyframes spin { to { transform: rotate(360deg); } }

.fin-header { background: #FFF; border-radius: 12px; padding: 18px 20px; margin-bottom: 16px; border: 1px solid #E5E7EB; }
.fin-meta { display: flex; flex-wrap: wrap; gap: 8px; font-size: 11px; color: #64748B; align-items: center; }
.fin-tag { background: #111; color: #FFF; padding: 3px 10px; border-radius: 4px; letter-spacing: .05em; font-weight: 700; }
.fin-id, .fin-mode { font-family: monospace; }
.fin-badge { background: #F1F5F9; padding: 2px 8px; border-radius: 4px; font-family: monospace; }
.fin-title { margin: 12px 0 6px; font-size: 24px; font-weight: 700; }
.fin-sub { color: #475569; margin: 0; font-size: 14px; line-height: 1.5; }

/* Section A */
.summary-grid { display: grid; grid-template-columns: 1.4fr 1fr; gap: 18px; }
.summary-main { padding: 18px; border-radius: 10px; border: 1px solid #E5E7EB; background: #FAFAFA; }
.summary-main.dir-up { border-color: #26A269; background: #F1FAF5; }
.summary-main.dir-down { border-color: #C0392B; background: #FFF6F5; }
.summary-main.dir-neutral { border-color: #94A3B8; background: #F8FAFC; }
.sm-asset { color: #64748B; font-size: 12px; margin-bottom: 8px; }
.sm-direction { font-size: 36px; font-weight: 700; line-height: 1; margin-bottom: 12px; }
.sm-meta { display: flex; gap: 18px; font-size: 13px; color: #475569; margin-bottom: 12px; }
.sm-meta b { color: #111; }
.sm-range, .sm-composite { display: flex; justify-content: space-between; padding: 8px 0; border-top: 1px dashed rgba(0,0,0,.1); font-size: 13px; }
.sm-range strong, .sm-composite strong { font-family: monospace; }
.sm-precise { margin-top: 8px; padding: 10px; border: 1px solid rgba(64, 120, 192, 0.25); background: rgba(64, 120, 192, 0.06); border-radius: 8px; }
.sm-precise.is-fallback { border-color: rgba(100, 116, 139, 0.25); background: rgba(100, 116, 139, 0.06); }
.sm-precise-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; font-size: 11px; }
.precise-tag { background: #4078c0; color: #fff; padding: 2px 8px; border-radius: 4px; font-weight: 600; letter-spacing: 0.5px; }
.sm-precise.is-fallback .precise-tag { background: #64748B; }
.precise-agree { color: #4078c0; font-weight: 600; }
.sm-precise-row { display: flex; justify-content: space-between; padding: 4px 0; font-size: 12px; }
.sm-precise-row strong { font-family: monospace; color: #1c2638; }
.sm-precise-row .precise-warning { max-width: 68%; text-align: right; white-space: normal; line-height: 1.35; color: #64748B; font-family: inherit; font-size: 11px; }

/* Section B tuning */
.tuning-shell { display: grid; grid-template-columns: minmax(0, 1fr) 300px; gap: 16px; align-items: start; }
.tuning-main { display: grid; gap: 14px; }
.tuning-row { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
.tuning-row label, .tuning-oasis { display: flex; flex-direction: column; gap: 5px; font-size: 12px; color: #64748B; }
.tuning-row span, .tuning-oasis span { font-weight: 700; color: #334155; }
.tuning-row select, .tuning-row input, .tuning-oasis input { width: 100%; min-height: 34px; border: 1px solid #CBD5E1; border-radius: 6px; padding: 6px 9px; color: #0F172A; background: #FFF; font-size: 13px; }
.tuning-row select:focus, .tuning-row input:focus, .tuning-oasis input:focus { outline: 2px solid rgba(15,23,42,.12); border-color: #111827; }
.weight-sliders { display: grid; grid-template-columns: 1fr; gap: 12px; }
.slider-group { border: 1px solid #E5E7EB; border-radius: 8px; background: #FFF; padding: 12px; }
.slider-group-head { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; margin-bottom: 8px; }
.slider-group-head strong { font-size: 13px; color: #111827; }
.slider-group-head span { color: #94A3B8; font-size: 11px; }
.slider-line { display: grid; grid-template-columns: 210px minmax(0, 1fr); gap: 12px; align-items: center; padding: 7px 0; border-top: 1px solid #F1F5F9; }
.slider-line:first-of-type { border-top: none; }
.slider-label { display: flex; justify-content: space-between; gap: 8px; min-width: 0; font-size: 12px; color: #475569; }
.slider-label span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.slider-label strong { font-family: monospace; }
.slider-label strong.pos { color: #26A269; }
.slider-label strong.neg { color: #C0392B; }
.slider-label strong.neu { color: #64748B; }
.slider-line input[type="range"] { width: 100%; accent-color: #111827; }
.tuning-side { position: sticky; top: 8px; display: grid; gap: 12px; border: 1px solid #111827; border-radius: 8px; background: #111827; color: #E5E7EB; padding: 14px; }
.tuning-source { display: grid; gap: 4px; }
.tuning-source span, .tuning-kv span { color: #94A3B8; font-size: 11px; text-transform: uppercase; letter-spacing: .04em; }
.tuning-source strong { color: #FFF; font-size: 15px; }
.tuning-source em { color: #FCD34D; font-size: 11px; font-style: normal; line-height: 1.4; }
.tuning-kv { display: grid; grid-template-columns: 92px minmax(0, 1fr); gap: 6px 10px; border-top: 1px solid rgba(255,255,255,.12); border-bottom: 1px solid rgba(255,255,255,.12); padding: 10px 0; font-size: 12px; }
.tuning-kv strong { color: #FFF; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tuning-kv .mono { font-family: monospace; }
.tuning-actions { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.tuning-actions button { min-height: 36px; border-radius: 6px; padding: 0 10px; font-weight: 800; font-size: 12px; cursor: pointer; }
.btn-secondary { border: 1px solid rgba(255,255,255,.28); background: transparent; color: #E5E7EB; }
.btn-primary { border: 1px solid #FFF; background: #FFF; color: #111827; }
.tuning-note { margin: 0; color: #CBD5E1; font-size: 11px; line-height: 1.5; }

/* Section C */
.pipeline-foot { margin-top: 16px; border-top: 1px dashed #E5E7EB; padding-top: 12px; }

/* Panel notes (C/D 顶部) */
.panel-note { background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; padding: 10px 14px; margin-bottom: 12px; display: grid; gap: 6px; font-size: 12px; color: #475569; line-height: 1.6; }
.panel-note .pn-row { display: grid; grid-template-columns: 80px 1fr; gap: 12px; align-items: start; }
.panel-note .pn-tag { background: #6366F1; color: #FFF; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 700; text-align: center; height: fit-content; }
.panel-note b { color: #111; }
.panel-note code { background: #E2E8F0; padding: 1px 5px; border-radius: 3px; font-family: monospace; color: #4F46E5; font-size: 11px; }
.panel-note .col-up { color: #26A269; font-weight: 700; }
.panel-note .col-down { color: #C0392B; font-weight: 700; }
.sub-note { font-size: 11px; color: #94A3B8; margin: 8px 0 6px; padding-left: 4px; border-left: 2px solid #CBD5E1; padding-left: 8px; }

/* Section C */
.observed-grid { display: grid; grid-template-columns: 2fr 1fr; gap: 14px; margin-bottom: 14px; }
.observed-chart { background: #FFF; border: 1px solid #E5E7EB; border-radius: 8px; padding: 8px; min-height: 280px; }
.observed-side { display: grid; gap: 10px; }
.placeholder { padding: 16px; }
.placeholder-empty { padding: 24px; color: #94A3B8; text-align: center; font-size: 13px; }
.ph-row { display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px dashed #E5E7EB; font-size: 13px; }
.ph-row strong { font-family: monospace; }
.kv-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
.kv-grid div { background: #FFF; border: 1px solid #E5E7EB; border-radius: 6px; padding: 8px 10px; }
.kv-grid span { display: block; color: #64748B; font-size: 11px; margin-bottom: 2px; }
.kv-grid strong { color: #111; font-size: 13px; }
.kv-grid .mono { font-family: monospace; }
.news-comments { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.news-col h4, .comments-col h4 { margin: 0 0 8px; font-size: 13px; color: #111; }
.news-list { margin: 0; padding-left: 16px; font-size: 12px; color: #475569; }
.news-list li { margin-bottom: 4px; }
.news-list a { color: #0EA5E9; text-decoration: none; }
.news-list em { color: #94A3B8; font-style: normal; margin-left: 6px; font-size: 11px; }
.comments-col blockquote { margin: 0 0 8px; padding: 8px 12px; border-left: 3px solid #6366F1; background: #FFF; font-size: 12px; color: #475569; border-radius: 4px; }
.comments-col cite { display: block; margin-top: 4px; color: #94A3B8; font-size: 11px; font-style: normal; }

/* Section D */
.inferred-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.senti-chart { background: #FFF; border: 1px solid #E5E7EB; border-radius: 8px; padding: 8px; }
.senti-meta { padding: 6px 8px; font-size: 12px; color: #64748B; display: flex; gap: 14px; }
.senti-meta b { color: #111; font-family: monospace; }
.drivers-table h4 { margin: 0 0 8px; font-size: 13px; }
.drivers-table table { width: 100%; border-collapse: collapse; font-size: 12px; background: #FFF; border-radius: 6px; overflow: hidden; }
.drivers-table th { text-align: left; padding: 6px 8px; background: #F1F5F9; color: #64748B; font-weight: 600; }
.drivers-table td { padding: 6px 8px; border-top: 1px solid #F1F5F9; }
.drivers-table .mono { font-family: monospace; }
.drivers-table .pos { color: #26A269; }
.drivers-table .neg { color: #C0392B; }
.drivers-table .neu { color: #475569; }
.divergence-row { margin-top: 12px; padding: 8px 12px; background: #FEF3C7; border: 1px solid #F59E0B; border-radius: 6px; display: flex; gap: 8px; flex-wrap: wrap; align-items: center; font-size: 12px; }
.div-label { font-weight: 700; color: #92400E; }
.div-tag { background: #FFF; padding: 2px 8px; border-radius: 4px; color: #92400E; font-family: monospace; }

/* Section E */
.pulses h4, .scenarios h4 { margin: 12px 0 8px; font-size: 13px; }
.pulse-list { list-style: none; padding: 0; margin: 0; display: grid; gap: 6px; }
.pulse-list li { display: grid; grid-template-columns: 80px 1fr auto; gap: 8px; padding: 8px 12px; background: #FFF; border: 1px solid #E5E7EB; border-radius: 6px; font-size: 12px; align-items: center; }
.pulse-list .p-time { font-family: monospace; color: #64748B; font-size: 11px; }
.pulse-list .p-name { color: #111; }
.pulse-list em { font-style: normal; font-family: monospace; }
.scenario-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 10px; }
.scenario-card { background: #FFF; border: 1px solid #E5E7EB; border-radius: 8px; padding: 10px 12px; }
.scenario-card strong { display: block; color: #6366F1; font-size: 12px; margin-bottom: 6px; }
.scenario-card p { margin: 0; font-size: 12px; color: #475569; line-height: 1.5; }

/* Section E extras */
.role-badges { display: flex; gap: 8px; flex-wrap: wrap; margin: 8px 0 12px; }
.role-badge { padding: 4px 12px; border-radius: 999px; font-size: 12px; font-weight: 700; border: 1px solid; }
.role-badge.rb-buy { color: #166534; background: #DCFCE7; border-color: #86EFAC; }
.role-badge.rb-sell { color: #991B1B; background: #FEE2E2; border-color: #FCA5A5; }
.role-badge.rb-hold { color: #92400E; background: #FEF3C7; border-color: #FCD34D; }
.role-badge.rb-other { color: #475569; background: #F1F5F9; border-color: #CBD5E1; }
.sim-footnote { margin-top: 12px; padding: 8px 12px; background: #FEF2F2; border: 1px solid #FCA5A5; border-radius: 6px; color: #991B1B; font-size: 11px; font-weight: 600; text-align: center; }

/* Section F */
.rs-grid { display: grid; grid-template-columns: 1fr 1.2fr; gap: 18px; }
.rs-grid h4 { margin: 0 0 8px; font-size: 13px; }
.risk-list { margin: 0; padding: 0; list-style: none; display: grid; gap: 6px; }
.risk-list li { padding: 8px 12px; border-left: 3px solid #C0392B; background: #FFF6F5; border-radius: 4px; font-size: 12px; color: #7F1D1D; }
.strategy-list { margin: 0 0 12px; padding: 0; list-style: none; display: grid; gap: 6px; }
.strategy-list li { padding: 8px 12px; background: #FFF; border-left: 3px solid #6366F1; border-radius: 4px; font-size: 12px; }
.strategy-list b { display: block; color: #6366F1; margin-bottom: 2px; }
.strategy-list span { color: #475569; }
.rationale-box { padding: 10px 12px; background: #F8FAFC; border-left: 3px solid #94A3B8; border-radius: 4px; font-size: 12px; color: #475569; line-height: 1.6; margin: 0; }

/* Section G original report */
.fin-sections { background: #FFF; border-radius: 8px; padding: 8px 12px; }
.fin-section { border-top: 1px solid #EAEAEA; padding: 12px 0; }
.fin-section:first-child { border-top: none; }
.fin-section-head { display: flex; align-items: center; gap: 12px; cursor: pointer; user-select: none; }
.fin-section-head .num { font-family: monospace; color: #888; }
.fin-section-head h3 { flex: 1; margin: 0; font-size: 15px; font-weight: 700; }
.fin-section-head .chev { color: #888; font-family: monospace; }
.fin-section-body { padding: 8px 4px 6px 32px; font-size: 13px; }
.markdown-body :deep(p) { line-height: 1.6; margin: 6px 0; }
.markdown-body :deep(ul) { padding-left: 20px; }
.muted { color: #94A3B8; font-size: 12px; }

@media (max-width: 980px) {
  .summary-grid, .tuning-shell, .observed-grid, .news-comments, .inferred-grid, .rs-grid { grid-template-columns: 1fr; }
  .tuning-row { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .tuning-side { position: static; }
}
@media (max-width: 640px) {
  .tuning-row, .slider-line { grid-template-columns: 1fr; }
}
</style>
