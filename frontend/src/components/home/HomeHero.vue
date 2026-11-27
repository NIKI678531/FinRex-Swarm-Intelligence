<template>
  <section class="hero">
    <!-- 顶部蓝图元数据：与 variant t0 风格对齐 -->
    <div class="hero__metarow">
      <span class="meta-fig">FIG 01</span>
      <span class="meta-sys">SYS.OVERVIEW · AR_VISUAL</span>
      <span class="meta-rev">REV. 2.0.4 / RENDER_ENGINE: GROUP_INTELLIGENCE</span>
    </div>

    <div class="hero__grid">
      <div class="hero__left">
        <div class="hero__eyebrow">
          ✦ <span>HOW FINREX RUNS YOUR MARKET INTELLIGENCE.</span> ✦
        </div>

        <h1 class="hero__title">
          群体智能 ·
          <span class="hero__title-accent">数字预演</span>
          · <br />可执行洞察。
        </h1>

        <p class="hero__lead">
          从现实种子生成高保真数字孪生世界，让上千个具备记忆与人格的智能体推演未来；
          FinRex 把推演结果直接转化为可发布的预测帖与可落地的策略建议。
        </p>

        <div class="hero__cta">
          <UiButton variant="primary" size="lg" @click="goSeed">从新闻开始推演 →</UiButton>
          <UiButton variant="ghost" size="lg" @click="$router.push('/report/rpt_demo')">查看示例报告</UiButton>
        </div>

        <div class="hero__metrics">
          <UiKpi label="推演时长" value="≤ 10 min" hint="平均一次完整推演" />
          <UiKpi label="模拟体量" value="1000+" hint="并行 Agent 数" />
          <UiKpi label="覆盖市场" value="5" hint="US · CN · HK · KR · MENA" />
        </div>
      </div>

      <div class="hero__right">
        <!-- 蓝图工位面板：标注式装饰 -->
        <div class="blueprint">
          <div class="blueprint__corner tl"></div>
          <div class="blueprint__corner tr"></div>
          <div class="blueprint__corner bl"></div>
          <div class="blueprint__corner br"></div>

          <div class="blueprint__crosshair"></div>
          <div class="orb">
            <div class="orb__ring" v-for="i in 3" :key="i" :style="{ animationDelay: `${i * 0.6}s` }"></div>
            <div class="orb__core">FX</div>
          </div>

          <div class="blueprint__caption">
            <span class="cap-label">DIGITAL TWIN · SOCIAL ORB</span>
            <span class="cap-meta">N=1024 · MEM_DEPTH=∞</span>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup>
import { useRouter } from 'vue-router'
import { UiButton, UiKpi } from '@/components/ui'

const router = useRouter()
function goSeed () {
  router.push({ path: '/sentiment', query: { source: 'fmp' } })
}
</script>

<style scoped>
.hero {
  padding: var(--s-6) var(--s-6) var(--s-8);
  background: var(--c-bg);
}

/* —— Top metadata row —— */
.hero__metarow {
  display: flex; align-items: center; gap: 12px;
  font-family: var(--f-mono);
  font-size: 11px;
  letter-spacing: .14em;
  color: var(--c-text-subtle);
  padding-bottom: var(--s-4);
  border-bottom: 1px solid var(--c-border);
  margin-bottom: var(--s-6);
}
.meta-fig {
  color: var(--c-bg);
  background: var(--c-text);
  padding: 3px 8px;
  letter-spacing: .18em;
  font-weight: 700;
}
.meta-sys { color: var(--c-text-muted); }
.meta-rev { margin-left: auto; }

.hero__grid {
  display: grid;
  grid-template-columns: 1.4fr 1fr;
  gap: var(--s-7);
  align-items: center;
}

.hero__eyebrow {
  font-family: var(--f-mono);
  font-size: 12px;
  letter-spacing: .14em;
  color: var(--c-text-muted);
  margin-bottom: var(--s-4);
}
.hero__eyebrow span { color: var(--c-text); font-weight: 600; }

.hero__title {
  font-size: 56px;
  line-height: 1.05;
  font-weight: 800;
  margin: 0 0 var(--s-4);
  color: var(--c-text);
  letter-spacing: -0.02em;
}
.hero__title-accent {
  background: linear-gradient(120deg, var(--c-accent) 0%, var(--c-brand) 100%);
  -webkit-background-clip: text; background-clip: text;
  color: transparent;
}

.hero__lead {
  max-width: 620px;
  color: var(--c-text-muted);
  font-size: 16px;
  line-height: 1.7;
  margin: 0 0 var(--s-5);
}

.hero__cta { display: flex; gap: var(--s-3); margin-bottom: var(--s-6); }
.hero__metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--s-3);
  padding-top: var(--s-4);
  border-top: 1px dashed var(--c-border);
}

/* —— Right blueprint panel —— */
.hero__right { display: flex; justify-content: center; align-items: center; }
.blueprint {
  position: relative;
  width: 360px; height: 360px;
  border: 1px solid var(--c-border);
  background:
    linear-gradient(var(--c-border) 1px, transparent 1px) 0 0 / 32px 32px,
    linear-gradient(90deg, var(--c-border) 1px, transparent 1px) 0 0 / 32px 32px,
    var(--c-bg-soft);
  display: flex; align-items: center; justify-content: center;
}
.blueprint__corner {
  position: absolute; width: 14px; height: 14px;
  border: 2px solid var(--c-brand);
}
.blueprint__corner.tl { top: -1px; left: -1px; border-right: none; border-bottom: none; }
.blueprint__corner.tr { top: -1px; right: -1px; border-left: none; border-bottom: none; }
.blueprint__corner.bl { bottom: -1px; left: -1px; border-right: none; border-top: none; }
.blueprint__corner.br { bottom: -1px; right: -1px; border-left: none; border-top: none; }
.blueprint__crosshair {
  position: absolute; inset: 0;
  background:
    linear-gradient(var(--c-border-strong), var(--c-border-strong)) center/1px 100% no-repeat,
    linear-gradient(var(--c-border-strong), var(--c-border-strong)) center/100% 1px no-repeat;
  opacity: 0.6;
}
.blueprint__caption {
  position: absolute; bottom: -28px; left: 0; right: 0;
  display: flex; justify-content: space-between;
  font-family: var(--f-mono);
  font-size: 10px;
  letter-spacing: .14em;
  color: var(--c-text-subtle);
}
.cap-label { color: var(--c-text-muted); font-weight: 600; }

.orb {
  position: relative;
  width: 240px; height: 240px;
  display: flex; align-items: center; justify-content: center;
  z-index: 2;
}
.orb__ring {
  position: absolute; inset: 0;
  border: 1px solid var(--c-border-strong);
  border-radius: 50%;
  animation: orb-pulse 3.6s ease-out infinite;
  opacity: 0;
}
.orb__core {
  width: 130px; height: 130px;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--c-accent) 0%, var(--c-brand) 100%);
  color: #fff;
  display: flex; align-items: center; justify-content: center;
  font-family: var(--f-mono);
  font-size: 28px;
  letter-spacing: 0.1em;
  box-shadow: 0 18px 40px rgba(31, 107, 255, 0.35);
}
@keyframes orb-pulse {
  0%   { transform: scale(0.6); opacity: 0; }
  20%  { opacity: 0.5; }
  100% { transform: scale(1.6); opacity: 0; }
}

@media (max-width: 1100px) {
  .hero__title { font-size: 42px; }
}
@media (max-width: 960px) {
  .hero__grid { grid-template-columns: 1fr; }
  .hero__right { display: none; }
  .hero__title { font-size: 36px; }
}
</style>
