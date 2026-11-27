<template>
  <UiCard padding="md" class="profile-card">
    <header class="profile-card__head">
      <UiAvatar :name="persona.name" :seed="persona.avatar_seed" size="lg" />
      <div class="profile-card__title">
        <h2>{{ persona.name }}</h2>
        <p>{{ persona.profession }} · {{ persona.dimensions.demographics.city }}</p>
        <div class="profile-card__tags">
          <UiChip v-for="t in persona.tags" :key="t" tone="brand">{{ t }}</UiChip>
        </div>
      </div>
      <UiChip :tone="stanceTone(persona.dimensions.signals.stance)" solid>
        当前立场 · {{ stanceLabel(persona.dimensions.signals.stance) }}
      </UiChip>
    </header>

    <div class="dim-grid">
      <DimRow label="人口" icon="◐">
        <span><b>年龄</b>{{ persona.dimensions.demographics.age }}</span>
        <span><b>性别</b>{{ persona.dimensions.demographics.gender }}</span>
      </DimRow>
      <DimRow label="心理" icon="◇">
        <span><b>MBTI</b>{{ persona.dimensions.psychology.mbti }}</span>
        <span><b>风险</b>{{ persona.dimensions.psychology.risk }}</span>
        <span><b>BIG5</b>{{ persona.dimensions.psychology.big5 }}</span>
      </DimRow>
      <DimRow label="投资" icon="◆">
        <span><b>风格</b>{{ persona.dimensions.investment.style }}</span>
        <span><b>周期</b>{{ persona.dimensions.investment.horizon }}</span>
        <span class="full"><b>组合</b>{{ persona.dimensions.investment.portfolio }}</span>
      </DimRow>
      <DimRow label="行为" icon="◌">
        <span><b>发帖</b>{{ persona.dimensions.behavior.post_freq }}/天</span>
        <span><b>回帖率</b>{{ Math.round(persona.dimensions.behavior.reply_rate * 100) }}%</span>
        <span><b>峰值</b>{{ persona.dimensions.behavior.peak_hour }}</span>
      </DimRow>
      <DimRow label="社交" icon="✦">
        <span><b>粉丝</b>{{ persona.dimensions.social.followers }}</span>
        <span><b>影响力</b>{{ Math.round(persona.dimensions.social.influence * 100) }}</span>
        <span v-if="persona.dimensions.social.follows.length"><b>关注</b>{{ persona.dimensions.social.follows.join(', ') }}</span>
      </DimRow>
      <DimRow label="信号" icon="⚡">
        <span><b>动量</b>{{ persona.dimensions.signals.momentum }}</span>
        <span><b>最近活跃</b>{{ formatTime(persona.dimensions.signals.last_active) }}</span>
      </DimRow>
    </div>
  </UiCard>
</template>

<script setup>
import { UiCard, UiChip, UiAvatar } from '@/components/ui'
import DimRow from './_DimRow.vue'

defineProps({ persona: { type: Object, required: true } })

const STANCE = {
  bull: { label: '看多', tone: 'bull' },
  bear: { label: '看空', tone: 'bear' },
  contrarian: { label: '逆向', tone: 'warn' },
  neutral: { label: '中性', tone: 'neutral' }
}
const stanceLabel = s => STANCE[s]?.label || s
const stanceTone  = s => STANCE[s]?.tone  || 'neutral'

function formatTime (iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}
</script>

<style scoped>
.profile-card__head {
  display: grid; grid-template-columns: auto 1fr auto;
  gap: var(--s-4); align-items: center;
  margin-bottom: var(--s-4); padding-bottom: var(--s-4);
  border-bottom: 1px solid var(--c-border);
}
.profile-card__title h2 { font-size: var(--fs-22); font-weight: 700; margin: 0 0 4px; color: var(--c-text); }
.profile-card__title p  { color: var(--c-text-muted); margin: 0 0 var(--s-2); font-size: var(--fs-13); }
.profile-card__tags { display: flex; flex-wrap: wrap; gap: 6px; }
.dim-grid { display: grid; grid-template-columns: 1fr 1fr; gap: var(--s-3); }
@media (max-width: 700px) { .dim-grid { grid-template-columns: 1fr; } }
</style>
