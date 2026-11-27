<template>
  <button
    class="ui-btn"
    :class="[`ui-btn--${variant}`, `ui-btn--${size}`, { 'is-block': block, 'is-loading': loading }]"
    :type="type"
    :disabled="disabled || loading"
    @click="$emit('click', $event)"
  >
    <span v-if="loading" class="ui-btn__spinner" aria-hidden="true"></span>
    <slot />
  </button>
</template>

<script setup>
defineProps({
  variant:  { type: String, default: 'primary' }, // primary | ghost | link | danger
  size:     { type: String, default: 'md' },      // sm | md | lg
  type:     { type: String, default: 'button' },
  block:    { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
  loading:  { type: Boolean, default: false }
})
defineEmits(['click'])
</script>

<style scoped>
.ui-btn {
  display: inline-flex; align-items: center; justify-content: center; gap: 8px;
  border: 1px solid transparent;
  border-radius: var(--r-md);
  font-family: var(--f-sans);
  font-weight: 600;
  cursor: pointer;
  transition: background .18s ease, color .18s ease, border-color .18s ease, box-shadow .18s ease;
  user-select: none;
}
.ui-btn[disabled] { opacity: .5; cursor: not-allowed; }
.ui-btn.is-block { width: 100%; }

.ui-btn--sm { padding: 6px 12px;  font-size: var(--fs-13); }
.ui-btn--md { padding: 10px 18px; font-size: var(--fs-14); }
.ui-btn--lg { padding: 12px 22px; font-size: var(--fs-16); }

.ui-btn--primary { background: var(--c-brand); color: #fff; }
.ui-btn--primary:hover:not([disabled]) { background: var(--c-brand-strong); }

.ui-btn--ghost { background: transparent; color: var(--c-brand); border-color: var(--c-border-strong); }
.ui-btn--ghost:hover:not([disabled]) { background: var(--c-accent-soft); border-color: var(--c-accent); }

.ui-btn--link { background: transparent; color: var(--c-accent); padding-left: 4px; padding-right: 4px; }
.ui-btn--link:hover:not([disabled]) { color: var(--c-brand); text-decoration: underline; }

.ui-btn--danger { background: var(--c-bear); color: #fff; }
.ui-btn--danger:hover:not([disabled]) { background: #B12E25; }

.ui-btn__spinner {
  width: 12px; height: 12px;
  border: 2px solid currentColor; border-top-color: transparent;
  border-radius: 50%; animation: ui-btn-spin .9s linear infinite;
}
@keyframes ui-btn-spin { to { transform: rotate(360deg); } }
</style>
