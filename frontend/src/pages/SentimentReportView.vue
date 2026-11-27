<template>
  <div class="reaction-view">
    <HomeNavbar />

    <main class="reaction-shell">
      <header class="page-head">
        <div class="eyebrow-row">
          <span>MARKET</span>
          <span>REACTION FORECAST</span>
          <span>MULTI-SOURCE + CSOP STRATEGY</span>
        </div>
        <h1>金融舆情模拟预测</h1>
        <p>
          选择 FMP 新闻、Binance 评论区或外部论坛种子，先按执行层设计归类市场信号，再预测市场方向、风险扩散和 CSOP 产品策略映射。
        </p>
      </header>

      <!-- ── SECTION 01 (NEW POSITION): 预测维度 + 标的类型 ── -->
      <section class="input-band">
        <div class="section-head compact">
          <span class="kicker">01</span>
          <div>
            <h2>预测维度与提示词</h2>
            <p>先选择资产类型与推演主题，下方的信息源池将按资产类型自动过滤。</p>
          </div>
        </div>

        <!-- 金融强预测报告 B：标的输入（前置，决定下方信息源池） -->
        <div class="form-grid forecast-asset-grid">
          <label>
            <span>分析标的（可选 · 用于金融强预测报告）</span>
            <input v-model="forecastSymbol" type="text" placeholder="例如：BTC / NVDA / AAPL；不填则生成事件级市场反应预测" />
          </label>
          <label>
            <span>标的类型</span>
            <select v-model="forecastAssetType">
              <option value="event">事件级（无标的）</option>
              <option value="stock">股票</option>
              <option value="crypto">加密货币</option>
            </select>
          </label>
          <label>
            <span>预测周期 Horizon</span>
            <select v-model.number="forecastHorizon">
              <optgroup label="短期预测">
                <option :value="1">1 天（短期）</option>
                <option :value="3">3 天（短期）</option>
              </optgroup>
              <optgroup label="长期预测">
                <option :value="5">5 天（长期）</option>
                <option :value="10">10 天（长期）</option>
              </optgroup>
            </select>
          </label>
          <label>
            <span>市场（可选）</span>
            <input v-model="forecastMarket" type="text" placeholder="例如：US / HK / CN" />
          </label>
        </div>
        <p class="horizon-hint">
          当前预测周期：<b>{{ forecastHorizonLabel }}</b>
          —— {{ forecastHorizon <= 3 ? '短期偏重技术面与即时舆情' : '长期更看重趋势与基本面演化' }}
        </p>

        <div class="dim-grid">
          <label v-for="dim in dimensions" :key="dim.key" class="dim-card" :class="{ active: selectedDims.includes(dim.key) }">
            <input type="checkbox" :value="dim.key" v-model="selectedDims" />
            <span>
              <strong>{{ dim.title }}</strong>
              <small>{{ dim.desc }}</small>
            </span>
          </label>
        </div>

        <label class="full-label prompt-box">
          <span>自定义补充（可选）</span>
          <textarea v-model="customPrompt" rows="5" placeholder="补充具体场景、主体或数据范围。例如：聚焦 BTC 与香港港股资金面联动" />
          <small class="prompt-engine">引擎：FinRex-V1.0</small>
        </label>
      </section>

      <section class="input-band">
        <div class="section-head">
          <span class="kicker">02</span>
          <div>
            <h2>信息源池</h2>
            <p>可以同时选择多个来源。真实评论作为直接评论样本；新闻和无评论帖子作为场景推演种子。当前资产类型：<b>{{ forecastAssetType }}</b>，仅展示与之匹配的源。</p>
          </div>
        </div>

        <div class="source-grid">
          <button
            v-for="item in sources"
            :key="item.key"
            type="button"
            class="source-card"
            :class="{ active: isSourceActive(item.key) }"
            @click="toggleSource(item.key)"
          >
            <span class="source-mark" :style="{ background: item.color }">{{ item.short }}</span>
            <span class="source-copy">
              <strong>{{ item.name }}</strong>
              <small>{{ item.desc }}</small>
              <em>
                {{ sourceSelectionCount(item.key) }} selected
                <b v-if="sourceHasObserved(item.key)">直接评论</b>
              </em>
            </span>
          </button>
        </div>
      </section>

      <section class="input-band">
        <div class="section-head">
          <span class="kicker">03</span>
          <div>
            <h2>选择输入种子</h2>
            <p>先按来源筛选和批量选择，再由前端预分类为标准信号、方向和产品域。</p>
          </div>
        </div>

        <div class="source-summary-grid">
          <div>
            <span>Active Sources</span>
            <strong>{{ activeSources.length }}</strong>
          </div>
          <div>
            <span>Selected Seeds</span>
            <strong>{{ selectedSeedCount }}</strong>
          </div>
          <div>
            <span>Potential Direct Comments</span>
            <strong>{{ potentialObservedCount }}</strong>
          </div>
        </div>

        <div v-if="!activeSources.length" class="status-line">请至少选择一个信息源。</div>

        <article v-if="isSourceActive('fmp')" class="source-panel">
          <header class="source-panel__head">
            <div>
              <span class="panel-kicker">FMP NEWS</span>
              <h3>FMP 新闻种子</h3>
              <p>FMP 后端代理仅提供分页列表；时间区间在当前已加载页内筛选，滚动刷新会追加第一页新内容。</p>
            </div>
            <strong>{{ selectedFmpArticles.length }} selected</strong>
          </header>

          <!-- FMP category tab bar (covers all 15 FMP stable endpoints) -->
          <nav class="fmp-tabs">
            <button
              v-for="tab in FMP_CATEGORY_TABS"
              :key="tab.key"
              type="button"
              class="fmp-tab"
              :class="{ active: fmpSourceCategory === tab.key }"
              @click="selectFmpCategory(tab.key)"
            >
              {{ tab.label }}
            </button>
          </nav>

          <!-- Search query input (search tab only) -->
          <div v-if="fmpSourceCategory === 'search'" class="fmp-search-row">
            <input
              v-model="fmpSearchQuery"
              type="text"
              placeholder="Search news (e.g. bitcoin, Apple, Fed rate)"
              @keyup.enter="reloadFmp"
            />
            <button type="button" class="plain-btn" :disabled="fmpLoading" @click="reloadFmp">
              {{ fmpLoading ? '加载中' : '搜索' }}
            </button>
          </div>

          <div v-if="fmpSourceCategory === 'stock-latest'" class="fmp-search-row">
            <input
              v-model="fmpStockSymbols"
              type="text"
              placeholder="Stock symbols: AAPL,MSFT,NVDA；留空则加载股票最新新闻"
              @keyup.enter="reloadFmp"
            />
            <button type="button" class="plain-btn" :disabled="fmpLoading" @click="reloadFmp">
              {{ fmpLoading ? '加载中' : '加载股票新闻' }}
            </button>
          </div>

          <!-- Social Sentiment panel (entirely replaces article list when active) -->
          <div v-if="fmpSourceCategory === 'social'" class="fmp-social-panel">
            <div class="fmp-social-controls">
              <label>
                <span>Mode</span>
                <select v-model="fmpSocialMode" @change="loadFmpSocial">
                  <option value="trending">Trending</option>
                  <option value="changes">Changes</option>
                  <option value="historical">Historical (by symbol)</option>
                </select>
              </label>
              <label v-if="fmpSocialMode !== 'historical'">
                <span>Type</span>
                <select v-model="fmpSocialType" @change="loadFmpSocial">
                  <option value="bullish">Bullish</option>
                  <option value="bearish">Bearish</option>
                </select>
              </label>
              <label v-if="fmpSocialMode !== 'historical'">
                <span>Source</span>
                <select v-model="fmpSocialSource" @change="loadFmpSocial">
                  <option value="stocktwits">StockTwits</option>
                  <option value="twitter">Twitter</option>
                </select>
              </label>
              <label v-if="fmpSocialMode === 'historical'">
                <span>Symbol</span>
                <input v-model="fmpSocialSymbol" type="text" placeholder="AAPL" @keyup.enter="loadFmpSocial" />
              </label>
              <button type="button" class="plain-btn" :disabled="fmpSocialLoading" @click="loadFmpSocial">
                {{ fmpSocialLoading ? '加载中' : '刷新' }}
              </button>
            </div>
            <div v-if="fmpSocialError" class="status-line error">{{ fmpSocialError }}</div>
            <div v-else-if="fmpSocialLoading && !fmpSocialData.length" class="status-line">正在加载社交情绪数据…</div>
            <div v-else-if="!fmpSocialData.length" class="status-line">暂无数据</div>
            <table v-else class="social-table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Name / Date</th>
                  <th class="num">StockTwits Sent.</th>
                  <th class="num">Twitter Sent.</th>
                  <th class="num">ST Posts</th>
                  <th class="num">TW Posts</th>
                  <th class="num">Rank</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(row, idx) in fmpSocialData.slice(0, 50)" :key="idx">
                  <td><b>{{ row.symbol || '-' }}</b></td>
                  <td>{{ row.name || row.date || '-' }}</td>
                  <td class="num" :class="row.stocktwits_sentiment >= 0 ? 'pos' : 'neg'">{{ Number(row.stocktwits_sentiment || 0).toFixed(3) }}</td>
                  <td class="num" :class="row.twitter_sentiment >= 0 ? 'pos' : 'neg'">{{ Number(row.twitter_sentiment || 0).toFixed(3) }}</td>
                  <td class="num">{{ row.stocktwits_posts || 0 }}</td>
                  <td class="num">{{ row.twitter_posts || 0 }}</td>
                  <td class="num">{{ row.rank ?? '-' }}</td>
                </tr>
              </tbody>
            </table>
          </div>

          <div v-if="fmpSourceCategory !== 'social'" class="source-panel__toolbar fmp-toolbar">
            <input v-model="fmpQuery" type="text" placeholder="搜索标题、正文、ticker" @keyup.enter="reloadFmp" />
            <select v-model="fmpCategoryFilter">
              <option v-for="category in signalCategories" :key="category.key" :value="category.key">{{ category.label }}</option>
            </select>
            <select v-model="fmpDirectionFilter">
              <option value="all">全部方向</option>
              <option v-for="(label, key) in directionLabels" :key="key" :value="key">{{ label }}</option>
            </select>
            <select v-model.number="fmpLimit" @change="reloadFmp">
              <option :value="20">20 条</option>
              <option :value="50">50 条</option>
              <option :value="100">100 条</option>
            </select>
            <button type="button" class="plain-btn" :disabled="fmpLoading" @click="reloadFmp">
              {{ fmpLoading ? '加载中' : '刷新' }}
            </button>
            <label class="inline-toggle">
              <input v-model="fmpAutoRefresh" type="checkbox" />
              <span>60s 滚动</span>
            </label>
          </div>

          <template v-if="fmpSourceCategory !== 'social'">
          <div class="filter-row">
            <button v-for="item in quickWindows" :key="item.key" type="button" class="chip-btn" @click="applyQuickWindow('fmp', item.key)">
              {{ item.label }}
            </button>
            <label>
              <span>开始</span>
              <input v-model="fmpStart" type="datetime-local" />
            </label>
            <label>
              <span>结束</span>
              <input v-model="fmpEnd" type="datetime-local" />
            </label>
          </div>

          <div class="batch-row">
            <button type="button" class="plain-btn" @click="selectAllFmp(filteredFmpArticles)">全选当前页</button>
            <button type="button" class="plain-btn" @click="selectAllFmp(fmpTimeRangeArticles)">全选时间区间</button>
            <button type="button" class="plain-btn" @click="clearFmpSelection">清空 FMP</button>
          </div>

          <div v-if="fmpError" class="status-line error">{{ fmpError }}</div>
          <div v-else-if="fmpLoading && !fmpArticles.length" class="status-line">正在加载 FMP 新闻。</div>
          <div v-else-if="!filteredFmpArticles.length" class="status-line">当前筛选下暂无新闻。</div>

          <div v-else class="article-list">
            <label
              v-for="article in filteredFmpArticles"
              :key="getArticleKey(article)"
              class="article-card"
              :class="{ selected: isFmpSelected(article) }"
            >
              <input type="checkbox" :checked="isFmpSelected(article)" @change="toggleFmp(article)" />
              <span class="article-body">
                <strong>{{ article.title || '(无标题)' }}</strong>
                <small>
                  <span>{{ formatArticleDate(article) }}</span>
                  <span v-if="article.site">{{ article.site }}</span>
                  <span v-if="article.tickers">{{ article.tickers }}</span>
                </small>
                <span class="tag-row">
                  <b>{{ article.classification.id }}</b>
                  <i>{{ article.classification.categoryLabel }}</i>
                  <i :class="['direction-tag', `direction-${article.classification.direction}`]">{{ article.classification.directionLabel }}</i>
                  <i v-if="article.classification.productDomains.length">{{ article.classification.productDomains.slice(0, 3).join(' / ') }}</i>
                </span>
                <em v-if="article.content">{{ stripHtml(article.content).slice(0, 220) }}</em>
              </span>
            </label>
          </div>
          </template>

          <div v-if="fmpSourceCategory !== 'social'" class="pager-row">
            <button type="button" class="plain-btn" :disabled="fmpPage <= 0 || fmpLoading" @click="changeFmpPage(fmpPage - 1)">上一页</button>
            <span>第 {{ fmpPage + 1 }} 页 · 筛选 {{ filteredFmpArticles.length }} 条 · 已选 {{ selectedFmpArticles.length }} 条</span>
            <button type="button" class="plain-btn" :disabled="fmpLoading || fmpArticles.length < fmpLimit" @click="changeFmpPage(fmpPage + 1)">下一页</button>
          </div>
        </article>

        <article v-if="isSourceActive('binance')" class="source-panel">
          <header class="source-panel__head">
            <div>
              <span class="panel-kicker">BINANCE SQUARE</span>
              <h3>Binance 新闻 / 帖子 / 评论区</h3>
              <p>News、Feed、Hashtag、User 可多选；有评论明细时作为直接评论样本，否则保持 agent-only 市场推演。</p>
            </div>
            <strong>{{ selectedBinanceArticles.length }} selected</strong>
          </header>

          <div class="chip-row source-chip-row">
            <button
              v-for="item in binanceSourceOptions"
              :key="item.key"
              type="button"
              class="chip-btn"
              :class="{ active: binanceSources.includes(item.key) }"
              @click="toggleBinanceSource(item.key)"
            >
              {{ item.label }}
            </button>
            <button type="button" class="chip-btn" @click="toggleAllBinanceSources">{{ allBinanceSourcesSelected ? '取消全选' : '全选类型' }}</button>
          </div>

          <div class="source-panel__toolbar binance-toolbar">
            <input v-model="binanceQuery" type="text" placeholder="搜索标题或内容" @keyup.enter="reloadBinance" />
            <select v-model="binanceCategoryFilter">
              <option v-for="category in signalCategories" :key="category.key" :value="category.key">{{ category.label }}</option>
            </select>
            <select v-model="binanceDirectionFilter">
              <option value="all">全部方向</option>
              <option v-for="(label, key) in directionLabels" :key="key" :value="key">{{ label }}</option>
            </select>
            <select v-model="binanceCommentMode" @change="reloadBinance">
              <option value="all">全部内容</option>
              <option value="commented">仅有评论</option>
            </select>
            <select v-model.number="binanceMinComments" @change="reloadBinance">
              <option :value="0">不限评论数</option>
              <option :value="1">至少 1 条</option>
              <option :value="5">至少 5 条</option>
              <option :value="20">至少 20 条</option>
              <option :value="100">至少 100 条</option>
            </select>
            <select v-model.number="binanceLimit" @change="reloadBinance">
              <option :value="20">20 条/类</option>
              <option :value="30">30 条/类</option>
              <option :value="50">50 条/类</option>
            </select>
            <button type="button" class="plain-btn" :disabled="binanceLoading" @click="reloadBinance">
              {{ binanceLoading ? '加载中' : '刷新' }}
            </button>
            <label class="inline-toggle">
              <input v-model="binanceAutoRefresh" type="checkbox" />
              <span>60s 滚动</span>
            </label>
          </div>

          <div class="filter-row">
            <button v-for="item in quickWindows" :key="item.key" type="button" class="chip-btn" @click="applyQuickWindow('binance', item.key)">
              {{ item.label }}
            </button>
            <label>
              <span>开始</span>
              <input v-model="binanceStart" type="datetime-local" />
            </label>
            <label>
              <span>结束</span>
              <input v-model="binanceEnd" type="datetime-local" />
            </label>
          </div>

          <div class="batch-row">
            <button type="button" class="plain-btn" @click="selectAllBinance(filteredBinanceArticles)">全选当前筛选</button>
            <button type="button" class="plain-btn" @click="selectAllBinance(binanceTimeRangeArticles)">全选时间区间</button>
            <button type="button" class="plain-btn" @click="clearBinanceSelection">清空 Binance</button>
          </div>

          <div v-if="binanceWarning" class="status-line warning">{{ binanceWarning }}</div>
          <div v-if="binanceError" class="status-line error">{{ binanceError }}</div>
          <div v-else-if="binanceLoading && !binanceArticles.length" class="status-line">正在加载 Binance 数据。</div>
          <div v-else-if="!filteredBinanceArticles.length" class="status-line">当前筛选下暂无帖子。</div>

          <div v-else class="article-list">
            <label
              v-for="article in filteredBinanceArticles"
              :key="article.id"
              class="article-card"
              :class="{ selected: isBinanceSelected(article) }"
            >
              <input type="checkbox" :checked="isBinanceSelected(article)" @change="toggleBinance(article)" />
              <span class="article-body">
                <strong>{{ article.title || '(无标题)' }}</strong>
                <small>
                  <span>{{ article.source || 'binance' }}</span>
                  <span>{{ formatArticleDate(article) }}</span>
                  <span v-if="article.author">{{ article.author }}</span>
                  <span>{{ Number(article.comments_count || 0) }} comments</span>
                </small>
                <span class="tag-row">
                  <b>{{ article.classification.id }}</b>
                  <i>{{ article.classification.categoryLabel }}</i>
                  <i :class="['direction-tag', `direction-${article.classification.direction}`]">{{ article.classification.directionLabel }}</i>
                  <i v-if="Number(article.comments_count || 0) > 0">Direct comment candidate</i>
                </span>
                <em v-if="article.content">{{ stripHtml(article.content).slice(0, 220) }}</em>
              </span>
            </label>
          </div>

          <div class="pager-row">
            <button type="button" class="plain-btn" :disabled="binancePage <= 0 || binanceLoading" @click="changeBinancePage(binancePage - 1)">上一页</button>
            <span>第 {{ binancePage + 1 }} 页 · 筛选 {{ filteredBinanceArticles.length }} 条 · 已选 {{ selectedBinanceArticles.length }} 条</span>
            <button type="button" class="plain-btn" :disabled="binanceLoading || binanceArticles.length < binanceLimit" @click="changeBinancePage(binancePage + 1)">下一页</button>
          </div>
        </article>

        <!-- Phase E: stock-mode dedicated source panels (FMP-style rich cards) -->
        <article v-if="isSourceActive('reddit_stock')" class="source-panel">
          <header class="source-panel__head">
            <div>
              <span class="panel-kicker">REDDIT / WSB · STOCK</span>
              <h3>Reddit 个股讨论</h3>
              <p>r/wallstreetbets · r/stocks · r/investing · r/options + 部分 ticker 专属社区。公共 JSON 端点，无需凭证。</p>
            </div>
            <strong>{{ selectedRedditStock.length }} selected</strong>
          </header>
          <div class="source-panel__toolbar fmp-toolbar">
            <input v-model="redditStockSymbol" type="text" :placeholder="forecastSymbol || '留空=当前热门'" style="width:140px" @keyup.enter="loadRedditStock" />
            <input v-model="redditStockQuery" type="text" placeholder="搜索标题、正文、subreddit" />
            <select v-model="redditStockCategoryFilter">
              <option v-for="c in signalCategories" :key="c.key" :value="c.key">{{ c.label }}</option>
            </select>
            <select v-model="redditStockDirectionFilter">
              <option value="all">全部方向</option>
              <option v-for="(label, key) in directionLabels" :key="key" :value="key">{{ label }}</option>
            </select>
            <select v-model.number="redditStockPageSize" @change="redditStockPage = 0">
              <option :value="20">20 条/页</option>
              <option :value="50">50 条/页</option>
              <option :value="100">100 条/页</option>
            </select>
            <button type="button" class="plain-btn" :disabled="redditStockLoading" @click="loadRedditStock">{{ redditStockLoading ? '加载中' : '刷新' }}</button>
          </div>
          <div class="batch-row">
            <button type="button" class="plain-btn" @click="selectAllInto(pagedRedditStock, selectedRedditStock)">全选当前页</button>
            <button type="button" class="plain-btn" @click="selectAllInto(filteredRedditStock, selectedRedditStock)">全选筛选全部</button>
            <button type="button" class="plain-btn" @click="clearListSelection(selectedRedditStock)">清空 Reddit</button>
          </div>
          <div v-if="redditStockError" class="status-line error">{{ redditStockError }}</div>
          <div v-else-if="!filteredRedditStock.length" class="status-line">{{ redditStockLoading ? '正在加载 Reddit 帖子…' : '暂无数据，点击「刷新」抓取。' }}</div>
          <div v-else class="article-list">
            <label
              v-for="article in pagedRedditStock"
              :key="getArticleKey(article)"
              class="article-card"
              :class="{ selected: isItemSelected(article, selectedRedditStock) }"
            >
              <input type="checkbox" :checked="isItemSelected(article, selectedRedditStock)" @change="toggleSelectInList(article, selectedRedditStock)" />
              <span class="article-body">
                <strong>{{ article.title || '(no title)' }}</strong>
                <small>
                  <span>{{ formatArticleDate(article) }}</span>
                  <span>r/{{ article.subreddit }}</span>
                  <span>score {{ article.score || 0 }}</span>
                  <span>{{ article.num_comments || 0 }} 评论</span>
                  <span v-if="article.author">u/{{ article.author }}</span>
                </small>
                <span class="tag-row">
                  <b>{{ article.classification.id }}</b>
                  <i>{{ article.classification.categoryLabel }}</i>
                  <i :class="['direction-tag', `direction-${article.classification.direction}`]">{{ article.classification.directionLabel }}</i>
                  <i v-if="article.classification.productDomains.length">{{ article.classification.productDomains.slice(0, 3).join(' / ') }}</i>
                </span>
                <em v-if="article.content">{{ stripHtml(article.content).slice(0, 220) }}</em>
              </span>
            </label>
          </div>
          <div class="meta-row"><span>共 {{ redditStockDisplay.length }} 条 · 当前筛选 {{ filteredRedditStock.length }} · 已选 {{ selectedRedditStock.length }}</span></div>
          <div class="pager-row">
            <button type="button" class="plain-btn" :disabled="redditStockPage <= 0" @click="redditStockPage--">上一页</button>
            <span>第 {{ redditStockPage + 1 }} / {{ Math.max(1, Math.ceil(filteredRedditStock.length / redditStockPageSize)) }} 页</span>
            <button type="button" class="plain-btn" :disabled="(redditStockPage + 1) * redditStockPageSize >= filteredRedditStock.length" @click="redditStockPage++">下一页</button>
          </div>
        </article>

        <article v-if="isSourceActive('stocktwits')" class="source-panel">
          <header class="source-panel__head">
            <div>
              <span class="panel-kicker">STOCKTWITS</span>
              <h3>StockTwits 公开流</h3>
              <p>带 Bullish / Bearish 用户标签，作为情绪先验 prior_sentiment 进入分层情绪打分。</p>
            </div>
            <strong>{{ selectedStockTwits.length }} selected</strong>
          </header>
          <div class="source-panel__toolbar fmp-toolbar">
            <input v-model="stockTwitsSymbol" type="text" :placeholder="forecastSymbol || '留空=热门流'" style="width:140px" @keyup.enter="loadStockTwits" />
            <input v-model="stockTwitsQuery" type="text" placeholder="搜索内容、用户、ticker" />
            <select v-model="stockTwitsCategoryFilter">
              <option v-for="c in signalCategories" :key="c.key" :value="c.key">{{ c.label }}</option>
            </select>
            <select v-model="stockTwitsDirectionFilter">
              <option value="all">全部方向</option>
              <option v-for="(label, key) in directionLabels" :key="key" :value="key">{{ label }}</option>
            </select>
            <select v-model.number="stockTwitsPageSize" @change="stockTwitsPage = 0">
              <option :value="20">20 条/页</option>
              <option :value="50">50 条/页</option>
              <option :value="100">100 条/页</option>
            </select>
            <button type="button" class="plain-btn" :disabled="stockTwitsLoading" @click="loadStockTwits">{{ stockTwitsLoading ? '加载中' : '刷新' }}</button>
          </div>
          <div class="batch-row">
            <button type="button" class="plain-btn" @click="selectAllInto(pagedStockTwits, selectedStockTwits)">全选当前页</button>
            <button type="button" class="plain-btn" @click="selectAllInto(filteredStockTwits, selectedStockTwits)">全选筛选全部</button>
            <button type="button" class="plain-btn" @click="clearListSelection(selectedStockTwits)">清空 StockTwits</button>
          </div>
          <div v-if="stockTwitsError" class="status-line error">{{ stockTwitsError }}</div>
          <div v-else-if="!filteredStockTwits.length" class="status-line">{{ stockTwitsLoading ? '正在加载 StockTwits…' : '暂无数据，点击「刷新」抓取。' }}</div>
          <div v-else class="article-list">
            <label
              v-for="article in pagedStockTwits"
              :key="getArticleKey(article)"
              class="article-card"
              :class="{ selected: isItemSelected(article, selectedStockTwits) }"
            >
              <input type="checkbox" :checked="isItemSelected(article, selectedStockTwits)" @change="toggleSelectInList(article, selectedStockTwits)" />
              <span class="article-body">
                <strong>{{ article.title || '(no title)' }}</strong>
                <small>
                  <span>{{ formatArticleDate(article) }}</span>
                  <span v-if="article.author">@{{ article.author }}</span>
                  <span v-if="article.prior_sentiment" :class="['direction-tag', `direction-${article.prior_sentiment === 'bullish' ? 'up' : article.prior_sentiment === 'bearish' ? 'down' : 'neutral'}`]">{{ article.prior_sentiment }}</span>
                </small>
                <span class="tag-row">
                  <b>{{ article.classification.id }}</b>
                  <i>{{ article.classification.categoryLabel }}</i>
                  <i :class="['direction-tag', `direction-${article.classification.direction}`]">{{ article.classification.directionLabel }}</i>
                </span>
                <em v-if="article.content">{{ stripHtml(article.content).slice(0, 220) }}</em>
              </span>
            </label>
          </div>
          <div class="meta-row"><span>共 {{ stockTwitsDisplay.length }} 条 · 当前筛选 {{ filteredStockTwits.length }} · 已选 {{ selectedStockTwits.length }}</span></div>
          <div class="pager-row">
            <button type="button" class="plain-btn" :disabled="stockTwitsPage <= 0" @click="stockTwitsPage--">上一页</button>
            <span>第 {{ stockTwitsPage + 1 }} / {{ Math.max(1, Math.ceil(filteredStockTwits.length / stockTwitsPageSize)) }} 页</span>
            <button type="button" class="plain-btn" :disabled="(stockTwitsPage + 1) * stockTwitsPageSize >= filteredStockTwits.length" @click="stockTwitsPage++">下一页</button>
          </div>
        </article>

        <article v-if="isSourceActive('yf_news')" class="source-panel">
          <header class="source-panel__head">
            <div>
              <span class="panel-kicker">YAHOO FINANCE</span>
              <h3>yfinance 聚合新闻</h3>
              <p>补全 FMP 个股新闻不足；30 分钟磁盘缓存。可按事件类别 / 方向筛选。</p>
            </div>
            <strong>{{ selectedYfNews.length }} selected</strong>
          </header>
          <div class="source-panel__toolbar fmp-toolbar">
            <input v-model="yfNewsSymbol" type="text" :placeholder="forecastSymbol || '留空=市场新闻'" style="width:140px" @keyup.enter="loadYfNews" />
            <input v-model="yfNewsQuery" type="text" placeholder="搜索标题、正文、出版方" />
            <select v-model="yfNewsCategoryFilter">
              <option v-for="c in signalCategories" :key="c.key" :value="c.key">{{ c.label }}</option>
            </select>
            <select v-model="yfNewsDirectionFilter">
              <option value="all">全部方向</option>
              <option v-for="(label, key) in directionLabels" :key="key" :value="key">{{ label }}</option>
            </select>
            <select v-model.number="yfNewsPageSize" @change="yfNewsPage = 0">
              <option :value="20">20 条/页</option>
              <option :value="50">50 条/页</option>
              <option :value="100">100 条/页</option>
            </select>
            <button type="button" class="plain-btn" :disabled="yfNewsLoading" @click="loadYfNews">{{ yfNewsLoading ? '加载中' : '刷新' }}</button>
          </div>
          <div class="batch-row">
            <button type="button" class="plain-btn" @click="selectAllInto(pagedYfNews, selectedYfNews)">全选当前页</button>
            <button type="button" class="plain-btn" @click="selectAllInto(filteredYfNews, selectedYfNews)">全选筛选全部</button>
            <button type="button" class="plain-btn" @click="clearListSelection(selectedYfNews)">清空 yfinance</button>
          </div>
          <div v-if="yfNewsError" class="status-line error">{{ yfNewsError }}</div>
          <div v-else-if="!filteredYfNews.length" class="status-line">{{ yfNewsLoading ? '正在加载 yfinance…' : '暂无数据，点击「刷新」抓取。' }}</div>
          <div v-else class="article-list">
            <label
              v-for="article in pagedYfNews"
              :key="getArticleKey(article)"
              class="article-card"
              :class="{ selected: isItemSelected(article, selectedYfNews) }"
            >
              <input type="checkbox" :checked="isItemSelected(article, selectedYfNews)" @change="toggleSelectInList(article, selectedYfNews)" />
              <span class="article-body">
                <strong>{{ article.title || '(no title)' }}</strong>
                <small>
                  <span>{{ formatArticleDate(article) }}</span>
                  <span v-if="article.publisher">{{ article.publisher }}</span>
                  <span v-if="article.tickers">{{ article.tickers }}</span>
                </small>
                <span class="tag-row">
                  <b>{{ article.classification.id }}</b>
                  <i>{{ article.classification.categoryLabel }}</i>
                  <i :class="['direction-tag', `direction-${article.classification.direction}`]">{{ article.classification.directionLabel }}</i>
                  <i v-if="article.classification.productDomains.length">{{ article.classification.productDomains.slice(0, 3).join(' / ') }}</i>
                </span>
                <em v-if="article.content">{{ stripHtml(article.content).slice(0, 220) }}</em>
              </span>
            </label>
          </div>
          <div class="meta-row"><span>共 {{ yfNewsDisplay.length }} 条 · 当前筛选 {{ filteredYfNews.length }} · 已选 {{ selectedYfNews.length }}</span></div>
          <div class="pager-row">
            <button type="button" class="plain-btn" :disabled="yfNewsPage <= 0" @click="yfNewsPage--">上一页</button>
            <span>第 {{ yfNewsPage + 1 }} / {{ Math.max(1, Math.ceil(filteredYfNews.length / yfNewsPageSize)) }} 页</span>
            <button type="button" class="plain-btn" :disabled="(yfNewsPage + 1) * yfNewsPageSize >= filteredYfNews.length" @click="yfNewsPage++">下一页</button>
          </div>
        </article>

        <article v-if="hasManualSeedSources" class="source-panel">
          <header class="source-panel__head">
            <div>
              <span class="panel-kicker">MANUAL / FORUM SEEDS</span>
              <h3>粘贴评论与其他论坛种子</h3>
              <p>Reddit、雪球、微博等当前作为手动种子进入同一预测流程；粘贴评论按行作为直接评论样本。</p>
            </div>
            <strong>{{ manualSeedCount }} seed</strong>
          </header>

          <div class="chip-row">
            <span v-for="key in activeManualSources" :key="key" class="source-pill">{{ getSourceLabel(key) }}</span>
          </div>

          <div class="form-grid">
            <label>
              <span>事件标题</span>
              <input v-model="manualTitle" type="text" placeholder="例如：BTC ETF 资金流入触发加密资产重估" />
            </label>
            <label>
              <span>目标社区 / 事件</span>
              <input v-model="target" type="text" placeholder="例如：r/wallstreetbets + NVDA earnings / 雪球 $NVDA$" />
            </label>
            <label>
              <span>关键词</span>
              <input v-model="keywords" type="text" placeholder="例如：NVDA, BTC, rate cut, risk" />
            </label>
            <label>
              <span>时间窗口</span>
              <select v-model="timeWindow">
                <option value="24h">最近 24 小时</option>
                <option value="3d">最近 3 天</option>
                <option value="7d">最近 7 天</option>
                <option value="30d">最近 30 天</option>
              </select>
            </label>
          </div>

          <label class="full-label">
            <span>事件背景 / 自定义信息源摘要</span>
            <textarea v-model="manualContent" rows="5" placeholder="补充新闻摘要、论坛讨论背景、资产、机构、地区或需要观察的市场假设。" />
          </label>

          <label v-if="isSourceActive('paste')" class="full-label">
            <span>真实评论（每行一条）</span>
            <textarea v-model="pastedText" rows="8" placeholder="每行一条评论；这些内容会作为直接评论样本，不会和模拟推演混写。" />
          </label>

          <div class="meta-row">
            <span>{{ pastedLines }} 条评论</span>
            <span>{{ pastedChars }} 字符</span>
          </div>
        </article>
      </section>

      <!-- ── 加密预测预览（依赖已选 Binance 种子）── -->
      <section v-if="forecastAssetType === 'crypto'" class="input-band">
        <div v-if="forecastAssetType === 'crypto'" class="crypto-preview-panel">
          <div class="crypto-preview-head">
            <div>
              <span class="panel-kicker">CRYPTO {{ forecastHorizon }}D FORECAST</span>
              <h3>{{ forecastSymbol || 'BTC' }} 价格预测预览</h3>
              <p>结合已选 Binance 评论/帖子与实盘行情，快速输出看涨、看跌或中性信号。当前周期：{{ forecastHorizonLabel }}。</p>
            </div>
            <button type="button" class="plain-btn" :disabled="!canPreviewCrypto" @click="previewCryptoForecast">
              {{ cryptoForecastLoading ? '预测中' : '生成方向看板' }}
            </button>
          </div>
          <div v-if="cryptoForecastError" class="status-line error">{{ cryptoForecastError }}</div>
          <div v-if="cryptoForecastProgress" class="crypto-progress">
            <div class="crypto-progress__head">
              <strong>{{ cryptoForecastProgress.message }}</strong>
              <span>{{ cryptoForecastProgressPercent }}%</span>
            </div>
            <div class="crypto-progress__bar">
              <i :style="{ width: cryptoForecastProgressPercent + '%' }"></i>
            </div>
            <div class="crypto-progress__detail">
              <span v-if="cryptoForecastProgress.detail">{{ cryptoForecastProgress.detail }}</span>
              <span v-if="cryptoForecastProgress.fmpArticleTotal > 0">
                FMP 新闻：{{ cryptoForecastProgress.fmpArticleTotal }} 条已纳入
              </span>
              <span v-if="cryptoForecastProgress.commentTotal > 0">
                Binance 评论：{{ cryptoForecastProgress.commentDone }}/{{ cryptoForecastProgress.commentTotal }}
                <b v-if="cryptoForecastProgress.commentFailed > 0">失败 {{ cryptoForecastProgress.commentFailed }} 条，已按无评论处理</b>
              </span>
              <span v-if="cryptoForecastProgress.observedCommentTotal > 0">
                已收集评论：{{ cryptoForecastProgress.observedCommentTotal }} 条
              </span>
            </div>
          </div>
          <div v-if="cryptoForecast" class="crypto-forecast-card" :class="cryptoForecastDirectionClass">
            <div class="crypto-forecast-main">
              <span>{{ cryptoForecast.symbol || forecastSymbol || 'BTC' }} · {{ cryptoForecast.pair || 'USDT' }}</span>
              <strong>{{ cryptoForecastDirectionLabel }}</strong>
              <em>{{ cryptoForecastProbability }} · {{ cryptoForecast.confidence || 'low' }}</em>
            </div>
            <div class="crypto-score-grid">
              <div>
                <span>技术面</span>
                <strong>{{ formatScore(cryptoForecast.score_breakdown?.technical) }}</strong>
              </div>
              <div>
                <span>舆情面</span>
                <strong>{{ formatScore(cryptoForecast.score_breakdown?.sentiment) }}</strong>
              </div>
              <div>
                <span>成交量</span>
                <strong>{{ formatScore(cryptoForecast.score_breakdown?.volume) }}</strong>
              </div>
              <div>
                <span>资金面</span>
                <strong>{{ formatScore(cryptoForecast.score_breakdown?.derivatives) }}</strong>
              </div>
            </div>
            <p class="crypto-rationale">{{ cryptoForecast.rationale }}</p>
            <div class="crypto-quality-row">
              <span>行情 {{ cryptoForecast.data_quality?.market_rows || 0 }} bars</span>
              <span>舆情 {{ cryptoForecast.data_quality?.sentiment_count || 0 }} samples</span>
              <span>状态 {{ cryptoForecast.status }}</span>
            </div>
          </div>
        </div>
      </section>

      <section class="action-row">
        <button type="button" class="primary-btn" :disabled="!canRun || analysisLoading" @click="runAnalysis">
          {{ analysisLoading ? '正在启动预测引擎' : '启动模拟预测引擎' }}
        </button>
        <button type="button" class="plain-btn" @click="router.push('/')">返回首页</button>
        <span class="launch-meta">{{ selectedSeedCount }} seeds · {{ selectedDims.length }} dimensions</span>
        <div v-if="launchProgress" class="launch-progress">
          <div class="launch-progress__head">
            <strong>{{ launchProgress.message }}</strong>
            <span>{{ launchProgressPercent }}%</span>
          </div>
          <div class="launch-progress__bar">
            <i :style="{ width: launchProgressPercent + '%' }"></i>
          </div>
          <div class="launch-progress__detail">
            <span v-if="launchProgress.detail">{{ launchProgress.detail }}</span>
            <span v-if="launchProgress.fmpArticleTotal > 0">
              FMP 新闻：{{ launchProgress.fmpArticleTotal }} 条已纳入
            </span>
            <span v-if="launchProgress.selectedArticleTotal > 0">
              新闻/种子：{{ launchProgress.selectedArticleTotal }} 条
            </span>
            <span v-if="launchProgress.commentTotal > 0">
              Binance 评论：{{ launchProgress.commentDone }}/{{ launchProgress.commentTotal }}
              <b v-if="launchProgress.commentFailed > 0">失败 {{ launchProgress.commentFailed }} 条，已按无评论处理</b>
            </span>
            <span v-if="launchProgress.observedCommentTotal > 0">
              已收集评论：{{ launchProgress.observedCommentTotal }} 条
            </span>
            <span v-else-if="launchProgress.binanceSeedTotal > 0">
              Binance 评论：已选 {{ launchProgress.binanceSeedTotal }} 个种子，无可拉取评论候选
            </span>
          </div>
        </div>
        <div v-if="analysisError" class="status-line error launch-error">{{ analysisError }}</div>
      </section>
    </main>
  </div>
</template>

<script setup>
import { computed, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import HomeNavbar from '@/components/home/HomeNavbar.vue'
import { fetchArticles, fetchBinanceArticleComments, fetchBinanceArticlesBySources } from '@/api/articles'
import { fmpNews } from '@/api/fmpNews'
import { redditNews } from '@/api/redditNews'
import { stockTwits } from '@/api/stockTwits'
import { yfinanceNews } from '@/api/yfinanceNews'
import { analyzeReaction, getReactionReportContext } from '@/api/reaction'
import { postCryptoForecast } from '@/api/financial'
import {
  DIRECTION_LABELS,
  SIGNAL_CATEGORIES,
  buildClassificationSummary,
  classifySignalSeed
} from '@/utils/signalTaxonomy'

const route = useRoute()
const router = useRouter()

const allSources = [
  { key: 'fmp', short: 'FMP', color: '#1f3f66', name: 'FMP 新闻', desc: '金融新闻作为事件种子，按执行层信号体系预分类', assetTypes: ['event', 'stock', 'crypto'] },
  { key: 'binance', short: 'B', color: '#f0b90b', name: 'Binance 新闻 / 评论', desc: 'News、Feed、Hashtag、User 多选，评论作为直接样本', assetTypes: ['event', 'crypto', 'stock'] },
  { key: 'paste', short: 'TXT', color: '#2b6cb0', name: '粘贴评论', desc: '每行一条真实评论，作为直接样本', assetTypes: ['event', 'stock', 'crypto'] },
  { key: 'manual', short: 'EVT', color: '#4a5568', name: '手动事件', desc: '无直接抓取器时，手动输入市场事件', assetTypes: ['event', 'stock', 'crypto'] },
  { key: 'reddit', short: 'R', color: '#d9471f', name: 'Reddit / WSB', desc: '当前作为手动论坛种子进入预测', assetTypes: ['event', 'crypto'] },
  { key: 'xueqiu', short: 'XQ', color: '#c13b30', name: '雪球 / 股吧', desc: '当前作为手动论坛种子进入预测', assetTypes: ['event', 'crypto'] },
  { key: 'weibo', short: 'WB', color: '#e6162d', name: '微博', desc: '当前作为手动社媒种子进入预测', assetTypes: ['event', 'crypto'] },
  // ── Stock-mode dedicated seeds (Phase E) ──
  { key: 'reddit_stock', short: 'R', color: '#ff4500', name: 'Reddit / WSB 抓取', desc: 'r/wallstreetbets · r/stocks 等公开 JSON；标的可选，留空抓当前热门讨论', assetTypes: ['event', 'stock'] },
  { key: 'stocktwits', short: 'ST', color: '#10b981', name: 'StockTwits', desc: '公开流 / 热门流，Bullish/Bearish 用户标签作为情绪先验；标的可选', assetTypes: ['event', 'stock'] },
  { key: 'yf_news', short: 'YF', color: '#7c3aed', name: 'Yahoo Finance', desc: 'yfinance / Yahoo 聚合新闻；标的可选，留空抓当前市场新闻', assetTypes: ['event', 'stock'] }
]

const dimensions = [
  { key: 'investor_demand_trends', title: '各方需求与未来投资趋势', desc: '推演不同投资者群体的资金流向、产品偏好与配置变化' },
  { key: 'sentiment_spiral', title: '舆情演变与情绪螺旋', desc: '推演传统扩散、KOL 影响、群体共识形成路径' },
  { key: 'crypto_fomo', title: '加密货币 FOMO 行情', desc: 'BTC/ETH 突破后社群情绪、衍生品资金、相关股票联动' },
  { key: 'fed_liquidity', title: '美联储议息与流动性', desc: '降息/加息预期下风险资产再定价路径' },
  { key: 'regulatory_compliance', title: '监管政策与合规风险', desc: '新规出台对发行方、交易所与产品的连锁反应' },
  { key: 'industry_ma_competition', title: '行业并购与竞争格局', desc: '收购/分拆/合资的二阶传导与受益标的' },
  { key: 'black_swan_contagion', title: '黑天鹅事件与风险传染', desc: '突发事件下避险情绪、跨市场传染与对冲需求' },
  { key: 'client_behavior_shift', title: '客群行为变迁', desc: 'CSOP 客群在事件冲击下的产品迁移与流失风险' }
]

const signalCategories = SIGNAL_CATEGORIES
const directionLabels = DIRECTION_LABELS
const quickWindows = [
  { key: '24h', label: '最近 24h', hours: 24 },
  { key: '3d', label: '最近 3 天', hours: 72 },
  { key: '7d', label: '最近 7 天', hours: 168 },
  { key: '30d', label: '最近 30 天', hours: 720 }
]
const binanceSourceOptions = [
  { key: 'news', label: 'News' },
  { key: 'feed', label: 'Feed' },
  { key: 'hashtag', label: 'Hashtag' },
  { key: 'user', label: 'User' }
]
const manualSourceKeys = ['paste', 'manual', 'reddit', 'xueqiu', 'weibo']

const initialAssetType = (() => {
  const q = typeof route.query.asset_type === 'string' ? route.query.asset_type : ''
  return ['event', 'stock', 'crypto'].includes(q) ? q : 'event'
})()
const forecastAssetType = ref(initialAssetType)

const sources = computed(() => allSources.filter(item => !item.assetTypes || item.assetTypes.includes(forecastAssetType.value)))

const initialSource = typeof route.query.source === 'string' ? route.query.source : 'fmp'
const initialActiveSources = sources.value.some(item => item.key === initialSource) ? [initialSource] : ['fmp']
const activeSources = ref(initialActiveSources)

const selectedDims = ref(dimensions.map(item => item.key))
const analysisLoading = ref(false)
const analysisError = ref('')
const reactionRun = ref(null)
const launchProgress = ref(null)

const fmpArticles = ref([])
const fmpPage = ref(0)
const fmpLimit = ref(100)
const fmpQuery = ref('')
const fmpCategoryFilter = ref('all')
const fmpDirectionFilter = ref('all')
const fmpStart = ref('')
const fmpEnd = ref('')
const fmpAutoRefresh = ref(false)
const fmpLoading = ref(false)
const fmpError = ref('')
const selectedFmpArticles = ref([])
const fmpSourceCategory = ref('articles')  // articles | general | stock-latest | crypto-latest | forex | forex-latest | press-latest | search | social
const fmpSearchQuery = ref('')
const fmpStockSymbols = ref('')
const fmpSocialSymbol = ref('AAPL')
const fmpSocialType = ref('bullish')
const fmpSocialSource = ref('stocktwits')
const fmpSocialMode = ref('trending')  // trending | changes | historical
const fmpSocialData = ref([])
const fmpSocialLoading = ref(false)
const fmpSocialError = ref('')

const FMP_CATEGORY_TABS = [
  { key: 'articles', label: 'Articles' },
  { key: 'general', label: 'General' },
  { key: 'stock-latest', label: 'Stock' },
  { key: 'crypto-latest', label: 'Crypto' },
  { key: 'forex-latest', label: 'Forex' },
  { key: 'press-latest', label: 'Press' },
  { key: 'search', label: 'Search' },
  { key: 'social', label: 'Social Sentiment' }
]

let fmpLoadedOnce = false
let fmpTimer = null

const binanceArticles = ref([])
const binancePage = ref(0)
const binanceLimit = ref(20)
const binanceQuery = ref('')
const binanceSources = ref(['news'])
const binanceCategoryFilter = ref('all')
const binanceDirectionFilter = ref('all')
const binanceCommentMode = ref('all')
const binanceMinComments = ref(0)
const binanceStart = ref('')
const binanceEnd = ref('')
const binanceAutoRefresh = ref(false)
const binanceLoading = ref(false)
const binanceError = ref('')
const binanceWarning = ref('')
const selectedBinanceArticles = ref([])
let binanceLoadedOnce = false
let binanceTimer = null

// ── Phase E: Stock-mode dedicated sources state ──
const redditStockSymbol = ref('')
const redditStockItems = ref([])
const redditStockLoading = ref(false)
const redditStockError = ref('')
const selectedRedditStock = ref([])

const stockTwitsSymbol = ref('')
const stockTwitsItems = ref([])
const stockTwitsLoading = ref(false)
const stockTwitsError = ref('')
const selectedStockTwits = ref([])

const yfNewsSymbol = ref('')
const yfNewsItems = ref([])
const yfNewsLoading = ref(false)
const yfNewsError = ref('')
const selectedYfNews = ref([])

// Stock source filters (FMP-style: query + category + direction)
const redditStockQuery = ref('')
const redditStockCategoryFilter = ref('all')
const redditStockDirectionFilter = ref('all')
const stockTwitsQuery = ref('')
const stockTwitsCategoryFilter = ref('all')
const stockTwitsDirectionFilter = ref('all')
const yfNewsQuery = ref('')
const yfNewsCategoryFilter = ref('all')
const yfNewsDirectionFilter = ref('all')
// Per-panel pagination
const redditStockPage = ref(0)
const redditStockPageSize = ref(20)
const stockTwitsPage = ref(0)
const stockTwitsPageSize = ref(20)
const yfNewsPage = ref(0)
const yfNewsPageSize = ref(20)

const target = ref('')
const keywords = ref('')
const limit = ref(300)
const timeWindow = ref('3d')
const manualTitle = ref('')
const manualContent = ref('')
const pastedText = ref('')
// 金融预测标的（可选）：用于 Step5 金融强预测报告 B
// type: 'stock' | 'crypto' | 'event'（event=无标的，事件级市场反应）
const forecastSymbol = ref('')
const forecastMarket = ref('')
const HORIZON_OPTIONS = [1, 3, 5, 10]
const initialHorizon = (() => {
  const q = Number(route.query.horizon)
  return HORIZON_OPTIONS.includes(q) ? q : 1
})()
const forecastHorizon = ref(initialHorizon)
const forecastHorizonLabel = computed(() => {
  const term = forecastHorizon.value <= 3 ? '短期' : '长期'
  return `${forecastHorizon.value} 天（${term}预测）`
})
const cryptoForecast = ref(null)
const cryptoForecastLoading = ref(false)
const cryptoForecastError = ref('')
const cryptoForecastProgress = ref(null)
const customPrompt = ref('')
let cryptoForecastTimer = null

const allBinanceSourcesSelected = computed(() => binanceSourceOptions.every(item => binanceSources.value.includes(item.key)))
const activeManualSources = computed(() => activeSources.value.filter(key => manualSourceKeys.includes(key)))
const hasManualSeedSources = computed(() => activeManualSources.value.length > 0)
const pastedLines = computed(() => pastedText.value.split('\n').filter(line => line.trim()).length)
const pastedChars = computed(() => pastedText.value.length)
const hasManualSeed = computed(() => Boolean(
  manualTitle.value.trim() || manualContent.value.trim() || target.value.trim() || keywords.value.trim() || pastedLines.value
))
const manualSeedCount = computed(() => hasManualSeedSources.value && hasManualSeed.value ? 1 : 0)
const selectedSeedCount = computed(() => selectedFmpArticles.value.length + selectedBinanceArticles.value.length + manualSeedCount.value + selectedRedditStock.value.length + selectedStockTwits.value.length + selectedYfNews.value.length)
const launchProgressPercent = computed(() => Math.max(0, Math.min(100, Number(launchProgress.value?.progress || 0))))
const potentialObservedCount = computed(() => {
  const binanceObserved = selectedBinanceArticles.value.filter(article => Number(article.comments_count || 0) > 0).length
  return binanceObserved + selectedRedditStock.value.length + selectedStockTwits.value.length + pastedLines.value
})

const fmpDisplayArticles = computed(() => fmpArticles.value.map(article => enrichSourceArticle(article, 'fmp', 'news')))
const fmpTimeRangeArticles = computed(() => fmpDisplayArticles.value.filter(article => matchDateRange(article, fmpStart.value, fmpEnd.value)))
const filteredFmpArticles = computed(() => fmpTimeRangeArticles.value.filter(article => matchArticleFilters(article, {
  query: fmpQuery.value,
  category: fmpCategoryFilter.value,
  direction: fmpDirectionFilter.value
})))

const binanceDisplayArticles = computed(() => binanceArticles.value.map(article => enrichSourceArticle(article, 'binance', article.source || 'post')))
const binanceTimeRangeArticles = computed(() => binanceDisplayArticles.value.filter(article => matchDateRange(article, binanceStart.value, binanceEnd.value)))
const filteredBinanceArticles = computed(() => binanceTimeRangeArticles.value.filter(article => {
  if (binanceCommentMode.value === 'commented' && Number(article.comments_count || 0) <= 0) return false
  return matchArticleFilters(article, {
    query: binanceQuery.value,
    category: binanceCategoryFilter.value,
    direction: binanceDirectionFilter.value
  })
}))

// Phase E – enriched + filtered lists for stock sources
const redditStockDisplay = computed(() => redditStockItems.value.map(item => enrichSourceArticle(item, 'reddit_stock', 'post')))
const filteredRedditStock = computed(() => redditStockDisplay.value.filter(a => matchArticleFilters(a, {
  query: redditStockQuery.value, category: redditStockCategoryFilter.value, direction: redditStockDirectionFilter.value
})))
const stockTwitsDisplay = computed(() => stockTwitsItems.value.map(item => enrichSourceArticle({
  ...item, title: item.title || (item.body || '').slice(0, 80), content: item.body || item.content || ''
}, 'stocktwits', 'message')))
const filteredStockTwits = computed(() => stockTwitsDisplay.value.filter(a => matchArticleFilters(a, {
  query: stockTwitsQuery.value, category: stockTwitsCategoryFilter.value, direction: stockTwitsDirectionFilter.value
})))
const yfNewsDisplay = computed(() => yfNewsItems.value.map(item => enrichSourceArticle({
  ...item, content: item.content || item.summary || ''
}, 'yf_news', 'news')))
const filteredYfNews = computed(() => yfNewsDisplay.value.filter(a => matchArticleFilters(a, {
  query: yfNewsQuery.value, category: yfNewsCategoryFilter.value, direction: yfNewsDirectionFilter.value
})))

const pagedRedditStock = computed(() => filteredRedditStock.value.slice(redditStockPage.value * redditStockPageSize.value, (redditStockPage.value + 1) * redditStockPageSize.value))
const pagedStockTwits = computed(() => filteredStockTwits.value.slice(stockTwitsPage.value * stockTwitsPageSize.value, (stockTwitsPage.value + 1) * stockTwitsPageSize.value))
const pagedYfNews = computed(() => filteredYfNews.value.slice(yfNewsPage.value * yfNewsPageSize.value, (yfNewsPage.value + 1) * yfNewsPageSize.value))

function listFromMaybeRef (target) {
  if (Array.isArray(target)) return target
  if (Array.isArray(target?.value)) return target.value
  return []
}

function replaceListSelection (target, items) {
  if (Array.isArray(target)) {
    target.splice(0, target.length, ...items)
  } else if (target && Array.isArray(target.value)) {
    target.value = items
  }
}

function selectAllInto (list, target) {
  const incoming = listFromMaybeRef(list)
  const current = listFromMaybeRef(target)
  const map = new Map(current.map(it => [getArticleKey(it), it]))
  for (const item of incoming) map.set(getArticleKey(item), item)
  replaceListSelection(target, Array.from(map.values()))
}

function clearListSelection (target) {
  replaceListSelection(target, [])
}

const canRun = computed(() => selectedDims.value.length > 0 && selectedSeedCount.value > 0 && !analysisLoading.value)
const canPreviewCrypto = computed(() => forecastAssetType.value === 'crypto' && !cryptoForecastLoading.value)
const cryptoForecastDirectionClass = computed(() => {
  const d = String(cryptoForecast.value?.direction || 'neutral').toLowerCase()
  if (['bullish', 'up'].includes(d)) return 'dir-up'
  if (['bearish', 'down'].includes(d)) return 'dir-down'
  return 'dir-neutral'
})
const cryptoForecastDirectionLabel = computed(() => directionDisplayLabel(cryptoForecast.value?.direction))
const cryptoForecastProbability = computed(() => formatProbability(cryptoForecast.value?.probability))
const cryptoForecastProgressPercent = computed(() => Math.max(0, Math.min(100, Number(cryptoForecastProgress.value?.progress || 0))))
const BINANCE_COMMENT_CONCURRENCY = 5

function setLaunchProgress (progress, message, detail = '', extra = {}) {
  const previous = launchProgress.value || {}
  launchProgress.value = {
    progress: Math.max(0, Math.min(100, Math.round(progress))),
    message,
    detail,
    fmpArticleTotal: extra.fmpArticleTotal ?? previous.fmpArticleTotal ?? 0,
    binanceSeedTotal: extra.binanceSeedTotal ?? previous.binanceSeedTotal ?? 0,
    selectedArticleTotal: extra.selectedArticleTotal ?? previous.selectedArticleTotal ?? 0,
    observedCommentTotal: extra.observedCommentTotal ?? previous.observedCommentTotal ?? 0,
    commentDone: extra.commentDone ?? previous.commentDone ?? 0,
    commentTotal: extra.commentTotal ?? previous.commentTotal ?? 0,
    commentFailed: extra.commentFailed ?? previous.commentFailed ?? 0
  }
}

function setCryptoForecastProgress (progress, message, detail = '', extra = {}) {
  const previous = cryptoForecastProgress.value || {}
  cryptoForecastProgress.value = {
    ...previous,
    ...extra,
    progress: Math.max(0, Math.min(100, Math.round(progress))),
    message,
    detail
  }
}

function stopCryptoForecastProgressTimer () {
  if (cryptoForecastTimer) {
    clearInterval(cryptoForecastTimer)
    cryptoForecastTimer = null
  }
}

function startCryptoForecastWaitProgress () {
  stopCryptoForecastProgressTimer()
  cryptoForecastTimer = setInterval(() => {
    if (!cryptoForecastLoading.value || !cryptoForecastProgress.value) return
    const current = cryptoForecastProgress.value.progress || 0
    const next = Math.min(85, current + (current < 55 ? 5 : current < 75 ? 2 : 1))
    setCryptoForecastProgress(next, '正在调用行情与预测接口...', 'Binance 行情、资金面与舆情模型为同步接口，返回前会停在 85%')
  }, 1600)
}

function isSourceActive (key) {
  return activeSources.value.includes(key)
}

function toggleSource (key) {
  const index = activeSources.value.indexOf(key)
  if (index >= 0) activeSources.value.splice(index, 1)
  else activeSources.value.push(key)
}

function sourceSelectionCount (key) {
  if (key === 'fmp') return selectedFmpArticles.value.length
  if (key === 'binance') return selectedBinanceArticles.value.length
  if (key === 'paste') return pastedLines.value
  if (key === 'reddit_stock') return selectedRedditStock.value.length
  if (key === 'stocktwits') return selectedStockTwits.value.length
  if (key === 'yf_news') return selectedYfNews.value.length
  if (manualSourceKeys.includes(key)) return isSourceActive(key) && hasManualSeed.value ? 1 : 0
  return 0
}

function sourceHasObserved (key) {
  if (key === 'paste') return pastedLines.value > 0
  if (key === 'binance') return selectedBinanceArticles.value.some(article => Number(article.comments_count || 0) > 0)
  if (key === 'reddit_stock') return selectedRedditStock.value.length > 0
  if (key === 'stocktwits') return selectedStockTwits.value.length > 0
  return false
}

function getSourceLabel (key) {
  return allSources.find(item => item.key === key)?.name || key
}

function stripHtml (html) {
  if (!html) return ''
  const tmp = document.createElement('div')
  tmp.innerHTML = html
  return (tmp.textContent || tmp.innerText || '').replace(/\s+/g, ' ').trim()
}

function normalizeTickerText (value) {
  if (Array.isArray(value)) return value.filter(Boolean).join(', ')
  return value ? String(value) : ''
}

function enrichSourceArticle (article, sourceType, contentType) {
  const normalized = {
    ...article,
    content: article.content || article.text || article.summary || '',
    summary: article.summary || article.text || article.content || '',
    tickers: normalizeTickerText(article.tickers || article.symbols || article.symbol || article.ticker)
  }
  const classification = normalized.classification || classifySignalSeed(normalized)
  return {
    ...normalized,
    classification,
    source_type: sourceType,
    content_type: contentType,
    signal_id: classification.id,
    signal_name: classification.name,
    signal_category: classification.category,
    signal_category_label: classification.categoryLabel,
    direction_hint: classification.direction,
    direction_label: classification.directionLabel,
    product_domains: classification.productDomains || [],
    has_observed_comments: sourceType === 'binance'
      ? Number(article.comments_count || 0) > 0
      : ['reddit_stock', 'stocktwits'].includes(sourceType)
  }
}

function matchArticleFilters (article, { query, category, direction }) {
  const normalizedQuery = query.trim().toLowerCase()
  if (normalizedQuery) {
    const blob = [
      article.title,
      article.content && stripHtml(article.content),
      article.tickers,
      article.author,
      article.site,
      article.source,
      article.classification?.name,
      article.classification?.productDomains?.join(' ')
    ].filter(Boolean).join(' ').toLowerCase()
    if (!blob.includes(normalizedQuery)) return false
  }
  if (category !== 'all' && article.classification?.category !== category) return false
  if (direction !== 'all' && article.classification?.direction !== direction) return false
  return true
}

function matchDateRange (article, startValue, endValue) {
  const start = parseInputDate(startValue)
  const end = parseInputDate(endValue)
  if (!start && !end) return true
  const date = getArticleDate(article)
  if (!date) return false
  if (start && date < start) return false
  if (end && date > end) return false
  return true
}

function getArticleDate (article) {
  const raw = article.publish_time || article.published_at || article.publishedDate || article.date || article.created_at
  if (!raw) return null
  if (typeof raw === 'number') return new Date(raw > 1e12 ? raw : raw * 1000)
  if (/^\d+$/.test(String(raw))) {
    const num = Number(raw)
    return new Date(num > 1e12 ? num : num * 1000)
  }
  const date = new Date(raw)
  return Number.isNaN(date.getTime()) ? null : date
}

function formatArticleDate (article) {
  const date = getArticleDate(article)
  if (!date) return article.date || article.publishedDate || '-'
  return date.toLocaleString('zh-HK', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

function parseInputDate (value) {
  if (!value) return null
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? null : date
}

function toDateInputValue (date) {
  const pad = value => String(value).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

function applyQuickWindow (kind, key) {
  const selected = quickWindows.find(item => item.key === key)
  if (!selected) return
  const end = new Date()
  const start = new Date(end.getTime() - selected.hours * 60 * 60 * 1000)
  if (kind === 'fmp') {
    fmpStart.value = toDateInputValue(start)
    fmpEnd.value = ''
  } else {
    binanceStart.value = toDateInputValue(start)
    binanceEnd.value = ''
    reloadBinance()
  }
}

function getArticleKey (article) {
  return article?.source_article_id || article?.post_id || article?.uuid || article?.id || article?.link || article?.url || `${article?.source_type || ''}|${article?.title || ''}|${article?.date || article?.publishedDate || article?.published_at || article?.publish_time || ''}`
}

function mergeArticles (current, incoming, prepend = false) {
  const ordered = prepend ? [...incoming, ...current] : [...current, ...incoming]
  const seen = new Set()
  return ordered.filter(article => {
    const key = getArticleKey(article)
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
}

async function loadFmp ({ append = false, silent = false } = {}) {
  if (!silent) fmpLoading.value = true
  fmpError.value = ''
  try {
    const cat = fmpSourceCategory.value
    const page = append ? 0 : fmpPage.value
    let items = []

    if (cat === 'articles') {
      const resp = await fetchArticles(page, fmpLimit.value)
      if (resp?.success === false) throw new Error(resp.error || 'FMP 新闻加载失败')
      items = resp.data?.items || []
    } else if (cat === 'general') {
      items = await fmpNews.general({ page, limit: fmpLimit.value })
    } else if (cat === 'stock-latest') {
      const symbols = (fmpStockSymbols.value || '').trim().toUpperCase()
      items = symbols
        ? await fmpNews.stock({ symbols, page, limit: fmpLimit.value })
        : await fmpNews.stockLatest({ page, limit: fmpLimit.value })
    } else if (cat === 'crypto-latest') {
      items = await fmpNews.cryptoLatest({ page, limit: fmpLimit.value })
    } else if (cat === 'forex-latest') {
      items = await fmpNews.forexLatest({ page, limit: fmpLimit.value })
    } else if (cat === 'press-latest') {
      items = await fmpNews.pressReleasesLatest({ page, limit: fmpLimit.value })
    } else if (cat === 'search') {
      const q = (fmpSearchQuery.value || '').trim()
      if (!q) { items = [] }
      else items = await fmpNews.search({ q, page, limit: fmpLimit.value })
    } else if (cat === 'social') {
      // social handled separately
      items = fmpArticles.value
    }

    fmpArticles.value = append ? mergeArticles(fmpArticles.value, items, true) : items
    fmpLoadedOnce = true
  } catch (error) {
    fmpError.value = error?.message || 'FMP 新闻加载失败'
    if (!append) fmpArticles.value = []
  } finally {
    fmpLoading.value = false
  }
}

async function loadFmpSocial () {
  fmpSocialLoading.value = true
  fmpSocialError.value = ''
  try {
    let items = []
    if (fmpSocialMode.value === 'trending') {
      items = await fmpNews.socialTrending({ type: fmpSocialType.value, source: fmpSocialSource.value })
    } else if (fmpSocialMode.value === 'changes') {
      items = await fmpNews.socialChanges({ type: fmpSocialType.value, source: fmpSocialSource.value })
    } else if (fmpSocialMode.value === 'historical') {
      const symbol = (fmpSocialSymbol.value || '').trim().toUpperCase()
      if (!symbol) { fmpSocialError.value = 'symbol required'; return }
      items = await fmpNews.socialHistorical({ symbol, page: 0 })
    }
    fmpSocialData.value = items
  } catch (error) {
    fmpSocialError.value = error?.message || 'social sentiment load failed'
    fmpSocialData.value = []
  } finally {
    fmpSocialLoading.value = false
  }
}

function selectFmpCategory (key) {
  if (fmpSourceCategory.value === key) return
  fmpSourceCategory.value = key
  fmpPage.value = 0
  fmpArticles.value = []
  if (key === 'social') {
    loadFmpSocial()
  } else if (key === 'search') {
    // wait for user query
  } else {
    loadFmp()
  }
}

function reloadFmp () {
  fmpPage.value = 0
  loadFmp()
}

function changeFmpPage (page) {
  if (page < 0) return
  fmpPage.value = page
  loadFmp()
}

function isFmpSelected (article) {
  const key = getArticleKey(article)
  return selectedFmpArticles.value.some(item => getArticleKey(item) === key)
}

function toggleFmp (article) {
  const key = getArticleKey(article)
  const index = selectedFmpArticles.value.findIndex(item => getArticleKey(item) === key)
  if (index >= 0) selectedFmpArticles.value.splice(index, 1)
  else selectedFmpArticles.value.push(article)
}

function selectAllFmp (articles) {
  selectedFmpArticles.value = mergeArticles(selectedFmpArticles.value, articles)
}

function clearFmpSelection () {
  selectedFmpArticles.value = []
}

async function loadBinance ({ append = false, silent = false } = {}) {
  if (!binanceSources.value.length) {
    binanceError.value = '请至少选择一个 Binance 内容类型。'
    binanceWarning.value = ''
    binanceArticles.value = []
    return
  }
  if (!silent) binanceLoading.value = true
  binanceError.value = ''
  binanceWarning.value = ''
  try {
    const minComments = binanceCommentMode.value === 'commented'
      ? Math.max(1, Number(binanceMinComments.value || 0))
      : Number(binanceMinComments.value || 0)
    const resp = await fetchBinanceArticlesBySources({
      page: append ? 0 : binancePage.value,
      limit: binanceLimit.value,
      sources: binanceSources.value,
      since: getUnixSeconds(binanceStart.value),
      q: binanceQuery.value.trim() || undefined,
      min_comments: minComments || undefined
    })
    const items = resp.data?.items || []
    binanceWarning.value = resp.data?.warning || ''
    binanceArticles.value = append ? mergeArticles(binanceArticles.value, items, true) : items
    binanceLoadedOnce = true
  } catch (error) {
    binanceError.value = error?.message || 'Binance 数据源加载失败'
    binanceWarning.value = ''
    if (!append) binanceArticles.value = []
  } finally {
    binanceLoading.value = false
  }
}

function getUnixSeconds (inputValue) {
  const date = parseInputDate(inputValue)
  return date ? Math.floor(date.getTime() / 1000) : undefined
}

function reloadBinance () {
  binancePage.value = 0
  loadBinance()
}

function changeBinancePage (page) {
  if (page < 0) return
  binancePage.value = page
  loadBinance()
}

function toggleBinanceSource (key) {
  const index = binanceSources.value.indexOf(key)
  if (index >= 0) binanceSources.value.splice(index, 1)
  else binanceSources.value.push(key)
  reloadBinance()
}

function toggleAllBinanceSources () {
  binanceSources.value = allBinanceSourcesSelected.value ? [] : binanceSourceOptions.map(item => item.key)
  reloadBinance()
}

// ── Phase E: stock-mode source loaders ──
function _stockTargetSymbol () {
  return (forecastSymbol.value || '').trim().toUpperCase()
}

async function loadRedditStock () {
  const sym = (redditStockSymbol.value || _stockTargetSymbol()).trim().toUpperCase()
  if (sym && !redditStockSymbol.value) redditStockSymbol.value = sym
  redditStockLoading.value = true
  redditStockError.value = ''
  try {
    const items = await redditNews.posts({ symbol: sym || undefined, limit_per_sub: 25 })
    redditStockItems.value = Array.isArray(items) ? items : []
    redditStockPage.value = 0
  } catch (err) {
    redditStockError.value = err?.message || 'Reddit 抓取失败'
    redditStockItems.value = []
  } finally {
    redditStockLoading.value = false
  }
}

async function loadStockTwits () {
  const sym = (stockTwitsSymbol.value || _stockTargetSymbol()).trim().toUpperCase()
  if (sym && !stockTwitsSymbol.value) stockTwitsSymbol.value = sym
  stockTwitsLoading.value = true
  stockTwitsError.value = ''
  try {
    const items = await stockTwits.stream({ symbol: sym || undefined, limit: 30 })
    stockTwitsItems.value = Array.isArray(items) ? items : []
    stockTwitsPage.value = 0
  } catch (err) {
    stockTwitsError.value = err?.message || 'StockTwits 抓取失败'
    stockTwitsItems.value = []
  } finally {
    stockTwitsLoading.value = false
  }
}

async function loadYfNews () {
  const sym = (yfNewsSymbol.value || _stockTargetSymbol()).trim().toUpperCase()
  if (sym && !yfNewsSymbol.value) yfNewsSymbol.value = sym
  yfNewsLoading.value = true
  yfNewsError.value = ''
  try {
    const items = await yfinanceNews.news({ symbol: sym || undefined, limit: 50 })
    yfNewsItems.value = Array.isArray(items) ? items : []
    yfNewsPage.value = 0
  } catch (err) {
    yfNewsError.value = err?.message || 'Yahoo Finance 抓取失败'
    yfNewsItems.value = []
  } finally {
    yfNewsLoading.value = false
  }
}

function toggleSelectInList (item, list) {
  const target = listFromMaybeRef(list)
  const key = getArticleKey(item)
  const idx = target.findIndex(x => getArticleKey(x) === key)
  if (idx >= 0) target.splice(idx, 1)
  else target.push(item)
}
function isItemSelected (item, list) {
  const target = listFromMaybeRef(list)
  return target.some(x => getArticleKey(x) === getArticleKey(item))
}

function isBinanceSelected (article) {
  return selectedBinanceArticles.value.some(item => getArticleKey(item) === getArticleKey(article))
}

function toggleBinance (article) {
  const key = getArticleKey(article)
  const index = selectedBinanceArticles.value.findIndex(item => getArticleKey(item) === key)
  if (index >= 0) selectedBinanceArticles.value.splice(index, 1)
  else selectedBinanceArticles.value.push(article)
}

function selectAllBinance (articles) {
  selectedBinanceArticles.value = mergeArticles(selectedBinanceArticles.value, articles)
}

function clearBinanceSelection () {
  selectedBinanceArticles.value = []
}

async function runAnalysis () {
  analysisLoading.value = true
  analysisError.value = ''
  reactionRun.value = null
  launchProgress.value = null
  try {
    setLaunchProgress(8, '正在整理现实种子...', '检查已选 FMP 新闻、Binance 评论与手动种子', {
      fmpArticleTotal: selectedFmpArticles.value.length,
      binanceSeedTotal: selectedBinanceArticles.value.length,
      selectedArticleTotal: selectedSeedCount.value
    })
    const payload = await buildPayload()
    const articles = buildEngineArticles(payload)
    if (!articles.length) throw new Error('缺少可提交到分析引擎的现实种子')
    const selectedArticles = payload.selected_articles || []
    const fmpArticleCount = selectedArticles.filter(article => article.source_type === 'fmp').length
    const binanceSeedCount = selectedArticles.filter(article => article.source_type === 'binance').length
    const redditSeedCount = selectedArticles.filter(article => article.source_type === 'reddit_stock').length
    const stockTwitsSeedCount = selectedArticles.filter(article => article.source_type === 'stocktwits').length
    const yfNewsSeedCount = selectedArticles.filter(article => article.source_type === 'yfinance').length
    setLaunchProgress(
      48,
      '现实种子整理完成',
      `FMP ${fmpArticleCount} · Binance ${binanceSeedCount} · Reddit ${redditSeedCount} · StockTwits ${stockTwitsSeedCount} · Yahoo ${yfNewsSeedCount} · 评论 ${payload.comments.length} 条`,
      {
        fmpArticleTotal: fmpArticleCount,
        binanceSeedTotal: binanceSeedCount,
        selectedArticleTotal: selectedArticles.length,
        observedCommentTotal: payload.comments.length
      }
    )
    setLaunchProgress(62, '正在运行 Reaction 分析...', '生成舆情来源、推断扩展和推演信号')
    const reaction = await runReactionAnalysis(payload)
    setLaunchProgress(78, '正在拼接预测提示词...', `reaction_run_id: ${reaction.run_id}`)
    const requirement = await buildLinkedEngineRequirement(payload, reaction)
    setLaunchProgress(90, '正在准备进入 Process...', '写入待处理种子和引擎提示词')
    const { setPendingArticles } = await import('@/context/pendingUpload')
    const normalizedForecastSymbol = forecastSymbol.value.trim() || (forecastAssetType.value === 'crypto' ? 'BTC' : '')
    const targetAsset = normalizedForecastSymbol || forecastAssetType.value !== 'event'
      ? {
          symbol: normalizedForecastSymbol,
          type: forecastAssetType.value || 'event',
          market: forecastMarket.value.trim(),
          horizon_days: forecastHorizon.value
        }
      : null
    setPendingArticles(articles, requirement, targetAsset, {
      selected_articles: payload.selected_articles || [],
      comments: payload.comments || [],
      metadata: payload.metadata || {}
    })
    setLaunchProgress(100, '启动完成，正在跳转 Process...', '后续本体生成与图谱构建会在 Process 页展示')
    await router.push({
      name: 'Process',
      params: { projectId: 'new' },
      query: { workflow: 'reaction', source: payload.source, reaction_run_id: reaction.run_id }
    })
  } catch (error) {
    const message = error?.message || '启动模拟预测引擎失败'
    analysisError.value = message
    setLaunchProgress(launchProgressPercent.value || 0, '启动失败', message)
  } finally {
    analysisLoading.value = false
  }
}

async function runReactionAnalysis (payload) {
  const response = await analyzeReaction(payload)
  const run = response?.data
  if (!run?.run_id) throw new Error('Reaction analysis did not return a run_id')
  reactionRun.value = run
  payload.reaction_run_id = run.run_id
  return run
}

async function previewCryptoForecast () {
  cryptoForecastLoading.value = true
  cryptoForecastError.value = ''
  cryptoForecast.value = null
  cryptoForecastProgress.value = null
  stopCryptoForecastProgressTimer()
  try {
    setCryptoForecastProgress(8, '正在整理预测输入...', '读取标的、已选 FMP / Binance / 手动种子')
    const symbol = forecastSymbol.value.trim() || 'BTC'
    let comments = []
    let articles = []
    if (selectedSeedCount.value > 0) {
      const payload = await buildPayload({
        silentProgress: true,
        progressTarget: 'crypto'
      })
      comments = payload.comments || []
      articles = payload.selected_articles || []
      setCryptoForecastProgress(36, '现实种子整理完成', `FMP 新闻 ${articles.filter(article => article.source_type === 'fmp').length} 条 · 评论 ${comments.length} 条`, {
        fmpArticleTotal: articles.filter(article => article.source_type === 'fmp').length,
        observedCommentTotal: comments.length
      })
    } else {
      setCryptoForecastProgress(28, '未选择现实种子', '将只使用实盘行情与可用新闻预测')
    }
    setCryptoForecastProgress(42, '正在提交预测请求...', `${symbol.toUpperCase()} · ${forecastHorizon.value}d`)
    startCryptoForecastWaitProgress()
    const response = await postCryptoForecast({
      symbol,
      horizon: String(forecastHorizon.value),
      comments,
      articles
    })
    stopCryptoForecastProgressTimer()
    setCryptoForecastProgress(92, '预测接口已返回...', '正在渲染方向、概率和因子分解')
    cryptoForecast.value = response?.data || null
    if (!cryptoForecast.value) throw new Error('预测接口没有返回结果')
    setCryptoForecastProgress(100, '预测完成', `${cryptoForecast.value.symbol || symbol} · ${directionDisplayLabel(cryptoForecast.value.direction)} · ${formatProbability(cryptoForecast.value.probability)}`)
  } catch (error) {
    stopCryptoForecastProgressTimer()
    cryptoForecastError.value = error?.message || '价格预测失败'
    setCryptoForecastProgress(cryptoForecastProgressPercent.value || 0, '预测失败', cryptoForecastError.value)
  } finally {
    cryptoForecastLoading.value = false
  }
}

async function buildPayload (options = {}) {
  const selectedArticles = []
  const comments = []

  selectedArticles.push(...selectedFmpArticles.value.map(article => toSelectedArticle(article, 'fmp', 'news', false)))

  const binanceCommentMap = await fetchSelectedBinanceComments(selectedBinanceArticles.value, options)
  for (const article of selectedBinanceArticles.value) {
    const postId = String(article.id || getArticleKey(article))
    const items = binanceCommentMap.get(postId) || []
    comments.push(...items.map(item => ({ ...item, source: 'binance', post_id: postId })))
    selectedArticles.push(toSelectedArticle(article, 'binance', article.source || 'post', items.length > 0, postId))
  }

  if (hasManualSeedSources.value && hasManualSeed.value) {
    const pastePostId = 'paste-comments'
    const pasted = pastedText.value.split('\n').map(line => line.trim()).filter(Boolean)
    comments.push(...pasted.map((text, index) => ({ text, source: 'paste', post_id: pastePostId, index })))
    selectedArticles.push(buildManualSelectedArticle(pasted.length > 0, pastePostId))
  }

  // ── Phase E: stock-mode dedicated sources into selected_articles ──
  for (const item of selectedRedditStock.value) {
    const postId = String(item.post_id || item.id || item.url || getArticleKey(item))
    const content = item.content || item.selftext || item.text || item.summary || item.title || ''
    const observed = buildObservedCommentFromSeed(item, 'reddit', postId)
    if (observed) comments.push(observed)
    selectedArticles.push(toSelectedArticle({
      title: item.title || '',
      content,
      url: item.url || '',
      source: 'reddit',
      site: `r/${item.subreddit || ''}`,
      author: item.author || '',
      published_at: item.created_iso || item.published_at || item.created_at || ''
    }, 'reddit_stock', 'post', Boolean(observed), postId))
  }
  for (const item of selectedStockTwits.value) {
    const postId = String(item.post_id || item.id || item.url || getArticleKey(item))
    const content = item.content || item.text || item.body || item.title || ''
    const observed = buildObservedCommentFromSeed(item, 'stocktwits', postId)
    if (observed) comments.push(observed)
    selectedArticles.push(toSelectedArticle({
      title: item.title || content.slice(0, 80),
      content,
      url: item.url || '',
      source: 'stocktwits',
      site: 'stocktwits',
      author: item.author || item.user || '',
      published_at: item.published_at || item.created_at || '',
      prior_sentiment: item.prior_sentiment || null
    }, 'stocktwits', 'message', Boolean(observed), postId))
  }
  for (const item of selectedYfNews.value) {
    selectedArticles.push(toSelectedArticle({
      title: item.title || '',
      content: item.content || item.summary || item.description || item.text || '',
      url: item.url || item.link || '',
      source: 'yfinance',
      site: item.publisher || item.site || item.source || 'yfinance',
      author: item.publisher || item.site || '',
      published_at: item.published_at || item.date || ''
    }, 'yfinance', 'news', false, String(item.id || item.uuid || item.url || getArticleKey(item))))
  }

  const first = selectedArticles[0] || {}
  const metadata = buildRunMetadata(selectedArticles)
  const title = manualTitle.value.trim() || first.title || 'Multi-source market reaction forecast'
  const content = selectedArticles.map(article => [
    `SOURCE=${article.source_type}/${article.content_type}`,
    `SIGNAL=${article.signal_id} ${article.signal_name}`,
    `DIRECTION=${article.direction_hint}`,
    article.title,
    stripHtml(article.content || '')
  ].filter(Boolean).join('\n')).join('\n\n---\n\n')

  return {
    source: 'multi',
    event: {
      title,
      content,
      source: 'multi',
      url: first.link || first.url || '',
      author: first.author || '',
      published_at: first.date || first.publishedDate || first.published_at || '',
      metadata
    },
    metadata,
    selected_articles: selectedArticles,
    comments,
    dimensions: selectedDims.value,
    custom_prompt: customPrompt.value
  }
}

function buildObservedCommentFromSeed (item, source, postId) {
  const text = stripHtml(item.content || item.text || item.body || item.summary || item.title || '')
  if (!text) return null
  return {
    text,
    source,
    post_id: postId,
    author: item.author || item.user || '',
    published_at: item.published_at || item.created_at || item.created_iso || item.date || '',
    like_count: Number(item.like_count || item.likes || item.score || 0),
    reply_count: Number(item.reply_count || item.num_comments || 0),
    prior_sentiment: item.prior_sentiment || null
  }
}

async function fetchSelectedBinanceComments (articles, options = {}) {
  const silentProgress = Boolean(options.silentProgress)
  const isCryptoProgress = options.progressTarget === 'crypto'
  const commentsByPost = new Map()
  const candidates = articles
    .map(article => ({
      article,
      postId: String(article.id || getArticleKey(article))
    }))
    .filter(item => item.article.id && Number(item.article.comments_count || 0) > 0)

  if (!articles.length) return commentsByPost
  if (!candidates.length) {
    if (!silentProgress) {
      setLaunchProgress(
        22,
        'FMP 新闻已纳入，暂无 Binance 评论可拉取',
        `FMP 新闻 ${selectedFmpArticles.value.length} 条；已选 Binance 种子没有评论候选`,
        {
          fmpArticleTotal: selectedFmpArticles.value.length,
          binanceSeedTotal: articles.length,
          selectedArticleTotal: selectedFmpArticles.value.length + articles.length + manualSeedCount.value
        }
      )
    }
    if (isCryptoProgress) {
      setCryptoForecastProgress(22, 'FMP 新闻已纳入，暂无 Binance 评论可拉取', `FMP 新闻 ${selectedFmpArticles.value.length} 条；已选 Binance 种子没有评论候选`, {
        fmpArticleTotal: selectedFmpArticles.value.length
      })
    }
    return commentsByPost
  }

  let nextIndex = 0
  let completed = 0
  let failed = 0
  const total = candidates.length
  if (!silentProgress) {
    setLaunchProgress(20, '正在整理 FMP 新闻并拉取 Binance 评论', `FMP 新闻 ${selectedFmpArticles.value.length} 条已纳入；Binance 评论：0/${total}`, {
      fmpArticleTotal: selectedFmpArticles.value.length,
      binanceSeedTotal: articles.length,
      selectedArticleTotal: selectedFmpArticles.value.length + articles.length + manualSeedCount.value,
      commentDone: 0,
      commentTotal: total,
      commentFailed: 0
    })
  }
  if (isCryptoProgress) {
    setCryptoForecastProgress(18, '正在整理 FMP 新闻并拉取 Binance 评论...', `FMP 新闻 ${selectedFmpArticles.value.length} 条已纳入；Binance 评论：0/${total}`, {
      fmpArticleTotal: selectedFmpArticles.value.length,
      commentDone: 0,
      commentTotal: total,
      commentFailed: 0
    })
  }

  async function worker () {
    while (nextIndex < total) {
      const current = candidates[nextIndex]
      nextIndex += 1
      let items = []
      try {
        const response = await fetchBinanceArticleComments(current.article.id, { limit: 200 })
        items = response.data?.items || []
      } catch (error) {
        failed += 1
      }
      commentsByPost.set(current.postId, items)
      completed += 1
      if (!silentProgress) {
        setLaunchProgress(20 + Math.round((completed / total) * 22), '正在整理 FMP 新闻并拉取 Binance 评论', `FMP 新闻 ${selectedFmpArticles.value.length} 条已纳入；Binance 评论：${completed}/${total}`, {
          fmpArticleTotal: selectedFmpArticles.value.length,
          binanceSeedTotal: articles.length,
          selectedArticleTotal: selectedFmpArticles.value.length + articles.length + manualSeedCount.value,
          commentDone: completed,
          commentTotal: total,
          commentFailed: failed
        })
      }
      if (isCryptoProgress) {
        setCryptoForecastProgress(18 + Math.round((completed / total) * 16), '正在整理 FMP 新闻并拉取 Binance 评论...', `FMP 新闻 ${selectedFmpArticles.value.length} 条已纳入；Binance 评论：${completed}/${total}`, {
          fmpArticleTotal: selectedFmpArticles.value.length,
          commentDone: completed,
          commentTotal: total,
          commentFailed: failed
        })
      }
    }
  }

  const workerCount = Math.min(BINANCE_COMMENT_CONCURRENCY, total)
  await Promise.all(Array.from({ length: workerCount }, () => worker()))
  return commentsByPost
}

function toSelectedArticle (article, sourceType, contentType, hasObservedComments, sourceArticleId = null) {
  const enriched = enrichSourceArticle(article, sourceType, contentType)
  return {
    ...enriched,
    id: sourceArticleId || getArticleKey(enriched),
    source_article_id: sourceArticleId || getArticleKey(enriched),
    has_observed_comments: hasObservedComments,
    source_type: sourceType,
    content_type: contentType,
    metadata: {
      classification_confidence: enriched.classification?.confidence,
      matched_keywords: enriched.classification?.matched_keywords || []
    }
  }
}

function buildManualSelectedArticle (hasObservedComments, sourceArticleId) {
  const activeLabels = activeManualSources.value.map(getSourceLabel).join(' / ')
  const title = manualTitle.value.trim() || target.value.trim() || 'Manual market forecast seed'
  const content = [
    manualContent.value.trim(),
    target.value.trim() && `target=${target.value.trim()}`,
    keywords.value.trim() && `keywords=${keywords.value.trim()}`,
    `window=${timeWindow.value}; requested_sample=${limit.value}`,
    activeLabels && `active_manual_sources=${activeLabels}`
  ].filter(Boolean).join('\n')
  const base = { title, content, source: 'manual', site: activeLabels }
  return toSelectedArticle(base, 'manual', activeManualSources.value.join('+') || 'manual', hasObservedComments, sourceArticleId)
}

function buildRunMetadata (selectedArticles) {
  const selectedCounts = {
    fmp: selectedFmpArticles.value.length,
    binance: selectedBinanceArticles.value.length,
    reddit_stock: selectedRedditStock.value.length,
    stocktwits: selectedStockTwits.value.length,
    yfinance: selectedYfNews.value.length,
    manual: manualSeedCount.value,
    observed_comments: potentialObservedCount.value
  }
  return {
    source_filters: {
      active_sources: [...activeSources.value],
      fmp: {
        query: fmpQuery.value,
        stock_symbols: fmpStockSymbols.value,
        source_category: fmpSourceCategory.value,
        category: fmpCategoryFilter.value,
        direction: fmpDirectionFilter.value,
        page: fmpPage.value,
        limit: fmpLimit.value,
        start: fmpStart.value,
        end: fmpEnd.value
      },
      binance: {
        sources: [...binanceSources.value],
        query: binanceQuery.value,
        category: binanceCategoryFilter.value,
        direction: binanceDirectionFilter.value,
        comment_mode: binanceCommentMode.value,
        min_comments: binanceMinComments.value,
        page: binancePage.value,
        limit: binanceLimit.value,
        start: binanceStart.value,
        end: binanceEnd.value
      },
      manual: {
        active_manual_sources: [...activeManualSources.value],
        target: target.value,
        keywords: keywords.value,
        time_window: timeWindow.value
      },
      reddit_stock: {
        symbol: redditStockSymbol.value,
        query: redditStockQuery.value,
        category: redditStockCategoryFilter.value,
        direction: redditStockDirectionFilter.value,
        page: redditStockPage.value,
        page_size: redditStockPageSize.value
      },
      stocktwits: {
        symbol: stockTwitsSymbol.value,
        query: stockTwitsQuery.value,
        category: stockTwitsCategoryFilter.value,
        direction: stockTwitsDirectionFilter.value,
        page: stockTwitsPage.value,
        page_size: stockTwitsPageSize.value
      },
      yfinance: {
        symbol: yfNewsSymbol.value,
        query: yfNewsQuery.value,
        category: yfNewsCategoryFilter.value,
        direction: yfNewsDirectionFilter.value,
        page: yfNewsPage.value,
        page_size: yfNewsPageSize.value
      }
    },
    classification_summary: buildClassificationSummary(selectedArticles),
    time_range: {
      fmp_start: fmpStart.value,
      fmp_end: fmpEnd.value,
      binance_start: binanceStart.value,
      binance_end: binanceEnd.value,
      manual_window: timeWindow.value
    },
    selected_counts: selectedCounts,
    custom_prompt: customPrompt.value
  }
}

function buildEngineArticles (payload) {
  const commentsByPost = new Map()
  ;(payload.comments || []).forEach(comment => {
    const postId = String(comment.post_id || '')
    if (!commentsByPost.has(postId)) commentsByPost.set(postId, [])
    commentsByPost.get(postId).push(comment)
  })

  return (payload.selected_articles || []).map((article, index) => {
    const postComments = commentsByPost.get(String(article.source_article_id || article.id || '')) || []
    const observedBlock = postComments.length
      ? postComments.map((comment, commentIndex) => `[${commentIndex + 1}] ${getCommentText(comment)}`).filter(Boolean).join('\n')
      : 'No real comment text was available for this seed; downstream simulation must treat reactions as Simulated, not Observed.'
    return normalizeEngineArticle({
      ...article,
      title: article.title || `Market seed ${index + 1}`,
      content: [
        `=== Source metadata ===`,
        `source_type: ${article.source_type}`,
        `content_type: ${article.content_type}`,
        `signal: ${article.signal_id} ${article.signal_name}`,
        `signal_category: ${article.signal_category_label}`,
        `direction_hint: ${article.direction_label}`,
        `product_domains: ${(article.product_domains || []).join(', ')}`,
        '',
        '=== Simulated seed material ===',
        stripHtml(article.content || article.title || ''),
        '',
        '=== Observed comment layer ===',
        observedBlock
      ].join('\n'),
      site: article.site || getSourceLabel(article.source_type)
    }, `Market seed ${index + 1}`, article.site || getSourceLabel(article.source_type))
  })
}

function normalizeEngineArticle (article, fallbackTitle, fallbackSite) {
  return {
    title: article.title || fallbackTitle,
    content: article.content || article.summary || article.title || fallbackTitle,
    date: article.date || article.publishedDate || article.published_at || '',
    link: article.link || article.url || '',
    tickers: article.tickers || '',
    author: article.author || '',
    site: article.site || fallbackSite
  }
}

function getCommentText (comment) {
  return String(comment.text || comment.content || comment.comment || comment.body || '').replace(/\s+/g, ' ').trim()
}

function directionDisplayLabel (direction) {
  const d = String(direction || 'neutral').toLowerCase()
  return {
    bullish: '看涨',
    up: '看涨',
    bearish: '看跌',
    down: '看跌',
    neutral: '中性'
  }[d] || d
}

function formatProbability (value) {
  if (value == null || Number.isNaN(Number(value))) return '-'
  return `${(Number(value) * 100).toFixed(1)}%`
}

function formatScore (value) {
  if (value == null || Number.isNaN(Number(value))) return '-'
  const n = Number(value)
  return `${n >= 0 ? '+' : ''}${n.toFixed(2)}`
}

async function buildLinkedEngineRequirement (payload, reaction) {
  const baseRequirement = buildEngineRequirement(payload)
  let context = ''
  try {
    const response = await getReactionReportContext(reaction.run_id)
    context = response?.data?.context || ''
  } catch (error) {
    console.warn('Reaction report context fetch failed:', error?.message || error)
    context = JSON.stringify({
      run_id: reaction.run_id,
      mode: reaction.mode,
      status: reaction.status,
      fusion: reaction.fusion
    }, null, 2)
  }

  return [
    baseRequirement,
    '',
    '---',
    'Linked Reaction Analysis',
    `reaction_run_id: ${reaction.run_id}`,
    `reaction_mode: ${reaction.mode}`,
    '',
    'SOURCE-LAYER GUARDRAIL: keep Observed, Inferred, and Simulated statements explicitly separate. Never describe simulated or inferred reactions as real comments or measured public opinion.',
    '',
    context
  ].filter(Boolean).join('\n')
}

function buildEngineRequirement (payload) {
  const observedCount = (payload.comments || []).length
  const mode = observedCount > 0 ? 'observed_augmented' : 'agent_only'
  const dimText = selectedDims.value.map(key => dimensions.find(dim => dim.key === key)?.title || key).join('、')
  const metadata = payload.metadata || {}
  const classificationText = (metadata.classification_summary || [])
    .map(item => `${item.category_label}/${item.direction_label}: ${item.count} seeds (${item.signals.join(', ') || '-'})`)
    .join('；')
  const selectedCounts = metadata.selected_counts || {}

  return [
    '金融舆情模拟预测。请复用原五步分析引擎处理当前多源现实种子：Step 1 图谱/本体构建，Step 2 Agent 环境搭建，Step 3 情绪与扩散仿真，Step 4 报告生成，Step 5 深度互动。',
    '核心目标：基于用户已选的推演主题（dimensions）动态展开分析。不要默认输出 FOMO/黑天鹅/CSOP/资金流向 等固定章节，只有当对应 dimension 被勾选时才展开。',
    `输入源：multi；运行模式：${mode}；真实评论条数：${observedCount}。`,
    `已选种子：FMP ${selectedCounts.fmp || 0}；Binance ${selectedCounts.binance || 0}；Reddit ${selectedCounts.reddit_stock || 0}；StockTwits ${selectedCounts.stocktwits || 0}；Yahoo Finance ${selectedCounts.yfinance || 0}；手动/论坛 ${selectedCounts.manual || 0}。`,
    `核心事件：${payload.event?.title || '-'}`,
    `推演主题（仅围绕这些主题展开章节）：${dimText || '-'}`,
    classificationText ? `前端预分类摘要：${classificationText}` : '',
    '主题要求：报告章节必须严格基于"推演主题"列表生成，每个被勾选的主题对应一个或多个独立章节；未勾选的主题只可作为必要背景一笔带过，不得作为独立章节。',
    '附加预测章节（无论是否勾选 dimension 都必须生成）：',
    '  - "热点话题预测"：列出未来 1-2 周可能升温的话题，给出预计情绪走向、相关标的、出现频次估算。',
    '  - "热点金融产品预测"：列出未来可能受关注的金融产品/标的（含 CSOP ETF / 加密资产 / 个股 / 板块），给出关注度评分、相关话题、出现频次估算。',
    '策略要求：结合方向、紧迫程度、影响板块、资金路径和客户画像，输出代表产品、话术要点、迁移风险和风险合规红线（仅在用户勾选了 CSOP/产品 相关主题时才展开 CSOP 段落）。',
    '报告必须分层标记 Observed / Inferred / Simulated：真实评论只能进入 Observed；样本偏差和沉默人群补齐属于 Inferred；agent/OASIS 推演属于 Simulated。',
    '不得把模拟评论或推断观点写成真实舆情，不得承诺收益率；杠杆/反向和虚拟资产产品必须明确风险提示。',
    customPrompt.value.trim() ? `自定义补充：${customPrompt.value.trim()}` : ''
  ].filter(Boolean).join('\n')
}

watch(activeSources, (value) => {
  if (value.includes('fmp') && !fmpLoadedOnce) loadFmp()
  if (value.includes('binance') && !binanceLoadedOnce) loadBinance()
  if (value.includes('reddit_stock') && !redditStockItems.value.length && !redditStockLoading.value) loadRedditStock()
  if (value.includes('stocktwits') && !stockTwitsItems.value.length && !stockTwitsLoading.value) loadStockTwits()
  if (value.includes('yf_news') && !yfNewsItems.value.length && !yfNewsLoading.value) loadYfNews()
}, { immediate: true, deep: true })

// 当资产类型切换时，剔除不兼容的已激活信息源；若全部失效则默认回到 fmp
watch(forecastAssetType, () => {
  const allowedKeys = sources.value.map(s => s.key)
  const filtered = activeSources.value.filter(k => allowedKeys.includes(k))
  activeSources.value = filtered.length ? filtered : (allowedKeys.includes('fmp') ? ['fmp'] : allowedKeys.slice(0, 1))
})

watch([fmpAutoRefresh, () => activeSources.value.includes('fmp')], () => {
  if (fmpTimer) clearInterval(fmpTimer)
  fmpTimer = null
  if (fmpAutoRefresh.value && activeSources.value.includes('fmp')) {
    fmpTimer = setInterval(() => loadFmp({ append: true, silent: true }), 60000)
  }
}, { immediate: true })

watch([binanceAutoRefresh, () => activeSources.value.includes('binance')], () => {
  if (binanceTimer) clearInterval(binanceTimer)
  binanceTimer = null
  if (binanceAutoRefresh.value && activeSources.value.includes('binance')) {
    binanceTimer = setInterval(() => loadBinance({ append: true, silent: true }), 60000)
  }
}, { immediate: true })

onUnmounted(() => {
  if (fmpTimer) clearInterval(fmpTimer)
  if (binanceTimer) clearInterval(binanceTimer)
  stopCryptoForecastProgressTimer()
})
</script>

<style scoped>
.reaction-view {
  min-height: 100vh;
  background: var(--c-bg, #f7f9fc);
  color: var(--c-text, #172033);
}

.reaction-shell {
  width: min(1180px, calc(100% - 40px));
  margin: 0 auto;
  padding: 32px 0 72px;
}

.page-head {
  padding: 12px 0 28px;
  border-bottom: 1px solid var(--c-border, #d9e1ec);
}

.eyebrow-row,
.meta-row,
.pager-row,
.batch-row,
.chip-row,
.filter-row,
.tag-row,
.source-chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px 12px;
  align-items: center;
}

.eyebrow-row,
.meta-row,
.pager-row {
  color: #657189;
  font-family: var(--f-mono, ui-monospace, SFMono-Regular, Consolas, monospace);
  font-size: 12px;
}

.page-head h1 {
  margin: 18px 0 10px;
  font-size: 34px;
  line-height: 1.12;
  letter-spacing: 0;
}

.page-head p,
.section-head p,
.source-panel__head p {
  margin: 0;
  max-width: 800px;
  color: #5a667c;
  line-height: 1.7;
}

.input-band {
  padding: 28px 0;
  border-bottom: 1px solid var(--c-border, #d9e1ec);
}

.section-head {
  display: grid;
  grid-template-columns: 44px minmax(0, 1fr);
  gap: 18px;
  align-items: start;
  margin-bottom: 18px;
}

.section-head.compact { margin-bottom: 14px; }

.kicker {
  display: inline-grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border: 1px solid #aebbd0;
  border-radius: 8px;
  font-family: var(--f-mono, ui-monospace, SFMono-Regular, Consolas, monospace);
  font-size: 12px;
  color: #31425f;
  background: #fff;
}

.section-head h2,
.source-panel__head h3 {
  margin: 0 0 6px;
  font-size: 22px;
  letter-spacing: 0;
}

.source-grid,
.dim-grid,
.source-summary-grid {
  display: grid;
  gap: 12px;
}

.source-grid { grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); }
.dim-grid { grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); }
.source-summary-grid { grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); margin-bottom: 16px; }

.source-card,
.dim-card,
.article-card,
.source-panel,
.source-summary-grid > div {
  border: 1px solid #d8e0ec;
  border-radius: 8px;
  background: #fff;
}

.source-card {
  position: relative;
  display: grid;
  grid-template-columns: 42px 1fr;
  gap: 12px;
  align-items: center;
  padding: 14px 58px 14px 14px;
  text-align: left;
  cursor: pointer;
  transition: border-color .16s ease, box-shadow .16s ease, background .16s ease, transform .16s ease;
}

.source-card.active,
.dim-card.active,
.article-card.selected,
.chip-btn.active {
  border-color: #2b6cb0;
  box-shadow: 0 0 0 2px rgba(43, 108, 176, 0.14);
}

.source-card.active {
  background: #f2f7ff;
}

.source-card:hover {
  transform: translateY(-1px);
  border-color: #8fb3dd;
}

.source-card::after {
  content: '未选';
  position: absolute;
  top: 12px;
  right: 12px;
  min-width: 36px;
  padding: 3px 8px;
  border: 1px solid #cfd8e6;
  border-radius: 999px;
  background: #fff;
  color: #64748b;
  font-size: 11px;
  font-weight: 700;
  text-align: center;
}

.source-card.active::after {
  content: '已选';
  border-color: #1f3f66;
  background: #1f3f66;
  color: #fff;
}

.source-mark {
  display: grid;
  place-items: center;
  width: 40px;
  height: 40px;
  border-radius: 8px;
  color: #111827;
  font-weight: 700;
}

.source-copy,
.dim-card span,
.article-body {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.source-copy small,
.source-copy em,
.dim-card small,
.article-body small,
.article-body em {
  color: #64748b;
  line-height: 1.5;
  font-style: normal;
}

.source-copy b {
  display: inline-block;
  margin-left: 8px;
  color: #2f855a;
}

.source-summary-grid > div {
  padding: 14px 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.source-summary-grid span {
  color: #64748b;
  font-size: 12px;
  margin-bottom: 0;
}

.source-summary-grid strong { font-size: 22px; }

.source-panel {
  padding: 18px;
  margin-top: 16px;
}

.source-panel__head {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: start;
  margin-bottom: 16px;
}

.panel-kicker {
  display: inline-block;
  margin-bottom: 8px;
  color: #2b6cb0;
  font-family: var(--f-mono, ui-monospace, SFMono-Regular, Consolas, monospace);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: .12em;
}

.source-panel__toolbar,
.form-grid {
  display: grid;
  gap: 12px;
  margin-bottom: 14px;
}

.fmp-toolbar { grid-template-columns: minmax(180px, 1fr) 140px 120px 90px 88px 118px; }
.binance-toolbar { grid-template-columns: minmax(160px, 1fr) 136px 110px 104px 130px 112px 88px 118px; }
.form-grid { grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); }

.filter-row {
  margin-bottom: 12px;
}

.filter-row label {
  min-width: 200px;
}

label span {
  display: block;
  margin-bottom: 6px;
  font-size: 13px;
  color: #526078;
}

input,
select,
textarea {
  width: 100%;
  border: 1px solid #cfd8e6;
  border-radius: 8px;
  background: #fff;
  color: #172033;
  font: inherit;
  padding: 10px 12px;
}

textarea {
  resize: vertical;
  min-height: 120px;
}

.full-label {
  display: grid;
  gap: 6px;
  margin-bottom: 14px;
}

.prompt-box { margin-top: 16px; }

.horizon-hint {
  margin: 10px 0 0;
  font-size: 13px;
  color: #475569;
}
.horizon-hint b { color: #0f172a; }

.prompt-engine {
  justify-self: end;
  color: #64748b;
  font-size: 12px;
}

.inline-toggle {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 10px;
  border: 1px solid #cfd8e6;
  border-radius: 8px;
  background: #fff;
}

.inline-toggle span {
  display: inline;
  margin: 0;
  color: #31425f;
  font-size: 13px;
  font-weight: 700;
}

.inline-toggle input {
  flex: none;
  width: 18px;
  height: 18px;
  accent-color: #1f3f66;
}

.dim-card input {
  width: auto;
}

.batch-row {
  margin-bottom: 14px;
}

.article-list {
  display: grid;
  gap: 10px;
  max-height: 520px;
  overflow: auto;
  padding-right: 4px;
}

.article-card {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 0;
  padding: 14px 14px 14px 54px;
  min-height: 112px;
  cursor: pointer;
  transition: border-color .16s ease, box-shadow .16s ease, background .16s ease, transform .16s ease;
}

.article-card:hover {
  border-color: #9bb7d8;
  box-shadow: 0 10px 22px rgba(31, 63, 102, 0.08);
  transform: translateY(-1px);
}

.article-card.selected {
  background: linear-gradient(90deg, #eaf3ff 0, #fff 34%);
}

.article-card.selected::before {
  content: '';
  position: absolute;
  inset: -1px auto -1px -1px;
  width: 5px;
  border-radius: 8px 0 0 8px;
  background: #1f3f66;
}

.article-card.selected::after {
  content: '已选择';
  position: absolute;
  top: 12px;
  right: 12px;
  padding: 3px 9px;
  border-radius: 999px;
  background: #1f3f66;
  color: #fff;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: .02em;
}

.article-card input[type="checkbox"] {
  position: absolute;
  top: 16px;
  left: 16px;
  width: 26px;
  height: 26px;
  margin: 0;
  border: 2px solid #9fb1c9;
  border-radius: 8px;
  appearance: none;
  background: #fff;
  cursor: pointer;
  display: grid;
  place-items: center;
}

.article-card input[type="checkbox"]::after {
  content: '';
  width: 8px;
  height: 13px;
  border: solid #fff;
  border-width: 0 2px 2px 0;
  transform: rotate(45deg) scale(0);
  transition: transform .12s ease;
}

.article-card input[type="checkbox"]:checked {
  border-color: #1f3f66;
  background: #1f3f66;
}

.article-card input[type="checkbox"]:checked::after {
  transform: rotate(45deg) scale(1);
}

.article-body small {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 12px;
}

.tag-row b,
.tag-row i,
.source-pill {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 2px 8px;
  border: 1px solid #d8e0ec;
  border-radius: 999px;
  background: #f8fafc;
  color: #526078;
  font-size: 12px;
  font-style: normal;
}

.tag-row b {
  color: #1f3f66;
  background: #eaf1fb;
}

.direction-bullish { color: #2f855a !important; background: #e8f5ee !important; }
.direction-bearish { color: #c53030 !important; background: #fff1f0 !important; }
.direction-volatile { color: #b7791f !important; background: #fff8e1 !important; }
.direction-risk_off { color: #553c9a !important; background: #f0ebff !important; }

.pager-row {
  justify-content: space-between;
  margin-top: 14px;
}

.dim-card {
  display: grid;
  grid-template-columns: 18px minmax(0, 1fr);
  gap: 10px;
  padding: 12px;
}

.crypto-preview-panel {
  margin-top: 16px;
  padding: 16px;
  border: 1px solid #cfd8e6;
  border-radius: 8px;
  background: #fff;
  display: grid;
  gap: 12px;
}

.crypto-preview-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
}

.crypto-preview-head h3 {
  margin: 4px 0;
  font-size: 18px;
}

.crypto-preview-head p,
.crypto-rationale {
  margin: 0;
  color: #64748b;
  font-size: 13px;
  line-height: 1.55;
}

.crypto-progress {
  display: grid;
  gap: 8px;
  padding: 12px;
  border: 1px solid #d8e0ec;
  border-radius: 8px;
  background: #f8fafc;
}

.crypto-progress__head,
.crypto-progress__detail {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.crypto-progress__head strong {
  color: #172033;
  font-size: 14px;
}

.crypto-progress__head span,
.crypto-progress__detail {
  color: #64748b;
  font-size: 12px;
}

.crypto-progress__bar {
  height: 8px;
  border-radius: 999px;
  background: #e5eaf2;
  overflow: hidden;
}

.crypto-progress__bar i {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: #1f3f66;
  transition: width .24s ease;
}

.crypto-progress__detail b {
  color: #b7791f;
  font-weight: 700;
}

.crypto-forecast-card {
  border: 1px solid #d8e0ec;
  border-radius: 8px;
  padding: 14px;
  display: grid;
  gap: 12px;
}

.crypto-forecast-card.dir-up { border-color: #2f855a; background: #eefaf3; }
.crypto-forecast-card.dir-down { border-color: #c53030; background: #fff5f5; }
.crypto-forecast-card.dir-neutral { border-color: #718096; background: #f8fafc; }

.crypto-forecast-main {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto;
  gap: 12px;
  align-items: center;
}

.crypto-forecast-main span,
.crypto-forecast-main em,
.crypto-quality-row {
  color: #64748b;
  font-size: 13px;
  font-style: normal;
}

.crypto-forecast-main strong {
  font-size: 20px;
  color: #172033;
}

.crypto-score-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.crypto-score-grid div {
  padding: 10px;
  border: 1px solid rgba(23, 32, 51, 0.08);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.72);
}

.crypto-score-grid span {
  display: block;
  color: #64748b;
  font-size: 12px;
  margin-bottom: 4px;
}

.crypto-score-grid strong {
  color: #172033;
}

.crypto-quality-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 14px;
}

.action-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  padding: 24px 0;
}

.launch-meta {
  color: #64748b;
  font-size: 13px;
}

.launch-progress {
  flex-basis: 100%;
  display: grid;
  gap: 8px;
  padding: 14px 16px;
  border: 1px solid #cfd8e6;
  border-radius: 8px;
  background: #fff;
}

.launch-progress__head,
.launch-progress__detail {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.launch-progress__head strong {
  color: #172033;
  font-size: 14px;
}

.launch-progress__head span,
.launch-progress__detail {
  color: #64748b;
  font-size: 12px;
}

.launch-progress__bar {
  height: 8px;
  border-radius: 999px;
  background: #e5eaf2;
  overflow: hidden;
}

.launch-progress__bar i {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: #1f3f66;
  transition: width .24s ease;
}

.launch-progress__detail b {
  color: #b7791f;
  font-weight: 700;
}

.launch-error { flex-basis: 100%; }

.primary-btn,
.plain-btn,
.chip-btn {
  border: 1px solid #1f3f66;
  border-radius: 8px;
  padding: 10px 16px;
  font-weight: 700;
  cursor: pointer;
}

.primary-btn {
  background: #1f3f66;
  color: #fff;
}

.plain-btn,
.chip-btn {
  background: #fff;
  color: #1f3f66;
}

.chip-btn.active {
  background: #1f3f66;
  color: #fff;
  border-color: #1f3f66;
}

.chip-btn {
  padding: 8px 12px;
  border-color: #cfd8e6;
  transition: background .16s ease, color .16s ease, border-color .16s ease, box-shadow .16s ease;
}

button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.status-line {
  padding: 14px 16px;
  border: 1px solid #cfd8e6;
  border-radius: 8px;
  background: #fff;
  color: #4a5568;
}

.status-line.error {
  border-color: #feb2b2;
  background: #fff5f5;
  color: #9b2c2c;
}

.status-line.warning {
  border-color: #f6d365;
  background: #fffaf0;
  color: #8a5a00;
}

@media (max-width: 1080px) {
  .fmp-toolbar,
  .binance-toolbar {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 840px) {
  .reaction-shell {
    width: min(100% - 24px, 1180px);
    padding-top: 20px;
  }

  .crypto-preview-head,
  .crypto-forecast-main {
    grid-template-columns: 1fr;
    flex-direction: column;
    align-items: flex-start;
  }

  .crypto-score-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .page-head h1 { font-size: 28px; }
  .section-head { grid-template-columns: 1fr; gap: 10px; }
  .source-panel__head { display: grid; }
  .fmp-toolbar,
  .binance-toolbar {
    grid-template-columns: 1fr;
  }
}

/* FMP category tab bar + search + social sentiment panel */
.fmp-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin: 4px 0 14px;
  border-bottom: 1px solid #d8dee8;
}
.fmp-tab {
  appearance: none;
  border: 1px solid transparent;
  background: transparent;
  padding: 8px 14px;
  font-size: 13px;
  color: #4d5b75;
  cursor: pointer;
  border-radius: 6px 6px 0 0;
  transition: background 0.15s, color 0.15s, border-color 0.15s;
}
.fmp-tab:hover { background: #eef1f6; color: #1c2638; }
.fmp-tab.active {
  background: #fff;
  color: #1c2638;
  border-color: #d8dee8;
  border-bottom-color: #fff;
  font-weight: 600;
  margin-bottom: -1px;
}
.fmp-search-row {
  display: flex;
  gap: 10px;
  margin-bottom: 12px;
}
.fmp-search-row input {
  flex: 1;
  padding: 8px 12px;
  border: 1px solid #cdd4e0;
  border-radius: 6px;
  font-size: 13px;
}
.fmp-social-panel {
  background: #fafbfd;
  border: 1px solid #e3e8f0;
  border-radius: 8px;
  padding: 14px;
}
.fmp-social-controls {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: flex-end;
  margin-bottom: 12px;
}
.fmp-social-controls label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
  color: #4d5b75;
}
.fmp-social-controls input,
.fmp-social-controls select {
  padding: 6px 10px;
  border: 1px solid #cdd4e0;
  border-radius: 6px;
  font-size: 13px;
  min-width: 140px;
}
.social-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
.social-table th,
.social-table td {
  padding: 8px 10px;
  border-bottom: 1px solid #e7eaf1;
  text-align: left;
}
.social-table th { background: #f1f4f9; color: #364257; font-weight: 600; }
.social-table td.num,
.social-table th.num { text-align: right; font-variant-numeric: tabular-nums; }
.social-table td.pos { color: #1a8754; }
.social-table td.neg { color: #c0392b; }
</style>
