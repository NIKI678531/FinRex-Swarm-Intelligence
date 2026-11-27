import axios from 'axios'

const baseURL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5001'

const client = axios.create({
  baseURL: `${baseURL}/api/paper-trading`,
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' }
})

const unwrap = (p) => p.then(r => r.data)

export const paperTradingApi = {
  listSymbols: () => unwrap(client.get('/symbols')),
  listAccounts: () => unwrap(client.get('/accounts')),
  createAccount: (payload) => unwrap(client.post('/accounts', payload)),
  getAccount: (id) => unwrap(client.get(`/accounts/${id}`)),
  deleteAccount: (id) => unwrap(client.delete(`/accounts/${id}`)),
  listOrders: (id) => unwrap(client.get(`/accounts/${id}/orders`)),
  placeOrder: (id, payload) => unwrap(client.post(`/accounts/${id}/orders`, payload)),
  equityCurve: (id) => unwrap(client.get(`/accounts/${id}/equity-curve`)),
  weekly: (id) => unwrap(client.get(`/accounts/${id}/weekly`)),
  quote: (symbol) => unwrap(client.get(`/quotes/${encodeURIComponent(symbol)}`)),
  ohlcv: (symbol, params = {}) => unwrap(client.get(`/ohlcv/${encodeURIComponent(symbol)}`, { params })),
  cancelOrder: (id, orderId) => unwrap(client.delete(`/accounts/${id}/orders/${orderId}`)),
  latestSignal: (symbol) => unwrap(client.get(`/signals/${encodeURIComponent(symbol)}`)),
  fusedSignal: (symbol) => unwrap(client.get(`/signals/fused/${encodeURIComponent(symbol)}`)),
  runAutoTrade: (id, payload = {}) => unwrap(client.post(`/accounts/${id}/auto-trade/run`, payload)),
  startAutoTrade: (id, payload = {}) => unwrap(client.post(`/accounts/${id}/auto-trade/start`, payload)),
  pollAutoTask: (taskId) => unwrap(client.get(`/auto-trade/tasks/${taskId}`)),
  autoTradeConfig: () => unwrap(client.get('/auto-trade/config'))
}

export default paperTradingApi
