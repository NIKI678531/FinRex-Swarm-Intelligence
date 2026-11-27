import service, { requestWithRetry } from './index'

/**
 * FMP News & Social Sentiment unified client — covers all 15 FMP `stable` endpoints
 * mounted at /api/fmp/news/*
 *
 * Categories: General / Stock / Crypto / Forex / Press Releases / Articles /
 *             Search / Social Sentiment (Trending, Changes, Historical)
 */

function get (path, params = {}) {
  return requestWithRetry(() =>
    service({ url: `/api/fmp/news/${path}`, method: 'get', params })
  ).then(res => {
    // service returns res.data; backend wraps as {success, data:{items,count}}
    const payload = res?.data || res
    return payload?.items || payload?.data?.items || []
  })
}

// ----- News categories -----
export const fmpNews = {
  general:           ({ page = 0, limit = 100, from, to } = {}) => get('general', { page, limit, from, to }),
  stock:             ({ symbols, page = 0, limit = 100, from, to } = {}) => get('stock', { symbols, page, limit, from, to }),
  stockLatest:       ({ page = 0, limit = 100 } = {}) => get('stock-latest', { page, limit }),
  crypto:            ({ symbols, page = 0, limit = 100, from, to } = {}) => get('crypto', { symbols, page, limit, from, to }),
  cryptoLatest:      ({ page = 0, limit = 100 } = {}) => get('crypto-latest', { page, limit }),
  forex:             ({ symbols, page = 0, limit = 100, from, to } = {}) => get('forex', { symbols, page, limit, from, to }),
  forexLatest:       ({ page = 0, limit = 100 } = {}) => get('forex-latest', { page, limit }),
  pressReleases:     ({ symbols, page = 0, limit = 100, from, to } = {}) => get('press-releases', { symbols, page, limit, from, to }),
  pressReleasesLatest: ({ page = 0, limit = 100 } = {}) => get('press-releases-latest', { page, limit }),
  search:            ({ q, page = 0, limit = 100, from, to } = {}) => get('search', { q, page, limit, from, to }),
  articles:          ({ page = 0, size = 20 } = {}) => get('articles', { page, size }),
  fmpArticles:       ({ page = 0, size = 20 } = {}) => get('fmp-articles', { page, size }),

  // Social sentiment
  socialHistorical:  ({ symbol, page = 0 } = {}) => get('social-sentiment/historical', { symbol, page }),
  socialTrending:    ({ type = 'bullish', source = 'stocktwits' } = {}) => get('social-sentiment/trending', { type, source }),
  socialChanges:     ({ type = 'bullish', source = 'stocktwits' } = {}) => get('social-sentiment/changes', { type, source }),

  health: () => requestWithRetry(() => service({ url: '/api/fmp/news/health', method: 'get' }))
}

export default fmpNews
