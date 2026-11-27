/**
 * 临时存储待上传的现实种子（文件 或 已勾选的 FMP 文章）
 * 用于首页点击启动引擎后立即跳转，在 Process 页面再调用 API。
 *
 * mode = 'files'    -> 使用 files (File[])
 * mode = 'articles' -> 使用 articles (Object[])
 */
import { reactive } from 'vue'

const state = reactive({
  mode: 'files', // 'files' | 'articles'
  files: [],
  articles: [],
  simulationRequirement: '',
  // 可选：金融预测标的 { symbol, type: 'stock'|'crypto'|'event', market }
  targetAsset: null,
  // 可选：Step1 结构化金融种子 { selected_articles, comments, metadata }
  financialSeedContext: null,
  isPending: false
})

export function setPendingUpload(files, requirement, targetAsset = null) {
  state.mode = 'files'
  state.files = files
  state.articles = []
  state.simulationRequirement = requirement
  state.targetAsset = targetAsset
  state.financialSeedContext = null
  state.isPending = true
}

export function setPendingArticles(articles, requirement, targetAsset = null, financialSeedContext = null) {
  state.mode = 'articles'
  state.articles = articles
  state.files = []
  state.simulationRequirement = requirement
  state.targetAsset = targetAsset
  state.financialSeedContext = financialSeedContext
  state.isPending = true
}

export function getPendingUpload() {
  return {
    mode: state.mode,
    files: state.files,
    articles: state.articles,
    simulationRequirement: state.simulationRequirement,
    targetAsset: state.targetAsset,
    financialSeedContext: state.financialSeedContext,
    isPending: state.isPending
  }
}

export function clearPendingUpload() {
  state.mode = 'files'
  state.files = []
  state.articles = []
  state.simulationRequirement = ''
  state.targetAsset = null
  state.financialSeedContext = null
  state.isPending = false
}

export default state
