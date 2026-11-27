import service, { requestWithRetry } from './index'

/**
 * Reddit posts API (public JSON proxy, no credentials required).
 * Backend: /api/reddit/posts
 */
function get (path, params = {}) {
  return requestWithRetry(() =>
    service({ url: `/api/reddit/${path}`, method: 'get', params })
  ).then(res => {
    const payload = res?.data || res
    return payload?.items || payload?.data?.items || []
  })
}

export const redditNews = {
  posts: ({ symbol, subreddits, limit_per_sub = 8 } = {}) =>
    get('posts', { symbol, subreddits, limit_per_sub })
}
