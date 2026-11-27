import service, { requestWithRetry } from './index'

/**
 * Fetch the cached asset-allocation bundle for a report.
 * Returns { success, data: { kpis, top_picks, allocation, ... } }
 *
 * @param {string} reportId
 * @param {object} opts - { horizon: '1w' | '2w' | '1m' | number, force?: boolean }
 */
export function getAssetAllocation (reportId, opts = {}) {
  const params = {}
  if (opts.horizon) params.horizon = opts.horizon
  if (opts.force) params.force = 1
  return service.get(`/api/report/${encodeURIComponent(reportId)}/asset-allocation`, { params })
}

/**
 * Force-regenerate the asset-allocation bundle.
 */
export function regenerateAssetAllocation (reportId, payload = {}) {
  return requestWithRetry(
    () => service.post(`/api/report/${encodeURIComponent(reportId)}/asset-allocation`, payload),
    2,
    500
  )
}

/**
 * Detailed forecast + recent OHLCV for a single ETF (for the drawer).
 */
export function getEtfForecast (code, lookbackDays = 365, horizon = '1w') {
  return service.get(
    `/api/asset-allocation/etf/${encodeURIComponent(code)}/forecast`,
    { params: { lookback_days: lookbackDays, horizon } }
  )
}

