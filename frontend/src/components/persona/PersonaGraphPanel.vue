<template>
  <div class="persona-panel">
    <!-- 顶部模式切换 + 统计（紧贴 GraphPanel header 之下，浅色风格） -->
    <div class="persona-toolbar">
      <div class="mode-tabs">
        <button
          v-for="m in modes"
          :key="m.key"
          class="mode-tab"
          :class="{ active: mode === m.key }"
          @click="mode = m.key"
          :title="m.tip"
        >
          <span class="mode-icon">{{ m.icon }}</span>
          <span class="mode-label">{{ m.label }}</span>
        </button>
      </div>

      <div class="stats">
        <span class="stat-pill" v-if="cards.length">
          <span class="stat-num">{{ cards.length }}</span>
          <span class="stat-label">投资者</span>
        </span>
        <span class="stat-pill" v-if="archetypes.length">
          <span class="stat-num">{{ archetypes.length }}</span>
          <span class="stat-label">投资原型</span>
        </span>
        <span class="stat-pill" v-if="segments.length">
          <span class="stat-num">{{ segments.length }}</span>
          <span class="stat-label">CSOP 客群</span>
        </span>
      </div>
    </div>

    <!-- 主体 -->
    <div class="persona-stage" ref="stageRef">
      <div v-if="loading && !cards.length" class="state-msg">加载投资者画像中...</div>
      <div v-else-if="error" class="state-msg error">{{ error }}</div>
      <div v-else-if="!cards.length" class="state-msg">
        <div class="empty-icon">◌</div>
        <div>该模拟暂无投资者画像数据</div>
        <div class="empty-hint">请先完成模拟准备阶段（生成 profile_index.json）</div>
      </div>

      <!-- ★ 模式 1: 人群原型星云 -->
      <svg
        v-show="cards.length && mode === 'archetype'"
        ref="archetypeSvg"
        class="viz-svg"
      ></svg>

      <!-- 人群原型图例 -->
      <div v-show="cards.length && mode === 'archetype'" class="arche-legend">
        <div
          v-for="a in archetypes"
          :key="a.key"
          class="arche-item"
          @mouseenter="hoverArchetype = a.key"
          @mouseleave="hoverArchetype = null"
        >
          <span class="arche-dot" :style="{ background: a.color }"></span>
          <span class="arche-name">{{ a.label }}</span>
          <span class="arche-count">{{ a.members.length }}</span>
        </div>
      </div>

      <!-- ★ 模式 2: 客群流向 Sankey + 鱼骨 -->
      <svg
        v-show="cards.length && mode === 'flow'"
        ref="flowSvg"
        class="viz-svg"
      ></svg>

      <!-- 鱼骨产品弹层 -->
      <div
        v-if="mode === 'flow' && fishboneSegment"
        class="fishbone-pop"
        :style="{ left: fishbonePos.x + 'px', top: fishbonePos.y + 'px' }"
      >
        <div class="fishbone-head">
          <span class="fb-icon">🐟</span>
          <span class="fb-title">{{ fishboneSegment.name }} · 推荐产品</span>
          <button class="fb-close" @click="closeFishbone">×</button>
        </div>
        <div class="fishbone-body">
          <div class="fb-desc">{{ fishboneSegment.description }}</div>
          <ul class="fb-products">
            <li
              v-for="(p, idx) in fishboneSegment.recommended_products"
              :key="idx"
              class="fb-product"
              :style="{ animationDelay: (idx * 80) + 'ms' }"
            >
              <span class="fb-bone"></span>
              <span class="fb-pname">{{ p }}</span>
            </li>
          </ul>
          <div class="fb-talking" v-if="fishboneSegment.talking_points && fishboneSegment.talking_points.length">
            <div class="fb-tt-title">销售话术要点</div>
            <div v-for="(tp, idx) in fishboneSegment.talking_points" :key="idx" class="fb-tt-item">· {{ tp }}</div>
          </div>
        </div>
      </div>

      <!-- ★ 模式 3: 便签墙 -->
      <div
        v-if="cards.length && mode === 'sticky'"
        class="sticky-wall"
      >
        <div
          v-for="card in cards"
          :key="card.persona_uuid || card.user_id"
          class="mini-card"
          :style="cardStyle(card)"
          @click="selected = card"
        >
          <div class="mini-arche-bar" :style="{ background: archetypeOf(card).color }"></div>
          <div class="mini-head">
            <div class="mini-name">{{ card.name || `Agent ${card.user_id}` }}</div>
            <div class="mini-sub">{{ [card.profession, card.country].filter(Boolean).join(' · ') }}</div>
          </div>
          <div class="mini-tags">
            <span class="arche-pill" :style="{ background: archetypeOf(card).color }" :title="archetypeOf(card).label">
              {{ archetypeOf(card).label }}
            </span>
          </div>
          <div class="mini-meta">
            <span v-if="card.risk_appetite" class="meta-row">
              <span class="meta-key">风险</span>
              <span class="meta-val" :title="card.risk_appetite">{{ card.risk_appetite }}</span>
            </span>
            <span v-if="card.portfolio_type" class="meta-row">
              <span class="meta-key">持仓</span>
              <span class="meta-val" :title="card.portfolio_type">{{ card.portfolio_type }}</span>
            </span>
          </div>
        </div>
      </div>
    </div>

    <!-- 详情弹窗 -->
    <div v-if="selected" class="detail-pop" @click.self="selected = null">
      <div class="detail-card">
        <div class="detail-head">
          <span class="detail-title">{{ selected.name || `Agent ${selected.user_id}` }}</span>
          <span class="detail-arche" :style="{ background: archetypeOf(selected).color }">
            {{ archetypeOf(selected).label }}
          </span>
          <button class="close" @click="selected = null">×</button>
        </div>
        <div class="detail-body">
          <div class="row" v-if="selected.user_name"><b>账号:</b> {{ selected.user_name }}</div>
          <div class="row" v-if="selected.profession"><b>职业:</b> {{ selected.profession }}</div>
          <div class="row"><b>国家·年龄·性别:</b> {{ [selected.country, selected.age, selected.gender].filter(v=>v!=null).join(' · ') }}</div>
          <div class="row" v-if="selected.mbti"><b>MBTI:</b> {{ selected.mbti }}</div>
          <div class="row"><b>风险偏好:</b> {{ selected.risk_appetite || '-' }} · {{ selected.portfolio_type || '-' }}</div>
          <div class="row" v-if="selected.confidence != null"><b>置信度:</b> {{ (selected.confidence * 100).toFixed(0) }}%</div>
          <div class="row" v-if="(selected.interested_topics || []).length"><b>关注话题:</b> {{ selected.interested_topics.join('、') }}</div>
          <div class="row" v-if="selected.bio"><b>简介:</b> {{ selected.bio }}</div>
          <div class="row tiny" v-if="selected.persona_uuid"><b>persona_uuid:</b> <code>{{ selected.persona_uuid }}</code></div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch, nextTick, onUnmounted } from 'vue'
import * as d3 from 'd3'
import { listPersonas, getPersonaSegments } from '../../api/persona'

const props = defineProps({
  simulationId: { type: String, required: true },
})

const modes = [
  { key: 'archetype', label: '投资原型', icon: '✦', tip: '按性格 / 持仓 / 偏好分类的 8 种投资者原型' },
  { key: 'flow',      label: '客群流向花园', icon: '✿', tip: '径向流向花园：同时呈现原型分布、流向、客群与推荐产品' },
  { key: 'sticky',    label: '便签墙',   icon: '▤', tip: '紧凑卡片视图，颜色与关系图谱实体类型一致' },
]
const mode = ref('archetype')

const cards = ref([])
const segments = ref([])
const loading = ref(false)
const error = ref('')
const selected = ref(null)
const stageRef = ref(null)
const archetypeSvg = ref(null)
const flowSvg = ref(null)
const hoverArchetype = ref(null)

// 鱼骨弹层
const fishboneSegment = ref(null)
const fishbonePos = ref({ x: 0, y: 0 })

// =====================================================
// 调色板：与 GraphPanel.vue 中 entityTypes 调色板一致
// =====================================================
const ENTITY_PALETTE = ['#FF6B35', '#004E89', '#7B2D8E', '#1A936F', '#C5283D', '#E9724C', '#3498db', '#9b59b6', '#27ae60', '#f39c12']

// =====================================================
// 8 种投资者原型（按 keywords 探测，避免"中等"扎堆）
// =====================================================
const ARCHETYPES = [
  { key: 'growth',      label: '激进成长型', color: ENTITY_PALETTE[0] },
  { key: 'global',      label: '全球配置型', color: ENTITY_PALETTE[1] },
  { key: 'rational',    label: '理性配置型', color: ENTITY_PALETTE[2] },
  { key: 'income',      label: '价值收息型', color: ENTITY_PALETTE[3] },
  { key: 'defensive',   label: '保守避险型', color: ENTITY_PALETTE[4] },
  { key: 'short_trade', label: '短线交易型', color: ENTITY_PALETTE[5] },
  { key: 'contrarian',  label: '逆向投机型', color: ENTITY_PALETTE[6] },
  { key: 'thematic',    label: '主题猎手型', color: ENTITY_PALETTE[7] },
]
const ARCHETYPE_BY_KEY = Object.fromEntries(ARCHETYPES.map(a => [a.key, a]))

const KEYWORDS = {
  growth:      [/AI|人工智能|科技|tech|growth|成长|半导体|芯片|互联网|新能源|电动车|英伟达|特斯拉/i],
  global:      [/全球|global|跨市场|多市场|海外|新兴市场|配置|分散|asset.?allocation/i],
  rational:    [/价值|value|理性|宽基|蓝筹|大盘|稳健|平衡/i],
  income:      [/股息|分红|高息|收息|REIT|reits|债券|bond|债基|高股息|月月派|fixed.?income/i],
  defensive:   [/避险|conservative|保守|货币|货基|短债|防守|低波|稳定|safe.?haven|黄金|gold/i],
  short_trade: [/短线|波段|swing|day.?trade|杠杆|反向|leveraged|inverse|L&I|热点|趋势/i],
  contrarian:  [/逆向|低估|undervalued|contrarian|抄底|左侧|reversal|反转/i],
  thematic:    [/主题|sector|行业|医药|生物|biotech|5G|光伏|碳中和|加密|crypto|比特币|沙特|越南|日本/i],
}

function detectArchetype(card) {
  const blob = [
    card.bio,
    card.profession,
    card.portfolio_type,
    card.risk_appetite,
    ...(card.interested_topics || []),
  ].filter(Boolean).join(' ').toLowerCase()

  const r = (card.risk_appetite || '').toLowerCase()
  const isHigh = /high|aggressive|激进|高/.test(r)
  const isLow = /low|conservative|保守|低/.test(r)

  const scores = {}
  for (const [k, regs] of Object.entries(KEYWORDS)) {
    let s = 0
    for (const re of regs) if (re.test(blob)) s += 1
    if (s > 0) scores[k] = s
  }
  if (isHigh) {
    scores.growth = (scores.growth || 0) + 0.5
    scores.short_trade = (scores.short_trade || 0) + 0.3
  }
  if (isLow) {
    scores.defensive = (scores.defensive || 0) + 0.8
    scores.income = (scores.income || 0) + 0.3
  }

  const ranked = Object.entries(scores).sort((a, b) => b[1] - a[1])
  if (ranked.length) return ARCHETYPE_BY_KEY[ranked[0][0]]

  // 兜底：哈希到 8 种之一（保证分布丰富）
  const idx = hash((card.user_name || '') + (card.profession || '') + String(card.user_id || '')) % ARCHETYPES.length
  return ARCHETYPES[idx]
}

function archetypeOf(card) {
  if (!card._archetype) card._archetype = detectArchetype(card)
  return card._archetype
}

const archetypes = computed(() => {
  const m = new Map()
  cards.value.forEach(c => {
    const a = archetypeOf(c)
    if (!m.has(a.key)) m.set(a.key, { ...a, members: [] })
    m.get(a.key).members.push(c)
  })
  return Array.from(m.values()).sort((a, b) => b.members.length - a.members.length)
})

function hash(s) {
  let h = 0
  for (let i = 0; i < (s || '').length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0
  return h
}

// 便签墙：与原型同色（淡化）
function cardStyle(card) {
  const a = archetypeOf(card)
  return {
    background: hexToSoft(a.color, 0.16),
    borderTop: `3px solid ${a.color}`,
  }
}
function hexToSoft(hex, alpha) {
  const m = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex)
  if (!m) return hex
  const r = parseInt(m[1], 16), g = parseInt(m[2], 16), b = parseInt(m[3], 16)
  return `rgba(${r},${g},${b},${alpha})`
}

// =====================================================
// 数据加载
// =====================================================
async function loadAll() {
  if (!props.simulationId) return
  loading.value = true
  error.value = ''
  try {
    const [pResp, sResp] = await Promise.all([
      listPersonas(props.simulationId).catch(() => ({ cards: [], graph_enabled: false })),
      getPersonaSegments(props.simulationId).catch(() => ({ segments: [], mappings: [] })),
    ])
    cards.value = (pResp.cards || []).map(c => ({ ...c }))
    segments.value = sResp.segments || []
  } catch (e) {
    error.value = e?.message || '加载画像失败'
  } finally {
    loading.value = false
    await nextTick()
    renderCurrent()
  }
}

function renderCurrent() {
  if (!cards.value.length) return
  if (mode.value === 'archetype') renderArchetypeGalaxy()
  else if (mode.value === 'flow') renderFlowSankey()
}

watch(mode, async () => {
  closeFishbone()
  await nextTick()
  renderCurrent()
})
watch(() => props.simulationId, () => loadAll())
watch(hoverArchetype, () => {
  if (mode.value === 'archetype') highlightArchetype()
})

let resizeObs = null
let flowAnimTimer = null
onMounted(() => {
  loadAll()
  if (stageRef.value && 'ResizeObserver' in window) {
    resizeObs = new ResizeObserver(() => {
      closeFishbone()
      renderCurrent()
    })
    resizeObs.observe(stageRef.value)
  }
})
onUnmounted(() => {
  if (resizeObs) resizeObs.disconnect()
  if (currentSim) currentSim.stop()
  if (flowAnimTimer) clearInterval(flowAnimTimer)
})

// =========================================================
// ★ 模式 1: 人群原型星云
// =========================================================
let currentSim = null
let archeNodeSel = null

function renderArchetypeGalaxy() {
  const el = archetypeSvg.value
  if (!el || !stageRef.value) return
  const W = stageRef.value.clientWidth || 800
  const H = stageRef.value.clientHeight || 500

  const svg = d3.select(el).attr('width', W).attr('height', H).attr('viewBox', `0 0 ${W} ${H}`)
  svg.selectAll('*').remove()

  // 浅色网格背景
  const bg = svg.append('g').attr('class', 'bg-grid')
  for (let x = 0; x < W; x += 40) {
    bg.append('line').attr('x1', x).attr('y1', 0).attr('x2', x).attr('y2', H)
      .attr('stroke', '#eef0f5').attr('stroke-width', 1)
  }
  for (let y = 0; y < H; y += 40) {
    bg.append('line').attr('x1', 0).attr('y1', y).attr('x2', W).attr('y2', y)
      .attr('stroke', '#eef0f5').attr('stroke-width', 1)
  }

  const cs = archetypes.value
  if (!cs.length) return

  const clusterCenters = {}
  cs.forEach((c, i) => {
    const angle = (i / cs.length) * Math.PI * 2 - Math.PI / 2
    const radius = Math.min(W, H) * 0.32
    clusterCenters[c.key] = {
      x: W / 2 + Math.cos(angle) * radius,
      y: H / 2 + Math.sin(angle) * radius,
    }
  })

  // 群心光晕
  const haloG = svg.append('g')
  cs.forEach(c => {
    const cc = clusterCenters[c.key]
    const r = 30 + Math.sqrt(c.members.length) * 12
    haloG.append('circle')
      .attr('cx', cc.x).attr('cy', cc.y).attr('r', r)
      .attr('fill', c.color).attr('opacity', 0.06)
    haloG.append('circle')
      .attr('cx', cc.x).attr('cy', cc.y).attr('r', r * 0.6)
      .attr('fill', c.color).attr('opacity', 0.1)
    haloG.append('text')
      .attr('x', cc.x).attr('y', cc.y - r - 8)
      .attr('text-anchor', 'middle').attr('fill', c.color)
      .attr('font-size', 12).attr('font-weight', 700)
      .text(`${c.label} (${c.members.length})`)
  })

  const nodes = cards.value.map(c => {
    const a = archetypeOf(c)
    return {
      ...c,
      _archeKey: a.key,
      _archeColor: a.color,
      cx: clusterCenters[a.key]?.x || W / 2,
      cy: clusterCenters[a.key]?.y || H / 2,
    }
  })

  if (currentSim) currentSim.stop()
  const sim = d3.forceSimulation(nodes)
    .force('x', d3.forceX(d => d.cx).strength(0.2))
    .force('y', d3.forceY(d => d.cy).strength(0.2))
    .force('charge', d3.forceManyBody().strength(-10))
    .force('collide', d3.forceCollide(d => bubbleR(d) + 1.5))
    .alpha(0.95)
  currentSim = sim

  // tooltip 元素（懒创建）
  let tip = d3.select(stageRef.value).select('.persona-tip')
  if (tip.empty()) {
    tip = d3.select(stageRef.value).append('div').attr('class', 'persona-tip')
  }

  const g = svg.append('g')
  archeNodeSel = g.selectAll('g.bubble').data(nodes).enter().append('g').attr('class', 'bubble')
    .style('cursor', 'pointer')
    .on('click', (e, d) => { selected.value = d })
    .on('mouseenter', (e, d) => {
      tip.style('opacity', 1)
        .html(
          `<b>${d.name || 'Agent ' + d.user_id}</b><br/>` +
          `<span style="color:${d._archeColor}">● ${ARCHETYPE_BY_KEY[d._archeKey]?.label || ''}</span><br/>` +
          `${d.profession || ''}${d.country ? ' · ' + d.country : ''}`
        )
    })
    .on('mousemove', (e) => {
      tip.style('left', (e.offsetX + 12) + 'px').style('top', (e.offsetY + 12) + 'px')
    })
    .on('mouseleave', () => tip.style('opacity', 0))

  archeNodeSel.append('circle')
    .attr('r', d => bubbleR(d))
    .attr('fill', d => d._archeColor)
    .attr('opacity', 0.85)
    .attr('stroke', '#fff').attr('stroke-width', 1.5)

  archeNodeSel.append('text')
    .attr('text-anchor', 'middle').attr('dy', 3)
    .attr('font-size', 9).attr('fill', '#fff').attr('font-weight', 700)
    .text(d => initials(d))

  sim.on('tick', () => {
    archeNodeSel.attr('transform', d => `translate(${d.x},${d.y})`)
  })
}

function highlightArchetype() {
  if (!archeNodeSel) return
  const k = hoverArchetype.value
  archeNodeSel.transition().duration(200)
    .attr('opacity', d => k && d._archeKey !== k ? 0.15 : 1)
}

function bubbleR(d) {
  const c = (d.confidence == null) ? 0.5 : d.confidence
  return 8 + c * 12
}
function initials(d) {
  const s = d.name || d.user_name || ('A' + (d.user_id ?? ''))
  return s.slice(0, 2).toUpperCase()
}

// =========================================================
// ★ 模式 2: 客群流向花园（径向 Chord + 产品花瓣，创新型）
//   - 上半圈：投资者原型弧（弧长 = 该原型人数）
//   - 下半圈：CSOP 客群弧（弧长 = 客群规模）
//   - 中间：渐变流向条带（宽度 = 流量），带流光动画
//   - 外圈：每个客群的推荐产品作为「花瓣」常驻显示
//   - 中心：总投资者数；点击客群 → 弹出销售话术与详细产品列表
// =========================================================
function renderFlowSankey() {
  const el = flowSvg.value
  if (!el || !stageRef.value) return
  const W = stageRef.value.clientWidth || 800
  const H = stageRef.value.clientHeight || 600
  const cx = W / 2, cy = H / 2
  const innerR = Math.min(W, H) * 0.13
  const archeR = Math.min(W, H) * 0.22
  const segR   = Math.min(W, H) * 0.31
  const petalR = Math.min(W, H) * 0.40

  const svg = d3.select(el).attr('width', W).attr('height', H).attr('viewBox', `0 0 ${W} ${H}`)
  svg.selectAll('*').remove()

  if (!segments.value.length || !archetypes.value.length) {
    svg.append('text').attr('x', cx).attr('y', cy)
      .attr('text-anchor', 'middle').attr('fill', '#999').attr('font-size', 13)
      .text('暂无 CSOP 客群数据')
    return
  }

  // tooltip
  let tip = d3.select(stageRef.value).select('.persona-tip')
  if (tip.empty()) {
    tip = d3.select(stageRef.value).append('div').attr('class', 'persona-tip')
  }

  // ---- 流量统计 ----
  const flowMap = {}
  cards.value.forEach(c => {
    const a = archetypeOf(c)
    const seg = matchSegment(c)
    if (!seg) return
    const k = a.key + '|' + seg.segment_id
    if (!flowMap[k]) flowMap[k] = { a: a.key, s: seg.segment_id, color: a.color, v: 0 }
    flowMap[k].v += 1
  })

  // ---- 原型弧（上半圈：math angle [-PI+0.15, -0.15]）----
  const archeData = archetypes.value.filter(a => a.members.length > 0)
  const totalA = archeData.reduce((s, a) => s + a.members.length, 0) || 1
  const aStart = -Math.PI + 0.15, aEnd = -0.15
  let cur = aStart
  archeData.forEach(a => {
    const span = (a.members.length / totalA) * (aEnd - aStart)
    a._a0 = cur
    a._a1 = cur + span - 0.025
    a._mid = (a._a0 + a._a1) / 2
    cur += span
  })

  // ---- 客群弧（下半圈：[0.15, PI-0.15]）----
  const segCount = {}
  Object.values(flowMap).forEach(f => { segCount[f.s] = (segCount[f.s] || 0) + f.v })
  const segData = segments.value
    .filter(s => segCount[s.segment_id])
    .map(s => ({ ...s, _v: segCount[s.segment_id] }))
  const totalS = segData.reduce((sum, s) => sum + s._v, 0) || 1
  const sStart = 0.15, sEnd = Math.PI - 0.15
  let curS = sStart
  segData.forEach(s => {
    const span = (s._v / totalS) * (sEnd - sStart)
    s._a0 = curS
    s._a1 = curS + span - 0.025
    s._mid = (s._a0 + s._a1) / 2
    curS += span
  })

  // ---- 流向带 ----
  const aOff = {}, sOff = {}
  archeData.forEach(a => { aOff[a.key] = a._a0 })
  segData.forEach(s => { sOff[s.segment_id] = s._a0 })
  const flowList = Object.values(flowMap)
    .filter(f => archeData.find(a => a.key === f.a) && segData.find(s => s.segment_id === f.s))
    .sort((x, y) => y.v - x.v)
  flowList.forEach(f => {
    const aN = archeData.find(a => a.key === f.a)
    const sN = segData.find(s => s.segment_id === f.s)
    const aSpan = (f.v / aN.members.length) * (aN._a1 - aN._a0)
    const sSpan = (f.v / sN._v) * (sN._a1 - sN._a0)
    f._aFrom = aOff[f.a]; aOff[f.a] += aSpan; f._aTo = aOff[f.a]
    f._sFrom = sOff[f.s]; sOff[f.s] += sSpan; f._sTo = sOff[f.s]
    f._color = aN.color
    f._segName = sN.name
  })

  // 极坐标转换（math angle）
  const polar = (r, a) => ({ x: Math.cos(a) * r, y: Math.sin(a) * r })

  // 渐变 defs
  const defs = svg.append('defs')
  flowList.forEach((f, i) => {
    const gid = `garden-grad-${i}`
    const aMid = (f._aFrom + f._aTo) / 2
    const sMid = (f._sFrom + f._sTo) / 2
    const p1 = polar(archeR, aMid), p2 = polar(archeR + 8, sMid)
    const grad = defs.append('linearGradient').attr('id', gid)
      .attr('gradientUnits', 'userSpaceOnUse')
      .attr('x1', cx + p1.x).attr('y1', cy + p1.y)
      .attr('x2', cx + p2.x).attr('y2', cy + p2.y)
    grad.append('stop').attr('offset', '0%').attr('stop-color', f._color).attr('stop-opacity', 0.85)
    grad.append('stop').attr('offset', '100%').attr('stop-color', '#5b56e8').attr('stop-opacity', 0.85)
    f._grad = `url(#${gid})`
  })

  // d3 弧生成器（math → d3 角度: + PI/2）
  const archeArc = d3.arc().innerRadius(innerR + 6).outerRadius(archeR).cornerRadius(3)
  const segArc = d3.arc().innerRadius(archeR + 8).outerRadius(segR).cornerRadius(3)

  // 中心标签
  const center = svg.append('g').attr('transform', `translate(${cx},${cy})`)
  center.append('circle').attr('r', innerR).attr('fill', '#fff').attr('stroke', '#e5e7ee')
  center.append('text').attr('text-anchor', 'middle').attr('y', -8)
    .attr('font-size', 10).attr('fill', '#888').attr('font-weight', 600)
    .text('投资者总数')
  center.append('text').attr('text-anchor', 'middle').attr('y', 14)
    .attr('font-size', 22).attr('fill', '#2c3041').attr('font-weight', 700)
    .text(cards.value.length)
  center.append('text').attr('text-anchor', 'middle').attr('y', 28)
    .attr('font-size', 9).attr('fill', '#aaa')
    .text(`${archeData.length} 原型 · ${segData.length} 客群`)

  // 流向条带（chord 形）
  const flowG = svg.append('g').attr('class', 'flow-ribbons').attr('transform', `translate(${cx},${cy})`)
  function ribbonPath(f) {
    const r1 = archeR, r2 = archeR + 8
    const p1 = polar(r1, f._aFrom)
    const p2 = polar(r1, f._aTo)
    const p3 = polar(r2, f._sTo)
    const p4 = polar(r2, f._sFrom)
    return `M${p1.x},${p1.y}
            A${r1},${r1} 0 0 1 ${p2.x},${p2.y}
            Q0,0 ${p3.x},${p3.y}
            A${r2},${r2} 0 0 0 ${p4.x},${p4.y}
            Q0,0 ${p1.x},${p1.y} Z`
  }

  const ribbonSel = flowG.selectAll('path.ribbon').data(flowList).enter().append('path')
    .attr('class', 'ribbon')
    .attr('d', ribbonPath)
    .attr('fill', d => d._grad)
    .attr('opacity', 0.5)
    .style('cursor', 'pointer')
    .on('mouseenter', function (e, d) {
      d3.select(this).transition().duration(150).attr('opacity', 0.92)
      tip.style('opacity', 1).html(
        `<b>${ARCHETYPE_BY_KEY[d.a]?.label || d.a}</b> → <b>${d._segName}</b><br/>${d.v} 位投资者`
      )
    })
    .on('mousemove', e => tip.style('left', (e.offsetX + 12) + 'px').style('top', (e.offsetY + 12) + 'px'))
    .on('mouseleave', function () {
      d3.select(this).transition().duration(150).attr('opacity', 0.5)
      tip.style('opacity', 0)
    })

  // 流光（沿条带中线动）
  if (flowAnimTimer) clearInterval(flowAnimTimer)
  const dashSel = flowG.selectAll('path.ribbon-dash').data(flowList).enter().append('path')
    .attr('class', 'ribbon-dash')
    .attr('d', d => {
      const aMid = (d._aFrom + d._aTo) / 2
      const sMid = (d._sFrom + d._sTo) / 2
      const p1 = polar(archeR + 1, aMid), p2 = polar(archeR + 7, sMid)
      return `M${p1.x},${p1.y} Q0,0 ${p2.x},${p2.y}`
    })
    .attr('fill', 'none').attr('stroke', '#fff').attr('stroke-opacity', 0.7)
    .attr('stroke-width', 1.4)
    .attr('stroke-dasharray', '4 10')
    .style('pointer-events', 'none')
  let off = 0
  flowAnimTimer = setInterval(() => {
    off = (off - 1) % 1000
    dashSel.attr('stroke-dashoffset', off)
  }, 30)

  // 原型弧
  const archeG = svg.append('g').attr('transform', `translate(${cx},${cy})`)
  const aSel = archeG.selectAll('g.arche-arc').data(archeData).enter().append('g').attr('class', 'arche-arc')
  aSel.append('path')
    .attr('d', d => archeArc({ startAngle: d._a0 + Math.PI / 2, endAngle: d._a1 + Math.PI / 2 }))
    .attr('fill', d => d.color).attr('opacity', 0.92)
    .style('cursor', 'pointer')
    .on('mouseenter', (e, d) => {
      ribbonSel.transition().duration(120).attr('opacity', r => r.a === d.key ? 0.95 : 0.08)
    })
    .on('mouseleave', () => ribbonSel.transition().duration(120).attr('opacity', 0.5))
  aSel.append('text')
    .attr('x', d => Math.cos(d._mid) * (archeR + 12))
    .attr('y', d => Math.sin(d._mid) * (archeR + 12))
    .attr('text-anchor', d => Math.abs(Math.cos(d._mid)) < 0.3 ? 'middle' : (Math.cos(d._mid) > 0 ? 'start' : 'end'))
    .attr('dominant-baseline', d => Math.sin(d._mid) > 0.3 ? 'hanging' : (Math.sin(d._mid) < -0.3 ? 'auto' : 'middle'))
    .attr('font-size', 11).attr('fill', '#2c3041').attr('font-weight', 700)
    .text(d => `${d.label} · ${d.members.length}`)
    .style('pointer-events', 'none')

  // 客群弧
  const segG = svg.append('g').attr('transform', `translate(${cx},${cy})`)
  const sSel = segG.selectAll('g.seg-arc').data(segData).enter().append('g').attr('class', 'seg-arc')
    .style('cursor', 'pointer')
    .on('click', (e, d) => openFishboneRadial(d))
    .on('mouseenter', (e, d) => {
      ribbonSel.transition().duration(120).attr('opacity', r => r.s === d.segment_id ? 0.95 : 0.08)
    })
    .on('mouseleave', () => ribbonSel.transition().duration(120).attr('opacity', 0.5))
  sSel.append('path')
    .attr('d', d => segArc({ startAngle: d._a0 + Math.PI / 2, endAngle: d._a1 + Math.PI / 2 }))
    .attr('fill', '#5b56e8').attr('opacity', 0.85)
  sSel.append('text')
    .attr('x', d => Math.cos(d._mid) * ((archeR + segR) / 2 + 4))
    .attr('y', d => Math.sin(d._mid) * ((archeR + segR) / 2 + 4))
    .attr('text-anchor', 'middle')
    .attr('dominant-baseline', 'middle')
    .attr('font-size', 10).attr('fill', '#fff').attr('font-weight', 700)
    .text(d => `${d.name} · ${d._v}`)
    .style('pointer-events', 'none')

  // 产品花瓣（永久显示在客群弧外侧）
  const petalG = svg.append('g').attr('transform', `translate(${cx},${cy})`)
  segData.forEach(seg => {
    const products = (seg.recommended_products || []).slice(0, 5)
    if (!products.length) return
    const segSpan = seg._a1 - seg._a0
    const pStep = segSpan / (products.length + 1)
    products.forEach((p, idx) => {
      const a = seg._a0 + pStep * (idx + 1)
      const x1 = Math.cos(a) * (segR + 4)
      const y1 = Math.sin(a) * (segR + 4)
      const x2 = Math.cos(a) * (petalR - 6)
      const y2 = Math.sin(a) * (petalR - 6)
      const labelSide = Math.cos(a) >= 0 ? 1 : -1
      const isVert = Math.abs(Math.cos(a)) < 0.3

      // 花茎
      const stem = petalG.append('path')
        .attr('d', `M${x1},${y1} Q${(x1 + x2) / 2 * 0.85},${(y1 + y2) / 2 * 0.85} ${x2},${y2}`)
        .attr('fill', 'none').attr('stroke', '#9c95ff').attr('stroke-width', 1.1)
        .attr('opacity', 0).attr('stroke-dasharray', '0 1')
      stem.transition().duration(500).delay(idx * 80).attr('opacity', 0.55).attr('stroke-dasharray', '1 0')

      // 花瓣
      const petal = petalG.append('g').attr('transform', `translate(${x2},${y2})`)
        .style('opacity', 0).style('cursor', 'default')
      petal.append('circle').attr('r', 11).attr('fill', '#5b56e8').attr('opacity', 0.1)
      petal.append('circle').attr('r', 4).attr('fill', '#5b56e8').attr('opacity', 0.95)
      const lbl = petal.append('g')
        .attr('transform', isVert ? `translate(0, ${labelSide >= 0 ? 18 : -18})` : `translate(${labelSide * 9}, 0)`)
      const txt = lbl.append('text')
        .attr('text-anchor', isVert ? 'middle' : (labelSide > 0 ? 'start' : 'end'))
        .attr('dominant-baseline', 'middle')
        .attr('font-size', 10).attr('fill', '#4b46d8').attr('font-weight', 600)
        .text(p)
      try {
        const bb = txt.node().getBBox()
        lbl.insert('rect', 'text')
          .attr('x', bb.x - 5).attr('y', bb.y - 2)
          .attr('width', bb.width + 10).attr('height', bb.height + 4)
          .attr('rx', 8).attr('fill', '#f1f0fe').attr('stroke', '#d6d3fc').attr('stroke-width', 0.8)
      } catch (_) { /* getBBox 在 hidden svg 时可能失败，忽略 */ }
      petal.transition().duration(400).delay(500 + idx * 80).style('opacity', 1)
    })
  })

  // 标题与图例
  svg.append('text').attr('x', 18).attr('y', 22)
    .attr('font-size', 12).attr('font-weight', 700).attr('fill', '#666')
    .text('▲ 投资者原型')
  svg.append('text').attr('x', 18).attr('y', H - 14)
    .attr('font-size', 12).attr('font-weight', 700).attr('fill', '#666')
    .text('▼ CSOP 客群')
  svg.append('text').attr('x', W - 18).attr('y', H - 14)
    .attr('text-anchor', 'end')
    .attr('font-size', 11).attr('font-weight', 600).attr('fill', '#888')
    .text('◌ 推荐产品（点击客群弧查看话术）')
}

// 客群弧点击 → 在中心右侧弹出鱼骨弹层
function openFishboneRadial(seg) {
  if (!seg) return
  fishboneSegment.value = seg
  const W = stageRef.value?.clientWidth || 800
  const H = stageRef.value?.clientHeight || 600
  fishbonePos.value = {
    x: Math.max(20, W / 2 - 150),
    y: Math.max(40, H / 2 - 140),
  }
}

// 把 agent 匹配到 segment（按 archetype 简单映射）
const ARCHETYPE_TO_SEGMENT = {
  growth: 'seg_aggressive',
  short_trade: 'seg_short_term',
  contrarian: 'seg_contrarian',
  income: 'seg_dividend',
  defensive: 'seg_conservative',
  global: 'seg_global',
  rational: 'seg_global',
  thematic: 'seg_aggressive',
}
function matchSegment(card) {
  const a = archetypeOf(card)
  const sid = ARCHETYPE_TO_SEGMENT[a.key]
  return segments.value.find(s => s.segment_id === sid) || segments.value[0]
}

// 鱼骨弹层关闭
function closeFishbone() {
  fishboneSegment.value = null
}

defineExpose({ refresh: loadAll })
</script>

<style scoped>
.persona-panel {
  width: 100%;
  height: 100%;
  background: #fafbfd;
  color: #2c3041;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* 顶部工具栏 —— 浅色，与 GraphPanel 风格一致 */
.persona-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 14px;
  background: linear-gradient(to bottom, rgba(255, 255, 255, 0.95), rgba(255, 255, 255, 0.85));
  border-bottom: 1px solid #e5e7ee;
  flex-shrink: 0;
}

.mode-tabs {
  display: flex;
  gap: 4px;
  background: #fff;
  border: 1px solid #e0e0e0;
  border-radius: 6px;
  padding: 3px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
}
.mode-tab {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 5px 12px;
  background: transparent;
  border: none;
  border-radius: 4px;
  color: #666;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
}
.mode-tab:hover { color: #333; background: #f5f5f7; }
.mode-tab.active {
  background: linear-gradient(135deg, #5b56e8, #8366ff);
  color: #fff;
  box-shadow: 0 2px 6px rgba(91, 86, 232, 0.35);
}
.mode-icon { font-size: 13px; }

.stats {
  display: flex;
  align-items: center;
  gap: 6px;
}
.stat-pill {
  display: inline-flex;
  align-items: baseline;
  gap: 3px;
  padding: 3px 10px;
  background: #fff;
  border: 1px solid #e0e0e0;
  border-radius: 12px;
  font-size: 11px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.03);
}
.stat-num { font-weight: 700; color: #333; }
.stat-label { color: #888; font-size: 10px; }

.persona-stage {
  flex: 1;
  position: relative;
  overflow: hidden;
  background: #fafbfd;
}
.viz-svg {
  position: absolute; inset: 0;
  width: 100%; height: 100%;
}

.state-msg {
  position: absolute; inset: 0;
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  color: #999; gap: 8px;
}
.state-msg.error { color: #d9534f; }
.empty-icon { font-size: 48px; color: #ddd; }
.empty-hint { font-size: 12px; color: #aaa; }

/* 原型图例 */
.arche-legend {
  position: absolute;
  left: 12px; bottom: 12px;
  background: rgba(255, 255, 255, 0.95);
  border: 1px solid #e5e7ee;
  border-radius: 6px;
  padding: 8px 10px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px 14px;
  max-width: calc(100% - 24px);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
  z-index: 5;
}
.arche-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  cursor: pointer;
  color: #333;
}
.arche-item:hover .arche-name { color: #5b56e8; }
.arche-dot { width: 10px; height: 10px; border-radius: 50%; }
.arche-name { font-weight: 600; }
.arche-count { color: #888; font-size: 10px; }

/* d3 注入的 tooltip */
:deep(.persona-tip) {
  position: absolute;
  pointer-events: none;
  background: #20223b;
  color: #fff;
  padding: 6px 10px;
  border-radius: 4px;
  font-size: 11px;
  opacity: 0;
  transition: opacity 0.12s;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
  z-index: 10;
  line-height: 1.5;
}

/* 鱼骨弹层 */
.fishbone-pop {
  position: absolute;
  width: 280px;
  background: #fff;
  border: 1px solid #d8dae6;
  border-radius: 8px;
  box-shadow: 0 8px 28px rgba(20, 30, 80, 0.15);
  z-index: 8;
  overflow: hidden;
  animation: fbIn 0.25s ease-out;
}
@keyframes fbIn {
  from { opacity: 0; transform: translateY(8px) scale(0.96); }
  to   { opacity: 1; transform: none; }
}
.fishbone-head {
  display: flex; align-items: center; gap: 6px;
  padding: 8px 12px;
  background: linear-gradient(135deg, #5b56e8, #8366ff);
  color: #fff;
  font-weight: 700;
  font-size: 12px;
}
.fb-icon { font-size: 14px; }
.fb-title { flex: 1; }
.fb-close {
  background: rgba(255, 255, 255, 0.2);
  border: none; color: #fff; cursor: pointer;
  width: 20px; height: 20px; border-radius: 4px;
  font-size: 14px; line-height: 1;
}
.fb-close:hover { background: rgba(255, 255, 255, 0.35); }
.fishbone-body { padding: 10px 12px; }
.fb-desc { font-size: 11px; color: #666; margin-bottom: 8px; line-height: 1.5; }

.fb-products {
  list-style: none;
  margin: 0; padding: 0;
  position: relative;
}
.fb-products::before {
  content: '';
  position: absolute;
  left: 6px; top: 6px; bottom: 6px;
  width: 2px;
  background: linear-gradient(to bottom, #5b56e8, #d8dae6);
  border-radius: 1px;
}
.fb-product {
  position: relative;
  display: flex; align-items: center;
  margin: 4px 0;
  padding-left: 22px;
  font-size: 12px;
  color: #333;
  font-weight: 600;
  opacity: 0;
  animation: fbProductIn 0.4s ease-out forwards;
}
@keyframes fbProductIn {
  from { opacity: 0; transform: translateX(-8px); }
  to   { opacity: 1; transform: none; }
}
.fb-bone {
  position: absolute;
  left: 7px; top: 50%;
  width: 14px; height: 2px;
  background: #5b56e8;
  transform: translateY(-50%);
  border-radius: 1px;
}
.fb-bone::after {
  content: '';
  position: absolute;
  right: -3px; top: -2px;
  width: 6px; height: 6px;
  background: #5b56e8;
  border-radius: 50%;
}
.fb-pname {
  background: #f1f0fe;
  border: 1px solid #d6d3fc;
  padding: 2px 8px;
  border-radius: 10px;
  color: #4b46d8;
}

.fb-talking {
  margin-top: 10px;
  padding-top: 8px;
  border-top: 1px dashed #e5e7ee;
}
.fb-tt-title {
  font-size: 10px; color: #888;
  font-weight: 700;
  margin-bottom: 4px;
}
.fb-tt-item {
  font-size: 11px; color: #555;
  line-height: 1.5;
}

/* 便签墙 */
.sticky-wall {
  position: absolute; inset: 0;
  overflow-y: auto;
  padding: 20px 22px;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 18px 16px;
  align-content: start;
}
.mini-card {
  position: relative;
  padding: 14px 14px 12px 14px;
  border-radius: 6px;
  color: #2c3041;
  cursor: pointer;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.06), 0 1px 2px rgba(0, 0, 0, 0.04);
  transform: rotate(-0.3deg);
  transition: transform 0.15s, box-shadow 0.15s;
  font-size: 12px;
  border: 1px solid rgba(0, 0, 0, 0.04);
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 130px;
}
.mini-card:hover {
  transform: rotate(0deg) translateY(-2px);
  box-shadow: 0 6px 16px rgba(0, 0, 0, 0.12);
}
.mini-arche-bar {
  position: absolute;
  left: 0; top: 0; right: 0;
  height: 3px;
  border-radius: 6px 6px 0 0;
}
.mini-head { display: flex; flex-direction: column; gap: 2px; padding-top: 4px; }
.mini-name {
  font-weight: 700; font-size: 13px;
  line-height: 1.35;
  word-break: break-word;
}
.mini-sub {
  font-size: 11px; color: #666;
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 1;
  -webkit-box-orient: vertical;
  overflow: hidden;
  text-overflow: ellipsis;
}
.mini-tags {
  display: flex; gap: 6px; flex-wrap: wrap;
  align-items: center;
}
.arche-pill {
  font-size: 10px;
  padding: 3px 9px;
  border-radius: 10px;
  font-weight: 600;
  white-space: nowrap;
  color: #fff;
  line-height: 1.4;
  letter-spacing: 0.2px;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
}
.mini-meta {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-top: auto;
  padding-top: 6px;
  border-top: 1px dashed rgba(0, 0, 0, 0.08);
}
.meta-row {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  line-height: 1.4;
  min-height: 16px;
}
.meta-key {
  flex-shrink: 0;
  font-size: 10px;
  color: #888;
  font-weight: 600;
  background: rgba(0, 0, 0, 0.05);
  padding: 1px 6px;
  border-radius: 6px;
  letter-spacing: 0.3px;
}
.meta-val {
  color: #444;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  min-width: 0;
}

/* 详情弹窗 */
.detail-pop {
  position: absolute; inset: 0;
  background: rgba(20, 30, 60, 0.35);
  display: flex; align-items: center; justify-content: center;
  z-index: 12;
}
.detail-card {
  background: #fff;
  border: 1px solid #d8dae6;
  border-radius: 8px;
  width: min(480px, 90%);
  max-height: 80%;
  overflow-y: auto;
  box-shadow: 0 12px 36px rgba(0, 0, 0, 0.2);
}
.detail-head {
  display: flex; justify-content: space-between; align-items: center;
  padding: 10px 14px;
  border-bottom: 1px solid #eef0f5;
  gap: 8px;
}
.detail-title { font-weight: 700; font-size: 14px; color: #2c3041; flex: 1; }
.detail-arche {
  font-size: 10px; color: #fff;
  padding: 3px 8px; border-radius: 8px; font-weight: 600;
}
.close {
  background: transparent; border: none; color: #999;
  font-size: 20px; cursor: pointer; line-height: 1;
}
.close:hover { color: #333; }
.detail-body { padding: 12px 14px; font-size: 12px; }
.detail-body .row { margin-bottom: 6px; line-height: 1.5; color: #333; }
.detail-body .row b { color: #777; margin-right: 4px; font-weight: 600; }
.detail-body .row.tiny { font-size: 10px; color: #999; word-break: break-all; }
.detail-body .row.tiny code { background: #f5f5f7; padding: 1px 4px; border-radius: 2px; }
</style>
