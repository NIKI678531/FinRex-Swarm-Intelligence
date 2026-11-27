export const DIRECTION_LABELS = {
  bullish: '看涨',
  bearish: '看跌',
  volatile: '高波动',
  neutral: '中性',
  risk_off: '避险'
}

export const SIGNAL_CATEGORIES = [
  { key: 'all', label: '全部主题' },
  { key: 'macro_policy', label: '宏观政策' },
  { key: 'sector_rotation', label: '行业轮动' },
  { key: 'market_sentiment', label: '市场情绪' },
  { key: 'fund_flow', label: '资金流向' },
  { key: 'regional_hotspot', label: '区域热点' }
]

export const SIGNAL_RULES = [
  {
    id: 'SIG-M01',
    name: '降息/宽松预期',
    category: 'macro_policy',
    direction: 'bullish',
    productDomains: ['FI_US_TREASURY', 'A_BROAD_BASE', 'HK_TECH'],
    keywords: ['降息', '宽松', '鸽派', '利率下行', 'rate cut', 'easing', 'dovish', 'liquidity']
  },
  {
    id: 'SIG-M02',
    name: '加息/紧缩预期',
    category: 'macro_policy',
    direction: 'bearish',
    productDomains: ['MM_USD', 'HK_TECH_INVERSE', 'FI_CN_BOND'],
    keywords: ['加息', '紧缩', '鹰派', '通胀', 'cpi', 'inflation', 'hike', 'hawkish', 'higher for longer']
  },
  {
    id: 'SIG-M03',
    name: '地缘风险升级',
    category: 'macro_policy',
    direction: 'risk_off',
    productDomains: ['COMMODITY_GOLD', 'FI_ALL', 'MM_ALL'],
    keywords: ['战争', '冲突', '制裁', '地缘', 'war', 'conflict', 'sanction', 'geopolitical', 'tariff']
  },
  {
    id: 'SIG-M04',
    name: '中国政策利好',
    category: 'macro_policy',
    direction: 'bullish',
    productDomains: ['A_BROAD_BASE', 'HK_INDEX', 'HK_TECH'],
    keywords: ['中国政策', '刺激', '稳增长', '产业扶持', '财政', 'china stimulus', 'policy support']
  },
  {
    id: 'SIG-S01',
    name: '科技热潮',
    category: 'sector_rotation',
    direction: 'bullish',
    productDomains: ['HK_TECH', 'REG_NASDAQ', 'MAG7', 'SINGLE_NVDA'],
    keywords: ['ai', '人工智能', '半导体', '芯片', '科技', '英伟达', 'nvidia', 'nvda', 'semiconductor', 'chip']
  },
  {
    id: 'SIG-S02',
    name: '新能源/ESG热',
    category: 'sector_rotation',
    direction: 'bullish',
    productDomains: ['A_PV', 'A_BROAD_BASE'],
    keywords: ['新能源', '光伏', '太阳能', '碳中和', 'esg', 'solar', 'renewable', 'green energy']
  },
  {
    id: 'SIG-S03',
    name: '生物医药突破',
    category: 'sector_rotation',
    direction: 'bullish',
    productDomains: ['HK_BIOTECH', 'A_BROAD_BASE'],
    keywords: ['医药', '生物', '疫苗', '创新药', 'biotech', 'pharma', 'drug approval', 'healthcare']
  },
  {
    id: 'SIG-S04',
    name: '加密货币热潮',
    category: 'sector_rotation',
    direction: 'volatile',
    productDomains: ['VA_BTC', 'VA_ETH', 'SINGLE_COIN'],
    keywords: ['比特币', '以太', '加密', '币安', 'btc', 'bitcoin', 'eth', 'ethereum', 'crypto', 'web3', 'binance']
  },
  {
    id: 'SIG-S05',
    name: '中东/能源主题',
    category: 'sector_rotation',
    direction: 'volatile',
    productDomains: ['REG_SAUDI', 'COMMODITY_GOLD'],
    keywords: ['石油', '油价', '天然气', '中东', '沙特', 'oil', 'energy', 'saudi', 'opec']
  },
  {
    id: 'SIG-E01',
    name: '极度恐慌',
    category: 'market_sentiment',
    direction: 'risk_off',
    productDomains: ['COMMODITY_GOLD', 'FI_ALL', 'HK_TECH_INVERSE'],
    keywords: ['恐慌', '暴跌', '黑天鹅', '爆仓', 'crash', 'panic', 'fear', 'selloff', 'liquidation']
  },
  {
    id: 'SIG-E02',
    name: '极度贪婪/FOMO',
    category: 'market_sentiment',
    direction: 'volatile',
    productDomains: ['HK_HIGH_DIV', 'HK_COVERED_CALL', 'MM_ALL'],
    keywords: ['fomo', '追涨', '狂热', '暴涨', '新高', 'greed', 'all time high', 'ath', 'moon']
  },
  {
    id: 'SIG-E03',
    name: '市场拐点信号',
    category: 'market_sentiment',
    direction: 'neutral',
    productDomains: ['A_BROAD_BASE', 'COMMODITY_GOLD', 'MM_ALL'],
    keywords: ['拐点', '背离', '反转', '回归', 'turning point', 'divergence', 'reversal', 'mean reversion']
  },
  {
    id: 'SIG-F01',
    name: '互联互通资金异动',
    category: 'fund_flow',
    direction: 'bullish',
    productDomains: ['HK_INDEX', 'HK_TECH'],
    keywords: ['北水', '南下', '南水', '北上', '互联互通', 'southbound', 'northbound', 'connect flow']
  },
  {
    id: 'SIG-F02',
    name: '外资流入A股',
    category: 'fund_flow',
    direction: 'bullish',
    productDomains: ['A_BROAD_BASE'],
    keywords: ['外资', 'msci', '流入a股', 'foreign inflow', 'inflow', 'rebalancing']
  },
  {
    id: 'SIG-F03',
    name: '避险资金涌入',
    category: 'fund_flow',
    direction: 'risk_off',
    productDomains: ['COMMODITY_GOLD', 'FI_ALL'],
    keywords: ['避险资金', '资金流入黄金', '国债流入', 'safe haven', 'gold inflow', 'treasury inflow']
  },
  {
    id: 'SIG-R01',
    name: '日本市场热',
    category: 'regional_hotspot',
    direction: 'bullish',
    productDomains: ['REG_JAPAN'],
    keywords: ['日本', '日经', '日元', 'nikkei', 'japan', 'yen']
  },
  {
    id: 'SIG-R02',
    name: '越南/东南亚热',
    category: 'regional_hotspot',
    direction: 'bullish',
    productDomains: ['REG_VIETNAM'],
    keywords: ['越南', '东南亚', '产业链转移', 'vietnam', 'asean', 'southeast asia']
  },
  {
    id: 'SIG-R03',
    name: '美股科技热',
    category: 'regional_hotspot',
    direction: 'bullish',
    productDomains: ['REG_NASDAQ', 'MAG7'],
    keywords: ['美股', '纳斯达克', '七巨头', 'nasdaq', 'mag7', 's&p', 'us tech']
  }
]

const DEFAULT_SIGNAL = {
  id: 'SIG-UNK',
  name: '待分类市场事件',
  category: 'market_sentiment',
  direction: 'neutral',
  productDomains: ['A_BROAD_BASE', 'MM_ALL'],
  confidence: 0.25,
  matched_keywords: []
}

export function getCategoryLabel (category) {
  return SIGNAL_CATEGORIES.find(item => item.key === category)?.label || category || '未分类'
}

export function getDirectionLabel (direction) {
  return DIRECTION_LABELS[direction] || direction || '中性'
}

export function classifySignalSeed (seed = {}) {
  const text = [
    seed.title,
    seed.sub_title,
    seed.summary,
    seed.content,
    seed.tickers,
    seed.trading_pairs,
    seed.author,
    seed.site,
    seed.source
  ].filter(Boolean).join(' ').toLowerCase()

  let best = null
  for (const rule of SIGNAL_RULES) {
    const matched = rule.keywords.filter(keyword => text.includes(keyword.toLowerCase()))
    if (!matched.length) continue
    const score = matched.length / Math.max(rule.keywords.length, 1)
    if (!best || matched.length > best.matched_keywords.length || score > best.score) {
      best = { ...rule, matched_keywords: matched, score }
    }
  }

  const result = best || DEFAULT_SIGNAL
  return {
    id: result.id,
    name: result.name,
    category: result.category,
    categoryLabel: getCategoryLabel(result.category),
    direction: result.direction,
    directionLabel: getDirectionLabel(result.direction),
    productDomains: result.productDomains || [],
    confidence: result.confidence || Math.min(0.88, 0.42 + (result.matched_keywords?.length || 0) * 0.08),
    matched_keywords: result.matched_keywords || []
  }
}

export function buildClassificationSummary (items = []) {
  const summary = {}
  for (const item of items) {
    const category = item.signal_category || item.classification?.category || 'market_sentiment'
    const direction = item.direction_hint || item.classification?.direction || 'neutral'
    const key = `${category}:${direction}`
    if (!summary[key]) {
      summary[key] = {
        category,
        category_label: getCategoryLabel(category),
        direction,
        direction_label: getDirectionLabel(direction),
        count: 0,
        signals: []
      }
    }
    summary[key].count += 1
    const signalId = item.signal_id || item.classification?.id
    if (signalId && !summary[key].signals.includes(signalId)) summary[key].signals.push(signalId)
  }
  return Object.values(summary)
}
