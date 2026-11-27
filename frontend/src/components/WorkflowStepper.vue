<template>
  <div class="workflow-stepper">
    <div class="stepper-nodes">
      <template v-for="(step, idx) in steps" :key="step.key">
        <div
          class="step-node"
          :class="{
            active: step.key === currentKey,
            done: idx < currentIdx && reachability[step.key],
            disabled: !reachability[step.key]
          }"
          @click="onClickStep(step)"
          :title="reachability[step.key] ? step.label : `${step.label}（暂不可达，请先完成前序步骤）`"
        >
          <span class="step-index">{{ idx + 1 }}</span>
          <span class="step-label">{{ step.label }}</span>
        </div>
        <div v-if="idx < steps.length - 1" class="step-divider" :class="{ done: idx < currentIdx }"></div>
      </template>
    </div>

    <div class="stepper-actions">
      <button class="nav-btn" :disabled="!prevRoute" @click="goPrev">‹ Prev</button>
      <button class="nav-btn primary" :disabled="!nextRoute" @click="goNext">Next ›</button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  WORKFLOW_STEPS,
  resolveCurrentStep,
  resolveWorkflowContext,
  buildRouteForStep,
  getNeighbors,
  getStepReachability,
} from '@/hooks/useWorkflowResolver'

const route = useRoute()
const router = useRouter()

const steps = WORKFLOW_STEPS
const ctx = ref({ projectId: null, simulationId: null, reportId: null, narrativeReportId: null, financialReportId: null })
const reachability = ref({})

const currentKey = computed(() => resolveCurrentStep(route))
const currentIdx = computed(() => steps.findIndex(s => s.key === currentKey.value))

const neighbors = computed(() => getNeighbors(currentKey.value, ctx.value))
const prevRoute = computed(() => neighbors.value.prev)
const nextRoute = computed(() => neighbors.value.next)

const refreshContext = async () => {
  ctx.value = await resolveWorkflowContext(route)
  reachability.value = getStepReachability(ctx.value)
}

onMounted(refreshContext)
watch(() => route.fullPath, refreshContext)

const goPrev = () => { if (prevRoute.value) router.push(prevRoute.value) }
const goNext = () => { if (nextRoute.value) router.push(nextRoute.value) }

const onClickStep = (step) => {
  if (!reachability.value[step.key]) return
  const target = buildRouteForStep(step.key, ctx.value)
  if (target) router.push(target)
}
</script>

<style scoped>
.workflow-stepper {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 10px 16px;
  background: #fff;
  border-bottom: 1px solid #eee;
  font-size: 12px;
}

.stepper-nodes {
  display: flex;
  align-items: center;
  flex: 1;
  overflow-x: auto;
}

.step-node {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border-radius: 16px;
  cursor: pointer;
  white-space: nowrap;
  background: #f4f4f4;
  color: #888;
  border: 1px solid transparent;
  transition: all .15s;
}

.step-node:hover:not(.disabled) { background: #ececec; }
.step-node.active { background: #1a1a1a; color: #fff; border-color: #1a1a1a; }
.step-node.done { background: #e8f5e9; color: #2e7d32; }
.step-node.disabled { cursor: not-allowed; opacity: .45; }

.step-index {
  display: inline-flex;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: rgba(0,0,0,.08);
  align-items: center;
  justify-content: center;
  font-weight: 600;
}
.step-node.active .step-index { background: rgba(255,255,255,.2); }
.step-node.done .step-index { background: rgba(46,125,50,.18); }

.step-divider {
  width: 18px;
  height: 1px;
  background: #ddd;
  margin: 0 4px;
}
.step-divider.done { background: #2e7d32; }

.stepper-actions { display: flex; gap: 8px; }
.nav-btn {
  padding: 6px 14px;
  border-radius: 4px;
  border: 1px solid #ccc;
  background: #fff;
  cursor: pointer;
  font-size: 12px;
}
.nav-btn:hover:not(:disabled) { border-color: #1a1a1a; }
.nav-btn.primary { background: #1a1a1a; color: #fff; border-color: #1a1a1a; }
.nav-btn:disabled { opacity: .4; cursor: not-allowed; }
</style>
