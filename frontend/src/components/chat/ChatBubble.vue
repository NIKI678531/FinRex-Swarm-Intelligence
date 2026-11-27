<template>
  <div class="bubble" :class="`bubble--${role}`">
    <UiAvatar v-if="role === 'persona'" :name="name" :seed="seed" size="sm" />
    <div class="bubble__body">
      <span class="bubble__text">{{ text }}<span v-if="streaming" class="caret">▋</span></span>
    </div>
  </div>
</template>

<script setup>
import { UiAvatar } from '@/components/ui'

defineProps({
  role:      { type: String, default: 'persona' },   // persona | user
  name:      { type: String, default: '' },
  seed:      { type: String, default: '' },
  text:      { type: String, default: '' },
  streaming: { type: Boolean, default: false }
})
</script>

<style scoped>
.bubble { display: flex; gap: 10px; align-items: flex-end; }
.bubble--user { justify-content: flex-end; }
.bubble__body {
  max-width: 70%;
  padding: 10px 14px;
  border-radius: 16px;
  line-height: var(--lh-relaxed);
  font-size: var(--fs-14);
  white-space: pre-wrap; word-break: break-word;
}
.bubble--persona .bubble__body {
  background: var(--c-bg);
  color: var(--c-text);
  border: 1px solid var(--c-border-strong);
  border-bottom-left-radius: 4px;
  box-shadow: var(--shadow-1);
}
.bubble--user .bubble__body {
  background: var(--c-accent);
  color: #fff;
  border-bottom-right-radius: 4px;
  box-shadow: 0 6px 16px rgba(47, 107, 255, .25);
}
.caret { display: inline-block; margin-left: 2px; animation: caret 1s step-end infinite; color: var(--c-accent); }
@keyframes caret { 50% { opacity: 0; } }
</style>
