<template>
  <div class="interaction-panel" :class="{ 'interaction-panel--report-only': reportOnly }">
    <!-- Main Split Layout -->
    <div class="main-split-layout">
      <!-- LEFT PANEL: Report Style -->
      <div class="left-panel report-style" ref="leftPanel">
        <div v-if="reportOutline" class="report-content-wrapper">
          <!-- Report Header -->
          <div class="report-header-block">
            <div class="report-meta">
              <span class="report-tag">Prediction Report</span>
              <span class="report-id">ID: {{ reportId || 'REF-2024-X92' }}</span>
            </div>
            <h1 class="main-title">{{ reportOutline.title }}</h1>
            <p class="sub-title">{{ reportOutline.summary }}</p>
            <div class="header-divider"></div>
          </div>

          <section class="full-report-document">
            <article v-if="fullReportMarkdown" class="generated-content full-report-body" v-html="renderMarkdown(fullReportMarkdown)"></article>
            <div v-else class="loading-state full-report-loading">
              <div class="loading-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                  <circle cx="12" cy="12" r="10" stroke-width="4" stroke="#E5E7EB"></circle>
                  <path d="M12 2a10 10 0 0 1 10 10" stroke-width="4" stroke="#4B5563" stroke-linecap="round"></path>
                </svg>
              </div>
              <span class="loading-text">Loading narrative report...</span>
            </div>
          </section>
        </div>

        <!-- Waiting State -->
        <div v-if="!reportOutline" class="waiting-placeholder">
          <div v-if="!reportLoadError" class="waiting-animation">
            <div class="waiting-ring"></div>
            <div class="waiting-ring"></div>
            <div class="waiting-ring"></div>
          </div>
          <span class="waiting-text" v-if="!reportLoadError">
            Waiting for Report Agent...{{ reportLoadElapsed > 5 ? ` (${reportLoadElapsed}s)` : '' }}
          </span>
          <div v-else class="waiting-error">
            <span class="waiting-text" style="color:#ff6b6b">{{ reportLoadError }}</span>
            <button class="retry-btn" @click="retryLoadReport">Retry</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { generateReport, getReport, getAgentLog, getReportBySimulation } from '../api/report'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()

const props = defineProps({
  reportId: String,
  simulationId: String,
  reportOnly: { type: Boolean, default: false }
})

const emit = defineEmits(['add-log', 'update-status'])

const reportOutline = ref(null)
const generatedSections = ref({})
// Report load state (timeout + retry)
const reportLoadError = ref('')
const reportLoadElapsed = ref(0)
const isRecoveringFailedReport = ref(false)
let reportLoadTimer = null
let reportLoadDeadlineTimer = null
const REPORT_LOAD_TIMEOUT_MS = 30000

// Helper Methods
const stripNarrativeLayerLabels = (content = '') => {
  return String(content)
    .replace(/\bObserved\s*\/\s*Inferred\s*\/\s*Simulated\b/gi, '')
    .replace(/\bObserved\s+Facts\b/gi, 'Facts')
    .replace(/\bInferred\s+Drivers\b/gi, 'Drivers')
    .replace(/\bSimulated\s+Scenarios\b/gi, 'Scenarios')
    .replace(/\bObserved\b/gi, '')
    .replace(/\bInferred\b/gi, '')
    .replace(/\bSimulated\b/gi, '')
    .replace(/[ \t]{2,}/g, ' ')
}

const fullReportMarkdown = computed(() => {
  return stripNarrativeLayerLabels(Object.values(generatedSections.value).filter(Boolean).join('\n\n'))
})

// Refs
const leftPanel = ref(null)

// Methods
const addLog = (msg) => {
  emit('add-log', msg)
}

const applyMarkdownReport = (report) => {
  const outline = report.outline || {}
  reportOutline.value = {
    title: outline.title || 'Prediction Report',
    summary: outline.summary || report.simulation_requirement || '',
    sections: [{ title: 'Full Report', description: '' }]
  }

  const full = report.markdown_content || (outline.sections || [])
    .map(section => section.content ? (section.content.startsWith('##') ? section.content : `## ${section.title}\n\n${section.content}`) : '')
    .filter(Boolean)
    .join('\n\n')

  generatedSections.value = full ? { 1: stripNarrativeLayerLabels(full) } : {}
}

const firstQueryValue = (value) => Array.isArray(value) ? value[0] : value

const findReusableCompletedReport = async (simulationId) => {
  try {
    const existing = await getReportBySimulation(simulationId, 'both')
    const narrative = existing?.data?.narrative || null
    if (narrative?.status === 'completed' && narrative?.report_id && (narrative.markdown_content || narrative.outline)) {
      return narrative.report_id
    }
  } catch (err) {
    console.warn('Failed to resolve completed report for recovery:', err)
  }
  return null
}

const recoverFailedReport = async (report) => {
  if (isRecoveringFailedReport.value) return false
  const simulationId = report?.simulation_id || props.simulationId || firstQueryValue(route.query.simulation_id || route.query.simulationId)
  if (!simulationId) return false

  isRecoveringFailedReport.value = true
  emit('update-status', 'processing')
  addLog(`Recovering failed report by regenerating simulation ${simulationId}...`)

  try {
    const reusableReportId = report?.replacement_report_id || await findReusableCompletedReport(simulationId)
    if (reusableReportId && reusableReportId !== props.reportId) {
      addLog(`Recovered by opening completed report ${reusableReportId}.`)
      router.replace({
        name: 'Interaction',
        params: { reportId: reusableReportId },
        query: {
          simulation_id: simulationId,
          recovered: '1',
          recovered_from: props.reportId,
          recovery_source: 'existing_completed'
        }
      })
      return true
    }

    const res = await generateReport({
      simulation_id: simulationId,
      force_regenerate: true,
      report_type: 'both'
    })
    const nextReportId = res?.data?.narrative_report_id || res?.data?.report_id
    if (!res?.success || !nextReportId) throw new Error(res?.error || 'Report regeneration did not return a report id')
    router.replace({
      name: 'Interaction',
      params: { reportId: nextReportId },
      query: {
        task_id: res.data.task_id,
        simulation_id: simulationId,
        recovered: '1',
        recovered_from: props.reportId
      }
    })
    return true
  } catch (err) {
    reportLoadError.value = err.message || 'Failed to recover failed report'
    emit('update-status', 'error')
    addLog(`Failed to recover report: ${err.message || err}`)
    return false
  } finally {
    isRecoveringFailedReport.value = false
  }
}

// Load Report Data
const loadReportData = async () => {
  if (!props.reportId) return

  // 启动 elapsed 计数与 30s 超时
  startReportLoadWatch()

  try {
    addLog(t('log.loadReportData', { id: props.reportId }))
    
      const reportRes = await getReport(props.reportId)
      if (reportRes.success && reportRes.data) {
        if (reportRes.data.status === 'failed' && !reportRes.data.markdown_content) {
          const recovering = await recoverFailedReport(reportRes.data)
          if (recovering) {
            stopReportLoadWatch()
            return
          }
        }
        applyMarkdownReport(reportRes.data)
        if (reportRes.data.status === 'completed' || reportRes.data.markdown_content) {
          stopReportLoadWatch()
          emit('update-status', 'completed')
          addLog('Narrative report loaded from markdown_content')
          return
        }

        await loadAgentLogs()
        if (reportOutline.value) stopReportLoadWatch()
      }
  } catch (err) {
    addLog(t('log.loadReportFailed', { error: err.message }))
    reportLoadError.value = err.message || 'Failed to load report'
    stopReportLoadWatch()
  }
}

const startReportLoadWatch = () => {
  reportLoadError.value = ''
  reportLoadElapsed.value = 0
  if (reportLoadTimer) clearInterval(reportLoadTimer)
  if (reportLoadDeadlineTimer) clearTimeout(reportLoadDeadlineTimer)
  reportLoadTimer = setInterval(() => {
    reportLoadElapsed.value += 1
  }, 1000)
  reportLoadDeadlineTimer = setTimeout(() => {
    if (!reportOutline.value) {
      reportLoadError.value = `Report Agent 30s 内未返回 outline，可能是 financial report 或后端任务未启动。请重试或检查后端日志。`
      stopReportLoadWatch(true)
    }
  }, REPORT_LOAD_TIMEOUT_MS)
}

const stopReportLoadWatch = (keepError = false) => {
  if (reportLoadTimer) { clearInterval(reportLoadTimer); reportLoadTimer = null }
  if (reportLoadDeadlineTimer) { clearTimeout(reportLoadDeadlineTimer); reportLoadDeadlineTimer = null }
  if (!keepError) reportLoadError.value = ''
}

const retryLoadReport = () => {
  reportLoadError.value = ''
  loadReportData()
}

  const loadAgentLogs = async () => {
  if (!props.reportId) return
  
  try {
    const res = await getAgentLog(props.reportId, 0)
    if (res.success && res.data) {
      const logs = res.data.logs || []
      
      logs.forEach(log => {
        if (log.action === 'planning_complete' && log.details?.outline) {
          reportOutline.value = log.details.outline
        }
        
        if (log.action === 'section_complete' && log.section_index < 100 && log.details?.content) {
          generatedSections.value[log.section_index] = log.details.content
        }
      })
      
      addLog(t('log.reportDataLoaded'))
    }
  } catch (err) {
    addLog(t('log.loadReportLogFailed', { error: err.message }))
  }
}

// Lifecycle
onMounted(() => {
  addLog(t('log.step5Init'))
})

onUnmounted(() => {
  stopReportLoadWatch()
})

  watch(() => props.reportId, (newId) => {
    if (newId) {
      isRecoveringFailedReport.value = false
      loadReportData()
    }
  }, { immediate: true })

</script>

<style scoped>
.interaction-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: #F8F9FA;
  font-family: 'Inter', 'Noto Sans SC', system-ui, sans-serif;
  overflow: hidden;
}

/* Main Split Layout */
.main-split-layout {
  flex: 1;
  display: flex;
  overflow: hidden;
}

/* Report Reader */
.left-panel.report-style {
  width: 100%;
  min-width: 0;
  background: #FFFFFF;
  border-right: none;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  padding: 30px 50px 60px 50px;
}


.left-panel::-webkit-scrollbar {
  width: 6px;
}

.left-panel::-webkit-scrollbar-track {
  background: transparent;
}

.left-panel::-webkit-scrollbar-thumb {
  background: transparent;
  border-radius: 3px;
  transition: background 0.3s ease;
}

.left-panel:hover::-webkit-scrollbar-thumb {
  background: rgba(0, 0, 0, 0.15);
}

.left-panel::-webkit-scrollbar-thumb:hover {
  background: rgba(0, 0, 0, 0.25);
}

/* Report Header */
.report-content-wrapper {
  max-width: 800px;
  margin: 0 auto;
  width: 100%;
}

.report-header-block {
  margin-bottom: 30px;
}

.report-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 24px;
}

.report-tag {
  background: #000000;
  color: #FFFFFF;
  font-size: 11px;
  font-weight: 700;
  padding: 4px 8px;
  letter-spacing: 0.05em;
  text-transform: uppercase;
}

.report-id {
  font-size: 11px;
  color: #9CA3AF;
  font-weight: 500;
  letter-spacing: 0.02em;
}

.main-title {
  font-family: 'Times New Roman', Times, serif;
  font-size: 36px;
  font-weight: 700;
  color: #111827;
  line-height: 1.2;
  margin: 0 0 16px 0;
  letter-spacing: -0.02em;
}

.sub-title {
  font-family: 'Times New Roman', Times, serif;
  font-size: 16px;
  color: #6B7280;
  font-style: italic;
  line-height: 1.6;
  margin: 0 0 30px 0;
  font-weight: 400;
}

.header-divider {
  height: 1px;
  background: #E5E7EB;
  width: 100%;
}

/* Generated Content */
.generated-content {
  font-family: 'Inter', 'Noto Sans SC', system-ui, sans-serif;
  font-size: 14px;
  line-height: 1.8;
  color: #374151;
}

.generated-content :deep(p) {
  margin-bottom: 1em;
}

.generated-content :deep(.md-h2),
.generated-content :deep(.md-h3),
.generated-content :deep(.md-h4) {
  font-family: 'Times New Roman', Times, serif;
  color: #111827;
  margin-top: 1.5em;
  margin-bottom: 0.8em;
  font-weight: 700;
}

.generated-content :deep(.md-h2) { font-size: 20px; border-bottom: 1px solid #F3F4F6; padding-bottom: 8px; }
.generated-content :deep(.md-h3) { font-size: 18px; }
.generated-content :deep(.md-h4) { font-size: 16px; }

.generated-content :deep(.md-ul),
.generated-content :deep(.md-ol) {
  padding-left: 20px;
  margin-bottom: 1em;
}

.generated-content :deep(.md-li) {
  margin-bottom: 0.5em;
}

.generated-content :deep(.md-quote) {
  border-left: 3px solid #E5E7EB;
  padding-left: 16px;
  margin: 1.5em 0;
  color: #6B7280;
  font-style: italic;
  font-family: 'Times New Roman', Times, serif;
}

.generated-content :deep(.code-block) {
  background: #F9FAFB;
  padding: 12px;
  border-radius: 6px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  overflow-x: auto;
  margin: 1em 0;
  border: 1px solid #E5E7EB;
}

.generated-content :deep(strong) {
  font-weight: 600;
  color: #111827;
}

/* Loading State */
.loading-state {
  display: flex;
  align-items: center;
  gap: 10px;
  color: #6B7280;
  font-size: 14px;
  margin-top: 4px;
}

.loading-icon {
  width: 18px;
  height: 18px;
  animation: spin 1s linear infinite;
  display: flex;
  align-items: center;
  justify-content: center;
}

.loading-text {
  font-family: 'Times New Roman', Times, serif;
  font-size: 15px;
  color: #4B5563;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* Content Styles Override */
.generated-content :deep(.md-h2) {
  font-family: 'Times New Roman', Times, serif;
  font-size: 18px;
  margin-top: 0;
}

/* Waiting Placeholder */
.waiting-placeholder {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 20px;
  padding: 40px;
  color: #9CA3AF;
}

.waiting-animation {
  position: relative;
  width: 48px;
  height: 48px;
}

.waiting-ring {
  position: absolute;
  width: 100%;
  height: 100%;
  border: 2px solid #E5E7EB;
  border-radius: 50%;
  animation: ripple 2s cubic-bezier(0.4, 0, 0.2, 1) infinite;
}

.waiting-ring:nth-child(2) {
  animation-delay: 0.4s;
}

.waiting-ring:nth-child(3) {
  animation-delay: 0.8s;
}

@keyframes ripple {
  0% { transform: scale(0.5); opacity: 1; }
  100% { transform: scale(2); opacity: 0; }
}

.waiting-text {
  font-size: 14px;
}

.waiting-error { display: flex; flex-direction: column; align-items: center; gap: 12px; }
.retry-btn {
  padding: 6px 16px;
  background: #1a1a1a;
  color: #fff;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
}
.retry-btn:hover { background: #333; }

/* Markdown Styles */
:deep(.md-p) {
  margin: 0 0 12px 0;
}

:deep(.md-h2) {
  font-size: 20px;
  font-weight: 700;
  color: #1F2937;
  margin: 24px 0 12px 0;
}

:deep(.md-h3) {
  font-size: 16px;
  font-weight: 600;
  color: #374151;
  margin: 20px 0 10px 0;
}

:deep(.md-h4) {
  font-size: 14px;
  font-weight: 600;
  color: #4B5563;
  margin: 16px 0 8px 0;
}

:deep(.md-h5) {
  font-size: 13px;
  font-weight: 600;
  color: #6B7280;
  margin: 12px 0 6px 0;
}

:deep(.md-ul), :deep(.md-ol) {
  margin: 12px 0;
  padding-left: 24px;
}

:deep(.md-li), :deep(.md-oli) {
  margin: 6px 0;
}


:deep(.code-block) {
  margin: 12px 0;
  padding: 12px 16px;
  background: #1F2937;
  border-radius: 6px;
  overflow-x: auto;
}

:deep(.code-block code) {
  font-family: 'JetBrains Mono', monospace;
  font-size: 13px;
  color: #E5E7EB;
}

:deep(.inline-code) {
  font-family: 'JetBrains Mono', monospace;
  font-size: 13px;
  background: #F3F4F6;
  padding: 2px 6px;
  border-radius: 4px;
  color: #1F2937;
}

:deep(.md-hr) {
  border: none;
  border-top: 1px solid #E5E7EB;
  margin: 24px 0;
}

.full-report-document {
  padding-bottom: 64px;
}

.full-report-body {
  color: #374151;
  font-size: 15px;
  line-height: 1.78;
}

.full-report-body :deep(.md-h2) {
  color: #111827;
  font-size: 24px;
  border-bottom: 1px solid #E5E7EB;
  padding-bottom: 10px;
}

.full-report-body :deep(.md-h3),
.full-report-body :deep(.md-h4),
.full-report-body :deep(.md-h5) {
  color: #111827;
}

.full-report-loading {
  min-height: 180px;
  justify-content: center;
}
</style>

<style>
/* English locale: smaller report title */
html[lang="en"] .report-header-block .main-title {
  font-size: 28px;
}
</style>
