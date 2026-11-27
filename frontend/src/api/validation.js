// Weekly bins-based Validation Lab API client.
// Companion to backend `/api/validation/*` endpoints.
import axios from 'axios'

const baseURL = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:5001') + '/api/validation'

const client = axios.create({ baseURL, timeout: 30_000 })

function unwrap (resp) {
  const body = resp.data || {}
  if (body.success === false) {
    const err = new Error(body.error || 'Request failed')
    err.payload = body
    throw err
  }
  return body.data
}

export const validationApi = {
  cycleCurrent (symbol = 'BTC') {
    return client.get('/cycle/current', { params: { symbol } }).then(unwrap)
  },
  snapshot ({ symbol = 'BTC', n_paths = 5000, place_bets = true, model_family = null } = {}) {
    return client.post('/snapshot', { symbol, n_paths, place_bets, model_family }).then(unwrap)
  },
  models () {
    return client.get('/models').then(unwrap)
  },
  forecastLatest (symbol = 'BTC') {
    return client.get('/forecast/latest', { params: { symbol } }).then(unwrap)
  },
  polymarketWeekly ({ mode = 'current', limit = 10 } = {}) {
    return client.get('/polymarket/weekly', { params: { mode, limit } }).then(unwrap)
  },
  positions (symbol = 'BTC', status = 'all') {
    return client.get('/positions', { params: { symbol, status } }).then(unwrap)
  },
  kpi (symbol = 'BTC') {
    return client.get('/kpi', { params: { symbol } }).then(unwrap)
  },
  equityCurve (symbol = 'BTC') {
    return client.get('/equity-curve', { params: { symbol } }).then(unwrap)
  },
  settle (symbol = 'BTC') {
    return client.post('/settle', { symbol }).then(unwrap)
  },
  forceSettle (symbol = 'BTC') {
    return client.post('/admin/force-settle', { symbol }).then(unwrap)
  }
}

export default validationApi
