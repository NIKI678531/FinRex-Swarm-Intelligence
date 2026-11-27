import service, { requestWithRetry } from './index'

export function getContentStudio(reportId) {
  return service.get(`/api/content-studio/${encodeURIComponent(reportId)}`)
}

export function generateContentStudio(reportId, payload = {}) {
  return requestWithRetry(
    () => service.post(`/api/content-studio/${encodeURIComponent(reportId)}/generate`, payload),
    2,
    500
  )
}

export function checkContent(payload) {
  return service.post('/api/content-studio/check', payload)
}

export function updateContentPost(postId, payload) {
  return service.patch(`/api/content-studio/posts/${encodeURIComponent(postId)}`, payload)
}

