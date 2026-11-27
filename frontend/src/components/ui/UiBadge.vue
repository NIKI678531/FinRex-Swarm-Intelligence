<template>
  <span class="ui-badge" :class="[`ui-badge--${tone}`]">
    <span v-if="dot" class="ui-badge__dot"></span>
    <slot />
  </span>
</template>

<script setup>
defineProps({
  tone: { type: String, default: 'neutral' }, // neutral | brand | bull | bear | warn
  dot:  { type: Boolean, default: true }
})
</script>

<style scoped>
.ui-badge {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: var(--fs-12); font-weight: 500;
  color: var(--c-text-muted);
}
.ui-badge__dot { width: 8px; height: 8px; border-radius: 50%; background: currentColor; }
.ui-badge--brand { color: var(--c-brand); }
.ui-badge--bull  { color: var(--c-bull); }
.ui-badge--bear  { color: var(--c-bear); }
.ui-badge--warn  { color: var(--c-warn); }
</style>
