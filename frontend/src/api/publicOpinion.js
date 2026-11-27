import service, { requestWithRetry } from './index'
import { normalizeReportId } from './reportIds'

export function getPublicOpinion(reportId) {
  return service.get(`/api/public-opinion/${encodeURIComponent(normalizeReportId(reportId))}`)
}

export function regeneratePublicOpinion(reportId) {
  return requestWithRetry(
    () => service.post(`/api/public-opinion/${encodeURIComponent(normalizeReportId(reportId))}/regenerate`),
    2,
    500
  )
}
