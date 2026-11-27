<template>
  <div class="finrex-v2 unified-report">
    <WorkflowStepper />
    <HomeNavbar>
      <LanguageSwitcher />
      <UiButton variant="primary" size="sm" @click="router.push('/quant/backtest')">策略回测实验室</UiButton>
      <UiButton variant="link" size="sm" @click="router.push('/')">返回首页</UiButton>
    </HomeNavbar>

    <div v-if="loading && !opinion" class="page-loading">正在装配统一报告…</div>

    <template v-else>
      <header class="report-hero">
        <div class="report-hero__copy">
          <UiBadge tone="brand" dot>{{ statusLabel }}</UiBadge>
          <h1>Unified Report</h1>
          <p>{{ opinion?.summary?.text || '报告正在生成或舆情层暂不可用，请稍后刷新。' }}</p>
          <div class="report-actions">
            <UiButton variant="primary" size="sm" :disabled="!reportId" @click="downloadMarkdown">导出 Markdown</UiButton>
            <UiButton variant="ghost" size="sm" @click="exportPdf">导出 PDF</UiButton>
          </div>
        </div>
        <div class="report-hero__meta">
          <div class="meta-cell">
            <span>Report ID</span>
            <strong>{{ reportId }}</strong>
          </div>
          <div class="meta-cell">
            <span>Simulation ID</span>
            <strong>{{ opinion?.simulation_id || '—' }}</strong>
          </div>
          <div class="meta-cell">
            <span>Generated</span>
            <strong>{{ formatTime(opinion?.summary?.generated_at) }}</strong>
          </div>
          <div class="meta-cell">
            <span>报告事件日期</span>
            <strong>{{ eventDateLabel }}</strong>
          </div>
          <div class="meta-cell">
            <span>数据截至日期</span>
            <strong>{{ dataCutoffLabel }}</strong>
          </div>
          <div class="meta-cell">
            <span>Data Coverage</span>
            <strong>{{ coverageLabel }}</strong>
          </div>
        </div>
      </header>

      <div v-if="error" class="page-error">{{ error }}</div>

      <div class="layout">
        <SectionNav :sections="navSections" :active="activeSection" @navigate="scrollTo" />
        <main class="content">
          <CryptoForecastSection :report-id="reportId" :simulation-id="opinion?.simulation_id || ''" />
          <LegacyReportSection :report-id="reportId" />
          <Section2_PersonaSpotlight :report-id="reportId" section-id="s3-persona" @open-personas="goPersonas" />
          <AssetAllocationSection :report-id="reportId" section-id="s5-allocation" />
          <ContentStudioSection :report-id="reportId" />

          <section id="s6-validation" class="validation-cta">
            <div class="validation-cta__inner">
              <div>
                <UiBadge tone="warning" dot>模拟数据 · 非投资建议</UiBadge>
                <h3>策略回测实验室</h3>
                <p>使用统一的 Quant Backtest Lab 对报告标的做历史回测，可运行双塔模型或金融舆情模拟价格预测模型。</p>
              </div>
              <UiButton variant="primary" size="lg" @click="router.push('/quant/backtest')">进入回测 →</UiButton>
            </div>
          </section>
        </main>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import HomeNavbar from '@/components/home/HomeNavbar.vue'
import LanguageSwitcher from '@/components/LanguageSwitcher.vue'
import WorkflowStepper from '@/components/WorkflowStepper.vue'
import SectionNav from '@/components/report/SectionNav.vue'
import CryptoForecastSection from '@/components/report/CryptoForecastSection.vue'
import LegacyReportSection from '@/components/report/LegacyReportSection.vue'
import Section2_PersonaSpotlight from '@/components/report/Section2_PersonaSpotlight.vue'
import ContentStudioSection from '@/components/report/ContentStudioSection.vue'
import AssetAllocationSection from '@/components/report/AssetAllocationSection.vue'
import { UiBadge, UiButton } from '@/components/ui'
import { getPublicOpinion, regeneratePublicOpinion } from '@/api/publicOpinion'
import { generateReport, getReport, getReportBySimulation } from '@/api/report'

const route = useRoute()
const router = useRouter()

const reportId = computed(() => route.params.reportId)
const opinion = ref(null)
const loading = ref(true)
const refreshing = ref(false)
const recovering = ref(false)
const error = ref('')
const activeSection = ref('s2-crypto')
const currentReport = ref(null)
const financialReport = ref(null)
let observer = null
let pollTimer = null

const navSections = computed(() => [
  { id: 's2-crypto', label: forecastNavLabel.value, hint: '价格预测 · 目标区间', status: 'ready' },
  { id: 's2-legacy', label: 'Legacy Report', hint: 'ReportAgent 原文', status: 'ready' },
  { id: 's3-persona', label: 'Persona', hint: '群体观点 · 画像中心', status: 'ready' },
  { id: 's5-allocation', label: 'Asset Allocation', hint: 'CSOP ETF · 5日预测', status: 'ready' },
  { id: 's4-content', label: 'Content Studio', hint: '多平台发布准备', status: 'ready' },
  { id: 's6-validation', label: 'Backtest Lab', hint: '策略回测 · 价格预测验证', status: 'ready' }
])

const statusLabel = computed(() => {
  const status = opinion.value?.summary?.status
  return ({ completed: '已完成', generating: '生成中', pending: '等待中', failed: '失败' }[status]) || status || '部分就绪'
})

const coverageLabel = computed(() => {
  const coverage = opinion.value?.summary?.data_coverage || {}
  const values = ['observed', 'inferred', 'simulated'].map(key => Math.round((coverage[key] || 0) * 100))
  return values.some(Boolean) ? values.join('/') + '%' : '—'
})

const reportForMeta = computed(() => financialReport.value || currentReport.value || {})
const reportMetadata = computed(() => reportForMeta.value?.financial_context?.report_metadata || reportForMeta.value || {})
const eventDateLabel = computed(() => formatTime(reportMetadata.value.event_date || currentReport.value?.created_at))
const dataCutoffLabel = computed(() => formatTime(reportMetadata.value.data_cutoff_at || currentReport.value?.completed_at || currentReport.value?.created_at))
const forecastNavLabel = computed(() => {
  const target = reportForMeta.value?.financial_context?.target_asset || {}
  const symbol = target.symbol || reportForMeta.value?.financial_context?.forecast?.crypto_forecast?.symbol
  return symbol ? `${symbol} Forecast` : 'Price Forecast'
})

async function loadOpinion (silent = false) {
  if (!silent) loading.value = true
  error.value = ''
  try {
    const res = await getPublicOpinion(reportId.value)
    opinion.value = res.data
    if (opinion.value?.summary?.status === 'failed') {
      await recoverFailedReport(opinion.value)
      return
    }
    await loadReportMeta()
    schedulePolling()
  } catch (err) {
    error.value = err.message || '舆情看板暂不可用。'
  } finally {
    if (!silent) loading.value = false
    setupObserverSoon()
  }
}

async function loadReportMeta () {
  currentReport.value = null
  financialReport.value = null
  try {
    const current = await getReport(reportId.value)
    currentReport.value = current.data
    const simulationId = currentReport.value?.simulation_id || opinion.value?.simulation_id
    if (currentReport.value?.report_type === 'financial') {
      financialReport.value = currentReport.value
      return
    }
    if (simulationId) {
      const fin = await getReportBySimulation(simulationId, 'financial')
      financialReport.value = fin.data
    }
  } catch (err) {
    console.warn('Failed to load report metadata:', err)
  }
}

async function recoverFailedReport (payload = {}) {
  if (recovering.value) return
  const simulationId = payload.simulation_id || route.query.simulation_id || route.query.simulationId
  if (!simulationId) return

  recovering.value = true
  error.value = ''
  try {
    let reusableReportId = payload.replacement_report_id || payload.summary?.replacement_report_id || null
    try {
      const existing = await getReportBySimulation(simulationId, 'both')
      const narrative = existing?.data?.narrative || null
      if (narrative?.status === 'completed' && narrative?.report_id && (narrative.markdown_content || narrative.outline)) {
        reusableReportId = narrative.report_id
      }
    } catch (err) {
      console.warn('Failed to resolve completed report for recovery:', err)
    }

    if (reusableReportId && reusableReportId !== reportId.value) {
      router.replace({
        name: 'Report',
        params: { reportId: reusableReportId },
        query: {
          simulation_id: simulationId,
          recovered: '1',
          recovered_from: reportId.value,
          recovery_source: 'existing_completed'
        }
      })
      return
    }

    const res = await generateReport({
      simulation_id: simulationId,
      force_regenerate: true,
      report_type: 'both'
    })
    const nextReportId = res?.data?.narrative_report_id || res?.data?.report_id
    if (!res?.success || !nextReportId) throw new Error(res?.error || 'Report regeneration did not return a report id')
    router.replace({
      name: 'Report',
      params: { reportId: nextReportId },
      query: {
        task_id: res.data.task_id,
        simulation_id: simulationId,
        recovered: '1',
        recovered_from: reportId.value
      }
    })
  } catch (err) {
    error.value = err.message || '报告重新生成失败。'
  } finally {
    recovering.value = false
  }
}

async function regenerateOpinion () {
  refreshing.value = true
  try {
    const res = await regeneratePublicOpinion(reportId.value)
    opinion.value = res.data
  } catch (err) {
    error.value = err.message || '重新聚合失败。'
  } finally {
    refreshing.value = false
  }
}

function schedulePolling () {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
  if (!shouldPollOpinion()) return
  pollTimer = setInterval(() => loadOpinion(true), 5000)
}

function shouldPollOpinion () {
  const status = opinion.value?.summary?.status
  if (status && !['completed', 'failed'].includes(status)) return true
  const dashboard = opinion.value?.model_status?.dashboard || {}
  return dashboard.source === 'oasis_actions' && dashboard.is_dynamic === false && dashboard.fallback_reason !== 'oasis_stream_has_no_positive_volume'
}

function setupObserverSoon () {
  setTimeout(() => {
    if (route.hash) scrollTo(route.hash.replace('#', ''))
    setupObserver()
  }, 200)
}

function setupObserver () {
  if (observer) observer.disconnect()
  observer = new IntersectionObserver(entries => {
    entries.forEach(entry => {
      if (entry.isIntersecting) activeSection.value = entry.target.id
    })
  }, { rootMargin: '-30% 0px -60% 0px', threshold: 0 })
  const sectionList = navSections.value || []
  sectionList.forEach(section => {
    const el = document.getElementById(section.id)
    if (el) observer.observe(el)
  })
}

function scrollTo (id) {
  const el = document.getElementById(id)
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

function goPersonas (payload = {}) {
  const query = {}
  if (payload.personaId) query.personaId = payload.personaId
  if (payload.clusterId) query.clusterId = payload.clusterId
  router.push({ name: 'Persona', params: { reportId: reportId.value }, query })
}

function formatTime (iso) {
  if (!iso) return '—'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')} ${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}:${String(date.getSeconds()).padStart(2, '0')}`
}

function downloadMarkdown () {
  const base = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5001'
  window.open(`${base}/api/report/${encodeURIComponent(reportId.value)}/download`, '_blank')
}

function exportPdf () {
  window.print()
}

onMounted(() => loadOpinion(false))
watch(() => route.params.reportId, () => {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
  loadOpinion(false)
})
onBeforeUnmount(() => {
  if (observer) observer.disconnect()
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<style scoped>
.unified-report { min-height: 100vh; background: var(--c-bg); }
.page-loading, .page-error { margin: var(--s-6); padding: var(--s-5); border: 1px dashed var(--c-border-strong); border-radius: var(--r-md); background: var(--c-bg-soft); color: var(--c-text-muted); }
.report-hero { display: grid; grid-template-columns: 1fr minmax(360px, 520px); gap: var(--s-5); padding: var(--s-6); border-bottom: 1px solid var(--c-border); background: linear-gradient(180deg, #FBFCFE 0%, #FFFFFF 100%); }
.report-hero__copy h1 { margin: var(--s-2) 0; color: var(--c-text); font-size: var(--fs-28); }
.report-hero__copy p { margin: 0; color: var(--c-text-muted); font-size: var(--fs-14); line-height: var(--lh-relaxed); max-width: 820px; }
.report-actions { display: flex; gap: var(--s-2); flex-wrap: wrap; margin-top: var(--s-4); }
.report-hero__meta { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--s-2); }
.meta-cell { padding: var(--s-3); border: 1px solid var(--c-border); border-radius: var(--r-md); background: var(--c-bg); min-width: 0; }
.meta-cell span { display: block; margin-bottom: 5px; color: var(--c-text-subtle); font-size: var(--fs-12); }
.meta-cell strong { display: block; color: var(--c-text); font-family: var(--f-mono); font-size: var(--fs-12); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.layout { display: grid; grid-template-columns: 240px 1fr; gap: var(--s-5); padding: var(--s-5) var(--s-6); max-width: 1480px; margin: 0 auto; }
.content { min-width: 0; }
@media (max-width: 1100px) { .report-hero { grid-template-columns: 1fr; } .layout { grid-template-columns: 1fr; } }
@media (max-width: 680px) { .report-hero__meta { grid-template-columns: 1fr; } .report-hero, .layout { padding: var(--s-4); } }
.validation-cta { margin-top: var(--s-5); padding: var(--s-5); border: 1px solid var(--c-border); border-radius: var(--r-md); background: linear-gradient(135deg, #FBFCFE 0%, #F2F5FB 100%); }
.validation-cta__inner { display: flex; gap: var(--s-4); align-items: center; justify-content: space-between; flex-wrap: wrap; }
.validation-cta h3 { margin: var(--s-2) 0 var(--s-1); font-size: var(--fs-18); }
.validation-cta p { margin: 0; color: var(--c-text-muted); font-size: var(--fs-13); max-width: 640px; }
@media print {
  .unified-report :deep(nav),
  .unified-report :deep(.workflow-stepper),
  .report-actions,
  .validation-cta button,
  .layout > aside { display: none !important; }
  .unified-report { background: #FFFFFF; }
  .report-hero, .layout { display: block; padding: 12px; max-width: none; }
  .content { width: 100%; }
}
</style>
