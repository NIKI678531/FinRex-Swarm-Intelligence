<template>
  <section :id="sectionId" class="asset-allocation-section">
    <header class="section-head">
      <div>
        <UiBadge tone="brand" dot>Asset Allocation</UiBadge>
        <h2>南方东英 ETF · 资产配置 Dashboard</h2>
        <p class="muted">
          以本报告主题信号 + 量化技术指标投票引擎为基础，输出未来 {{ horizonLabel }} 的 CSOP ETF 推荐组合与销售要点。
          <span v-if="bundle?.generated_at" class="muted-strong">
            · 生成于 {{ formatTime(bundle.generated_at) }}
          </span>
        </p>
      </div>
      <div class="head-actions">
        <UiSegmented
          v-model="horizon"
          :options="horizonOptions"
          size="sm"
          @update:modelValue="onHorizonChange"
        />
        <UiButton size="sm" variant="ghost" :disabled="refreshing" @click="refresh">
          {{ refreshing ? '更新中…' : '重新计算' }}
        </UiButton>
      </div>
    </header>

    <div v-if="loading && !bundle" class="state-card">正在装配资产配置…</div>
    <div v-else-if="error" class="state-card error">{{ error }}</div>

    <template v-else-if="bundle">
      <!-- KPI strip -->
      <div class="kpi-strip">
        <div class="kpi-cell" :class="kpiTone(bundle.kpis.expected_return_pct)">
          <span>组合{{ horizonLabel }}预期收益</span>
          <strong>{{ formatPct(bundle.kpis.expected_return_pct) }}</strong>
        </div>
        <div class="kpi-cell">
          <span>平均置信度</span>
          <strong>{{ Math.round((bundle.kpis.avg_confidence || 0) * 100) }}%</strong>
        </div>
        <div class="kpi-cell">
          <span>看多 / 中性 / 看空</span>
          <strong>
            {{ bundle.kpis.bullish_count }} / {{ bundle.kpis.neutral_count }} / {{ bundle.kpis.bearish_count }}
          </strong>
        </div>
        <div class="kpi-cell" :class="riskTone(bundle.kpis.portfolio_risk_tier)">
          <span>组合风险等级</span>
          <strong>{{ riskLabel(bundle.kpis.portfolio_risk_tier) }}</strong>
        </div>
      </div>

      <!-- Theme chips -->
      <div class="theme-chips" v-if="bundle.themes_used?.length">
        <span class="muted">命中主题：</span>
        <UiChip v-for="t in bundle.themes_used" :key="t.key">
          {{ themeLabel(t.key) }}
          <small>· {{ Math.round(t.strength * 100) }}%</small>
        </UiChip>
      </div>

      <div class="dashboard-grid">
        <!-- Top picks: ETF cards -->
        <div class="picks-col">
          <h3 class="block-title">
            <span>核心推荐 ETF</span>
            <small class="muted">{{ horizonLabel }}方向 · 置信度 · 历史胜率 · 推荐权重</small>
          </h3>
          <div class="picks-grid" v-if="bundle.top_picks?.length">
            <article
              v-for="pick in bundle.top_picks"
              :key="pick.code"
              class="pick-card"
              :class="['dir-' + (pick.direction || 'na')]"
              @click="openDrawer(pick)"
            >
              <header class="pick-head">
                <div>
                  <strong>{{ pick.code }}</strong>
                  <small class="muted">{{ pick.asset_class }}</small>
                </div>
                <span class="pick-arrow">{{ directionArrow(pick.direction) }}</span>
              </header>
              <h4 class="pick-name">{{ pick.name_zh }}</h4>
              <p class="pick-en muted">{{ pick.name_en }}</p>

              <div class="hit-badge" v-if="pick.backtest && pick.backtest.directional_samples >= 10">
                <span class="hit-label">历史胜率</span>
                <strong :class="hitTone(pick.backtest.hit_rate)">{{ Math.round((pick.backtest.hit_rate || 0) * 100) }}%</strong>
                <small class="muted">{{ pick.backtest.directional_samples }} 样本</small>
              </div>

              <div class="pick-row">
                <span>方向</span>
                <strong>{{ directionLabel(pick.direction) }}</strong>
              </div>
              <div class="pick-row">
                <span>置信度</span>
                <div class="conf-bar">
                  <div class="conf-fill" :style="{ width: ((pick.confidence || 0) * 100) + '%' }"></div>
                </div>
                <strong>{{ Math.round((pick.confidence || 0) * 100) }}%</strong>
              </div>
              <div class="pick-row">
                <span>{{ horizonLabel }}预期</span>
                <strong>
                  {{ formatPct(pick.expected_return_pct?.central) }}
                  <small class="muted">
                    [{{ formatPct(pick.expected_return_pct?.lower) }} ~ {{ formatPct(pick.expected_return_pct?.upper) }}]
                  </small>
                </strong>
              </div>
              <div class="pick-row">
                <span>建议权重</span>
                <strong>{{ formatWeight(pick.code) }}</strong>
              </div>
              <div class="pick-tags">
                <UiChip v-for="tag in pick.theme_tags" :key="tag" tone="muted" size="sm">{{ themeLabel(tag) }}</UiChip>
                <UiChip :tone="riskChipTone(pick.risk_tier)" size="sm">风险 {{ riskLabel(pick.risk_tier) }}</UiChip>
              </div>
            </article>
          </div>
          <div v-else class="state-card">暂无推荐：上游主题信号或行情数据不足。</div>
        </div>

        <!-- Allocation pie + sales brief -->
        <div class="side-col">
          <h3 class="block-title"><span>建议配置权重</span></h3>
          <UiCard v-if="allocationItems.length">
            <EChart :option="pieOption" height="280px" />
            <ul class="alloc-list">
              <li v-for="it in allocationItems" :key="it.code">
                <span class="dot" :style="{ background: colorFor(it.code) }"></span>
                <strong>{{ it.code }}</strong>
                <small class="muted">{{ it.name_zh }}</small>
                <span class="weight">{{ (it.weight * 100).toFixed(1) }}%</span>
              </li>
            </ul>
          </UiCard>
          <div v-else class="state-card">无可分配权重。</div>

          <h3 class="block-title" style="margin-top: 24px">
            <span>销售要点 · Sales Brief</span>
          </h3>
          <UiCard>
            <pre class="sales-brief">{{ bundle.sales_brief }}</pre>
          </UiCard>

          <div v-if="avoidList.length" class="avoid-card">
            <h4>建议规避</h4>
            <ul>
              <li v-for="it in avoidList" :key="it.code">
                <strong>{{ it.code }}</strong> {{ it.name_zh }}
                <small class="muted">— {{ it.reason }}</small>
              </li>
            </ul>
          </div>
        </div>
      </div>

      <p class="disclaimer muted">
        免责声明：此处展示的方向预测、置信度、配置权重均由规则化技术指标投票引擎与本报告主题信号融合生成，
        仅作销售辅助参考，不构成任何投资建议。最终决策应结合客户风险承受能力、合规审核及市场实时变化。
      </p>
    </template>

    <EtfDetailDrawer
      v-if="drawerOpen"
      :code="drawerCode"
      :name-zh="drawerName"
      :horizon="horizon"
      @close="drawerOpen = false"
    />
  </section>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { UiBadge, UiButton, UiCard, UiChip, UiSegmented } from '@/components/ui'
import EChart from '@/components/report/widgets/EChart.vue'
import EtfDetailDrawer from '@/components/report/EtfDetailDrawer.vue'
import { getAssetAllocation, regenerateAssetAllocation } from '@/api/assetAllocation'

const props = defineProps({
  reportId: { type: String, required: true },
  sectionId: { type: String, default: 's5-allocation' }
})

const bundle = ref(null)
const loading = ref(false)
const refreshing = ref(false)
const error = ref('')
const drawerOpen = ref(false)
const drawerCode = ref('')
const drawerName = ref('')
const horizon = ref('1w')

const horizonOptions = [
  { value: '1w', label: '1周' },
  { value: '2w', label: '2周' },
  { value: '1m', label: '1月' }
]
const HORIZON_LABEL_MAP = { '1w': '5日', '2w': '10日', '1m': '21日' }
const horizonLabel = computed(() => HORIZON_LABEL_MAP[horizon.value] || '5日')

const PALETTE = ['#5B8DEF', '#2BC4A1', '#F4A23C', '#E5685A', '#9B7BD8', '#3CC5C9', '#F275B8', '#6FCB7C']

const THEME_LABELS = {
  crypto: '加密',
  us_tech: '美股科技',
  china_policy: '中国政策',
  tech_growth: '科技成长',
  macro_risk: '宏观风险',
  safe_haven: '避险'
}

const RISK_LABELS = {
  low: '低', mid: '中', high: '高', very_high: '极高', 'n/a': '—'
}

function themeLabel (k) { return THEME_LABELS[k] || k }
function riskLabel (k)  { return RISK_LABELS[k] || k }
function riskChipTone (k) { return k === 'low' ? 'success' : k === 'very_high' ? 'danger' : k === 'high' ? 'warning' : 'muted' }
function riskTone (k) { return 'risk-' + (k || 'mid') }
function kpiTone (v) { return typeof v === 'number' && v < 0 ? 'kpi-bear' : typeof v === 'number' && v > 0 ? 'kpi-bull' : '' }
function hitTone (rate) {
  if (rate === null || rate === undefined) return ''
  if (rate >= 0.55) return 'hit-good'
  if (rate >= 0.45) return 'hit-mid'
  return 'hit-bad'
}

function directionLabel (d) {
  return ({ bullish: '看多', neutral: '中性', bearish: '看空' }[d]) || '—'
}
function directionArrow (d) {
  return ({ bullish: '▲', neutral: '◆', bearish: '▼' }[d]) || '—'
}
function formatPct (v) {
  if (v === null || v === undefined || Number.isNaN(v)) return '—'
  return (v >= 0 ? '+' : '') + Number(v).toFixed(2) + '%'
}
function formatTime (iso) {
  if (!iso) return ''
  try { return new Date(iso).toLocaleString('zh-CN') } catch (e) { return iso }
}

const allocationItems = computed(() => bundle.value?.allocation?.items || [])
const avoidList = computed(() => bundle.value?.allocation?.avoid || [])

const weightLookup = computed(() => {
  const map = {}
  for (const it of allocationItems.value) map[it.code] = it.weight
  return map
})
function formatWeight (code) {
  const w = weightLookup.value[code]
  return w !== undefined ? (w * 100).toFixed(1) + '%' : '—'
}

const colorMap = computed(() => {
  const m = {}
  allocationItems.value.forEach((it, i) => { m[it.code] = PALETTE[i % PALETTE.length] })
  return m
})
function colorFor (code) { return colorMap.value[code] || '#9aa6b8' }

const pieOption = computed(() => ({
  tooltip: { trigger: 'item', formatter: '{b}<br/>{c}% ({d}%)' },
  legend: { show: false },
  series: [{
    type: 'pie',
    radius: ['45%', '72%'],
    avoidLabelOverlap: true,
    itemStyle: { borderColor: '#fff', borderWidth: 2 },
    label: { show: true, formatter: '{b}\n{d}%', fontSize: 11 },
    data: allocationItems.value.map(it => ({
      name: it.code,
      value: Number((it.weight * 100).toFixed(2)),
      itemStyle: { color: colorFor(it.code) }
    }))
  }]
}))

async function load (silent = false) {
  if (!props.reportId) return
  if (!silent) loading.value = true
  error.value = ''
  try {
    const res = await getAssetAllocation(props.reportId, { horizon: horizon.value })
    bundle.value = res.data
  } catch (err) {
    error.value = err?.response?.data?.error || err.message || '资产配置数据暂不可用。'
  } finally {
    loading.value = false
  }
}

async function refresh () {
  refreshing.value = true
  error.value = ''
  try {
    const res = await regenerateAssetAllocation(props.reportId, { horizon: horizon.value })
    bundle.value = res.data
  } catch (err) {
    error.value = err?.response?.data?.error || err.message || '重新计算失败。'
  } finally {
    refreshing.value = false
  }
}

function onHorizonChange () {
  load(true)
}

function openDrawer (pick) {
  drawerCode.value = pick.code
  drawerName.value = pick.name_zh
  drawerOpen.value = true
}

onMounted(load)
watch(() => props.reportId, () => load(true))
</script>

<style scoped>
.asset-allocation-section {
  display: flex; flex-direction: column; gap: 20px;
  padding: 24px 28px; background: #fff; border-radius: 16px;
  box-shadow: 0 4px 20px rgba(15, 23, 42, 0.04);
  margin-top: 32px;
}
.section-head {
  display: flex; align-items: flex-start; justify-content: space-between; gap: 16px;
}
.section-head h2 { margin: 8px 0 4px; font-size: 22px; }
.muted { color: #6b7280; font-size: 13px; }
.muted-strong { color: #4b5563; }

.kpi-strip {
  display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px;
}
.kpi-cell {
  background: #f7f8fb; border-radius: 12px; padding: 14px 16px;
  display: flex; flex-direction: column; gap: 6px;
}
.kpi-cell span { color: #6b7280; font-size: 12px; }
.kpi-cell strong { font-size: 20px; color: #111827; }
.kpi-bull strong { color: #16a34a; }
.kpi-bear strong { color: #dc2626; }
.risk-low strong    { color: #16a34a; }
.risk-mid strong    { color: #ca8a04; }
.risk-high strong   { color: #ea580c; }
.risk-very_high strong { color: #dc2626; }

.theme-chips { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }

.dashboard-grid {
  display: grid; grid-template-columns: minmax(0, 1.7fr) minmax(0, 1fr); gap: 20px;
}
.block-title {
  display: flex; align-items: baseline; justify-content: space-between;
  margin: 4px 0 12px; font-size: 15px; font-weight: 600;
}

.picks-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 12px;
}
.pick-card {
  background: #fff; border: 1px solid #e5e7eb; border-radius: 12px; padding: 14px;
  cursor: pointer; transition: all .18s; display: flex; flex-direction: column; gap: 8px;
}
.pick-card:hover { transform: translateY(-2px); box-shadow: 0 6px 18px rgba(15,23,42,.08); }
.pick-card.dir-bullish { border-left: 3px solid #16a34a; }
.pick-card.dir-bearish { border-left: 3px solid #dc2626; }
.pick-card.dir-neutral { border-left: 3px solid #ca8a04; }
.pick-head { display: flex; justify-content: space-between; align-items: baseline; }
.pick-arrow { font-size: 18px; }
.dir-bullish .pick-arrow { color: #16a34a; }
.dir-bearish .pick-arrow { color: #dc2626; }
.dir-neutral .pick-arrow { color: #ca8a04; }
.pick-name { margin: 2px 0 0; font-size: 14px; font-weight: 600; line-height: 1.3; }
.pick-en   { font-size: 11px; }
.pick-row {
  display: grid; grid-template-columns: 60px 1fr auto; gap: 6px; align-items: center;
  font-size: 12px;
}
.pick-row span { color: #6b7280; }
.pick-row strong { font-weight: 600; color: #111827; font-size: 12px; }
.conf-bar { background: #eef2f7; height: 6px; border-radius: 3px; overflow: hidden; }
.conf-fill { background: linear-gradient(90deg, #5B8DEF, #2BC4A1); height: 100%; }
.pick-tags { display: flex; gap: 4px; flex-wrap: wrap; margin-top: 4px; }

.hit-badge {
  display: flex; align-items: center; gap: 6px;
  background: #f3f4f6; border-radius: 8px; padding: 4px 10px;
  font-size: 11px; margin: 2px 0;
}
.hit-badge .hit-label { color: #6b7280; }
.hit-badge strong { font-size: 13px; }
.hit-good { color: #16a34a; }
.hit-mid  { color: #ca8a04; }
.hit-bad  { color: #dc2626; }

.head-actions { display: flex; gap: 10px; align-items: center; }

.alloc-list { list-style: none; padding: 0; margin: 12px 0 0; display: flex; flex-direction: column; gap: 6px; }
.alloc-list li { display: flex; align-items: center; gap: 8px; font-size: 12px; }
.alloc-list .dot { width: 10px; height: 10px; border-radius: 50%; }
.alloc-list .weight { margin-left: auto; font-weight: 600; }

.sales-brief {
  margin: 0; white-space: pre-wrap; word-break: break-word;
  font-family: inherit; font-size: 13px; line-height: 1.7; color: #1f2937;
}
.avoid-card {
  margin-top: 16px; background: #fef2f2; border: 1px solid #fecaca;
  border-radius: 10px; padding: 12px 14px;
}
.avoid-card h4 { margin: 0 0 6px; color: #b91c1c; font-size: 13px; }
.avoid-card ul { margin: 0; padding-left: 16px; font-size: 12px; }

.state-card { padding: 16px; background: #f7f8fb; border-radius: 12px; color: #6b7280; }
.state-card.error { background: #fef2f2; color: #b91c1c; }
.disclaimer { font-size: 11px; line-height: 1.6; }

@media (max-width: 1024px) {
  .dashboard-grid { grid-template-columns: 1fr; }
  .kpi-strip { grid-template-columns: repeat(2, 1fr); }
}
</style>
