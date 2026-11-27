<template>
  <div class="ui-avatar" :class="[`ui-avatar--${size}`]" :style="bgStyle" :title="name">
    <img v-if="src" :src="src" :alt="name" />
    <span v-else class="ui-avatar__initials">{{ initials }}</span>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  name: { type: String, default: '' },
  src:  { type: String, default: '' },
  size: { type: String, default: 'md' }, // sm | md | lg
  seed: { type: String, default: '' }    // 用于色相生成
})

const initials = computed(() => {
  if (!props.name) return '?'
  const parts = props.name.trim().split(/\s+/)
  return (parts[0][0] + (parts[1]?.[0] || '')).toUpperCase()
})

// 简单 hash → hue
const hue = computed(() => {
  const s = props.seed || props.name || '?'
  let h = 0
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) % 360
  return h
})
const bgStyle = computed(() => ({
  background: `hsl(${hue.value}deg 60% 92%)`,
  color: `hsl(${hue.value}deg 50% 30%)`
}))
</script>

<style scoped>
.ui-avatar {
  display: inline-flex; align-items: center; justify-content: center;
  border-radius: 50%;
  overflow: hidden;
  font-weight: 600;
  user-select: none;
  border: 1px solid var(--c-border);
}
.ui-avatar img { width: 100%; height: 100%; object-fit: cover; }
.ui-avatar--sm { width: 28px; height: 28px; font-size: 11px; }
.ui-avatar--md { width: 40px; height: 40px; font-size: 14px; }
.ui-avatar--lg { width: 64px; height: 64px; font-size: 22px; }
</style>
