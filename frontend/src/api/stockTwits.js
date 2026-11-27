import service, { requestWithRetry } from './index'

/**
 * StockTwits public stream API.
 * Backend: /api/stocktwits/stream
 */
function get (path, params = {}) {
  return requestWithRetry(() =>
    service({ url: `/api/stocktwits/${path}`, method: 'get', params })
  ).then(res => {
    const payload = res?.data || res
    return payload?.items || payload?.data?.items || []
  })
}

export const stockTwits = {
  stream: ({ symbol, limit = 30 } = {}) => get('stream', { symbol, limit })
}
