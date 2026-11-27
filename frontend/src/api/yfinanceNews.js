import service, { requestWithRetry } from './index'

/**
 * Yahoo Finance news API (via yfinance backend, 30min disk cache).
 * Backend: /api/yfinance/news
 */
function get (path, params = {}) {
  return requestWithRetry(() =>
    service({ url: `/api/yfinance/${path}`, method: 'get', params })
  ).then(res => {
    const payload = res?.data || res
    return payload?.items || payload?.data?.items || []
  })
}

export const yfinanceNews = {
  news: ({ symbol, limit = 15 } = {}) => get('news', { symbol, limit })
}
