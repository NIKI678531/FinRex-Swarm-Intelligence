<template>
  <div class="dim-row">
    <header>
      <span class="ico">{{ icon }}</span>
      <span class="label">{{ label }}</span>
    </header>
    <div class="items"><slot /></div>
  </div>
</template>

<script setup>
defineProps({
  label: { type: String, required: true },
  icon:  { type: String, default: '◇' }
})
</script>

<style scoped>
.dim-row {
  padding: var(--s-3);
  border: 1px solid var(--c-border);
  border-radius: var(--r-md);
  background: var(--c-bg-soft);
}
.dim-row header { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.ico { color: var(--c-accent); font-size: 14px; }
.label {
  color: var(--c-text-subtle);
  font-size: var(--fs-12); font-weight: 600;
  letter-spacing: .12em; text-transform: uppercase;
}
.items {
  display: flex; flex-wrap: wrap; gap: var(--s-3);
  font-size: var(--fs-13); color: var(--c-text);
}
.items :deep(b) {
  font-weight: 600; color: var(--c-text-subtle);
  margin-right: 6px;
}
.items :deep(.full) { flex-basis: 100%; }
</style>
