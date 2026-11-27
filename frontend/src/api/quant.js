import axios from 'axios'

const baseURL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5001'

const client = axios.create({
  baseURL: `${baseURL}/api/quant`,
  timeout: 300000,
  headers: { 'Content-Type': 'application/json' }
})

const unwrap = (p) => p.then(r => r.data)

export const quantApi = {
  listSymbols: () => unwrap(client.get('/symbols')),
  listRuns: () => unwrap(client.get('/backtest/runs')),
  createRun: (payload) => unwrap(client.post('/backtest/runs', payload)),
  getRun: (id) => unwrap(client.get(`/backtest/runs/${id}`)),
  equityCurve: (id) => unwrap(client.get(`/backtest/runs/${id}/equity-curve`)),
  trades: (id) => unwrap(client.get(`/backtest/runs/${id}/trades`)),
  deleteRun: (id) => unwrap(client.delete(`/backtest/runs/${id}`))
}

export default quantApi
