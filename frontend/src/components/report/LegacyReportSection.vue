<template>
  <section id="s2-legacy" class="legacy-section">
    <header class="section-head">
      <div>
        <span class="kicker">LEGACY REPORT</span>
        <h2>ReportAgent 原始报告</h2>
        <p>保留原 ReportAgent 内容，作为统一报告页中的可追溯章节。</p>
      </div>
      <UiButton variant="ghost" size="sm" :disabled="!reportId" @click="downloadMarkdown">
        导出 Markdown
      </UiButton>
    </header>

    <div v-if="loading" class="loading">正在读取 ReportAgent 内容…</div>
    <div v-else-if="error" class="empty">{{ error }}</div>
    <div v-else class="legacy-body">
      <article v-for="(section, index) in sections" :key="`${section.title}-${index}`" class="legacy-card">
        <span class="legacy-card__idx">{{ String(index + 1).padStart(2, '0') }}</span>
        <div>
          <h3>{{ section.title }}</h3>
          <p>{{ section.content || '该章节内容暂未写入。' }}</p>
        </div>
      </article>
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { UiButton } from '@/components/ui'
import { getReport } from '@/api/report'

const props = defineProps({ reportId: { type: String, required: true } })

const report = ref(null)
const loading = ref(true)
const error = ref('')

const sections = computed(() => {
  const outlineSections = report.value?.outline?.sections || []
  if (outlineSections.length) return outlineSections
  const markdown = report.value?.markdown_content || ''
  if (!markdown) return []
  return [{ title: report.value?.outline?.title || '完整报告', content: markdown }]
})

async function loadReport () {
  if (!props.reportId) return
  loading.value = true
  error.value = ''
  try {
    const res = await getReport(props.reportId)
    report.value = res.data
  } catch (err) {
    error.value = err.message || '报告内容暂不可用。'
  } finally {
    loading.value = false
  }
}

function downloadMarkdown () {
  const markdown = report.value?.markdown_content || sections.value.map(s => `## ${s.title}\n\n${s.content}`).join('\n\n')
  const blob = new Blob([markdown], { type: 'text/markdown;charset=utf-8' })
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = `${props.reportId}.md`
  link.click()
  URL.revokeObjectURL(link.href)
}

onMounted(loadReport)
watch(() => props.reportId, loadReport)
</script>

<style scoped>
.legacy-section { padding: var(--s-6) 0; scroll-margin-top: 80px; }
.section-head { display: flex; justify-content: space-between; align-items: flex-start; gap: var(--s-4); margin-bottom: var(--s-4); }
.kicker { color: var(--c-accent); font-size: var(--fs-12); font-weight: 700; letter-spacing: .14em; }
.section-head h2 { margin: 4px 0; color: var(--c-text); font-size: var(--fs-22); }
.section-head p { margin: 0; color: var(--c-text-muted); font-size: var(--fs-13); }
.legacy-body { display: flex; flex-direction: column; gap: var(--s-3); }
.legacy-card { display: grid; grid-template-columns: 48px 1fr; gap: var(--s-4); padding: var(--s-4); border: 1px solid var(--c-border); border-radius: var(--r-lg); background: var(--c-bg); }
.legacy-card__idx { font-family: var(--f-mono); color: var(--c-accent); font-weight: 700; }
.legacy-card h3 { margin: 0 0 var(--s-2); color: var(--c-text); font-size: var(--fs-16); }
.legacy-card p { margin: 0; color: var(--c-text-muted); font-size: var(--fs-13); line-height: var(--lh-relaxed); white-space: pre-wrap; }
.loading, .empty { padding: var(--s-5); color: var(--c-text-muted); border: 1px dashed var(--c-border-strong); border-radius: var(--r-md); background: var(--c-bg-soft); }
@media (max-width: 720px) { .section-head { flex-direction: column; } .legacy-card { grid-template-columns: 1fr; } }
</style>

