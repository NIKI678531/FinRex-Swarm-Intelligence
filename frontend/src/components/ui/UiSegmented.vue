<template>
  <div class="ui-segmented" role="tablist">
    <button
      v-for="opt in options"
      :key="opt.value"
      role="tab"
      :aria-selected="opt.value === modelValue"
      class="ui-segmented__btn"
      :class="{ active: opt.value === modelValue }"
      @click="$emit('update:modelValue', opt.value)"
    >
      <span v-if="opt.icon" class="ui-segmented__icon">{{ opt.icon }}</span>
      <span>{{ opt.label }}</span>
      <span v-if="opt.badge !== undefined" class="ui-segmented__badge">{{ opt.badge }}</span>
    </button>
  </div>
</template>

<script setup>
defineProps({
  options:    { type: Array, required: true }, // [{ label, value, icon?, badge? }]
  modelValue: { type: [String, Number], required: true }
})
defineEmits(['update:modelValue'])
</script>

<style scoped>
.ui-segmented {
  display: inline-flex;
  padding: 4px;
  background: var(--c-bg-soft);
  border: 1px solid var(--c-border);
  border-radius: var(--r-md);
  gap: 2px;
}
.ui-segmented__btn {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 6px 14px;
  background: transparent;
  border: 0;
  border-radius: var(--r-sm);
  font-size: var(--fs-13); font-weight: 500;
  color: var(--c-text-muted);
  cursor: pointer;
  transition: background .16s ease, color .16s ease;
}
.ui-segmented__btn:hover { color: var(--c-text); }
.ui-segmented__btn.active {
  background: var(--c-bg);
  color: var(--c-brand);
  box-shadow: var(--shadow-1);
}
.ui-segmented__badge {
  font-size: 11px;
  padding: 1px 6px; border-radius: 8px;
  background: var(--c-accent-soft); color: var(--c-brand);
}
</style>
