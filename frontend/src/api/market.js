import axios from 'axios'

const baseURL = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:5001') + '/api/market'

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

export const marketApi = {
  btcOhlcv ({ interval = '1h', lookback = '7d' } = {}) {
    return client.get('/btc/ohlcv', { params: { interval, lookback } }).then(unwrap)
  },
  btcTicker () {
    return client.get('/btc/ticker').then(unwrap)
  },
  btcDepth (limit = 20) {
    return client.get('/btc/depth', { params: { limit } }).then(unwrap)
  },
  btcTrades (limit = 50) {
    return client.get('/btc/trades', { params: { limit } }).then(unwrap)
  }
}

export default marketApi
