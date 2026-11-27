import service from './index'
import { normalizeReportId } from './reportIds'
import {
  fetchReportMeta as fetchMockReportMeta,
  fetchDashboard as fetchMockDashboard,
  fetchPersonasSection as fetchMockPersonasSection,
  fetchPredictions as fetchMockPredictions,
  fetchPostsForTheme as fetchMockPostsForTheme,
  fetchHighlights as fetchMockHighlights
} from './v2Mock'

const bundleCache = new Map()

export function clearReportBundleCache(reportId) {
  if (reportId) bundleCache.delete(normalizeReportId(reportId))
  else bundleCache.clear()
}

async function fetchRealBundle(reportId, options = {}) {
  reportId = normalizeReportId(reportId)
  if (!reportId || reportId === 'rpt_demo') return null
  if (!options.force && bundleCache.has(reportId)) return bundleCache.get(reportId)

  try {
    const res = await service.get(`/api/report/${encodeURIComponent(reportId)}/v2`)
    const bundle = res?.data || null
    bundleCache.set(reportId, bundle)
    return bundle
  } catch (error) {
    console.warn('[reportV2] falling back to demo data:', error?.message || error)
    bundleCache.set(reportId, null)
    return null
  }
}

export async function fetchReportMeta(reportId) {
  const bundle = await fetchRealBundle(reportId)
  return bundle?.meta || fetchMockReportMeta(reportId)
}

export async function fetchDashboard(reportId) {
  const bundle = await fetchRealBundle(reportId)
  return bundle?.dashboard || fetchMockDashboard(reportId)
}

export async function fetchPersonasSection(reportId) {
  const bundle = await fetchRealBundle(reportId)
  return bundle?.personas || fetchMockPersonasSection(reportId)
}

export async function fetchPredictions(reportId) {
  const bundle = await fetchRealBundle(reportId)
  return bundle?.predictions || fetchMockPredictions(reportId)
}

export async function fetchPostsForTheme(reportId, themeId, n = 3) {
  const bundle = await fetchRealBundle(reportId)
  const posts = bundle?.posts_by_theme?.[themeId]
  if (Array.isArray(posts) && posts.length) {
    return { posts: posts.slice(0, n) }
  }
  return fetchMockPostsForTheme(reportId, themeId, n)
}

export async function fetchHighlights(reportId, personaId) {
  const bundle = await fetchRealBundle(reportId)
  const personas = bundle?.personas?.personas || []
  const persona = personas.find(item => item.id === personaId)
  const topics = bundle?.public_opinion?.hot_topics || []

  if (persona && topics.length) {
    return {
      scope: 'persona',
      id: personaId,
      highlights: topics.slice(0, 3).map((topic, index) => ({
        id: `${personaId}_h_${index + 1}`,
        text: `${persona.name} 关注“${topic.title}”：${topic.summary}`,
        stance: persona.dimensions?.signals?.stance || topic.stance || 'neutral',
        evidence_post_ids: topic.evidence_ids || [],
        ts_range: [bundle.meta?.generated_at || '', bundle.meta?.generated_at || '']
      }))
    }
  }

  return fetchMockHighlights(personaId)
}
