<template>
  <section class="sim-validation" id="simulation-validation">
    <header class="sim-validation__head">
      <div class="fig-row">
        <span class="fig-label">FIG 04</span>
        <span class="fig-sys">SYS.STRATEGY / SIMULATION_VALIDATION</span>
        <span class="fig-rev">REV. 1.0.0</span>
      </div>
      <h2 class="sim-validation__title">{{ t('home.simulationValidation.title') }}</h2>
      <p class="sim-validation__lead">{{ t('home.simulationValidation.lead') }}</p>
    </header>

    <div class="card-row">
      <button class="quant-card" type="button" @click="goBacktest">
        <span class="card-num">01</span>
        <div class="card-body">
          <span class="card-tag">BACKTEST LAB</span>
          <h3>{{ t('home.simulationValidation.cardBacktest.title') }}</h3>
          <p>{{ t('home.simulationValidation.cardBacktest.desc') }}</p>
          <ul class="bullets">
            <li>{{ t('home.simulationValidation.cardBacktest.b1') }}</li>
            <li>{{ t('home.simulationValidation.cardBacktest.b2') }}</li>
            <li>{{ t('home.simulationValidation.cardBacktest.b3') }}</li>
          </ul>
          <span class="card-cta">{{ t('home.simulationValidation.cardBacktest.cta') }} <span class="arrow">→</span></span>
        </div>
      </button>

      <button class="quant-card quant-card--alt" type="button" @click="goPaperTrading">
        <span class="card-num">02</span>
        <div class="card-body">
          <span class="card-tag">PAPER TRADING</span>
          <h3>{{ t('home.simulationValidation.cardPaperTrading.title') }}</h3>
          <p>{{ t('home.simulationValidation.cardPaperTrading.desc') }}</p>
          <ul class="bullets">
            <li>{{ t('home.simulationValidation.cardPaperTrading.b1') }}</li>
            <li>{{ t('home.simulationValidation.cardPaperTrading.b2') }}</li>
            <li>{{ t('home.simulationValidation.cardPaperTrading.b3') }}</li>
          </ul>
          <span class="card-cta">{{ t('home.simulationValidation.cardPaperTrading.cta') }} <span class="arrow">→</span></span>
        </div>
      </button>

      <button class="quant-card quant-card--market" type="button" @click="goPolymarket">
        <span class="card-num">03</span>
        <div class="card-body">
          <span class="card-tag">POLYMARKET VALIDATION</span>
          <h3>{{ t('home.simulationValidation.cardPolymarket.title') }}</h3>
          <p>{{ t('home.simulationValidation.cardPolymarket.desc') }}</p>
          <ul class="bullets">
            <li>{{ t('home.simulationValidation.cardPolymarket.b1') }}</li>
            <li>{{ t('home.simulationValidation.cardPolymarket.b2') }}</li>
            <li>{{ t('home.simulationValidation.cardPolymarket.b3') }}</li>
          </ul>
          <span class="card-cta">{{ t('home.simulationValidation.cardPolymarket.cta') }} <span class="arrow">→</span></span>
        </div>
      </button>
    </div>
  </section>
</template>

<script setup>
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'

const router = useRouter()
const { t } = useI18n()

function goBacktest () {
  router.push({ path: '/quant/backtest' })
}
function goPaperTrading () {
  router.push({ path: '/quant/paper-trading' })
}
function goPolymarket () {
  router.push({ path: '/validation' })
}
</script>

<style scoped>
.sim-validation {
  padding: var(--s-7) var(--s-6);
  background: var(--c-bg);
  border-bottom: 1px solid var(--c-border);
}
.fig-row {
  display: inline-flex;
  align-items: center;
  gap: 12px;
  font-family: var(--f-mono);
  font-size: 11px;
  letter-spacing: .14em;
  color: var(--c-text-subtle);
  margin-bottom: var(--s-3);
}
.fig-label {
  color: var(--c-bg);
  background: var(--c-text);
  padding: 3px 8px;
  letter-spacing: .18em;
  font-weight: 700;
}
.fig-sys { color: var(--c-text-muted); }
.fig-rev { margin-left: auto; }
.sim-validation__head { max-width: 920px; margin-bottom: var(--s-5); }
.sim-validation__title {
  font-size: clamp(26px, 4vw, 34px);
  line-height: 1.2;
  font-weight: 700;
  color: var(--c-text);
  margin: 0 0 var(--s-3);
}
.sim-validation__lead {
  color: var(--c-text-muted);
  font-size: 15px;
  line-height: 1.7;
  max-width: 760px;
  margin: 0;
}
.card-row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--s-5);
  margin-top: var(--s-5);
}
@media (max-width: 880px) {
  .card-row { grid-template-columns: 1fr; }
}
.quant-card {
  display: flex;
  gap: var(--s-4);
  text-align: left;
  background: var(--c-bg-soft);
  border: 1px solid var(--c-border);
  border-radius: var(--r-lg);
  padding: var(--s-5);
  cursor: pointer;
  transition: border-color .15s ease, transform .15s ease, box-shadow .15s ease;
  color: inherit;
  font: inherit;
}
.quant-card:hover {
  border-color: var(--c-text);
  transform: translateY(-2px);
  box-shadow: 0 6px 24px rgba(0,0,0,.08);
}
.card-num {
  font-family: var(--f-mono);
  font-size: 28px;
  font-weight: 700;
  color: var(--c-text-subtle);
  min-width: 48px;
}
.card-body { flex: 1; }
.card-tag {
  display: inline-block;
  font-family: var(--f-mono);
  font-size: 10px;
  letter-spacing: .18em;
  background: var(--c-text);
  color: var(--c-bg);
  padding: 3px 8px;
  font-weight: 700;
  margin-bottom: var(--s-3);
}
.card-body h3 {
  margin: 0 0 var(--s-2);
  font-size: 20px;
  font-weight: 700;
  color: var(--c-text);
}
.card-body > p {
  margin: 0 0 var(--s-3);
  color: var(--c-text-muted);
  font-size: 14px;
  line-height: 1.6;
}
.bullets {
  list-style: none;
  padding: 0;
  margin: 0 0 var(--s-4);
}
.bullets li {
  font-size: 13px;
  color: var(--c-text-muted);
  line-height: 1.7;
  padding-left: 14px;
  position: relative;
}
.bullets li::before {
  content: '·';
  position: absolute;
  left: 4px;
  color: var(--c-text);
  font-weight: 700;
}
.card-cta {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-family: var(--f-mono);
  font-size: 12px;
  letter-spacing: .12em;
  font-weight: 700;
  color: var(--c-text);
  text-transform: uppercase;
}
.card-cta .arrow {
  transition: transform .15s ease;
}
.quant-card:hover .card-cta .arrow {
  transform: translateX(4px);
}
.quant-card--alt {
  background: var(--c-text);
  color: var(--c-bg);
  border-color: var(--c-text);
}
.quant-card--alt .card-num { color: rgba(255,255,255,.45); }
.quant-card--alt .card-tag { background: var(--c-bg); color: var(--c-text); }
.quant-card--alt h3 { color: var(--c-bg); }
.quant-card--alt > .card-body > p,
.quant-card--alt .bullets li { color: rgba(255,255,255,.78); }
.quant-card--alt .bullets li::before { color: var(--c-bg); }
.quant-card--alt .card-cta { color: var(--c-bg); }
.quant-card--alt:hover { box-shadow: 0 6px 28px rgba(0,0,0,.25); }
.quant-card--market {
  background: #F8FAFC;
  border-color: #CBD5E1;
}
.quant-card--market .card-tag {
  background: #1B3A8B;
  color: #fff;
}
</style>
