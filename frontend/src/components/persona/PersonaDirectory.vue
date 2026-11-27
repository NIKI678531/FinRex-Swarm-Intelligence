<template>
  <aside class="persona-dir">
    <div class="persona-dir__search">
      <input
        v-model="q"
        type="text"
        placeholder="搜索 Persona / 关键词"
      />
    </div>

    <div v-for="cluster in groupedClusters" :key="cluster.id" class="persona-dir__group">
      <header class="persona-dir__group-head">
        <span class="cluster-name">{{ cluster.name }}</span>
        <UiChip tone="neutral">{{ cluster.personas.length }}</UiChip>
      </header>
      <ul>
        <li
          v-for="p in cluster.personas"
          :key="p.id"
          class="persona-dir__item"
          :class="{ active: p.id === activeId }"
          @click="$emit('select', p.id)"
        >
          <UiAvatar :name="p.name" :seed="p.avatar_seed" size="sm" />
          <div class="persona-dir__main">
            <div class="persona-dir__name">{{ p.name }}</div>
            <div class="persona-dir__sub">{{ p.profession }}</div>
          </div>
          <UiChip :tone="stanceTone(p.dimensions.signals.stance)">
            {{ stanceLabel(p.dimensions.signals.stance) }}
          </UiChip>
        </li>
      </ul>
    </div>
  </aside>
</template>

<script setup>
import { ref, computed } from 'vue'
import { UiAvatar, UiChip } from '@/components/ui'

const props = defineProps({
  personas: { type: Array, required: true },
  clusters: { type: Array, required: true },
  activeId: { type: String, default: '' }
})
defineEmits(['select'])

const q = ref('')

const filtered = computed(() => {
  const k = q.value.trim().toLowerCase()
  if (!k) return props.personas
  return props.personas.filter(p =>
    p.name.toLowerCase().includes(k) ||
    p.profession.toLowerCase().includes(k) ||
    p.tags.some(t => t.toLowerCase().includes(k)) ||
    p.id.toLowerCase().includes(k)
  )
})

const groupedClusters = computed(() =>
  props.clusters.map(c => ({
    ...c,
    personas: filtered.value.filter(p => p.cluster_id === c.id)
  })).filter(c => c.personas.length)
)

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
.persona-dir {
  display: flex; flex-direction: column;
  height: 100%;
  background: var(--c-bg-soft);
  border-right: 1px solid var(--c-border);
  overflow-y: auto;
}
.persona-dir__search { padding: var(--s-3); border-bottom: 1px solid var(--c-border); }
.persona-dir__search input {
  width: 100%; padding: 8px 12px;
  border: 1px solid var(--c-border);
  border-radius: var(--r-md);
  background: var(--c-bg);
  font-family: var(--f-sans);
  font-size: var(--fs-13);
  color: var(--c-text);
}
.persona-dir__search input:focus { outline: none; border-color: var(--c-accent); box-shadow: 0 0 0 2px var(--c-accent-soft); }

.persona-dir__group { padding: var(--s-2) 0; }
.persona-dir__group-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 6px var(--s-3);
}
.cluster-name {
  color: var(--c-text-subtle);
  font-size: var(--fs-12); font-weight: 600;
  letter-spacing: .08em; text-transform: uppercase;
}

.persona-dir__group ul { list-style: none; padding: 0; margin: 0; }
.persona-dir__item {
  display: grid; grid-template-columns: auto 1fr auto;
  gap: 10px; align-items: center;
  padding: 8px var(--s-3);
  cursor: pointer;
  border-left: 3px solid transparent;
}
.persona-dir__item:hover { background: var(--c-bg); }
.persona-dir__item.active {
  background: var(--c-bg);
  border-left-color: var(--c-accent);
}
.persona-dir__name { font-size: var(--fs-13); font-weight: 600; color: var(--c-text); }
.persona-dir__sub  { font-size: var(--fs-12); color: var(--c-text-muted); }
</style>
