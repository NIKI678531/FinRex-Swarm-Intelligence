<template>
  <UiCard padding="md">
    <template #header>群体观点摘录 · Highlights</template>
    <div v-if="loading" class="loading">正在抽取代表性观点…</div>
    <ul v-else-if="highlights.length" class="highlights">
      <li v-for="h in highlights" :key="h.id" class="highlight">
        <UiChip :tone="stanceTone(h.stance)">
          {{ stanceLabel(h.stance) }}
        </UiChip>
        <p class="highlight__text">"{{ h.text }}"</p>
        <div class="highlight__foot">
          <span v-if="h.ts_range?.length === 2" class="ts">
            {{ h.ts_range[0] }} → {{ h.ts_range[1] }}
          </span>
          <span v-if="h.evidence_post_ids?.length" class="evid">
            证据：{{ h.evidence_post_ids.length }} 条帖子
          </span>
        </div>
      </li>
    </ul>
    <div v-else class="loading">暂无观点。</div>
  </UiCard>
</template>

<script setup>
import { ref, watch } from 'vue'
import { UiCard, UiChip } from '@/components/ui'
import { fetchHighlights } from '@/api/reportV2'

const props = defineProps({
  personaId: { type: String, required: true },
  reportId: { type: String, default: '' }
})

const highlights = ref([])
const loading    = ref(true)

async function load () {
  loading.value = true
  const res = await fetchHighlights(props.reportId, props.personaId)
  highlights.value = res.highlights
  loading.value = false
}
watch(() => [props.reportId, props.personaId], load, { immediate: true })

const STANCE = {
  bull: { label: '看多', tone: 'bull' },
  bear: { label: '看空', tone: 'bear' },
  contrarian: { label: '逆向', tone: 'warn' },
  neutral: { label: '中性', tone: 'neutral' }
}
const stanceLabel = s => STANCE[s]?.label || s
const stanceTone  = s => STANCE[s]?.tone  || 'neutral'
</script>

<style scoped>
.highlights { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: var(--s-3); }
.highlight {
  padding: var(--s-3);
  border: 1px solid var(--c-border);
  border-left: 3px solid var(--c-accent);
  border-radius: var(--r-md);
  background: var(--c-bg-soft);
}
.highlight__text { margin: 8px 0 6px; color: var(--c-text); line-height: var(--lh-relaxed); font-size: var(--fs-14); }
.highlight__foot { display: flex; gap: var(--s-3); font-size: var(--fs-12); color: var(--c-text-subtle); font-family: var(--f-mono); }
.loading { color: var(--c-text-muted); padding: var(--s-3) 0; }
</style>
