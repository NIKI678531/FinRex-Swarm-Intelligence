/**
 * Workflow Resolver
 *
 * 解析当前路由所处的 workflow 步骤，并提供跨页面前进/后退所需的 ID。
 *
 * 步骤定义（6 节点）：
 *   sentiment   -> /sentiment
 *   step1_2     -> /process/:projectId   (MainView)
 *   step3       -> /simulation/:simulationId/start
 *   step4       -> /report/:reportId/replay
 *   step5       -> /interaction/:reportId
 *   unified     -> /report/:reportId
 *
 * 注：原 step7 'analysis' 节点已下线，buildRouteForStep 中保留 'analysis' 兼容
 * 别名，将旧链接 fallback 到 Interaction 页，避免外部链接失效。
 */

import api from '@/api/index'

export const WORKFLOW_STEPS = [
  { key: 'sentiment', label: 'Sentiment', routeName: 'Sentiment' },
  { key: 'step1_2',   label: 'Step 1-2',  routeName: 'Process' },
  { key: 'step3',     label: 'Step 3',    routeName: 'SimulationRun' },
  { key: 'step4',     label: 'Step 4',    routeName: 'ReportReplay' },
  { key: 'step5',     label: 'Step 5',    routeName: 'Interaction' },
  { key: 'unified',   label: 'Unified Report',   routeName: 'Report' }
]

/**
 * 根据当前 route 推断当前 step key
 */
export function resolveCurrentStep (route) {
  const name = route?.name
  if (name === 'Sentiment') return 'sentiment'
  if (name === 'Process') return 'step1_2'
  if (name === 'Simulation' || name === 'SimulationRun') return 'step3'
  if (name === 'ReportReplay') return 'step4'
  if (name === 'Interaction') return 'step5'
  if (name === 'Report') return 'unified'
  return null
}

/**
 * 通过当前 route + 必要的 API 调用，解析出 prev / next 跳转所需的所有 id。
 *
 * 返回：
 *   {
 *     projectId, simulationId, reportId,
 *     narrativeReportId, financialReportId
 *   }
 */
export async function resolveWorkflowContext (route) {
  const ctx = {
    projectId: route?.params?.projectId || null,
    simulationId: route?.params?.simulationId || null,
    reportId: route?.params?.reportId || null,
    narrativeReportId: null,
    financialReportId: null,
  }

  // 从 reportId -> simulationId -> projectId 反推
  if (ctx.reportId && !ctx.simulationId) {
    try {
      const res = await api.get(`/api/report/${ctx.reportId}`)
      const data = res.data?.data || res.data
      ctx.simulationId = data?.simulation_id || null
    } catch (e) { /* ignore */ }
  }

  if (ctx.simulationId) {
    try {
      const res = await api.get(`/api/simulation/${ctx.simulationId}/reports`)
      const data = res.data?.data || res.data
      ctx.narrativeReportId = data?.narrative_report_id || null
      ctx.financialReportId = data?.financial_report_id || null
      if (!ctx.reportId) ctx.reportId = ctx.narrativeReportId || ctx.financialReportId
    } catch (e) { /* ignore */ }
  }

  if (ctx.simulationId && !ctx.projectId) {
    try {
      const res = await api.get(`/api/simulation/${ctx.simulationId}`)
      const data = res.data?.data || res.data
      ctx.projectId = data?.project_id || null
    } catch (e) { /* ignore */ }
  }

  return ctx
}

/**
 * 根据 step key + 上下文，返回对应路由的 { name, params }；若无法跳转返回 null。
 */
export function buildRouteForStep (stepKey, ctx) {
  switch (stepKey) {
    case 'sentiment':
      return { name: 'Sentiment' }
    case 'step1_2':
      return ctx.projectId ? { name: 'Process', params: { projectId: ctx.projectId } } : null
    case 'step3':
      return ctx.simulationId ? { name: 'SimulationRun', params: { simulationId: ctx.simulationId } } : null
    case 'step4': {
      const id = ctx.narrativeReportId || ctx.reportId
      return id ? { name: 'ReportReplay', params: { reportId: id } } : null
    }
    case 'step5': {
      const id = ctx.narrativeReportId || ctx.reportId
      return id ? { name: 'Interaction', params: { reportId: id } } : null
    }
    case 'unified': {
      const id = ctx.narrativeReportId || ctx.reportId || ctx.financialReportId
      return id ? { name: 'Report', params: { reportId: id } } : null
    }
    case 'analysis': {
      const id = ctx.narrativeReportId || ctx.reportId
      return id ? { name: 'Interaction', params: { reportId: id } } : null
    }
    default:
      return null
  }
}

/**
 * 给定当前 step + ctx，返回 prev / next route（不可达时为 null）。
 */
export function getNeighbors (currentKey, ctx) {
  const idx = WORKFLOW_STEPS.findIndex(s => s.key === currentKey)
  if (idx < 0) return { prev: null, next: null }
  const prevKey = idx > 0 ? WORKFLOW_STEPS[idx - 1].key : null
  const nextKey = idx < WORKFLOW_STEPS.length - 1 ? WORKFLOW_STEPS[idx + 1].key : null
  return {
    prev: prevKey ? buildRouteForStep(prevKey, ctx) : null,
    next: nextKey ? buildRouteForStep(nextKey, ctx) : null,
  }
}

/**
 * 返回每个 step 是否可达（用于 Stepper 灰显）。
 * 注：保留 analysis 键作为 buildRouteForStep 兼容别名的可达性判定。
 */
export function getStepReachability (ctx) {
  return {
    sentiment: true,
    step1_2: !!ctx.projectId,
    step3: !!ctx.simulationId,
    step4: !!(ctx.narrativeReportId || ctx.reportId),
    step5: !!(ctx.narrativeReportId || ctx.reportId),
    unified: !!(ctx.narrativeReportId || ctx.reportId || ctx.financialReportId),
    analysis: !!(ctx.narrativeReportId || ctx.reportId),
  }
}
