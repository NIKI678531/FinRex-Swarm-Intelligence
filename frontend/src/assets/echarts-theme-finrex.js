/**
 * ECharts 主题 · FinRex v2（白底蓝字）
 * 用法：
 *   import * as echarts from 'echarts'
 *   import { finrexTheme } from '@/assets/echarts-theme-finrex'
 *   echarts.registerTheme('finrex', finrexTheme)
 *   echarts.init(el, 'finrex')
 */
export const finrexTheme = {
  color: ['#2F6BFF', '#1B3A8B', '#1F9D55', '#D43A2F', '#C57E10', '#7A5AF8'],
  backgroundColor: 'transparent',
  textStyle: {
    color: '#0E1A33',
    fontFamily: 'Inter, "PingFang SC", "Microsoft YaHei", sans-serif'
  },
  title: {
    textStyle: { color: '#0E1A33', fontWeight: 600 },
    subtextStyle: { color: '#5B6B86' }
  },
  legend: { textStyle: { color: '#5B6B86' } },
  tooltip: {
    backgroundColor: '#FFFFFF',
    borderColor: '#E3E8F0',
    borderWidth: 1,
    textStyle: { color: '#0E1A33' },
    extraCssText: 'box-shadow: 0 6px 18px rgba(16,36,86,.08); border-radius: 10px;'
  },
  grid: { borderColor: '#E3E8F0', containLabel: true },
  categoryAxis: {
    axisLine: { lineStyle: { color: '#C9D3E2' } },
    axisTick: { show: false },
    axisLabel: { color: '#5B6B86' },
    splitLine: { show: false }
  },
  valueAxis: {
    axisLine: { show: false },
    axisTick: { show: false },
    axisLabel: { color: '#5B6B86' },
    splitLine: { lineStyle: { color: '#EDF1F7' } }
  },
  timeAxis: {
    axisLine: { lineStyle: { color: '#C9D3E2' } },
    axisTick: { show: false },
    axisLabel: { color: '#5B6B86' },
    splitLine: { show: false }
  },
  line: { smooth: true, symbol: 'circle', symbolSize: 4 },
  bar: { itemStyle: { borderRadius: [6, 6, 0, 0] } }
}
