<template>
  <section :id="sectionId" class="sec2">
    <header class="sec2__head">
      <div>
        <h2>② 群体画像 & 投资者画像</h2>
        <p>基于关系图谱生成的 cluster 与代表性 Persona，点击进入完整画像中心做深度互动。</p>
      </div>
      <UiButton variant="primary" size="md" @click="$emit('open-personas')">
        进入投资者画像 / 互动中心 →
      </UiButton>
    </header>

    <div v-if="loading" class="loading">正在装配 cluster 与 persona…</div>

    <template v-else-if="data">
      <div v-if="topicNodes.length && stakeholderNodes.length" class="viewpoint-map">
        <header class="viewpoint-map__head">
          <span class="kicker">观点脉络图</span>
          <span class="hint">报告热点与利益相关方主要观点</span>
        </header>
        <div class="viewpoint-map__grid">
          <div class="viewpoint-map__col">
            <div v-for="node in stakeholderNodes" :key="node.id" class="map-node map-node--stakeholder">
              <strong>{{ node.label }}</strong>
              <span>{{ node.stance || 'neutral' }}</span>
            </div>
          </div>
          <div class="viewpoint-map__col viewpoint-map__col--edges">
            <div v-for="edge in visibleEdges" :key="`${edge.source}-${edge.target}`" class="map-edge">
              <span>{{ nodeLabel(edge.source) }}</span>
              <i>{{ edge.label }}</i>
              <span>{{ nodeLabel(edge.target) }}</span>
            </div>
          </div>
          <div class="viewpoint-map__col">
            <div v-for="node in topicNodes" :key="node.id" class="map-node map-node--topic">
              <strong>{{ node.label }}</strong>
              <span>heat {{ Math.round((node.heat || 0) * 100) }}</span>
            </div>
          </div>
        </div>
      </div>

      <div class="cluster-row">
        <UiCard
          v-for="c in data.clusters" :key="c.id"
          hoverable padding="md"
          class="cluster-card"
          @click="$emit('open-personas', { clusterId: c.id })"
        >
          <div class="cluster-card__head">
            <UiChip tone="brand" solid>{{ c.size }} agents</UiChip>
            <span class="cluster-card__id">#{{ shortId(c.id) }}</span>
          </div>
          <h3>{{ c.name }}</h3>
          <p>{{ c.summary }}</p>
          <div class="cluster-card__foot">
            <UiAvatar v-for="pid in c.top_persona_ids.slice(0, 3)" :key="pid"
                      :name="pid" :seed="pid" size="sm" />
            <span class="cluster-card__more">代表 {{ c.top_persona_ids.length }} 位</span>
          </div>
        </UiCard>
      </div>

      <div class="persona-row">
        <header class="persona-row__head">
          <span class="kicker">代表性投资者</span>
          <span class="hint">点击进入个人档案 + 1:1 对话</span>
        </header>
        <div class="persona-grid">
          <UiCard v-for="p in data.personas.slice(0, 6)" :key="p.id"
                  hoverable padding="md"
                  class="persona-card"
                  @click="$emit('open-personas', { personaId: p.id })">
            <div class="persona-card__row">
              <UiAvatar :name="p.name" :seed="p.avatar_seed" size="md" />
              <div>
                <div class="persona-card__name">{{ p.name }}</div>
                <div class="persona-card__sub">{{ p.profession }}</div>
              </div>
              <UiChip :tone="stanceTone(p.dimensions.signals.stance)">
                {{ stanceLabel(p.dimensions.signals.stance) }}
              </UiChip>
            </div>
            <div class="persona-card__tags">
              <UiChip v-for="t in p.tags" :key="t" tone="neutral">{{ t }}</UiChip>
            </div>
            <div class="persona-card__dims">
              <span><b>风险</b> {{ p.dimensions.psychology.risk }}</span>
              <span><b>风格</b> {{ p.dimensions.investment.style }}</span>
              <span><b>影响力</b> {{ Math.round(p.dimensions.social.influence * 100) }}</span>
            </div>
          </UiCard>
        </div>
      </div>
    </template>
  </section>
</template>

<script setup>
import { computed, ref, onMounted } from 'vue'
import { UiCard, UiChip, UiButton, UiAvatar } from '@/components/ui'
import { fetchPersonasSection } from '@/api/reportV2'

const props = defineProps({
  reportId:  { type: String, required: true },
  sectionId: { type: String, default: 's2-personas' }
})
defineEmits(['open-personas'])

const data    = ref(null)
const loading = ref(true)

onMounted(async () => {
  data.value = await fetchPersonasSection(props.reportId)
  loading.value = false
})

const viewpointNodes = computed(() => data.value?.viewpoint_map?.nodes || [])
const viewpointEdges = computed(() => data.value?.viewpoint_map?.edges || [])
const topicNodes = computed(() => viewpointNodes.value.filter(node => node.type === 'topic').slice(0, 5))
const stakeholderNodes = computed(() => viewpointNodes.value.filter(node => node.type === 'stakeholder').slice(0, 5))
const visibleEdges = computed(() => viewpointEdges.value.slice(0, 8))

function nodeLabel (id) {
  return viewpointNodes.value.find(node => node.id === id)?.label || id
}

const STANCE = {
  bull: { label: '看多', tone: 'bull' },
  bear: { label: '看空', tone: 'bear' },
  contrarian: { label: '逆向', tone: 'warn' },
  neutral: { label: '中性', tone: 'neutral' }
}
const stanceLabel = s => STANCE[s]?.label || s
const stanceTone  = s => STANCE[s]?.tone  || 'neutral'
function shortId (id) { return id.slice(-4) }
</script>

<style scoped>
.sec2 { padding: var(--s-6) 0; scroll-margin-top: 80px; }
.sec2__head { display: flex; align-items: flex-end; justify-content: space-between; gap: var(--s-4); margin-bottom: var(--s-4); }
.sec2__head h2 { font-size: var(--fs-22); font-weight: 700; margin: 0 0 4px; color: var(--c-text); }
.sec2__head p  { color: var(--c-text-muted); margin: 0; font-size: var(--fs-13); }

.viewpoint-map {
  margin-bottom: var(--s-5);
  padding: var(--s-4);
  border: 1px solid var(--c-border);
  border-radius: var(--r-lg);
  background: var(--c-bg-soft);
}

.viewpoint-map__head {
  display: flex;
  align-items: baseline;
  gap: var(--s-3);
  margin-bottom: var(--s-3);
}

.viewpoint-map__grid {
  display: grid;
  grid-template-columns: 1fr 1.2fr 1fr;
  gap: var(--s-3);
  align-items: stretch;
}

.viewpoint-map__col {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.viewpoint-map__col--edges {
  justify-content: center;
}

.map-node,
.map-edge {
  border: 1px solid var(--c-border);
  border-radius: var(--r-md);
  background: var(--c-bg);
  padding: 10px 12px;
}

.map-node {
  display: flex;
  justify-content: space-between;
  gap: var(--s-3);
}

.map-node strong {
  color: var(--c-text);
  font-size: var(--fs-13);
}

.map-node span,
.map-edge i {
  color: var(--c-text-subtle);
  font-size: var(--fs-12);
  font-style: normal;
}

.map-node--topic { border-left: 3px solid var(--c-accent); }
.map-node--stakeholder { border-left: 3px solid var(--c-brand); }

.map-edge {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  gap: 8px;
  align-items: center;
  color: var(--c-text-muted);
  font-size: var(--fs-12);
}

@media (max-width: 900px) { .viewpoint-map__grid { grid-template-columns: 1fr; } }

.cluster-row {
  display: grid; grid-template-columns: repeat(4, 1fr);
  gap: var(--s-3); margin-bottom: var(--s-5);
}
@media (max-width: 1100px) { .cluster-row { grid-template-columns: repeat(2, 1fr); } }
.cluster-card { cursor: pointer; }
.cluster-card__head { display: flex; align-items: center; justify-content: space-between; margin-bottom: var(--s-2); }
.cluster-card__id { color: var(--c-text-subtle); font-family: var(--f-mono); font-size: var(--fs-12); }
.cluster-card h3 { font-size: var(--fs-16); margin: 0 0 6px; color: var(--c-text); }
.cluster-card p  { color: var(--c-text-muted); font-size: var(--fs-13); line-height: var(--lh-relaxed); margin: 0 0 var(--s-3); }
.cluster-card__foot { display: flex; align-items: center; gap: 6px; }
.cluster-card__more { color: var(--c-text-subtle); font-size: var(--fs-12); margin-left: 4px; }

.persona-row__head { display: flex; align-items: baseline; gap: var(--s-3); margin-bottom: var(--s-2); }
.kicker { color: var(--c-accent); font-size: var(--fs-12); font-weight: 600; letter-spacing: .14em; }
.hint   { color: var(--c-text-subtle); font-size: var(--fs-12); }

.persona-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: var(--s-3); }
@media (max-width: 1100px) { .persona-grid { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 640px)  { .persona-grid { grid-template-columns: 1fr; } }
.persona-card { cursor: pointer; }
.persona-card__row { display: grid; grid-template-columns: auto 1fr auto; gap: var(--s-3); align-items: center; }
.persona-card__name { font-weight: 600; color: var(--c-text); }
.persona-card__sub  { color: var(--c-text-muted); font-size: var(--fs-12); }
.persona-card__tags { display: flex; flex-wrap: wrap; gap: 6px; margin: var(--s-3) 0 var(--s-2); }
.persona-card__dims { display: flex; gap: var(--s-3); flex-wrap: wrap; color: var(--c-text-muted); font-size: var(--fs-12); }
.persona-card__dims b { color: var(--c-text); margin-right: 4px; font-weight: 600; }

.loading { padding: var(--s-6); color: var(--c-text-muted); }
</style>
