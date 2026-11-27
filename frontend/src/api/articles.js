import service, { requestWithRetry } from './index'

/**
 * 获取 FMP 文章列表（后端代理）
 * @param {Number} page  页码（FMP 是 0-based）
 * @param {Number} limit 每页条数
 */
export function fetchArticles(page = 0, limit = 100) {
  return requestWithRetry(() =>
    service({
      url: '/api/graph/articles',
      method: 'get',
      params: { page, limit }
    })
  )
}

/**
 * 获取 Binance 评论区帖子列表（Cloudflare D1）
 * @param {Object} opts {page, limit, source, since, q, min_comments}
 */
export function fetchBinanceArticles({ page = 0, limit = 20, source, since, q, min_comments } = {}) {
  const params = { page, limit }
  if (source) params.source = source
  if (since) params.since = since
  if (q) params.q = q
  if (min_comments) params.min_comments = min_comments
  return requestWithRetry(() =>
    service({
      url: '/api/graph/articles/binance',
      method: 'get',
      params
    })
  )
}

/**
 * 获取多个 Binance source 的帖子并在前端按 id 去重。
 * 后端 API 仍保持单 source 查询，避免为了前端筛选改后端接口。
 * @param {Object} opts {page, limit, sources, since, q, min_comments}
 */
export async function fetchBinanceArticlesBySources({ page = 0, limit = 20, sources = ['news'], since, q, min_comments } = {}) {
  const normalizedSources = [...new Set((sources || ['news']).filter(Boolean))]
  const requestSources = normalizedSources.length > 1 ? ['all'] : normalizedSources
  const requests = requestSources.map(source => fetchBinanceArticles({ page, limit, source, since, q, min_comments }))
  const responses = await Promise.all(requests)
  const seen = new Set()
  const items = []
  const warnings = []
  const dataQuality = []

  responses.forEach(response => {
    const warning = response.data?.warning || ''
    if (warning) warnings.push(warning)
    if (response.data?.data_quality) dataQuality.push(response.data.data_quality)
    ;(response.data?.items || []).forEach(item => {
      const key = item.id || item.link || `${item.source || 'binance'}:${item.title || ''}:${item.date || item.publish_time || ''}`
      if (seen.has(key)) return
      seen.add(key)
      items.push(item)
    })
  })

  items.sort((a, b) => Number(b.publish_time || 0) - Number(a.publish_time || 0))
  return {
    success: true,
    data: {
      items,
      page,
      limit,
      count: items.length,
      sources: normalizedSources,
      requested_sources: requestSources,
      warning: [...new Set(warnings)].join(' | '),
      data_quality: dataQuality
    }
  }
}

/**
 * Fetch Binance comments for one post when the backend D1 schema has comment rows.
 * Returns an empty list with comments_available=false when only post metadata exists.
 */
export function fetchBinanceArticleComments(postId, { limit = 200, offset = 0 } = {}) {
  return requestWithRetry(() =>
    service({
      url: `/api/graph/articles/binance/${encodeURIComponent(postId)}/comments`,
      method: 'get',
      params: { limit, offset }
    })
  )
}

/**
 * 用勾选的文章生成本体（替代 generateOntology 文件上传流程）
 * @param {Object} payload {articles, simulation_requirement, project_name?, additional_context?}
 */
export function generateOntologyFromArticles(payload) {
  return requestWithRetry(() =>
    service({
      url: '/api/graph/ontology/generate-from-articles',
      method: 'post',
      data: payload
    })
  )
}
