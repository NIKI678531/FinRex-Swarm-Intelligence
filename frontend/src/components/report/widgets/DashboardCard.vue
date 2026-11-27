<template>
  <section class="dash-card" :class="{ accent, collapsed: isCollapsed }">
    <header class="dc-head" :class="{ clickable: collapsible }" @click="onToggle">
      <div class="dc-titles">
        <h3>{{ title }}</h3>
        <p v-if="subtitle">{{ subtitle }}</p>
      </div>
      <button v-if="collapsible" type="button" class="dc-toggle">
        {{ isCollapsed ? '展开 +' : '收起 −' }}
      </button>
    </header>
    <div v-show="!isCollapsed" class="dc-body">
      <slot />
    </div>
  </section>
</template>

<script setup>
import { ref } from 'vue'

const props = defineProps({
  title: { type: String, required: true },
  subtitle: { type: String, default: '' },
  accent: { type: Boolean, default: false },
  collapsible: { type: Boolean, default: false },
  defaultCollapsed: { type: Boolean, default: false },
})

const isCollapsed = ref(props.collapsible && props.defaultCollapsed)

function onToggle () {
  if (props.collapsible) isCollapsed.value = !isCollapsed.value
}
</script>

<style scoped>
.dash-card {
  background: #FFF;
  border: 1px solid #E5E7EB;
  border-radius: 12px;
  padding: 16px 18px;
  margin-bottom: 16px;
}
.dash-card.accent {
  border-color: #6366F1;
  box-shadow: 0 2px 12px rgba(99, 102, 241, 0.08);
}
.dc-head {
  display: flex; justify-content: space-between; align-items: flex-start; gap: 12px;
  margin-bottom: 12px; padding-bottom: 10px; border-bottom: 1px solid #F1F5F9;
}
.dc-head.clickable { cursor: pointer; }
.dash-card.accent .dc-head { border-bottom-color: #E0E7FF; }
.dc-titles h3 { margin: 0; font-size: 15px; font-weight: 700; color: #111; letter-spacing: .02em; }
.dash-card.accent .dc-titles h3 { color: #4F46E5; }
.dc-titles p { margin: 4px 0 0; font-size: 12px; color: #64748B; }
.dc-toggle { border: 1px solid #E5E7EB; background: #FFF; color: #475569; padding: 4px 10px; border-radius: 4px; font-size: 11px; cursor: pointer; }
.dash-card.collapsed { padding-bottom: 12px; }
.dash-card.collapsed .dc-head { margin-bottom: 0; padding-bottom: 0; border-bottom: none; }
</style>
