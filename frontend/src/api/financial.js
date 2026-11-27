import service, { requestWithRetry } from './index'

export function postCryptoForecast (payload = {}) {
  return requestWithRetry(
    () => service.post('/api/financial/crypto-forecast', payload),
    2,
    500
  )
}
