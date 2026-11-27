import { createRouter, createWebHistory } from 'vue-router'
import Home from '@/pages/HomeV2.vue'
import Process from '@/pages/MainView.vue'
import SimulationView from '@/pages/SimulationView.vue'
import SimulationRunView from '@/pages/SimulationRunView.vue'
import ReportView from '@/pages/ReportView.vue'
import InteractionView from '@/pages/InteractionView.vue'
import UnifiedReportView from '@/pages/UnifiedReportView.vue'
import PersonaHubView from '@/pages/PersonaHubView.vue'
import SentimentReportView from '@/pages/SentimentReportView.vue'
import ValidationLab from '@/pages/ValidationLab.vue'
import QuantBacktestLab from '@/pages/QuantBacktestLab.vue'
import PaperTradingLab from '@/pages/PaperTradingLab.vue'

const routes = [
  { path: '/', name: 'Home', component: Home },
  { path: '/sentiment', name: 'Sentiment', component: SentimentReportView },
  { path: '/process/:projectId', name: 'Process', component: Process, props: true },
  { path: '/simulation/:simulationId', name: 'Simulation', component: SimulationView, props: true },
  { path: '/simulation/:simulationId/start', name: 'SimulationRun', component: SimulationRunView, props: true },
  { path: '/report/:reportId', name: 'Report', component: UnifiedReportView, props: true },
  { path: '/report/:reportId/replay', name: 'ReportReplay', component: ReportView, props: true },
  { path: '/interaction/:reportId', name: 'Interaction', component: InteractionView, props: true },
  { path: '/personas/:reportId', name: 'Persona', component: PersonaHubView, props: true },
  { path: '/backtest', redirect: '/quant/backtest' },
  { path: '/backtest/:runId', redirect: '/quant/backtest' },
  { path: '/validation', name: 'ValidationLab', component: ValidationLab },
  { path: '/quant/backtest', name: 'QuantBacktestLab', component: QuantBacktestLab },
  { path: '/quant/backtest/:runId', name: 'QuantBacktestRun', component: QuantBacktestLab, props: true },
  { path: '/quant/paper-trading', name: 'PaperTradingLab', component: PaperTradingLab },
  { path: '/quant/paper-trading/:symbol', name: 'PaperTradingDetail', component: PaperTradingLab, props: true },
  { path: '/:pathMatch(.*)*', redirect: '/' }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router
