<template>
  <div class="finrex-v2 home-v2">
    <HomeNavbar />

    <main>
      <HomeHero />

      <!-- FIG 03 · 报告输入端双轨 -->
      <ReportInputTypes />

      <!-- FIG 04 · 模拟验证区（策略回测 / 模拟实盘交易） -->
      <SimulationValidationSection />

      <section class="history-section">
        <header class="history-section__head">
          <span class="kicker">FIG 04 · SYS.HISTORY</span>
          <h2>推演记录</h2>
          <p class="sub">所有项目按时间倒序，点击进入详情。</p>
        </header>
        <div class="history-wrap">
          <HistoryDatabase />
        </div>
      </section>

      <footer class="footer">
        <span>© FinRex · Predict Anything</span>
        <span class="footer__sep">·</span>
        <span>Blueprint Edition v2 · {{ new Date().getFullYear() }}</span>
      </footer>
    </main>
  </div>
</template>

<script setup>
import HomeNavbar from '@/components/home/HomeNavbar.vue'
import HomeHero from '@/components/home/HomeHero.vue'
import ReportInputTypes from '@/components/home/ReportInputTypes.vue'
import SimulationValidationSection from '@/components/home/SimulationValidationSection.vue'
import HistoryDatabase from '@/components/HistoryDatabase.vue'
</script>

<style scoped>
.home-v2 { min-height: 100vh; background: var(--c-bg); }
.history-section { padding: var(--s-7) var(--s-6); background: var(--c-bg-soft); }
.history-section__head { margin-bottom: var(--s-5); }
.history-section__head .kicker {
  font-family: var(--f-mono);
  color: var(--c-bg);
  background: var(--c-text);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: .18em;
  padding: 3px 8px;
}
.history-section__head h2 { font-size: var(--fs-22); font-weight: 700; margin: 10px 0 4px; color: var(--c-text); }
.history-section__head .sub { color: var(--c-text-muted); font-size: var(--fs-13); margin: 0; }
.history-wrap {
  background: var(--c-bg);
  border: 1px solid var(--c-border);
  border-radius: var(--r-lg);
  overflow: hidden;
}
.footer {
  padding: var(--s-6) var(--s-6);
  text-align: center;
  color: var(--c-text-subtle);
  font-size: var(--fs-12);
  border-top: 1px solid var(--c-border);
}
.footer__sep { margin: 0 var(--s-2); }
</style>
