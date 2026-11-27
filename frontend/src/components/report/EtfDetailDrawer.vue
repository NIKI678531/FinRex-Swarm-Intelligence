<template>
  <transition name="drawer-fade">
    <div class="drawer-mask" @click.self="$emit('close')">
      <aside class="drawer">
        <header class="drawer-head">
          <div>
            <strong class="code">{{ code }}</strong>
            <span class="name">{{ nameZh }}</span>
          </div>
          <button class="close-btn" @click="$emit('close')">×</button>
        </header>

        <div v-if="loading" class="state">正在加载行情与指标…</div>
        <div v-else-if="error" class="state error">{{ error }}</div>

        <div v-else-if="data?.signal?.ok" class="drawer-body">
          <!-- Top summary -->
          <div class="summary-grid">
            <div class="cell">
              <span>方向</span>
              <strong :class="'dir-' + data.signal.direction">{{ dirLabel(data.signal.direction) }}</strong>
            </div>
            <div class="cell">
              <span>置信度</span>
              <strong>{{ Math.round((data.signal.confidence || 0) * 100) }}%</strong>
            </div>
            <div class="cell">
              <span>{{ horizonLabel }}预期</span>
              <strong>{{ pct(data.signal.expected_return_pct?.central) }}</strong>
              <small class="muted">
                [{{ pct(data.signal.expected_return_pct?.lower) }} ~ {{ pct(data.signal.expected_return_pct?.upper) }}]
              </small>
            </div>
            <div class="cell">
              <span>最新收盘 ({{ data.signal.as_of }})</span>
              <strong>{{ data.signal.last_close }}</strong>
            </div>
          </div>

          <!-- K-line chart with Bollinger band -->
          <h4>近 90 日 K 线 · 布林带 · 均线</h4>
          <EChart :option="klineOption" height="320px" />

          <!-- Indicator votes -->
          <h4>指标投票</h4>
          <ul class="vote-list">
            <li v-for="(v, i) in data.signal.votes" :key="i" :class="'pol-' + v.polarity">
              <span class="vote-w">{{ v.weight > 0 ? '+1' : '-1' }}</span>
              <span class="vote-label">{{ v.label }}</span>
            </li>
          </ul>

          <!-- Indicator snapshot -->
          <h4>关键指标 (最新)</h4>
          <div class="ind-grid">
            <div v-for="(v, k) in indSnapshot" :key="k" class="ind-cell">
              <span>{{ k }}</span><strong>{{ v }}</strong>
            </div>
          </div>

          <!-- Backtest hit rate -->
          <h4 v-if="data.backtest && data.backtest.directional_samples >= 10">历史胜率 · 近一年走理回测</h4>
          <div v-if="data.backtest && data.backtest.directional_samples >= 10" class="ind-grid">
            <div class="ind-cell">
              <span>总胜率</span>
              <strong>{{ Math.round((data.backtest.hit_rate || 0) * 100) }}%</strong>
            </div>
            <div class="ind-cell">
              <span>看多胜率</span>
              <strong>{{ data.backtest.bullish_count > 0 ? Math.round((data.backtest.bullish_hit_rate || 0) * 100) + '%' : '—' }}</strong>
              <small class="muted">{{ data.backtest.bullish_count }} 样本</small>
            </div>
            <div class="ind-cell">
              <span>看空胜率</span>
              <strong>{{ data.backtest.bearish_count > 0 ? Math.round((data.backtest.bearish_hit_rate || 0) * 100) + '%' : '—' }}</strong>
              <small class="muted">{{ data.backtest.bearish_count }} 样本</small>
            </div>
            <div class="ind-cell">
              <span>中性跳过</span>
              <strong>{{ data.backtest.neutral_samples }}</strong>
            </div>
          </div>

          <!-- Risk -->
          <h4>风险度量 (近 120 日)</h4>
          <div class="ind-grid">
            <div class="ind-cell"><span>年化波动</span><strong>{{ pct((data.signal.risk?.ann_vol || 0) * 100) }}</strong></div>
            <div class="ind-cell"><span>最大回撤</span><strong>{{ pct((data.signal.risk?.max_drawdown || 0) * 100) }}</strong></div>
            <div class="ind-cell"><span>Sharpe</span><strong>{{ data.signal.risk?.sharpe }}</strong></div>
          </div>
        </div>

        <div v-else class="state">
          {{ data?.error || '该 ETF 暂无可用历史数据，无法计算技术信号。' }}
        </div>
      </aside>
    </div>
  </transition>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import EChart from '@/components/report/widgets/EChart.vue'
import { getEtfForecast } from '@/api/assetAllocation'

const props = defineProps({
  code: { type: String, required: true },
  nameZh: { type: String, default: '' },
  horizon: { type: String, default: '1w' }
})
defineEmits(['close'])

const HORIZON_LABEL_MAP = { '1w': '5日', '2w': '10日', '1m': '21日' }
const horizonLabel = computed(() => HORIZON_LABEL_MAP[props.horizon] || '5日')

const data = ref(null)
const loading = ref(true)
const error = ref('')

function dirLabel (d) { return ({ bullish: '看多', neutral: '中性', bearish: '看空' }[d]) || '—' }
function pct (v) {
  if (v === null || v === undefined || Number.isNaN(v)) return '—'
  return (v >= 0 ? '+' : '') + Number(v).toFixed(2) + '%'
}

const indSnapshot = computed(() => {
  const i = data.value?.signal?.indicators_last || {}
  return {
    'SMA20': i.sma20, 'SMA60': i.sma60, 'EMA20': i.ema20,
    'RSI14': i.rsi14, 'MACD': i.macd, 'MACD-Signal': i.macd_signal,
    'Boll Upper': i.boll_upper, 'Boll Lower': i.boll_lower,
    'ATR14': i.atr14, 'Mom10 (%)': i.mom10_pct, 'Mom20 (%)': i.mom20_pct
  }
})

const klineOption = computed(() => {
  const rows = data.value?.ohlcv_tail || []
  const dates = rows.map(r => r.date)
  const ohlc = rows.map(r => [r.open, r.close, r.low, r.high])
  // re-compute SMA20 / Bollinger band on display rows (cheap, transparent)
  const closes = rows.map(r => r.close)
  const sma20 = movingAvg(closes, 20)
  const boll = bands(closes, 20, 2)
  return {
    tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
    legend: { data: ['K线', 'SMA20', 'Boll上轨', 'Boll下轨'], textStyle: { fontSize: 11 } },
    grid: { left: 50, right: 16, top: 32, bottom: 28 },
    xAxis: { type: 'category', data: dates, boundaryGap: true, axisLabel: { fontSize: 10 } },
    yAxis: { scale: true, axisLabel: { fontSize: 10 } },
    series: [
      {
        name: 'K线', type: 'candlestick', data: ohlc,
        itemStyle: { color: '#dc2626', color0: '#16a34a', borderColor: '#dc2626', borderColor0: '#16a34a' }
      },
      { name: 'SMA20', type: 'line', data: sma20, smooth: true, showSymbol: false, lineStyle: { color: '#5B8DEF', width: 1.5 } },
      { name: 'Boll上轨', type: 'line', data: boll.upper, smooth: true, showSymbol: false, lineStyle: { color: '#9CA3AF', type: 'dashed', width: 1 } },
      { name: 'Boll下轨', type: 'line', data: boll.lower, smooth: true, showSymbol: false, lineStyle: { color: '#9CA3AF', type: 'dashed', width: 1 } }
    ]
  }
})

function movingAvg (arr, n) {
  const out = []; let s = 0
  for (let i = 0; i < arr.length; i++) {
    s += arr[i]
    if (i >= n) s -= arr[i - n]
    out.push(i >= n - 1 ? +(s / n).toFixed(4) : null)
  }
  return out
}

function bands (arr, n, k) {
  const upper = [], lower = []
  for (let i = 0; i < arr.length; i++) {
    if (i < n - 1) { upper.push(null); lower.push(null); continue }
    const w = arr.slice(i - n + 1, i + 1)
    const mean = w.reduce((a, b) => a + b, 0) / n
    const std = Math.sqrt(w.reduce((a, b) => a + (b - mean) ** 2, 0) / n)
    upper.push(+(mean + k * std).toFixed(4))
    lower.push(+(mean - k * std).toFixed(4))
  }
  return { upper, lower }
}

onMounted(async () => {
  try {
    const res = await getEtfForecast(props.code, 365, props.horizon)
    data.value = res.data
    if (!data.value?.signal?.ok && data.value?.error) error.value = data.value.error
  } catch (err) {
    error.value = err?.response?.data?.error || err.message || '加载失败'
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.drawer-mask {
  position: fixed; inset: 0; background: rgba(15, 23, 42, 0.45); z-index: 1000;
  display: flex; justify-content: flex-end;
}
.drawer {
  width: min(720px, 92vw); height: 100%; background: #fff; overflow-y: auto;
  padding: 20px 24px; box-shadow: -8px 0 32px rgba(0, 0, 0, 0.18);
}
.drawer-head { display: flex; justify-content: space-between; align-items: baseline; padding-bottom: 12px; border-bottom: 1px solid #e5e7eb; margin-bottom: 16px; }
.drawer-head .code { font-size: 18px; margin-right: 10px; }
.drawer-head .name { color: #4b5563; font-size: 14px; }
.close-btn { background: none; border: 0; font-size: 24px; cursor: pointer; color: #6b7280; }
.close-btn:hover { color: #111827; }

.state { padding: 24px; text-align: center; color: #6b7280; }
.state.error { color: #b91c1c; }

.summary-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 20px; }
.summary-grid .cell { background: #f7f8fb; border-radius: 10px; padding: 10px 12px; }
.summary-grid .cell span { display: block; color: #6b7280; font-size: 11px; }
.summary-grid .cell strong { font-size: 18px; }
.summary-grid .cell small { display: block; font-size: 10px; }
.dir-bullish { color: #16a34a; } .dir-bearish { color: #dc2626; } .dir-neutral { color: #ca8a04; }

h4 { margin: 16px 0 8px; font-size: 13px; color: #111827; }
.muted { color: #6b7280; font-size: 11px; }

.vote-list { list-style: none; padding: 0; margin: 0; display: grid; grid-template-columns: repeat(2, 1fr); gap: 6px; }
.vote-list li { display: flex; align-items: center; gap: 8px; padding: 6px 8px; border-radius: 6px; font-size: 12px; background: #f7f8fb; }
.vote-list li.pol-bull { background: #ecfdf5; }
.vote-list li.pol-bear { background: #fef2f2; }
.vote-w { font-weight: 700; min-width: 22px; }
.pol-bull .vote-w { color: #16a34a; }
.pol-bear .vote-w { color: #dc2626; }

.ind-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
.ind-cell { background: #f7f8fb; border-radius: 8px; padding: 8px 10px; display: flex; flex-direction: column; gap: 2px; }
.ind-cell span { font-size: 11px; color: #6b7280; }
.ind-cell strong { font-size: 13px; }

.drawer-fade-enter-active, .drawer-fade-leave-active { transition: opacity .22s; }
.drawer-fade-enter-from, .drawer-fade-leave-to { opacity: 0; }
</style>
