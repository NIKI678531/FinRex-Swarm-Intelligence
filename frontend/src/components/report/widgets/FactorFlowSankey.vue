<template>
  <div class="factor-sankey">
    <EChart v-if="hasData" :option="option" :height="height" />
    <div v-else class="empty">暂无足够因子数据生成流水图</div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import EChart from './EChart.vue'
import { buildFactorSankey } from './financialFactorAdapter'

const props = defineProps({
  financialContext: { type: Object, default: () => ({}) },
  height: { type: String, default: '320px' },
})

const sankey = computed(() => buildFactorSankey(props.financialContext))
const hasData = computed(() => sankey.value.nodes.length > 0 && sankey.value.links.length > 0)

const option = computed(() => ({
  tooltip: { trigger: 'item', triggerOn: 'mousemove' },
  series: [{
    type: 'sankey',
    left: 8,
    right: 80,
    top: 12,
    bottom: 12,
    nodeWidth: 14,
    nodeGap: 10,
    layoutIterations: 32,
    emphasis: { focus: 'adjacency' },
    data: sankey.value.nodes.map(n => ({
      name: n.name,
      itemStyle: {
        color: n.depth === 3 ? '#1F2937' : n.depth === 2 ? '#0EA5E9' : n.depth === 1 ? '#6366F1' : '#94A3B8'
      }
    })),
    links: sankey.value.links,
    label: { color: '#1F2937', fontSize: 12 },
    lineStyle: { curveness: 0.5 },
  }]
}))
</script>

<style scoped>
.factor-sankey { width: 100%; }
.empty { padding: 24px; color: #94A3B8; text-align: center; font-size: 13px; }
</style>
