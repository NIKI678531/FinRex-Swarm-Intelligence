/**
 * Financial Factor Adapter
 *
 * 把 ReportAgent.financial_context（observed/inferred/simulated/forecast）
 * 归一化为可视化组件需要的 dataset。所有函数纯函数无副作用，
 * 在 financial_context 缺字段时给出合理的空数组/默认值，避免组件里散落判空。
 */

const FACTOR_LABELS = {
  technical: '技术面',
  technical_trend: '技术面',
  sentiment: '舆情面',
  volume: '资金/成交',
  derivatives: '衍生品',
  oasis_pulse: 'OASIS 脉冲',
  composite: '综合',
}

const DEFAULT_WEIGHTS = {
  technical: 0.4,
  technical_trend: 0.4,
  sentiment: 0.3,
  volume: 0.15,
  derivatives: 0.15,
  oasis_pulse: 0.3,
}

const POS_COLOR = '#26A269'
const NEG_COLOR = '#C0392B'
const NEU_COLOR = '#94A3B8'

function num (v, fallback = 0) {
  if (v == null || v === '' || Number.isNaN(Number(v))) return fallback
  return Number(v)
}

function colorFor (value) {
  const n = num(value, 0)
  if (n > 0.05) return POS_COLOR
  if (n < -0.05) return NEG_COLOR
  return NEU_COLOR
}

/**
 * 抽取因子三元组：[{ key, label, score, weight, color }]
 * 优先 crypto 分支的 score_breakdown，其次 forecast.factors。
 */
export function extractFactors (financialContext) {
  const fc = financialContext || {}
  const forecast = fc.forecast || {}
  const crypto = forecast.crypto_forecast || null

  const breakdown = crypto?.score_breakdown
  const factors = forecast.factors || {}
  const weights = factors.weights || crypto?.factors?.weights || {}

  const source = breakdown && Object.keys(breakdown).length
    ? breakdown
    : Object.fromEntries(
        Object.entries(factors).filter(([k]) => k !== 'weights' && k !== 'composite')
      )

  return Object.entries(source).map(([key, score]) => ({
    key,
    label: FACTOR_LABELS[key] || key,
    score: num(score, 0),
    weight: num(weights[key], DEFAULT_WEIGHTS[key] ?? 0),
    color: colorFor(score),
  }))
}

/** 综合分 (composite) */
export function extractComposite (financialContext) {
  const f = financialContext?.forecast || {}
  return num(f.factors?.composite ?? f.crypto_forecast?.factors?.composite, 0)
}

/**
 * 因子 Sankey 数据：原始数据源 → 中间因子 → 加权融合 → 最终方向
 * value 用 |score| * weight * 100 作为流量粗细。
 */
export function buildFactorSankey (financialContext) {
  const factors = extractFactors(financialContext)
  const direction = String(financialContext?.forecast?.direction || 'neutral').toLowerCase()
  const directionNode = ['up', 'bullish'].includes(direction)
    ? '看涨 ↑'
    : ['down', 'bearish'].includes(direction)
      ? '看跌 ↓'
      : '中性 →'

  // 数据源 → 因子 的对应关系
  const sourceMap = {
    technical: '行情/OHLCV',
    technical_trend: '行情/OHLCV',
    sentiment: '新闻 + 评论',
    volume: '成交量',
    derivatives: '资金费率/合约',
    oasis_pulse: 'OASIS 模拟脉冲',
  }

  const nodes = []
  const seen = new Set()
  function addNode (name, depth) {
    const key = `${depth}::${name}`
    if (seen.has(key)) return
    seen.add(key)
    nodes.push({ name, depth })
  }

  const links = []
  factors.forEach(f => {
    const src = sourceMap[f.key] || '其他信号'
    addNode(src, 0)
    addNode(f.label, 1)
    addNode('加权融合', 2)
    addNode(directionNode, 3)
    const flow = Math.max(0.5, Math.abs(f.score) * (f.weight || 0.2) * 100)
    links.push({ source: src, target: f.label, value: flow, lineStyle: { color: f.color, opacity: 0.45 } })
    links.push({ source: f.label, target: '加权融合', value: flow, lineStyle: { color: f.color, opacity: 0.55 } })
  })
  if (factors.length) {
    const total = factors.reduce((s, f) => s + Math.max(0.5, Math.abs(f.score) * (f.weight || 0.2) * 100), 0)
    links.push({
      source: '加权融合',
      target: directionNode,
      value: Math.max(1, total),
      lineStyle: { color: colorFor(extractComposite(financialContext)), opacity: 0.7 }
    })
  }

  return { nodes, links }
}

/** 雷达图：双层（实际分数 vs 权重） */
export function buildFactorRadar (financialContext) {
  const factors = extractFactors(financialContext)
  if (!factors.length) return { indicator: [], series: [] }
  // 把 score 从 [-1,1] 归一到 [0,1] 便于雷达比较
  const scoreSeries = factors.map(f => (num(f.score) + 1) / 2)
  const weightSeries = factors.map(f => num(f.weight))
  return {
    indicator: factors.map(f => ({ name: f.label, max: 1 })),
    series: [
      { name: '实际得分（归一）', value: scoreSeries },
      { name: '权重', value: weightSeries },
    ],
  }
}

/** 因子条形图数据 */
export function buildFactorBars (financialContext) {
  const factors = extractFactors(financialContext)
  return factors.map(f => ({
    label: f.label,
    score: f.score,
    weight: f.weight,
    contribution: f.score * f.weight,
    color: f.color,
  }))
}

/** 价格 sparkline：从 observed.ohlcv_recent 抽 close 序列 */
export function buildPriceSparkline (financialContext) {
  const ohlcv = financialContext?.observed?.ohlcv_recent || []
  if (!Array.isArray(ohlcv) || !ohlcv.length) return { data: [], labels: [] }
  return {
    labels: ohlcv.map(r => r.date || r.timestamp || ''),
    data: ohlcv.map(r => num(r.close ?? r[4] ?? r.c, null)).filter(v => v != null),
  }
}

/** 情绪 sparkline：从 inferred.sentiment_timeline 抽 score 序列 */
export function buildSentimentSparkline (financialContext) {
  const tl = financialContext?.inferred?.sentiment_timeline || []
  if (!Array.isArray(tl) || !tl.length) return { data: [], labels: [] }
  return {
    labels: tl.map(r => r.date || r.window || r.timestamp || ''),
    data: tl.map(r => num(r.score ?? r.compound ?? r.value, 0)),
  }
}

/** OHLCV 转 ECharts candlestick 数据 [open, close, low, high] */
export function buildCandlestick (financialContext) {
  const ohlcv = financialContext?.observed?.ohlcv_recent || []
  if (!Array.isArray(ohlcv) || !ohlcv.length) return { dates: [], data: [] }
  return {
    dates: ohlcv.map(r => r.date || r.timestamp || ''),
    data: ohlcv.map(r => [
      num(r.open ?? r.o, 0),
      num(r.close ?? r.c, 0),
      num(r.low ?? r.l, 0),
      num(r.high ?? r.h, 0),
    ]),
  }
}

export const FACTOR_COLORS = { POS_COLOR, NEG_COLOR, NEU_COLOR }
