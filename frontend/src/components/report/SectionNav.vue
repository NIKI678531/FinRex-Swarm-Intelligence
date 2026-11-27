<template>
  <aside class="section-nav">
    <div class="section-nav__title">REPORT SECTIONS</div>
    <a
      v-for="s in sections"
      :key="s.id"
      :href="`#${s.id}`"
      class="section-nav__item"
      :class="{ active: active === s.id }"
      @click.prevent="$emit('navigate', s.id)"
    >
      <span class="section-nav__bar"></span>
      <div class="section-nav__main">
        <div class="section-nav__name">{{ s.label }}</div>
        <div class="section-nav__hint">{{ s.hint }}</div>
      </div>
      <UiChip v-if="s.status" :tone="s.status === 'ready' ? 'bull' : 'warn'">
        {{ s.status === 'ready' ? '就绪' : '生成中' }}
      </UiChip>
    </a>
  </aside>
</template>

<script setup>
import { UiChip } from '@/components/ui'

defineProps({
  sections: { type: Array, required: true },   // [{ id, label, hint, status }]
  active:   { type: String, default: '' }
})
defineEmits(['navigate'])
</script>

<style scoped>
.section-nav {
  position: sticky; top: 84px;
  display: flex; flex-direction: column; gap: 4px;
  width: 240px;
  padding: var(--s-4);
  background: var(--c-bg-soft);
  border: 1px solid var(--c-border);
  border-radius: var(--r-lg);
  height: fit-content;
}
.section-nav__title {
  color: var(--c-accent);
  font-size: var(--fs-12); font-weight: 600; letter-spacing: .14em;
  margin-bottom: var(--s-2);
}
.section-nav__item {
  display: grid; grid-template-columns: 4px 1fr auto;
  gap: 10px; align-items: center;
  padding: 10px 8px;
  border-radius: var(--r-sm);
  text-decoration: none;
  color: var(--c-text);
  cursor: pointer;
}
.section-nav__item:hover { background: var(--c-bg); }
.section-nav__item.active { background: var(--c-bg); box-shadow: var(--shadow-1); }
.section-nav__item.active .section-nav__bar { background: var(--c-accent); }
.section-nav__bar { width: 4px; height: 24px; border-radius: 2px; background: var(--c-border); }
.section-nav__name { font-size: var(--fs-14); font-weight: 600; }
.section-nav__hint { font-size: var(--fs-12); color: var(--c-text-subtle); margin-top: 2px; }
</style>
