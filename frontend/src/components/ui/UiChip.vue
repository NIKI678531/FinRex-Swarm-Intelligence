<template>
  <span class="ui-chip" :class="[`ui-chip--${tone}`, { 'is-solid': solid }]">
    <span v-if="dot" class="ui-chip__dot"></span>
    <slot />
  </span>
</template>

<script setup>
defineProps({
  tone:  { type: String, default: 'neutral' }, // neutral | bull | bear | brand | warn
  solid: { type: Boolean, default: false },
  dot:   { type: Boolean, default: false }
})
</script>

<style scoped>
.ui-chip {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 3px 10px;
  border-radius: 999px;
  font-size: var(--fs-12); font-weight: 500;
  border: 1px solid transparent;
  white-space: nowrap;
}
.ui-chip__dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }

.ui-chip--neutral { color: var(--c-text-muted); background: var(--c-bg-soft); border-color: var(--c-border); }
.ui-chip--brand   { color: var(--c-brand);     background: var(--c-accent-soft); border-color: #D6E2FF; }
.ui-chip--bull    { color: var(--c-bull);      background: #E7F6EE; border-color: #C7E9D5; }
.ui-chip--bear    { color: var(--c-bear);      background: #FBE9E7; border-color: #F2C8C3; }
.ui-chip--warn    { color: var(--c-warn);      background: #FBEFD7; border-color: #ECD3A0; }

.ui-chip.is-solid.ui-chip--brand { background: var(--c-brand); color: #fff; border-color: var(--c-brand); }
.ui-chip.is-solid.ui-chip--bull  { background: var(--c-bull);  color: #fff; border-color: var(--c-bull); }
.ui-chip.is-solid.ui-chip--bear  { background: var(--c-bear);  color: #fff; border-color: var(--c-bear); }
</style>
