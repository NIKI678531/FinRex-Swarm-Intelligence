<template>
  <section id="s4-content" class="content-studio">
    <header class="section-head">
      <div>
        <span class="kicker">CONTENT STUDIO</span>
        <h2>发布准备</h2>
        <p>同页生成小红书 / LinkedIn / X / 微信草稿，支持改写、合规检查、复制与导出。</p>
      </div>
      <div class="head-actions">
        <UiButton variant="ghost" size="sm" :loading="loading" @click="loadStudio">刷新</UiButton>
        <UiButton variant="primary" size="sm" :loading="generating" @click="regenerate">重新生成</UiButton>
      </div>
    </header>

    <div v-if="loading && !studio" class="loading">正在准备平台草稿…</div>
    <div v-else-if="error" class="empty">{{ error }}</div>

    <template v-else-if="studio">
      <div class="platform-tabs">
        <button
          v-for="platform in platforms"
          :key="platform.key"
          class="platform-tab"
          :class="{ active: activePlatform === platform.key }"
          @click="activePlatform = platform.key"
        >
          <span>{{ platform.label }}</span>
          <small>{{ postCount(platform.key) }}</small>
        </button>
      </div>

      <div class="studio-grid">
        <article v-for="post in activePosts" :key="post.post_id" class="draft-panel">
          <div class="draft-panel__head">
            <div>
              <span class="post-id">#{{ post.post_id.slice(-8) }}</span>
              <h3>{{ post.title }}</h3>
            </div>
            <UiChip :tone="statusTone(post.compliance_status)">{{ post.compliance_status || 'unchecked' }}</UiChip>
          </div>

          <label class="field">
            <span>标题</span>
            <input v-model="post.title" />
          </label>

          <label class="field field--body">
            <span>正文</span>
            <textarea v-model="post.body" rows="12"></textarea>
          </label>

          <div class="tag-row">
            <UiChip v-for="tag in post.tags" :key="tag" tone="neutral">{{ tag }}</UiChip>
          </div>

          <div v-if="post.issues?.length" class="issue-list">
            <div v-for="issue in post.issues" :key="`${post.post_id}-${issue.rule_id}-${issue.message}`" class="issue-row">
              <strong>{{ issue.rule_id }}</strong>
              <span>{{ issue.message }}</span>
            </div>
          </div>

          <div class="draft-actions">
            <UiButton variant="ghost" size="sm" @click="check(post)">合规检查</UiButton>
            <UiButton variant="ghost" size="sm" @click="save(post)">保存改写</UiButton>
            <UiButton variant="ghost" size="sm" @click="copy(post)">复制</UiButton>
            <UiButton variant="link" size="sm" @click="exportPost(post)">导出 JSON</UiButton>
          </div>
        </article>

        <aside class="basis-panel">
          <h3>Source Basis</h3>
          <div class="basis-block">
            <span>Opinion Topics</span>
            <p>{{ (studio.source_basis?.opinion_topics || []).join(', ') || 'n/a' }}</p>
          </div>
          <div class="basis-block">
            <span>Report Sections</span>
            <p>{{ (studio.source_basis?.report_sections || []).join(' / ') || 'n/a' }}</p>
          </div>
          <div class="basis-block">
            <span>Evidence IDs</span>
            <p>{{ (studio.source_basis?.evidence_ids || []).join(', ') || 'n/a' }}</p>
          </div>
          <div v-if="message" class="message">{{ message }}</div>
        </aside>
      </div>
    </template>
  </section>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { UiButton, UiChip } from '@/components/ui'
import { checkContent, generateContentStudio, getContentStudio, updateContentPost } from '@/api/contentStudio'

const props = defineProps({ reportId: { type: String, required: true } })

const studio = ref(null)
const loading = ref(false)
const generating = ref(false)
const error = ref('')
const message = ref('')
const activePlatform = ref('xiaohongshu')

const platforms = [
  { key: 'xiaohongshu', label: '小红书' },
  { key: 'linkedin', label: 'LinkedIn' },
  { key: 'x', label: 'X' },
  { key: 'wechat', label: '微信' }
]

const activePosts = computed(() => studio.value?.platforms?.[activePlatform.value] || [])

function postCount (platform) {
  return studio.value?.platforms?.[platform]?.length || 0
}

async function loadStudio () {
  if (!props.reportId) return
  loading.value = true
  error.value = ''
  try {
    const res = await getContentStudio(props.reportId)
    studio.value = res.data
  } catch (err) {
    error.value = err.message || 'Content Studio 暂不可用。'
  } finally {
    loading.value = false
  }
}

async function regenerate () {
  generating.value = true
  error.value = ''
  try {
    const res = await generateContentStudio(props.reportId)
    studio.value = res.data
    message.value = '已重新生成四个平台草稿。'
  } catch (err) {
    error.value = err.message || '重新生成失败。'
  } finally {
    generating.value = false
  }
}

async function check (post) {
  const res = await checkContent({ platform: post.platform, text: post.body, post })
  const compliance = res.data?.compliance || res.data || {}
  post.compliance_status = compliance.status
  post.issues = compliance.issues || []
  post.publish_ready = compliance.status === 'pass'
  message.value = `${post.platform} 已完成合规检查。`
}

async function save (post) {
  const res = await updateContentPost(post.post_id, {
    title: post.title,
    body: post.body,
    tags: post.tags,
    status: post.status
  })
  Object.assign(post, res.data)
  message.value = '改写已保存。'
}

async function copy (post) {
  await navigator.clipboard.writeText(`${post.title}\n\n${post.body}`)
  message.value = '已复制到剪贴板。'
}

function exportPost (post) {
  const blob = new Blob([JSON.stringify(post, null, 2)], { type: 'application/json;charset=utf-8' })
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = `${post.post_id}.json`
  link.click()
  URL.revokeObjectURL(link.href)
}

function statusTone (status) {
  return { pass: 'bull', warn: 'warn', block: 'bear' }[status] || 'neutral'
}

onMounted(loadStudio)
watch(() => props.reportId, loadStudio)
</script>

<style scoped>
.content-studio { padding: var(--s-6) 0; scroll-margin-top: 80px; }
.section-head { display: flex; justify-content: space-between; align-items: flex-start; gap: var(--s-4); margin-bottom: var(--s-4); }
.kicker { color: var(--c-accent); font-size: var(--fs-12); font-weight: 700; letter-spacing: .14em; }
.section-head h2 { margin: 4px 0; color: var(--c-text); font-size: var(--fs-22); }
.section-head p { margin: 0; color: var(--c-text-muted); font-size: var(--fs-13); }
.head-actions { display: flex; gap: var(--s-2); flex-wrap: wrap; }
.platform-tabs { display: flex; gap: var(--s-2); flex-wrap: wrap; margin-bottom: var(--s-4); }
.platform-tab { display: inline-flex; align-items: center; gap: 8px; border: 1px solid var(--c-border); border-radius: var(--r-md); background: var(--c-bg); padding: 9px 14px; cursor: pointer; color: var(--c-text); }
.platform-tab.active { border-color: var(--c-brand); background: var(--c-accent-soft); }
.platform-tab small { color: var(--c-text-subtle); font-family: var(--f-mono); }
.studio-grid { display: grid; grid-template-columns: 1fr 320px; gap: var(--s-4); align-items: start; }
.draft-panel, .basis-panel { border: 1px solid var(--c-border); border-radius: var(--r-lg); background: var(--c-bg); padding: var(--s-4); }
.draft-panel__head { display: flex; justify-content: space-between; align-items: flex-start; gap: var(--s-3); margin-bottom: var(--s-3); }
.post-id { color: var(--c-text-subtle); font-family: var(--f-mono); font-size: var(--fs-12); }
.draft-panel h3, .basis-panel h3 { margin: 4px 0 0; color: var(--c-text); font-size: var(--fs-16); }
.field { display: flex; flex-direction: column; gap: 6px; margin-bottom: var(--s-3); color: var(--c-text-subtle); font-size: var(--fs-12); }
.field input, .field textarea { width: 100%; border: 1px solid var(--c-border); border-radius: var(--r-md); padding: 10px 12px; font: inherit; color: var(--c-text); background: var(--c-bg-soft); box-sizing: border-box; }
.field textarea { resize: vertical; min-height: 220px; line-height: var(--lh-relaxed); }
.tag-row { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: var(--s-3); }
.issue-list { display: flex; flex-direction: column; gap: 6px; margin-bottom: var(--s-3); }
.issue-row { display: grid; grid-template-columns: 88px 1fr; gap: var(--s-2); padding: var(--s-2); border-radius: var(--r-md); background: #FBE9E7; color: var(--c-bear); font-size: var(--fs-12); }
.draft-actions { display: flex; gap: var(--s-2); flex-wrap: wrap; }
.basis-panel { position: sticky; top: 88px; display: flex; flex-direction: column; gap: var(--s-3); }
.basis-block span { display: block; color: var(--c-text-subtle); font-family: var(--f-mono); font-size: var(--fs-12); margin-bottom: 5px; }
.basis-block p { margin: 0; color: var(--c-text-muted); font-size: var(--fs-13); line-height: var(--lh-relaxed); }
.message, .loading, .empty { padding: var(--s-3); border: 1px dashed var(--c-border-strong); border-radius: var(--r-md); background: var(--c-bg-soft); color: var(--c-text-muted); font-size: var(--fs-13); }
@media (max-width: 980px) { .studio-grid { grid-template-columns: 1fr; } .basis-panel { position: static; } }
@media (max-width: 720px) { .section-head { flex-direction: column; } }
</style>

