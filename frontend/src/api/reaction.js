import service, { requestWithRetry } from './index'

export const analyzeReaction = (payload) => {
  return requestWithRetry(() => service.post('/api/reaction/analyze', payload), 2, 800)
}

export const getReactionReportContext = (runId) => {
  return service.get(`/api/reaction/${runId}/report-context`)
}
