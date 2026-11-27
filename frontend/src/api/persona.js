import service from './index'

/**
 * 列出某模拟的所有用户画像（便签卡片数据）
 */
export const listPersonas = (simulationId) => {
  return service.get(`/api/persona/${simulationId}/list`)
}

/**
 * 获取 InvestorSegment 与映射结果
 */
export const getPersonaSegments = (simulationId) => {
  return service.get(`/api/persona/${simulationId}/segments`)
}
