import service, { requestWithRetry } from './index'
import { normalizeReportId } from './reportIds'

/**
 * 开始报告生成
 * @param {Object} data - { simulation_id, force_regenerate? }
 */
export const generateReport = (data) => {
  return requestWithRetry(() => service.post('/api/report/generate', data), 3, 1000)
}

/**
 * 获取报告生成状态
 * @param {string|Object} input - reportId or { task_id, simulation_id, report_id }
 */
export const getReportStatus = (input) => {
  const params = typeof input === 'string'
    ? { report_id: normalizeReportId(input) }
    : {
        task_id: input?.task_id,
        simulation_id: input?.simulation_id,
        report_id: normalizeReportId(input?.report_id || input?.reportId)
      }

  Object.keys(params).forEach(key => {
    if (params[key] === undefined || params[key] === null || params[key] === '') delete params[key]
  })

  return service.get(`/api/report/generate/status`, { params })
}

/**
 * 获取 Agent 日志（增量）
 * @param {string} reportId
 * @param {number} fromLine - 从第几行开始获取
 */
export const getAgentLog = (reportId, fromLine = 0) => {
  return service.get(`/api/report/${normalizeReportId(reportId)}/agent-log`, { params: { from_line: fromLine } })
}

/**
 * 获取控制台日志（增量）
 * @param {string} reportId
 * @param {number} fromLine - 从第几行开始获取
 */
export const getConsoleLog = (reportId, fromLine = 0) => {
  return service.get(`/api/report/${normalizeReportId(reportId)}/console-log`, { params: { from_line: fromLine } })
}

/**
 * 获取报告详情
 * @param {string} reportId
 */
export const getReport = (reportId) => {
  return service.get(`/api/report/${normalizeReportId(reportId)}`)
}

/**
 * 根据 simulation_id 获取报告
 * @param {string} simulationId
 * @param {string} [reportType] 'narrative' | 'financial' | 'both'
 */
export const getReportBySimulation = (simulationId, reportType) => {
  const params = reportType ? { report_type: reportType } : {}
  return service.get(`/api/report/by-simulation/${simulationId}`, { params })
}

/**
 * 与 Report Agent 对话
 * @param {Object} data - { simulation_id, message, chat_history? }
 */
export const chatWithReport = (data) => {
  return requestWithRetry(() => service.post('/api/report/chat', data), 3, 1000)
}
