<template>
  <form class="composer" @submit.prevent="send">
    <textarea
      ref="ta"
      v-model="text"
      :disabled="disabled"
      rows="1"
      placeholder="问问 TA：你怎么看 6 月议息？"
      @keydown.enter.exact.prevent="send"
      @input="autoResize"
    />
    <UiButton type="submit" variant="primary" size="md" :disabled="!canSend">
      发送 ↵
    </UiButton>
  </form>
</template>

<script setup>
import { ref, computed, nextTick } from 'vue'
import { UiButton } from '@/components/ui'

const props = defineProps({ disabled: { type: Boolean, default: false } })
const emit  = defineEmits(['send'])

const text = ref('')
const ta   = ref(null)
const canSend = computed(() => text.value.trim().length > 0 && !props.disabled)

function send () {
  if (!canSend.value) return
  emit('send', text.value.trim())
  text.value = ''
  nextTick(autoResize)
}
function autoResize () {
  if (!ta.value) return
  ta.value.style.height = 'auto'
  ta.value.style.height = Math.min(160, ta.value.scrollHeight) + 'px'
}
</script>

<style scoped>
.composer {
  display: grid; grid-template-columns: 1fr auto;
  gap: var(--s-2);
  padding: var(--s-3);
  background: var(--c-bg);
  border-top: 1px solid var(--c-border);
}
textarea {
  resize: none;
  border: 1px solid var(--c-border);
  border-radius: var(--r-md);
  padding: 10px 12px;
  font-family: var(--f-sans);
  font-size: var(--fs-14);
  line-height: var(--lh-relaxed);
  background: var(--c-bg-soft);
  color: var(--c-text);
  min-height: 44px;
  max-height: 160px;
}
textarea:focus { outline: none; border-color: var(--c-accent); box-shadow: 0 0 0 2px var(--c-accent-soft); background: var(--c-bg); }
</style>
