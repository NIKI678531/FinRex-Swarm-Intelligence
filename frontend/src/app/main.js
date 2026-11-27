import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import i18n from '../i18n'

// v2 设计令牌（白底蓝字）— 仅作用于 .finrex-v2 包裹的页面
import '../assets/styles/tokens.css'

// ECharts 主题注册
import * as echarts from 'echarts'
import { finrexTheme } from '../assets/echarts-theme-finrex'
echarts.registerTheme('finrex', finrexTheme)
if (typeof window !== 'undefined') window.__finrex_theme_registered__ = true

const app = createApp(App)

app.use(router)
app.use(i18n)

app.mount('#app')
