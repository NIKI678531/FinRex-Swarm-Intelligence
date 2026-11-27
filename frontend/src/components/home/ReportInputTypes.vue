<template>
  <section class="reaction-inputs" id="report-inputs">
    <header class="reaction-inputs__head">
      <div class="fig-row">
        <span class="fig-label">FIG 03</span>
        <span class="fig-sys">SYS.INPUTS / MARKET_REACTION_FORECAST</span>
        <span class="fig-rev">REV. 2.1.0</span>
      </div>
      <h2 class="reaction-inputs__title">金融事件模拟预测入口</h2>
      <p class="reaction-inputs__lead">
        FinRex 将 FMP 新闻、Binance 评论区和外部论坛种子合并为同一条市场反应预测 workflow：先识别事件主题与市场方向，
        再用 agents 推演未来情绪扩散，并映射到 CSOP 产品策略。
      </p>
    </header>

    <div class="workflow-panel">
      <div class="workflow-panel__main">
        <span class="panel-tag">MARKET REACTION FORECAST</span>
        <h3>信号分类 / 方向预测 / 产品策略映射</h3>
        <p>报告输出市场信号、资产影响、客户分群和合规提示，并在金融强预测报告中保留可审计的证据来源结构。</p>
        <button class="primary-cta" type="button" @click="goReaction('fmp')">
          启动模拟预测 <span>→</span>
        </button>
      </div>

      <div class="mode-list">
        <button class="mode-item" type="button" @click="goReaction('fmp')">
          <span class="mode-num">01</span>
          <span class="mode-copy">
            <strong>FMP 新闻，无评论</strong>
            <small>按宏观政策、行业轮动、市场情绪、资金流向和区域热点预分类，再做 agent-only 市场预测。</small>
          </span>
          <span class="mode-arrow">→</span>
        </button>

        <button class="mode-item" type="button" @click="goReaction('paste')">
          <span class="mode-num">02</span>
          <span class="mode-copy">
            <strong>已有评论数据</strong>
            <small>真实评论作为直接输入，agents 补齐沉默人群，并输出市场方向和产品策略。</small>
          </span>
          <span class="mode-arrow">→</span>
        </button>

        <button class="mode-item" type="button" @click="goReaction('binance')">
          <span class="mode-num">03</span>
          <span class="mode-copy">
            <strong>Binance 帖子 / 评论区</strong>
            <small>支持 News / Feed / Hashtag / User 多选，结合评论热度判断加密资产与风险偏好变化。</small>
          </span>
          <span class="mode-arrow">→</span>
        </button>
      </div>
    </div>
  </section>
</template>

<script setup>
import { useRouter } from 'vue-router'

const router = useRouter()

function goReaction (source) {
  router.push({ path: '/sentiment', query: { source } })
}
</script>

<style scoped>
.reaction-inputs {
  padding: var(--s-7) var(--s-6);
  background: var(--c-bg-soft);
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

.reaction-inputs__head {
  max-width: 920px;
  margin-bottom: var(--s-5);
}

.reaction-inputs__title {
  font-size: clamp(26px, 4vw, 34px);
  line-height: 1.2;
  font-weight: 700;
  color: var(--c-text);
  margin: 0 0 var(--s-3);
  letter-spacing: 0;
}

.reaction-inputs__lead {
  color: var(--c-text-muted);
  font-size: 15px;
  line-height: 1.7;
  max-width: 760px;
  margin: 0;
}

.reaction-inputs__lead b {
  color: var(--c-text);
  font-weight: 700;
}

.workflow-panel {
  display: grid;
  grid-template-columns: minmax(280px, 0.85fr) minmax(360px, 1.15fr);
  gap: var(--s-4);
  align-items: stretch;
}

.workflow-panel__main,
.mode-item {
  border: 1px solid var(--c-border);
  border-radius: var(--r-lg);
  background: var(--c-bg);
}

.workflow-panel__main {
  padding: var(--s-5);
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  min-height: 248px;
  border-left: 3px solid var(--c-brand);
}

.panel-tag {
  align-self: flex-start;
  font-family: var(--f-mono);
  font-size: 11px;
  letter-spacing: .14em;
  color: var(--c-bg);
  background: var(--c-brand);
  padding: 3px 8px;
  border-radius: 3px;
  margin-bottom: var(--s-3);
}

.workflow-panel__main h3 {
  margin: 0 0 10px;
  color: var(--c-text);
  font-size: 22px;
  line-height: 1.25;
  letter-spacing: 0;
}

.workflow-panel__main p {
  color: var(--c-text-muted);
  font-size: 14px;
  line-height: 1.7;
  margin: 0 0 var(--s-5);
}

.primary-cta {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  width: fit-content;
  min-height: 40px;
  padding: 0 18px;
  border: 1px solid var(--c-brand);
  background: var(--c-brand);
  color: #fff;
  font-size: 14px;
  font-weight: 700;
  border-radius: var(--r-md);
  cursor: pointer;
}

.mode-list {
  display: grid;
  gap: 10px;
}

.mode-item {
  display: grid;
  grid-template-columns: 44px minmax(0, 1fr) 20px;
  gap: 12px;
  align-items: center;
  min-height: 76px;
  padding: 14px;
  text-align: left;
  cursor: pointer;
  transition: border-color .15s ease, transform .15s ease, box-shadow .15s ease;
}

.mode-item:hover {
  border-color: var(--c-brand);
  transform: translateY(-1px);
  box-shadow: 0 10px 24px rgba(31, 107, 255, 0.07);
}

.mode-num {
  display: inline-grid;
  place-items: center;
  width: 38px;
  height: 38px;
  font-family: var(--f-mono);
  font-size: 12px;
  color: var(--c-accent);
  background: var(--c-bg-soft);
  border: 1px solid var(--c-border);
  border-radius: 6px;
  font-weight: 700;
}

.mode-copy {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.mode-copy strong {
  color: var(--c-text);
  font-size: 15px;
  line-height: 1.35;
}

.mode-copy small {
  color: var(--c-text-muted);
  font-size: 12px;
  line-height: 1.5;
  max-width: 54ch;
}

.mode-arrow {
  color: var(--c-text-subtle);
  font-size: 18px;
}

@media (max-width: 900px) {
  .workflow-panel {
    grid-template-columns: 1fr;
  }

  .workflow-panel__main {
    min-height: auto;
  }
}

@media (max-width: 640px) {
  .reaction-inputs {
    padding: var(--s-6) var(--s-4);
  }

  .fig-row {
    display: flex;
    flex-wrap: wrap;
    row-gap: 6px;
  }

  .fig-rev {
    margin-left: 0;
  }

  .workflow-panel__main {
    padding: var(--s-4);
  }

  .mode-item {
    grid-template-columns: 38px minmax(0, 1fr);
    align-items: start;
  }

  .mode-arrow {
    display: none;
  }
}
</style>
