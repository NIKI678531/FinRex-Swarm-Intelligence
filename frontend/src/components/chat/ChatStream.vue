<template>
  <section class="chat-stream">
    <header class="chat-stream__head">
      <div>
        <div class="chat-stream__title">与 {{ persona?.name || 'Persona' }} 对话</div>
        <div class="chat-stream__sub">基于 TA 的图谱记忆 + 立场，做 1:1 互动</div>
      </div>
      <UiButton variant="ghost" size="sm" @click="reset">清空</UiButton>
    </header>

    <main ref="scroller" class="chat-stream__body">
      <div v-if="!messages.length" class="chat-stream__empty">
        从问候开始：<br />
        "你怎么看下周的议息会议？"
      </div>
      <ChatBubble
        v-for="(m, i) in messages"
        :key="i"
        :role="m.role"
        :name="persona?.name"
        :seed="persona?.avatar_seed"
        :text="m.text"
        :streaming="m.streaming"
      />
    </main>

    <ChatComposer :disabled="busy" @send="onSend" />
  </section>
</template>

<script setup>
import { ref, watch, nextTick } from 'vue'
import { UiButton } from '@/components/ui'
import ChatBubble from './ChatBubble.vue'
import ChatComposer from './ChatComposer.vue'
import { mockChatStream } from '@/api/v2Mock'

const props = defineProps({ persona: { type: Object, default: null } })

const messages = ref([])
const busy     = ref(false)
const scroller = ref(null)

watch(() => props.persona?.id, () => { messages.value = []; busy.value = false })

async function onSend (text) {
  if (!props.persona) return
  messages.value.push({ role: 'user', text })
  await scrollToEnd()

  const idx = messages.value.push({ role: 'persona', text: '', streaming: true }) - 1
  busy.value = true

  for await (const ch of mockChatStream(props.persona.id, text)) {
    messages.value[idx].text += ch
    if (messages.value[idx].text.length % 8 === 0) scrollToEnd()
  }
  messages.value[idx].streaming = false
  busy.value = false
  scrollToEnd()
}

async function scrollToEnd () {
  await nextTick()
  if (scroller.value) scroller.value.scrollTop = scroller.value.scrollHeight
}

function reset () { messages.value = [] }
</script>

<style scoped>
.chat-stream {
  display: flex; flex-direction: column;
  height: 100%;
  background: var(--c-bg);
  border-left: 1px solid var(--c-border);
}
.chat-stream__head {
  display: flex; align-items: center; justify-content: space-between;
  padding: var(--s-3) var(--s-4);
  border-bottom: 1px solid var(--c-border);
}
.chat-stream__title { font-size: var(--fs-15); font-weight: 600; color: var(--c-text); }
.chat-stream__sub   { font-size: var(--fs-12); color: var(--c-text-subtle); margin-top: 2px; }

.chat-stream__body {
  flex: 1; overflow-y: auto;
  padding: var(--s-4);
  display: flex; flex-direction: column; gap: var(--s-3);
  background: linear-gradient(180deg, #FBFCFE 0%, #FFFFFF 100%);
}
.chat-stream__empty {
  margin: auto;
  text-align: center;
  color: var(--c-text-subtle);
  font-size: var(--fs-13);
  line-height: var(--lh-relaxed);
}
</style>
