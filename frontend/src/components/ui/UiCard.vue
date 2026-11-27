<template>
  <div
    class="ui-card"
    :class="[
      `ui-card--pad-${padding}`,
      { 'ui-card--elevated': elevated, 'ui-card--accent': accent, 'ui-card--hoverable': hoverable }
    ]"
  >
    <header v-if="$slots.header" class="ui-card__header">
      <slot name="header" />
    </header>
    <div class="ui-card__body">
      <slot />
    </div>
    <footer v-if="$slots.footer" class="ui-card__footer">
      <slot name="footer" />
    </footer>
  </div>
</template>

<script setup>
defineProps({
  padding:   { type: String, default: 'md' }, // sm | md | lg
  elevated:  { type: Boolean, default: false },
  accent:    { type: Boolean, default: false },
  hoverable: { type: Boolean, default: false }
})
</script>

<style scoped>
.ui-card {
  background: var(--c-bg);
  border: 1px solid var(--c-border);
  border-radius: var(--r-lg);
  box-shadow: var(--shadow-1);
  transition: box-shadow .22s ease, border-color .22s ease, transform .22s ease;
}
.ui-card--elevated  { box-shadow: var(--shadow-2); }
.ui-card--accent    { border-color: var(--c-accent); box-shadow: 0 0 0 3px var(--c-accent-soft); }
.ui-card--hoverable:hover {
  border-color: var(--c-border-strong);
  box-shadow: var(--shadow-2);
  transform: translateY(-1px);
}
.ui-card--pad-sm .ui-card__body { padding: var(--s-3); }
.ui-card--pad-md .ui-card__body { padding: var(--s-5); }
.ui-card--pad-lg .ui-card__body { padding: var(--s-6); }
.ui-card__header {
  padding: var(--s-4) var(--s-5);
  border-bottom: 1px solid var(--c-border);
  font-weight: 600;
  color: var(--c-text);
}
.ui-card__footer {
  padding: var(--s-3) var(--s-5);
  border-top: 1px solid var(--c-border);
  color: var(--c-text-muted);
  font-size: var(--fs-13);
}
</style>
