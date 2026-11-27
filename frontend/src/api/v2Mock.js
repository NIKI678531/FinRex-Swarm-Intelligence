/**
 * 改版 v2 的 Mock 数据层
 * 后端就绪后，把这里的 fetchers 替换成 axios 调用即可。
 *
 * 真实接口不可用时，用这里的报告看板 mock 保持页面可预览。
 */

const wait = (ms = 200) => new Promise(r => setTimeout(r, ms))

// ────────────────────────── REPORT META ──────────────────────────
export async function fetchReportMeta (reportId) {
  await wait(80)
  return {
    id: reportId,
    simulation_id: 'sim_demo',
    status: 'ready',
    generated_at: '2026-05-04T08:00:00Z',
    summary: '围绕"美联储 6 月议息预期"做的多 Persona 双平台仿真：声量在 T+18h 出现首个高峰，情绪从中性偏多滑向震荡；预测主力资金 72h 内回流科技板块，但需警惕长尾风险。',
    sections: [
      { id: 'dashboard',   kind: 'dashboard',   status: 'ready' },
      { id: 'personas',    kind: 'personas',    status: 'ready' },
      { id: 'predictions', kind: 'predictions', status: 'ready' }
    ]
  }
}

// ────────────────────────── DASHBOARD (Section 1) ──────────────────────────
function genTimeline () {
  const out = []
  let t = new Date('2026-04-20T08:00:00Z').getTime()
  let v = 120, s = 0.05
  for (let i = 0; i < 80; i++) {
    // 模拟 3 个脉冲
    const pulse = (i === 18 || i === 42 || i === 60) ? 850 + Math.random() * 300 : 0
    v = Math.max(40, v * 0.92 + (Math.random() - 0.45) * 80 + pulse * 0.6)
    s = Math.max(-1, Math.min(1, s + (Math.random() - 0.5) * 0.18))
    out.push({ t: new Date(t).toISOString(), volume: Math.round(v), sentiment: +s.toFixed(2) })
    t += 60 * 60 * 1000 // 每小时
  }
  return out
}

export async function fetchDashboard (reportId) {
  await wait(180)
  const timeline = genTimeline()
  const peak = timeline.reduce((a, b) => b.volume > a.volume ? b : a)
  const avg = timeline.reduce((s, x) => s + x.sentiment, 0) / timeline.length
  return {
    kpis: {
      total_volume: timeline.reduce((s, x) => s + x.volume, 0),
      peak_time: peak.t,
      sentiment_avg: +avg.toFixed(2),
      active_personas: 76
    },
    timeline,
    pulse_events: [
      {
        t: timeline[18].t, volume: timeline[18].volume,
        title: '科技股集体下挫', summary: 'Persona p_42 起始，48 分钟扩散到 30 个节点',
        trigger_post_id: 'post_seed_1'
      },
      {
        t: timeline[42].t, volume: timeline[42].volume,
        title: 'KOL 反向喊话', summary: 'KOL_07 发表"估值未达底部"观点，转发 580 次',
        trigger_post_id: 'post_seed_2'
      },
      {
        t: timeline[60].t, volume: timeline[60].volume,
        title: '资金回流科技', summary: '主力资金 ETF 出现连续 3h 净流入',
        trigger_post_id: 'post_seed_3'
      }
    ],
    key_events: [
      { t: timeline[6].t,  label: '事件起点：政策草案泄露',     weight: 0.6, post_ids: [] },
      { t: timeline[18].t, label: '科技股大跌 2.4%',           weight: 0.9, post_ids: ['post_seed_1'] },
      { t: timeline[28].t, label: '群体情绪由中性转为悲观',     weight: 0.7, post_ids: [] },
      { t: timeline[42].t, label: 'KOL 反向观点引发讨论',      weight: 0.8, post_ids: ['post_seed_2'] },
      { t: timeline[60].t, label: '主力资金 ETF 回流',         weight: 0.85, post_ids: ['post_seed_3'] },
      { t: timeline[72].t, label: '声量回落至基线',           weight: 0.4, post_ids: [] }
    ]
  }
}

// ────────────────────────── PERSONAS (Section 2) ──────────────────────────
const CLUSTERS = [
  { id: 'cl_tech_aggressive', name: '科技积极型', size: 24,
    summary: '高风险偏好，对 AI / 半导体高度敏感的群体。事件初期最先发声，扩散力强。',
    top_persona_ids: ['p_204', 'p_148', 'p_077'] },
  { id: 'cl_defensive', name: '避险保守型', size: 18,
    summary: '风险厌恶，倾向防御板块；在情绪悲观点位入场，发声以风险提示为主。',
    top_persona_ids: ['p_312', 'p_355'] },
  { id: 'cl_yield', name: '收息型', size: 12,
    summary: '关注高股息标的，对利率政策非常敏感。',
    top_persona_ids: ['p_402'] },
  { id: 'cl_contrarian', name: '逆向型', size: 9,
    summary: '在共识高点反向操作；声量小但触达精准。',
    top_persona_ids: ['p_511'] }
]

const PERSONAS = [
  {
    id: 'p_204', name: '张志远', avatar_seed: 'p_204',
    cluster_id: 'cl_tech_aggressive',
    profession: '私募研究员', tags: ['bull-tech', 'mid-risk', 'fundamentals'],
    dimensions: {
      demographics: { age: 34, gender: 'male', city: '上海' },
      psychology:   { mbti: 'ENTP', risk: '中高', big5: 'O+/C+/E+/A-/N-' },
      investment:   { style: '成长', horizon: '6-12m', portfolio: '科技 60% · 周期 20% · 防御 20%' },
      behavior:     { post_freq: 4.2, reply_rate: 0.61, peak_hour: '21:00' },
      social:       { followers: 1240, influence: 0.72, follows: ['KOL_07'] },
      signals:      { stance: 'bull', momentum: '上升', last_active: '2026-05-04T10:08:00Z' }
    }
  },
  {
    id: 'p_148', name: 'Linda Wei', avatar_seed: 'p_148',
    cluster_id: 'cl_tech_aggressive',
    profession: '科技 KOL', tags: ['bull-tech', 'high-risk', 'narrative'],
    dimensions: {
      demographics: { age: 29, gender: 'female', city: '北京' },
      psychology:   { mbti: 'ENFP', risk: '高', big5: 'O+/C-/E+/A+/N-' },
      investment:   { style: '主题轮动', horizon: '1-3m', portfolio: 'AI 50% · 半导体 30% · 现金 20%' },
      behavior:     { post_freq: 7.8, reply_rate: 0.42, peak_hour: '23:00' },
      social:       { followers: 5400, influence: 0.88, follows: [] },
      signals:      { stance: 'bull', momentum: '强', last_active: '2026-05-04T11:21:00Z' }
    }
  },
  {
    id: 'p_077', name: 'Marco Lin', avatar_seed: 'p_077',
    cluster_id: 'cl_tech_aggressive',
    profession: '量化研究员', tags: ['data-driven', 'mid-risk'],
    dimensions: {
      demographics: { age: 31, gender: 'male', city: '深圳' },
      psychology:   { mbti: 'INTJ', risk: '中', big5: 'O+/C+/E-/A/N-' },
      investment:   { style: '量化因子', horizon: '1-6m', portfolio: '多因子组合' },
      behavior:     { post_freq: 1.6, reply_rate: 0.18, peak_hour: '14:00' },
      social:       { followers: 320, influence: 0.31, follows: ['p_148'] },
      signals:      { stance: 'neutral', momentum: '中', last_active: '2026-05-04T09:30:00Z' }
    }
  },
  {
    id: 'p_312', name: '王素芬', avatar_seed: 'p_312',
    cluster_id: 'cl_defensive',
    profession: '保险资管', tags: ['defensive', 'low-risk'],
    dimensions: {
      demographics: { age: 47, gender: 'female', city: '深圳' },
      psychology:   { mbti: 'ISTJ', risk: '低', big5: 'O-/C+/E-/A+/N+' },
      investment:   { style: '稳健配置', horizon: '12m+', portfolio: '债券 50% · 高息股 30% · 现金 20%' },
      behavior:     { post_freq: 0.8, reply_rate: 0.32, peak_hour: '09:30' },
      social:       { followers: 280, influence: 0.22, follows: [] },
      signals:      { stance: 'bear', momentum: '弱', last_active: '2026-05-04T07:15:00Z' }
    }
  },
  {
    id: 'p_355', name: 'Daniel Wu', avatar_seed: 'p_355',
    cluster_id: 'cl_defensive',
    profession: '风控顾问', tags: ['defensive', 'risk-aware'],
    dimensions: {
      demographics: { age: 42, gender: 'male', city: '香港' },
      psychology:   { mbti: 'ISTJ', risk: '低', big5: 'O/C+/E-/A/N+' },
      investment:   { style: '风险平价', horizon: '12m+', portfolio: '美债 40% · 黄金 20% · 防御股 40%' },
      behavior:     { post_freq: 1.1, reply_rate: 0.38, peak_hour: '08:00' },
      social:       { followers: 410, influence: 0.28, follows: [] },
      signals:      { stance: 'bear', momentum: '中', last_active: '2026-05-04T08:50:00Z' }
    }
  },
  {
    id: 'p_402', name: '陈维民', avatar_seed: 'p_402',
    cluster_id: 'cl_yield',
    profession: '退休工程师', tags: ['yield', 'low-risk'],
    dimensions: {
      demographics: { age: 61, gender: 'male', city: '台北' },
      psychology:   { mbti: 'ISFJ', risk: '低', big5: 'O-/C+/E-/A+/N' },
      investment:   { style: '高股息', horizon: '12m+', portfolio: '高息股 70% · 债券 30%' },
      behavior:     { post_freq: 0.4, reply_rate: 0.61, peak_hour: '07:30' },
      social:       { followers: 90, influence: 0.11, follows: [] },
      signals:      { stance: 'neutral', momentum: '低', last_active: '2026-05-04T06:40:00Z' }
    }
  },
  {
    id: 'p_511', name: 'Echo Han', avatar_seed: 'p_511',
    cluster_id: 'cl_contrarian',
    profession: '独立分析师', tags: ['contrarian'],
    dimensions: {
      demographics: { age: 36, gender: 'female', city: '杭州' },
      psychology:   { mbti: 'INTP', risk: '中', big5: 'O+/C/E-/A-/N-' },
      investment:   { style: '逆向', horizon: '3-9m', portfolio: '空科技 + 多周期' },
      behavior:     { post_freq: 2.1, reply_rate: 0.27, peak_hour: '22:00' },
      social:       { followers: 760, influence: 0.45, follows: [] },
      signals:      { stance: 'contrarian', momentum: '中', last_active: '2026-05-04T10:55:00Z' }
    }
  }
]

export async function fetchPersonasSection (reportId) {
  await wait(120)
  return { clusters: CLUSTERS, personas: PERSONAS }
}

export async function fetchPersonaById (id) {
  await wait(40)
  return PERSONAS.find(p => p.id === id) || null
}

// ────────────────────────── HIGHLIGHTS ──────────────────────────
const HIGHLIGHTS = {
  p_204: [
    { id: 'h1', text: '美联储 6 月若降息，科技股会先于消费股反弹。', stance: 'bull',
      evidence_post_ids: ['post_a', 'post_b'], ts_range: ['2026-04-20', '2026-04-22'] },
    { id: 'h2', text: 'AI 资本开支不会因为短期回吐而减速。', stance: 'bull',
      evidence_post_ids: ['post_c'], ts_range: ['2026-04-23', '2026-04-23'] },
    { id: 'h3', text: '现在的回调是结构性机会，而不是趋势反转。', stance: 'bull',
      evidence_post_ids: ['post_d'], ts_range: ['2026-04-24', '2026-04-25'] }
  ],
  p_148: [
    { id: 'h1', text: '半导体补库周期在 6 月会进一步加速。', stance: 'bull',
      evidence_post_ids: [], ts_range: ['2026-04-21', '2026-04-23'] },
    { id: 'h2', text: '叙事驱动行情通常领先基本面 2 个季度。', stance: 'bull',
      evidence_post_ids: [], ts_range: ['2026-04-22', '2026-04-22'] }
  ],
  p_312: [
    { id: 'h1', text: '在利率不确定阶段，债券哑铃组合仍是最稳的。', stance: 'bear',
      evidence_post_ids: [], ts_range: ['2026-04-20', '2026-04-22'] },
    { id: 'h2', text: '高股息板块在情绪低点表现明显占优。', stance: 'neutral',
      evidence_post_ids: [], ts_range: ['2026-04-22', '2026-04-23'] }
  ],
  p_511: [
    { id: 'h1', text: '主流共识低估了二季度财报的下修幅度。', stance: 'contrarian',
      evidence_post_ids: [], ts_range: ['2026-04-21', '2026-04-22'] }
  ],
  // 默认
  __default__: [
    { id: 'h1', text: '当前事件还处在第一波情绪扩散阶段。', stance: 'neutral',
      evidence_post_ids: [], ts_range: ['2026-04-20', '2026-04-22'] }
  ]
}

export async function fetchHighlights (personaId) {
  await wait(80)
  return { scope: 'persona', id: personaId, highlights: HIGHLIGHTS[personaId] || HIGHLIGHTS.__default__ }
}

// ────────────────────────── PREDICTIONS (Section 3) ──────────────────────────
function band (n, base = 100, amp = 30) {
  const out = { x: [], mean: [], low: [], high: [] }
  for (let i = 0; i < n; i++) {
    const m = base + Math.sin(i / 3) * amp + (Math.random() - 0.5) * 8
    out.x.push(`+${i}h`)
    out.mean.push(+m.toFixed(1))
    out.low.push(+(m - 18).toFixed(1))
    out.high.push(+(m + 18).toFixed(1))
  }
  return out
}

const THEMES = [
  {
    id: 'theme_capital_flow', title: '资金面', confidence: 0.78,
    charts: [
      { id: 'ch_netflow', kind: 'line_with_band',
        title: '未来 72h 主力净流入预测（亿元）',
        data: band(24, 14, 8) },
      { id: 'ch_rotation', kind: 'bar',
        title: '板块轮动力度（标准化）',
        data: { x: ['科技', '半导体', '消费', '金融', '周期', '医药'], y: [0.82, 0.74, 0.31, 0.18, 0.42, 0.27] } }
    ],
    insight: '未来 72h 主力资金大概率回流科技板块；板块轮动力度显示半导体与科技领先优势明显。',
    actions: [
      { kind: 'allocate', text: '配置：科技 30% / 周期 20% / 防御 50%' },
      { kind: 'risk',     text: '警惕利率会议前一日的高波动回吐' }
    ],
    evidence_ids: ['ev_001', 'ev_004', 'ev_017']
  },
  {
    id: 'theme_sentiment', title: '情绪面', confidence: 0.66,
    charts: [
      { id: 'ch_sent', kind: 'line_with_band',
        title: '未来 48h 情绪指数走势',
        data: band(24, 0.1, 0.35) }
    ],
    insight: '群体情绪从悲观区间向中性回归，但波动率仍高，留意 KOL 反向喊话引发的二次回调。',
    actions: [
      { kind: 'tactic', text: '在情绪指数 ≤ -0.3 时分批进场' },
      { kind: 'risk',   text: 'KOL_07 一旦反向，需在 6h 内做仓位调整' }
    ],
    evidence_ids: ['ev_021']
  },
  {
    id: 'theme_rotation', title: '行业轮动', confidence: 0.71,
    charts: [
      { id: 'ch_rot2', kind: 'bar',
        title: '主题热度变化',
        data: { x: ['AI 应用', '半导体', '新能源', '消费', '银行'], y: [0.91, 0.76, 0.34, 0.22, 0.18] } }
    ],
    insight: 'AI 应用 / 半导体维持领先，新能源出现温和反弹但持续性不足。',
    actions: [
      { kind: 'allocate', text: '在 AI 应用层做 alpha，避免硬件层估值过热' }
    ],
    evidence_ids: ['ev_009', 'ev_012']
  },
  {
    id: 'theme_event_shock', title: '事件冲击', confidence: 0.62,
    charts: [
      { id: 'ch_shock', kind: 'line_with_band',
        title: '议息会议前后波动率预测',
        data: band(24, 22, 10) }
    ],
    insight: '议息会议前一日预计出现波动率显著抬升，会后情绪有反弹空间。',
    actions: [
      { kind: 'risk',   text: '会议日前后控制单日仓位变动 ≤ 8%' },
      { kind: 'tactic', text: '在会后 4h 观察资金回流确认信号' }
    ],
    evidence_ids: ['ev_031']
  },
  {
    id: 'theme_tail_risk', title: '长尾风险', confidence: 0.48,
    charts: [
      { id: 'ch_tail', kind: 'bar',
        title: '尾部风险打分（按主题）',
        data: { x: ['流动性', '地缘', '监管', '汇率', '信用'], y: [0.42, 0.71, 0.55, 0.38, 0.29] } }
    ],
    insight: '地缘与监管是当前尾部风险的主要驱动；如果两者叠加，模型预测下行幅度将放大 1.6x。',
    actions: [
      { kind: 'risk', text: '保持 ≥ 15% 的现金敞口以应对尾部冲击' }
    ],
    evidence_ids: ['ev_044']
  }
]

export async function fetchPredictions (reportId) {
  await wait(160)
  return { themes: THEMES }
}

// ────────────────────────── POSTS ──────────────────────────
const ANGLE_CATALOG = {
  educator:    { label: '科普向',  tone: 'brand',   personaId: 'p_077' },
  data_driven: { label: '数据向',  tone: 'brand',   personaId: 'p_077' },
  bull:        { label: '多头视角', tone: 'bull',   personaId: 'p_148' },
  bear:        { label: '空头视角', tone: 'bear',   personaId: 'p_312' },
  contrarian:  { label: '逆向视角', tone: 'warn',   personaId: 'p_511' },
  anecdotal:   { label: '故事向',   tone: 'neutral',personaId: 'p_204' }
}

function pickAngles (n) {
  const keys = Object.keys(ANGLE_CATALOG)
  // 简单互斥抽样
  const picked = []
  while (picked.length < n && keys.length) {
    const i = Math.floor(Math.random() * keys.length)
    picked.push(keys.splice(i, 1)[0])
  }
  return picked
}

const SAMPLE_POSTS = {
  // 不同 angle 的差异化模板（避免雷同）
  educator: {
    title: '为什么主力资金会在 72h 内回流科技？',
    body:  '当流动性边际改善、估值回到 5 年均值附近时，机构通常会优先回补具备盈利可见度的赛道。本轮事件中…',
    twitter: '主力资金的 72h 回流，本质上是流动性预期 + 估值锚点共振。看图说话： 1) … 2) … 3) …'
  },
  data_driven: {
    title: '数据视角：净流入背离信号怎么解读',
    body:  '把 ETF 净流入按 6h 切片，会看到 T+18h 出现显著的"价格下跌但资金净流入"背离。历史上类似形态的 7 天后…',
    twitter: '把净流入切到 6h 粒度，T+18 出现"价跌量增"背离。统计样本 N=42，7 天后正收益概率 71%。'
  },
  bull: {
    title: '科技股估值修复的三个支撑',
    body:  '盈利上修 + 流动性边际改善 + 叙事强化 —— 三者叠加的窗口期一年只有几次，错过就要等下一轮…',
    twitter: '科技这波回流，多头逻辑只有一句话：估值已经压到 5 年 -1σ，催化剂在 6 月。'
  },
  bear: {
    title: '估值修复，但趋势没反转',
    body:  '请区分"反弹"与"反转"。从盈利预期、信用利差和波动率三方面看，目前的反弹缺乏可持续性…',
    twitter: '别把反弹当反转。盈利下修没结束、利差没收敛、VIX 还在高位 —— 三件事不解决，趋势就在。'
  },
  contrarian: {
    title: '主流共识低估了 Q2 财报的下修幅度',
    body:  '当卖方一致看多，往往就是预期最饱满的时候。把市场情绪指数和分析师 EPS 修正放在一起看，会看到…',
    twitter: '当卖方一致看多 → 看空机会。EPS 修正还在下行，但价格已经先行反弹 8%。这是典型的预期透支。'
  },
  anecdotal: {
    title: '一位散户经理人的 24 小时',
    body:  '凌晨两点，他第三次刷新 ETF 数据。距离议息还有 16 小时，他知道每一小时都在重新定价…',
    twitter: '凌晨两点，他刷第 17 次 ETF 净流入。议息倒计时 16h，每一小时都在重新定价。'
  }
}

export async function fetchPostsForTheme (reportId, themeId, n = 3) {
  await wait(220)
  const angles = pickAngles(Math.min(n, 6))
  return {
    posts: angles.map((angle, i) => {
      const tpl = SAMPLE_POSTS[angle]
      return {
        id: `post_${themeId}_${angle}_${i}`,
        angle,
        angle_label: ANGLE_CATALOG[angle].label,
        angle_tone:  ANGLE_CATALOG[angle].tone,
        persona_id:  ANGLE_CATALOG[angle].personaId,
        title: tpl.title,
        body:  tpl.body,
        evidence_ids: ['ev_demo'],
        platform_variants: { twitter: tpl.twitter, reddit: tpl.body }
      }
    })
  }
}

// ────────────────────────── CHAT (mock SSE) ──────────────────────────
export async function* mockChatStream (personaId, message) {
  const persona = await fetchPersonaById(personaId)
  const reply = persona
    ? `（${persona.name}）我会从${persona.dimensions.investment.style}的视角看这个问题：${message.slice(0, 30)}…\n首先，主力资金的方向比情绪更重要；其次，本轮波动还在我配置区间之内。`
    : `已收到你的问题：${message}`
  // 按字符流式吐出
  for (const ch of reply) {
    await wait(18)
    yield ch
  }
}
