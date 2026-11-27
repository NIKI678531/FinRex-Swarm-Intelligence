<div align="center">



简洁通用的群体智能引擎，预测万物
</br>
<em>A Simple and Universal Swarm Intelligence Engine, Predicting Anything</em>



[English](./README.md) | [中文文档](./README-ZH.md)

</div>

## 项目概述

**FinRex** 是一款多智能体 AI 预测引擎：上传现实世界的种子信息（新闻、研究报告、金融信号），用自然语言描述预测需求，便可以构建一个可交互的平行数字世界并推演未来走向，最终产出一份详尽的预测报告。

## 工作流程

FinRex 通过两条互补的工作流给出预测，两者最终汇入同一份报告：

**工作流 A：群体智能模拟（定性推演「会发生什么」）**

1. **图谱构建**：从种子材料中提取实体与关系，注入个体与群体记忆，构建 GraphRAG 知识图谱。
2. **环境搭建**：抽取实体关系、生成智能体人设，由环境配置 Agent 解析预测需求并注入仿真参数。
3. **双平台并行模拟**：在 Reddit / Twitter 双平台上并行驱动成千上万个智能体自由交互，过程中动态更新时序记忆。
4. **报告生成 & 深度互动**：ReportAgent 调用丰富工具集与模拟后的环境深度交互，产出报告；你还可与世界中的任意智能体或 ReportAgent 对话。

**工作流 B：基础模型量化预测（定量推演「数字是多少」）**

1. **行情接入**：通过 ccxt / yfinance / akshare 获取加密货币与股票的历史与实时数据。
2. **价格预测**：用 Kronos 与 Chronos-Bolt 基础模型生成价格预测序列。
3. **回测与验证**：对预测进行回测和纸面交易验证，量化策略表现。

**两条工作流如何协作：**群体模拟（A）刻画市场情绪与事件演化的「定性」面，量化预测（B）给出价格走势的「定量」面；其中公众舆情情绪分析既为模拟智能体提供情绪标签，又作为量化预测的特征输入。最终 ReportAgent 将二者整合为同一份预测报告，并支持持续对话与深度交互。

## 功能特点

- **多智能体群体模拟**：基于 CAMEL-OASIS 驱动成千上万个具备独立人格、长期记忆与行为逻辑的智能体自由交互。
- **GraphRAG 图谱与长期记忆**：通过 Zep Cloud + FalkorDB 构建用户画像图谱，注入个体与群体记忆并动态更新时序记忆。
- **双平台并行模拟**：Reddit / Twitter 风格的双平台并行推演，自动解析自然语言预测需求。
- **基础模型量化预测**：集成 Kronos 与 Chronos-Bolt 基础模型，支持加密货币与股票的价格预测与回测。
- **公众舆情情绪分析**：可选 Hugging Face 远程推理生成金融情绪 / 多语言情绪标签，失败时自动降级到本地规则标签。
- **深度报告生成**：ReportAgent 拥有丰富的工具集，对模拟后环境进行深度交互并产出详尽预测报告。
- **数字世界交互对话**：可与模拟世界中的任意智能体或 ReportAgent 进行自然语言对话。
- **内容工作室与纸面交易**：内置 Content Studio、纸面交易与回测能力，覆盖研究到执行的完整链路。

## 技术栈

| 层级 | 技术 |
|------|------|
| **前端** | Vue 3 · Vite 7 · Vue Router · Vue I18n · ECharts · D3 · Lightweight Charts · Axios |
| **后端** | Python 3.11/3.12 · Flask 3 · Flask-CORS · OpenAI SDK · Pydantic |
| **智能体 / 记忆** | CAMEL-OASIS · CAMEL-AI · Zep Cloud · FalkorDB（Graphiti 图谱后端） |
| **量化 / 预测** | PyTorch · Kronos · Chronos-Bolt · LightGBM · scikit-learn · pandas · numpy |
| **市场数据** | ccxt · yfinance · akshare |
| **文档与处理** | PyMuPDF · charset-normalizer · chardet |
| **基础设施** | Docker · docker-compose · uv（Python 包管理器） · Node.js 18+ |

## 本地环境建立

#### 前置要求

| 工具 | 版本要求 | 说明 | 安装检查 |
|------|---------|------|---------|
| **Node.js** | 18+ | 前端运行环境，包含 npm | `node -v` |
| **Python** | ≥3.11, ≤3.12 | 后端运行环境 | `python --version` |
| **uv** | 最新版 | Python 包管理器 | `uv --version` |

#### 配置环境变量

```bash
# 复制示例配置文件
cp .env.example .env

# 编辑 .env 文件，填入必要的 API 密钥
```

**必需的环境变量：** 后端启动时仅强制校验 `LLM_API_KEY` 与 `ZEP_API_KEY`，其余均为可选。

```env
# ===== LLM API 配置（支持 OpenAI SDK 格式的任意 LLM API）=====
# 兼容 OpenAI / Azure OpenAI / 任意兼容接口
# 注意消耗较大，可先进行小于 40 轮的模拟尝试
LLM_API_KEY=your_api_key_here
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL_NAME=gpt-4o-mini
# 仅 Azure OpenAI 需要：deployment 可与模型名不同，留空则回退到 LLM_MODEL_NAME
LLM_API_VERSION=2024-12-01-preview
LLM_DEPLOYMENT_NAME=

# ===== Zep 记忆图谱配置 =====
# 每月免费额度即可支撑简单使用：https://app.getzep.com/
ZEP_API_KEY=your_zep_api_key_here
```

**可选配置（按需开启）：**

```env
# ----- 加速 LLM（可选）-----
# 默认关闭；设为 true 时，双平台并行模拟使用下面这组更快的模型配置
LLM_BOOST_ENABLED=false
LLM_BOOST_API_KEY=your_api_key_here
LLM_BOOST_BASE_URL=your_base_url_here
LLM_BOOST_MODEL_NAME=your_model_name_here

# ----- Hugging Face 远程推理（可选）-----
# 为公众舆情层补充金融情绪 / 多语言情绪标签
# 未配置 token 或远程调用失败时，后端自动降级到本地规则标签
HF_TOKEN=your_huggingface_token_here
HF_ENABLE_REMOTE_INFERENCE=true
HF_INFERENCE_BASE_URL=https://router.huggingface.co/hf-inference/models
HF_FINANCIAL_SENTIMENT_MODEL=mrm8488/distilroberta-finetuned-financial-news-sentiment-analysis
HF_EMOTION_MODEL=tabularisai/multilingual-emotion-classification
# 多语言情绪模型为非商用许可（CC-BY-NC-4.0），需显式开启才会远程调用，否则走本地规则
HF_ALLOW_NON_COMMERCIAL_MODELS=false

# ----- Cloudflare D1（Binance Square 社区数据源，可选）-----
# 缺失或 Token 过期时，相关接口自动回退到本地缓存 / 公共公告流
CLOUDFLARE_D1_ACCOUNT_ID=your_cloudflare_account_id
CLOUDFLARE_D1_DATABASE_ID=your_d1_database_id
CLOUDFLARE_D1_API_TOKEN=your_d1_api_token
```

> 前端环境变量（可选）：在 `frontend/.env.local` 中设置 `VITE_REPORT_V2=true`（默认）启用 v2 报告界面，设为 `false` 可回退旧版界面。

#### 本地 Docker 建立

```bash
# 1. 配置环境变量（同源码部署）
cp .env.example .env

# 2. 拉取镜像并启动
docker compose up -d
```

默认会读取根目录下的 `.env`，并映射端口 `3000（前端）/5001（后端）`。`docker-compose.yml` 同时启动 `finrex` 主服务与 `falkordb` 图谱后端（暴露 `6379` 供 Graphiti 客户端连接，`3001` 为其内置仪表板）。

> 在 `docker-compose.yml` 中已通过注释提供加速镜像地址，可按需替换。

## 开始使用

### 安装依赖

```bash
# 一键安装所有依赖（根目录 + 前端 + 后端）
npm run setup:all
```

或者分步安装：

```bash
# 安装 Node 依赖（根目录 + 前端）
npm run setup

# 安装 Python 依赖（后端，自动创建虚拟环境）
npm run setup:backend
```

### Npm 开发模式运行

```bash
# 同时启动前后端（在项目根目录执行）
npm run dev
```

**服务地址：**
- 前端：`http://localhost:3000`
- 后端 API：`http://localhost:5001`

**单独启动：**

```bash
npm run backend   # 仅启动后端
npm run frontend  # 仅启动前端
```

### 构建生产版本

```bash
# 构建前端生产产物（输出至 frontend/dist）
npm run build
```

## 项目结构

```text
FinRex_rebrand/
├── package.json                # 根工作区脚本（setup / dev / build / backend / frontend）
├── docker-compose.yml          # 编排 finrex 主服务 + falkordb 图谱后端
├── Dockerfile                  # 前后端一体化镜像
│
├── backend/                    # Flask 后端（由 uv 管理 Python 依赖）
│   ├── run.py                  # 后端入口（启动 Flask 应用，端口 5001）
│   ├── pyproject.toml          # Python 依赖与项目配置
│   ├── app/
│   │   ├── config.py           # 环境变量与全局配置加载
│   │   ├── controllers/        # HTTP 接口层（Flask Blueprint，按需挂载）
│   │   ├── services/           # 业务逻辑层
│   │   │   ├── simulation_*     #   群体模拟编排与运行（工作流 A）
│   │   │   ├── graph_builder    #   GraphRAG 图谱构建
│   │   │   ├── persona_graph/   #   智能体人设与画像图谱
│   │   │   ├── zep_*            #   Zep 长期记忆读写与更新
│   │   │   ├── asset_forecast/  #   Kronos / Chronos 价格预测（工作流 B）
│   │   │   ├── public_opinion_* #   公众舆情与情绪分析
│   │   │   └── report_agent     #   ReportAgent 报告生成与交互
│   │   ├── quant/              # 量化预测核心算法
│   │   ├── repositories/       # 数据访问层（缓存 / 持久化）
│   │   ├── models/             # 数据模型定义
│   │   └── utils/              # 通用工具函数
│   ├── scripts/                # 调度与离线脚本（纸面交易、回测、校验等）
│   ├── tests/                  # pytest 测试
│   └── uploads/                # 运行产物与各类缓存（行情 / 新闻 / 图谱等）
│
├── frontend/                   # Vue 3 + Vite 前端（端口 3000）
│   └── src/
│       ├── api/                # Axios API 封装（与后端控制器一一对应）
│       ├── pages/              # 页面级视图
│       ├── components/         # 可复用组件
│       ├── context/            # 全局状态
│       ├── hooks/              # 组合式函数（composables）
│       ├── i18n/               # 国际化资源
│       └── utils/              # 前端工具函数
│
├── Kronos/                     # Kronos 基础模型源码、微调脚本与示例
└── locales/                    # 顶层多语言文案（en / zh）
```

## API 集成

后端基于 **Flask Blueprint** 组织接口，控制器位于 [backend/app/controllers](backend/app/controllers)，并在启动时按需挂载（缺少可选依赖的蓝图会被安全跳过）。主要接口域包括：

| 接口域 | 说明 |
|--------|------|
| `graph` | 图谱构建与查询 |
| `simulation` | 群体模拟生命周期管理 |
| `report` | 报告生成与交互 |
| `public_opinion` | 公众舆情与情绪分析 |
| `content_studio` | 内容工作室 |
| `financial` | 金融数据与指标 |
| `persona` | 人设生成与画像 |
| `quant` | 量化预测与回测 |
| `paper_trading` | 纸面交易 |
| `market` / `articles` / `reaction` | 行情、资讯与反应数据 |

前端通过 [frontend/src/api](frontend/src/api) 下的 Axios 模块与上述接口一一对应进行调用。

## API 管理与优化

- **统一 LLM 接入**：通过 OpenAI SDK 兼容协议接入任意 LLM（`LLM_BASE_URL` / `LLM_MODEL_NAME`），便于切换供应商与模型。
- **优雅降级**：控制器按需挂载，缺少 LLM / 仿真依赖时不影响其余蓝图；Hugging Face 远程推理失败时自动回退本地规则标签。
- **缓存机制**：行情、新闻、图谱等结果缓存于 `backend/uploads/*_cache`，减少重复外部请求与 Token 消耗。
- **成本控制**：默认推荐先进行小于 40 轮的模拟尝试，避免高额 LLM 调用费用。

## 贡献指南

1. Fork 本仓库并创建特性分支：`git checkout -b feature/your-feature`
2. 遵循现有代码风格，提交前确保后端测试通过：`cd backend && uv run pytest`
3. 提交清晰的 commit message，并发起 Pull Request 说明变更动机与影响范围。
4. 涉及接口变更时，请同步更新前端 `frontend/src/api` 与本文档。

## 版本历史

| 版本 | 说明 |
|------|------|
| `0.1.0` | 初始版本：多智能体群体模拟、GraphRAG 记忆、基础模型量化预测与报告生成。 |

## 最近更新

- **Docker 一体化部署**：`docker-compose.yml` 集成 `finrex` 主服务与 `falkordb` 图谱后端，开箱即用。
- **基础模型量化预测**：接入 Kronos 与 Chronos-Bolt，支持加密货币与股票预测。

## 变更累计记录

- 新增可选 Hugging Face 远程推理，并提供本地规则标签的自动降级路径。
- 新增控制器按需挂载机制，缺少可选依赖时安全跳过对应蓝图。
- 新增前后端一体化 `Dockerfile` 与 docker-compose 部署支持。

## 协议

本项目以 [AGPL-3.0](./LICENSE) 协议开源。

