<template>
  <div class="finrex-v2 persona-hub">
    <HomeNavbar>
      <LanguageSwitcher />
      <UiButton variant="link" size="sm" @click="back">← 返回报告</UiButton>
    </HomeNavbar>

    <div v-if="loading" class="loading">加载 Persona 数据…</div>

    <div v-else class="hub-layout">
      <PersonaDirectory
        :personas="personas"
        :clusters="clusters"
        :active-id="activeId"
        @select="selectPersona"
      />

      <main class="hub-main">
        <div v-if="!active" class="hub-main__empty">
          ← 从左侧选择一位投资者，查看完整画像并开始对话。
        </div>
        <template v-else>
          <PersonaProfileCard :persona="active" />
          <HighlightBubbleList :persona-id="active.id" :report-id="route.params.reportId" />
        </template>
      </main>

      <ChatStream :persona="active" />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import HomeNavbar from '@/components/home/HomeNavbar.vue'
import LanguageSwitcher from '@/components/LanguageSwitcher.vue'
import { UiButton } from '@/components/ui'
import PersonaDirectory from '@/components/persona/PersonaDirectory.vue'
import PersonaProfileCard from '@/components/persona/PersonaProfileCard.vue'
import HighlightBubbleList from '@/components/persona/HighlightBubbleList.vue'
import ChatStream from '@/components/chat/ChatStream.vue'
import { fetchPersonasSection } from '@/api/reportV2'

const route   = useRoute()
const router  = useRouter()
const personas = ref([])
const clusters = ref([])
const activeId = ref('')
const loading  = ref(true)

const active = computed(() => personas.value.find(p => p.id === activeId.value) || null)

onMounted(async () => {
  const res = await fetchPersonasSection(route.params.reportId)
  personas.value = res.personas
  clusters.value = res.clusters

  // 初始选中：query.personaId > query.clusterId 的代表 > 第一个
  const qPid = route.query.personaId
  const qCid = route.query.clusterId
  if (qPid && personas.value.some(p => p.id === qPid)) {
    activeId.value = qPid
  } else if (qCid) {
    const c = clusters.value.find(c => c.id === qCid)
    activeId.value = c?.top_persona_ids?.[0] || personas.value[0]?.id || ''
  } else {
    activeId.value = personas.value[0]?.id || ''
  }
  loading.value = false
})

watch(activeId, (id) => {
  router.replace({ query: { ...route.query, personaId: id } })
})

function selectPersona (id) { activeId.value = id }

function back () {
  router.push(`/report/${route.params.reportId}#s2-personas`)
}
</script>

<style scoped>
.persona-hub { min-height: 100vh; background: var(--c-bg); display: flex; flex-direction: column; }

.hub-layout {
  flex: 1;
  display: grid;
  grid-template-columns: 280px 1fr 420px;
  height: calc(100vh - 64px);
  overflow: hidden;
}
.hub-main {
  overflow-y: auto;
  padding: var(--s-5);
  display: flex; flex-direction: column; gap: var(--s-4);
  background: var(--c-bg-soft);
}
.hub-main__empty { margin: auto; color: var(--c-text-subtle); font-size: var(--fs-14); }
.loading { padding: var(--s-7); text-align: center; color: var(--c-text-muted); }

@media (max-width: 1180px) {
  .hub-layout { grid-template-columns: 240px 1fr 380px; }
}
@media (max-width: 980px) {
  .hub-layout { grid-template-columns: 1fr; height: auto; }
  .hub-layout > * + * { border-top: 1px solid var(--c-border); }
}
</style>
