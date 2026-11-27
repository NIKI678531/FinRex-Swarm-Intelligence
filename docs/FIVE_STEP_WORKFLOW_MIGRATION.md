# FinRex Five-Step Workflow Migration Technical Document

生成日期：2026-06-18

本文档只描述当前项目中 Step 1 到 Step 5 的核心工作流，不覆盖 Unified Report。目标读者是准备把这套 Vue 工作流迁移到 React 应用的开发者，所以文档重点放在页面职责、状态结构、API 调用、跳转关系、后端保存结构和迁移建议。

> 重要范围说明：
>
> - 覆盖：Step 1 图谱构建、Step 2 环境准备、Step 3 推演运行、Step 4 报告生成回放、Step 5 报告交互。
> - 不覆盖：`/report/:reportId` 对应的 `UnifiedReportView.vue`。
> - 前置入口 `SentimentReportView.vue` 和首页历史入口会在附录中说明，但不作为五步工作流主流程的一部分。

---

## 1. 总览

### 1.1 五步工作流主路径

```text
Step 1
/process/:projectId
MainView.vue + Step1GraphBuild.vue
        |
        | createSimulation()
        v
Step 2
/simulation/:simulationId
SimulationView.vue + Step2EnvSetup.vue
        |
        | router.push({ name: 'SimulationRun', query: { maxRounds? } })
        v
Step 3
/simulation/:simulationId/start
SimulationRunView.vue + Step3Simulation.vue
        |
        | generateReport({ simulation_id, force_regenerate: true, report_type: 'both' })
        v
Step 4
/report/:reportId/replay
ReportView.vue + Step4Report.vue
        |
        | router.push({ name: 'Interaction', params: { reportId } })
        v
Step 5
/interaction/:reportId
InteractionView.vue + Step5Interaction.vue
```

### 1.2 路由表

源文件：`frontend/src/app/router/index.js`

| 路由 name | URL | 页面组件 | 本文档中的角色 |
|---|---|---|---|
| `Process` | `/process/:projectId` | `MainView.vue` | Step 1 |
| `Simulation` | `/simulation/:simulationId` | `SimulationView.vue` | Step 2 |
| `SimulationRun` | `/simulation/:simulationId/start` | `SimulationRunView.vue` | Step 3 |
| `ReportReplay` | `/report/:reportId/replay` | `ReportView.vue` | Step 4 |
| `Interaction` | `/interaction/:reportId` | `InteractionView.vue` | Step 5 |
| `Report` | `/report/:reportId` | `UnifiedReportView.vue` | 本文档不覆盖 |

### 1.3 五步导航解析

源文件：

- `frontend/src/hooks/useWorkflowResolver.js`
- `frontend/src/components/WorkflowStepper.vue`

`WorkflowStepper.vue` 负责渲染顶部流程导航。它不直接保存业务状态，而是通过 `useWorkflowResolver.js` 解析当前路由，再反查缺失的 `projectId`、`simulationId`、`reportId`。

当前 resolver 中存在 6 个节点：

```js
sentiment -> /sentiment
step1_2   -> /process/:projectId
step3     -> /simulation/:simulationId/start
step4     -> /report/:reportId/replay
step5     -> /interaction/:reportId
unified   -> /report/:reportId
```

React 迁移时建议只保留本文档需要的 5 个节点：

```ts
type WorkflowStepKey =
  | 'step1'
  | 'step2'
  | 'step3'
  | 'step4'
  | 'step5'
```

推荐 React 版路由映射：

```ts
const workflowRoutes = {
  step1: '/process/:projectId',
  step2: '/simulation/:simulationId',
  step3: '/simulation/:simulationId/start',
  step4: '/report/:reportId/replay',
  step5: '/interaction/:reportId',
}
```

---

## 2. 全局数据 ID 关系

整个工作流依赖 3 个核心 ID：

| ID | 生成位置 | 用途 | 持久化位置 |
|---|---|---|---|
| `project_id` | Step 1 ontology 生成后 | 标识上传材料、模拟需求、本体、图谱状态 | `backend/uploads/projects/{project_id}/project.json` |
| `simulation_id` | Step 1 完成后创建 simulation | 标识一次推演环境、Agent、配置、运行状态 | `backend/uploads/simulations/{simulation_id}/state.json` |
| `report_id` | Step 3 生成报告时创建 | 标识叙事报告或金融报告 | `backend/uploads/reports/{report_id}/meta.json` |

关系链：

```text
project_id
  -> graph_id
  -> simulation_id
  -> narrative report_id
  -> financial report_id
```

当前代码中叙事报告 ID 前缀是：

```text
report_xxxxxxxxxxxx
```

金融报告 ID 前缀是：

```text
freport_xxxxxxxxxxxx
```

五步工作流主线使用叙事报告 ID 进入 Step 4 和 Step 5。

---

## 3. 通用前端布局模式

Step 1 到 Step 4 都使用类似的双栏工作台结构：

```text
Header
  - FINREX brand
  - WorkflowStepper
  - 状态/按钮

Main Workspace
  Left panel
    - GraphPanel
    - 图谱加载/刷新

  Right panel
    - 当前 Step 的工作组件
    - 进度、日志、操作按钮
```

主要共同状态：

```ts
type ViewMode = 'graph' | 'split' | 'workbench'

type SystemLog = {
  time: string
  msg: string
}

type RuntimeStatus = 'processing' | 'completed' | 'error'
```

React 迁移建议：

- 抽出 `WorkflowShell`，统一 Header、Stepper、左右栏布局。
- 抽出 `GraphWorkspacePanel`，统一图谱展示、刷新、loading。
- 每个 Step 只负责右侧业务面板。
- 日志可以抽成 `useSystemLogs(max = 100 | 200)`。
- 轮询可以抽成 `usePolling(fn, interval, enabled)`。

---

## 4. Step 1：图谱构建

### 4.1 页面和组件

源文件：

- 页面：`frontend/src/pages/MainView.vue`
- 业务组件：`frontend/src/components/Step1GraphBuild.vue`
- API：`frontend/src/api/graph.js`
- 后端 Controller：`backend/app/controllers/graph.py`
- 项目存储：`backend/app/repositories/project_repository.py`
- 异步任务：`backend/app/repositories/task_repository.py`

路由：

```text
/process/:projectId
```

特殊 projectId：

```text
/process/new
```

当 `projectId === 'new'` 时，`MainView.vue` 会从 `pendingUpload` 上下文读取刚刚上传或选择的输入，然后创建新项目。

### 4.2 页面职责

`MainView.vue` 负责：

1. 判断是新建项目还是加载已有项目。
2. 提交文件或文章输入，生成 ontology。
3. 启动图谱构建任务。
4. 轮询图谱构建状态。
5. 加载图谱数据。
6. 把 `projectData`、`graphData`、进度信息传给 `Step1GraphBuild.vue`。

`Step1GraphBuild.vue` 负责：

1. 展示 ontology 生成结果。
2. 展示图谱构建进度。
3. 展示图谱统计信息。
4. 在图谱完成后创建 simulation。
5. 跳转到 Step 2。

### 4.3 Step 1 前端状态

`MainView.vue` 的核心状态：

```ts
type Step1State = {
  currentProjectId: string
  loading: boolean
  graphLoading: boolean
  error: string
  projectData: Project | null
  graphData: GraphData | null
  currentPhase: -1 | 0 | 1 | 2
  ontologyProgress: any | null
  buildProgress: {
    progress: number
    message: string
  } | null
  systemLogs: SystemLog[]
}
```

`currentPhase` 含义：

| 值 | 含义 |
|---|---|
| `-1` | 上传/初始化 |
| `0` | ontology 生成中或已生成 |
| `1` | graph 构建中 |
| `2` | graph 构建完成 |

### 4.4 Step 1 初始化逻辑

入口函数：

```js
initProject()
```

逻辑：

```text
if currentProjectId === 'new'
  -> handleNewProject()
else
  -> loadProject()
```

新项目路径：

```text
pendingUpload
  -> generateOntology() 或 generateOntologyFromArticles()
  -> router.replace({ name: 'Process', params: { projectId } })
  -> startBuildGraph()
```

已有项目路径：

```text
getProject(projectId)
  -> 根据 project.status 判断当前阶段
  -> ontology_generated 且没有 graph_id：启动 buildGraph()
  -> graph_building：恢复轮询 task
  -> graph_completed：加载 graphData
```

### 4.5 Step 1 API 调用

源文件：`frontend/src/api/graph.js`

#### 4.5.1 生成 ontology

```ts
POST /api/graph/ontology/generate
Content-Type: multipart/form-data
```

请求字段：

```text
files
simulation_requirement
project_name?
additional_context?
target_asset_symbol?
target_asset_type?
target_asset_market?
target_asset_horizon_days?
```

前端方法：

```js
generateOntology(formData)
```

后端方法：

```py
generate_ontology()
```

后端做的事情：

1. 校验 `simulation_requirement`。
2. 校验上传文件。
3. 创建 `Project`。
4. 保存上传文件。
5. 解析 PDF/MD/TXT 文本。
6. 保存 `extracted_text.txt`。
7. 调用 `OntologyGenerator.generate()`。
8. 保存 ontology 到 `project.json`。
9. 将项目状态改为 `ontology_generated`。

响应核心字段：

```json
{
  "success": true,
  "data": {
    "project_id": "proj_xxxx",
    "project_name": "Unnamed Project",
    "ontology": {
      "entity_types": [],
      "edge_types": []
    },
    "analysis_summary": "",
    "files": [],
    "total_text_length": 12345
  }
}
```

#### 4.5.2 文章输入路径

源文件：

- `frontend/src/api/articles.js`
- `backend/app/controllers/articles.py`

当前 Step 1 也支持从文章或金融种子数据创建项目：

```ts
POST /api/graph/ontology/generate-from-articles
```

这条路径会保存：

```text
financial_seed_context
selected_articles
comments
metadata
target_asset
```

如果 React 迁移目标只需要文件上传，可以先不迁移文章路径。如果要保留金融预测上下文，则必须迁移这条路径。

#### 4.5.3 构建图谱

```ts
POST /api/graph/build
```

请求：

```json
{
  "project_id": "proj_xxxx",
  "graph_name": "optional",
  "chunk_size": 500,
  "chunk_overlap": 50
}
```

前端方法：

```js
buildGraph(data)
```

后端方法：

```py
build_graph()
```

后端做的事情：

1. 读取 project。
2. 校验 project 已经有 ontology。
3. 读取 `extracted_text.txt`。
4. 创建 `TaskManager` 任务。
5. 将 project 状态改为 `graph_building`。
6. 后台线程创建 Zep graph。
7. 设置 ontology。
8. 分 chunk 写入文本。
9. 等待 Zep episodes 处理。
10. 读取 graph data。
11. 更新 `project.graph_id`。
12. 将 project 状态改为 `graph_completed`。
13. 将 task 标记为 completed。

响应：

```json
{
  "success": true,
  "data": {
    "project_id": "proj_xxxx",
    "task_id": "uuid",
    "message": "graph build task started"
  }
}
```

#### 4.5.4 查询图谱构建任务

```ts
GET /api/graph/task/:taskId
```

前端每 2 秒轮询一次。

响应结构来自 `Task.to_dict()`：

```ts
type TaskResponse = {
  task_id: string
  task_type: string
  status: 'pending' | 'processing' | 'completed' | 'failed'
  progress: number
  message: string
  progress_detail?: Record<string, any>
  result?: Record<string, any>
  error?: string
  metadata?: Record<string, any>
}
```

#### 4.5.5 加载图谱数据

```ts
GET /api/graph/data/:graphId
```

`MainView.vue` 中有两种图谱刷新：

1. 图谱构建期间每 10 秒刷新一次。
2. 构建完成后最终加载一次完整图谱。

### 4.6 Step 1 后端保存结构

项目保存目录：

```text
backend/uploads/projects/{project_id}/
  project.json
  extracted_text.txt
  files/
    original_file.pdf
    original_file.md
    original_file.txt
```

`project.json` 对应 `Project` 数据结构：

```ts
type Project = {
  project_id: string
  name: string
  status:
    | 'created'
    | 'ontology_generated'
    | 'graph_building'
    | 'graph_completed'
    | 'failed'
  created_at: string
  updated_at: string
  files: Array<{ filename: string; size?: number; path?: string }>
  total_text_length: number
  ontology?: {
    entity_types: any[]
    edge_types: any[]
  }
  analysis_summary?: string
  graph_id?: string
  graph_build_task_id?: string
  simulation_requirement?: string
  chunk_size: number
  chunk_overlap: number
  target_asset?: Record<string, any>
  financial_seed_context?: Record<string, any>
  error?: string
}
```

### 4.7 Step 1 到 Step 2 跳转

触发组件：

```text
Step1GraphBuild.vue
```

触发函数：

```js
handleEnterEnvSetup()
```

前端调用：

```js
createSimulation({
  project_id: projectData.project_id,
  graph_id: projectData.graph_id,
  enable_twitter: true,
  enable_reddit: true
})
```

后端接口：

```ts
POST /api/simulation/create
```

成功后跳转：

```js
router.push({
  name: 'Simulation',
  params: { simulationId: res.data.simulation_id }
})
```

React 迁移时对应：

```ts
navigate(`/simulation/${simulationId}`)
```

---

## 5. Step 2：推演环境准备

### 5.1 页面和组件

源文件：

- 页面：`frontend/src/pages/SimulationView.vue`
- 业务组件：`frontend/src/components/Step2EnvSetup.vue`
- API：`frontend/src/api/simulation.js`
- 后端 Controller：`backend/app/controllers/simulation.py`
- 后端 Service：`backend/app/services/simulation_manager.py`

路由：

```text
/simulation/:simulationId
```

### 5.2 页面职责

`SimulationView.vue` 负责：

1. 读取 `simulationId`。
2. 加载 simulation 信息。
3. 根据 simulation 的 `project_id` 加载 project。
4. 根据 project 的 `graph_id` 加载图谱。
5. 接收 Step 2 组件的 `next-step` 事件。
6. 将用户选择的 `maxRounds` 放入 Step 3 的 query。
7. 如果用户从 Step 3 返回 Step 2，尝试关闭正在运行的推演环境。

`Step2EnvSetup.vue` 负责：

1. 自动启动推演准备任务。
2. 轮询准备任务进度。
3. 实时读取生成中的 Agent profiles。
4. 实时读取生成中的 simulation config。
5. 展示推演环境配置。
6. 允许用户使用自动轮数或自定义轮数。
7. 点击开始推演后进入 Step 3。

### 5.3 Step 2 UI 子模块

`Step2EnvSetup.vue` 模板中分为 5 类信息区：

1. Simulation instance 创建状态。
2. Agent personas 生成状态。
3. 双平台配置状态。
4. 初始激活内容：
   - narrative direction
   - hot topics
   - initial posts
   - time config
5. Setup complete：
   - 自动计算轮数
   - 自定义最大轮数
   - 开始推演按钮

### 5.4 Step 2 前端状态

```ts
type Step2State = {
  phase: 0 | 1 | 2 | 3 | 4
  taskId: string | null
  prepareProgress: number
  currentStage: string
  progressMessage: string
  profiles: AgentProfile[]
  entityTypes: string[]
  expectedTotal: number | null
  simulationConfig: SimulationConfig | null
  selectedProfile: AgentProfile | null
  showProfilesDetail: boolean
  useCustomRounds: boolean
  customMaxRounds: number
}
```

当前 `phase` 在代码中的含义：

| 值 | 含义 |
|---|---|
| `0` | 初始化 |
| `1` | 生成 Agent 人设 |
| `2` | 生成配置/准备脚本 |
| `3` | 中间完成态，当前代码较少使用 |
| `4` | 环境准备完成 |

### 5.5 Step 2 自动轮数计算

`Step2EnvSetup.vue` 从 `simulationConfig.time_config` 计算自动轮数：

```js
const calculatedRounds = Math.floor(
  (total_simulation_hours * 60) / minutes_per_round
)

return Math.max(calculatedRounds, 40)
```

也就是说，前端至少显示 40 轮作为推荐下限。

### 5.6 Step 2 API 调用

#### 5.6.1 创建 simulation

Step 1 已经触发：

```ts
POST /api/simulation/create
```

请求：

```json
{
  "project_id": "proj_xxxx",
  "graph_id": "graph_xxxx",
  "enable_twitter": true,
  "enable_reddit": true
}
```

响应：

```json
{
  "success": true,
  "data": {
    "simulation_id": "sim_xxxx",
    "project_id": "proj_xxxx",
    "graph_id": "graph_xxxx",
    "status": "created",
    "enable_twitter": true,
    "enable_reddit": true,
    "created_at": "..."
  }
}
```

#### 5.6.2 准备推演环境

```ts
POST /api/simulation/prepare
```

前端调用：

```js
prepareSimulation({
  simulation_id,
  use_llm_for_profiles: true,
  parallel_profile_count: 5
})
```

后端做的事情：

1. 校验 simulation 是否存在。
2. 检查是否已经准备完成。
3. 读取 project。
4. 读取 `simulation_requirement`。
5. 读取 `extracted_text.txt`。
6. 从 Zep 图谱读取实体。
7. 创建 `simulation_prepare` 异步任务。
8. 后台执行 `SimulationManager.prepare_simulation()`。

响应可能是新任务：

```json
{
  "success": true,
  "data": {
    "simulation_id": "sim_xxxx",
    "task_id": "uuid",
    "status": "preparing",
    "already_prepared": false,
    "expected_entities_count": 32,
    "entity_types": ["Investor", "Company"]
  }
}
```

也可能是已经准备完成：

```json
{
  "success": true,
  "data": {
    "simulation_id": "sim_xxxx",
    "status": "ready",
    "already_prepared": true,
    "prepare_info": {}
  }
}
```

#### 5.6.3 轮询准备任务

```ts
POST /api/simulation/prepare/status
```

请求：

```json
{
  "task_id": "uuid",
  "simulation_id": "sim_xxxx"
}
```

前端每 2 秒轮询。

关键响应字段：

```ts
type PrepareStatus = {
  status: 'pending' | 'processing' | 'completed' | 'failed' | 'ready'
  progress: number
  message: string
  progress_detail?: {
    current_stage: string
    current_stage_name: string
    stage_index: number
    total_stages: number
    stage_progress: number
    current_item: number
    total_items: number
    item_description: string
  }
  already_prepared?: boolean
}
```

后端准备阶段权重：

| stage | 总进度区间 | 含义 |
|---|---:|---|
| `reading` | 0-20 | 读取图谱实体 |
| `generating_profiles` | 20-70 | 生成 Agent profiles |
| `generating_config` | 70-90 | 生成 simulation config |
| `copying_scripts` | 90-100 | 准备推演脚本 |

#### 5.6.4 实时读取 Agent profiles

```ts
GET /api/simulation/:simulationId/profiles/realtime?platform=reddit
```

前端每 3 秒轮询。

响应用于更新：

```ts
profiles: AgentProfile[]
total_expected: number
```

#### 5.6.5 实时读取 simulation config

```ts
GET /api/simulation/:simulationId/config/realtime
```

前端每 2 秒轮询。

当响应中出现：

```json
{
  "config_generated": true,
  "config": {}
}
```

则认为 Step 2 完成。

### 5.7 Step 2 后端保存结构

目录：

```text
backend/uploads/simulations/{simulation_id}/
  state.json
  reddit_profiles.json
  twitter_profiles.csv
  simulation_config.json
```

`state.json` 对应 `SimulationState`：

```ts
type SimulationState = {
  simulation_id: string
  project_id: string
  graph_id: string
  enable_twitter: boolean
  enable_reddit: boolean
  status:
    | 'created'
    | 'preparing'
    | 'ready'
    | 'running'
    | 'paused'
    | 'completed'
    | 'failed'
  entities_count: number
  profiles_count: number
  entity_types: string[]
  config_generated: boolean
  config_reasoning?: string
  current_round: number
  twitter_status?: string
  reddit_status?: string
  created_at: string
  updated_at: string
  error?: string
}
```

`simulation_config.json` 是 Step 3 运行推演脚本的主配置。React 前端通常不需要完全理解它，但需要读取以下字段用于展示和轮数计算：

```ts
type SimulationConfig = {
  time_config?: {
    total_simulation_hours: number
    minutes_per_round: number
  }
  event_config?: {
    narrative_direction?: string
    hot_topics?: string[]
  }
  initial_posts?: any[]
  twitter_config?: Record<string, any>
  reddit_config?: Record<string, any>
}
```

### 5.8 Step 2 到 Step 3 跳转

触发组件：

```text
Step2EnvSetup.vue
```

触发函数：

```js
handleStartSimulation()
```

如果用户启用自定义轮数：

```js
emit('next-step', { maxRounds: customMaxRounds.value })
```

父页面 `SimulationView.vue` 接收后跳转：

```js
router.push({
  name: 'SimulationRun',
  params: { simulationId },
  query: { maxRounds }
})
```

React 迁移时：

```ts
navigate(`/simulation/${simulationId}/start?maxRounds=${maxRounds}`)
```

如果使用自动轮数，不传 query。

---

## 6. Step 3：推演运行

### 6.1 页面和组件

源文件：

- 页面：`frontend/src/pages/SimulationRunView.vue`
- 业务组件：`frontend/src/components/Step3Simulation.vue`
- API：`frontend/src/api/simulation.js`
- 报告 API：`frontend/src/api/report.js`
- 后端 Controller：`backend/app/controllers/simulation.py`
- 后端 Runner：`backend/app/services/simulation_runner.py`

路由：

```text
/simulation/:simulationId/start
```

可选 query：

```text
?maxRounds=40
```

### 6.2 页面职责

`SimulationRunView.vue` 负责：

1. 读取 `simulationId`。
2. 从 query 读取 `maxRounds`。
3. 加载 simulation。
4. 加载 simulation config，得到 `minutes_per_round`。
5. 加载 project 和 graph。
6. 推演运行时每 30 秒刷新图谱。
7. 返回 Step 2 时关闭/停止正在运行的推演。

`Step3Simulation.vue` 负责：

1. 自动启动推演。
2. 如果已有运行中推演，恢复运行状态。
3. 如果已有完成或停止的推演，直接进入可生成报告状态。
4. 轮询运行状态。
5. 轮询 Agent 行为详情。
6. 展示 Twitter/Reddit 双平台行为流。
7. 达到条件后生成报告。
8. 跳转 Step 4。

### 6.3 Step 3 前端状态

```ts
type Step3State = {
  isGeneratingReport: boolean
  phase: 0 | 1 | 2
  isStarting: boolean
  isStopping: boolean
  startError: string | null
  runStatus: RunStatus
  allActions: AgentAction[]
  actionIds: Set<string>
}
```

`phase` 含义：

| 值 | 含义 |
|---|---|
| `0` | 未开始 |
| `1` | 运行中 |
| `2` | 已完成或已停止，允许生成报告 |

### 6.4 报告生成解锁条件

`Step3Simulation.vue` 中有一个硬性阈值：

```js
const EARLY_REPORT_MIN_ROUNDS = 40
```

允许生成报告的条件：

```js
phase === 2 || completedRoundForReport >= 40
```

`completedRoundForReport` 取以下值的最大值：

```js
max(
  runStatus.current_round,
  runStatus.twitter_current_round,
  runStatus.reddit_current_round
)
```

这意味着：

1. 推演完整完成后可以生成报告。
2. 如果推演仍在运行，但已经达到 40 轮，也可以提前停止并生成报告。

### 6.5 Step 3 API 调用

#### 6.5.1 启动推演

```ts
POST /api/simulation/start
```

前端调用：

```js
startSimulation({
  simulation_id,
  platform: 'parallel',
  force: true,
  enable_graph_memory_update: true,
  max_rounds?: number
})
```

后端做的事情：

1. 校验 simulation。
2. 校验 simulation 是否 ready。
3. 如果 `force: true`，清理旧运行日志。
4. 如果启用 `enable_graph_memory_update`，确认 graph_id 存在。
5. 调用 `SimulationRunner.start_simulation()`。
6. 启动推演脚本。
7. 保存 `run_state.json`。
8. 启动监控线程。
9. 将 simulation 状态改成 `running`。

响应：

```ts
type StartSimulationResponse = {
  simulation_id: string
  runner_status: 'starting' | 'running'
  process_pid: number
  twitter_running: boolean
  reddit_running: boolean
  started_at: string
  graph_memory_update_enabled: boolean
  force_restarted: boolean
  max_rounds_applied?: number
}
```

#### 6.5.2 查询运行状态

```ts
GET /api/simulation/:simulationId/run-status
```

前端每 2 秒轮询。

用于展示：

- runner 状态
- 当前轮次
- Twitter 当前轮次
- Reddit 当前轮次
- action 计数
- 是否完成

#### 6.5.3 查询详细运行状态

```ts
GET /api/simulation/:simulationId/run-status/detail
```

前端每 3 秒轮询。

用于获取：

```ts
all_actions: AgentAction[]
twitter_actions: AgentAction[]
reddit_actions: AgentAction[]
recent_actions: AgentAction[]
run_state: RunStatus
```

前端会用 `actionIds` 去重，然后追加到 `allActions`。

#### 6.5.4 停止推演

```ts
POST /api/simulation/stop
```

请求：

```json
{
  "simulation_id": "sim_xxxx"
}
```

使用场景：

1. 用户点击停止。
2. 用户提前生成报告时，先停止正在运行的推演。
3. 用户从 Step 3 返回 Step 2。

#### 6.5.5 生成报告

```ts
POST /api/report/generate
```

Step 3 触发的请求：

```js
generateReport({
  simulation_id,
  force_regenerate: true,
  report_type: 'both'
})
```

虽然请求 `report_type: 'both'`，但五步工作流主线进入的是 narrative report。

响应：

```ts
type GenerateReportResponse = {
  simulation_id: string
  report_id: string
  narrative_report_id: string
  financial_report_id: string
  report_type: 'both'
  task_id: string
  status: 'generating'
  already_generated: boolean
}
```

跳转 Step 4：

```js
router.push({
  name: 'ReportReplay',
  params: { reportId },
  query: {
    task_id,
    simulation_id
  }
})
```

React 迁移：

```ts
navigate(`/report/${reportId}/replay?task_id=${taskId}&simulation_id=${simulationId}`)
```

### 6.6 Step 3 后端运行结构

`SimulationRunner.start_simulation()` 会在 simulation 目录下写入运行文件：

```text
backend/uploads/simulations/{simulation_id}/
  simulation_config.json
  run_state.json
  simulation.log
  twitter/
    actions.jsonl
  reddit/
    actions.jsonl
```

`run_state.json` 对应 `SimulationRunState`：

```ts
type SimulationRunState = {
  simulation_id: string
  runner_status:
    | 'idle'
    | 'starting'
    | 'running'
    | 'completed'
    | 'failed'
    | 'stopped'
  current_round: number
  total_rounds: number
  simulated_hours: number
  twitter_current_round: number
  reddit_current_round: number
  twitter_actions_count: number
  reddit_actions_count: number
  twitter_running: boolean
  reddit_running: boolean
  twitter_completed: boolean
  reddit_completed: boolean
  recent_actions: AgentAction[]
  started_at?: string
  completed_at?: string
  error?: string
  process_pid?: number
}
```

`AgentAction` 结构：

```ts
type AgentAction = {
  round_num: number
  timestamp: string
  platform: 'twitter' | 'reddit'
  agent_id: string | number
  agent_name?: string
  action_type:
    | 'CREATE_POST'
    | 'REPOST'
    | 'LIKE_POST'
    | 'CREATE_COMMENT'
    | 'LIKE_COMMENT'
    | 'DO_NOTHING'
    | 'FOLLOW'
    | 'SEARCH_POSTS'
    | 'QUOTE_POST'
    | 'UPVOTE_POST'
    | 'DOWNVOTE_POST'
    | string
  action_args?: Record<string, any>
  result?: Record<string, any>
  success: boolean
}
```

### 6.7 Step 3 到 Step 4 跳转

触发组件：

```text
Step3Simulation.vue
```

触发函数：

```js
handleNextStep()
```

逻辑：

```text
if 没有达到 40 轮且推演未完成
  -> 不允许生成报告

if 推演仍在运行
  -> stopSimulation()
  -> phase = completed

generateReport({
  simulation_id,
  force_regenerate: true,
  report_type: 'both'
})

router.push('/report/:reportId/replay?task_id=:taskId&simulation_id=:simulationId')
```

---

## 7. Step 4：报告生成回放

### 7.1 页面和组件

源文件：

- 页面：`frontend/src/pages/ReportView.vue`
- 业务组件：`frontend/src/components/Step4Report.vue`
- 报告 API：`frontend/src/api/report.js`
- 后端 Controller：`backend/app/controllers/report.py`
- 报告 Agent：`backend/app/services/report_agent.py`

路由：

```text
/report/:reportId/replay
```

常见 query：

```text
?task_id=uuid&simulation_id=sim_xxxx
```

### 7.2 页面职责

`ReportView.vue` 负责：

1. 读取 `reportId`。
2. 调用 `getReport(reportId)` 获取 report 元信息。
3. 从 report 中拿到 `simulation_id` 和 `graph_id`。
4. 加载 simulation。
5. 加载 project。
6. 加载 graph。
7. 将 `reportId`、`simulationId`、日志状态传给 `Step4Report.vue`。

`Step4Report.vue` 负责：

1. 轮询报告生成状态。
2. 轮询结构化 agent 日志。
3. 轮询控制台日志。
4. 根据 agent 日志实时还原 outline 和 section。
5. 报告完成后读取完整 Markdown。
6. 展示已生成章节、预测卡片、persona、dashboard 等。
7. 失败时尝试恢复或重新生成。
8. 跳转 Step 5。

### 7.3 Step 4 前端状态

```ts
type Step4State = {
  agentLogs: AgentLog[]
  consoleLogs: string[]
  agentLogLine: number
  consoleLogLine: number
  reportOutline: ReportOutline | null
  dashboardData: any | null
  dashboardLoading: boolean
  reportStatus: ReportStatusResponse | null
  hasHydratedCompletedReport: boolean
  isRecoveringFailedReport: boolean
  currentSectionIndex: number | null
  generatedSections: Record<number, string>
  expandedContent: Set<number>
  expandedLogs: Set<string>
  collapsedSections: Set<number>
  isComplete: boolean
  startTime: Date | null
  profiles: AgentProfile[]
  profileChatTarget: string
  selectedProfile: AgentProfile | null
  profileChatHistory: any[]
}
```

### 7.4 Step 4 API 调用

#### 7.4.1 查询报告生成状态

```ts
GET /api/report/generate/status
```

查询参数来自：

```ts
{
  task_id?: string
  simulation_id?: string
  report_id?: string
}
```

前端每 2 秒轮询。

后端查询顺序：

1. 如果传了 `report_id`，先读取持久化 report。
2. 如果传了 `task_id`，查内存中的 `TaskManager`。
3. 如果传了 `simulation_id`，查该 simulation 下已有 completed report。
4. 都没有则返回 generating placeholder。

#### 7.4.2 读取结构化 Agent 日志

```ts
GET /api/report/:reportId/agent-log?from_line=0
```

前端每 2 秒轮询。

日志文件：

```text
backend/uploads/reports/{report_id}/agent_log.jsonl
```

重要 action：

| action | 前端处理 |
|---|---|
| `report_start` | 设置开始时间 |
| `planning_complete` | 设置 `reportOutline` |
| `section_start` | 设置当前生成中的 section |
| `section_complete` | 把 `details.content` 写入 `generatedSections` |
| `report_complete` | 标记完成，停止轮询，读取完整报告 |
| `error` | 显示失败，触发恢复逻辑 |

#### 7.4.3 读取控制台日志

```ts
GET /api/report/:reportId/console-log?from_line=0
```

前端每 1.5 秒轮询。

日志文件：

```text
backend/uploads/reports/{report_id}/console_log.txt
```

#### 7.4.4 读取报告详情

```ts
GET /api/report/:reportId
```

用于：

1. 页面初始化反查 simulation。
2. 已完成报告 hydrate。
3. Step 5 加载完整 Markdown。

响应中的关键字段：

```ts
type Report = {
  report_id: string
  simulation_id: string
  graph_id: string
  simulation_requirement: string
  status:
    | 'pending'
    | 'planning'
    | 'generating'
    | 'completed'
    | 'failed'
  outline?: ReportOutline
  markdown_content?: string
  created_at: string
  completed_at?: string
  error?: string
  report_type: 'narrative' | 'financial'
  financial_context?: Record<string, any>
}
```

### 7.5 后端报告生成逻辑

后端入口：

```py
backend/app/controllers/report.py
generate_report()
```

请求：

```json
{
  "simulation_id": "sim_xxxx",
  "force_regenerate": true,
  "report_type": "both"
}
```

后端做的事情：

1. 校验 simulation。
2. 如果 `force_regenerate` 为 false，则尝试复用已有 completed report。
3. 读取 project。
4. 读取 graph_id。
5. 读取 simulation_requirement。
6. 生成 `narrative_report_id`。
7. 生成 `financial_report_id`。
8. 创建 `report_generate` 异步任务。
9. 后台线程先生成 narrative report。
10. 如果 `report_type` 是 `both`，再生成 financial report。
11. 完成后把 task 标记为 completed。

叙事报告实际生成：

```py
backend/app/services/report_agent.py
ReportAgent.generate_report()
```

生成阶段：

```text
pending
  -> planning
  -> generating
  -> completed
```

失败则：

```text
failed
```

### 7.6 报告保存结构

目录：

```text
backend/uploads/reports/{report_id}/
  meta.json
  outline.json
  progress.json
  section_01.md
  section_02.md
  ...
  full_report.md
  agent_log.jsonl
  console_log.txt
```

文件含义：

| 文件 | 作用 |
|---|---|
| `meta.json` | 报告元信息，对应 `Report.to_dict()` |
| `outline.json` | 报告大纲 |
| `progress.json` | 当前阶段、百分比、当前章节、已完成章节 |
| `section_XX.md` | 单章节内容 |
| `full_report.md` | 最终完整 Markdown |
| `agent_log.jsonl` | 前端 Step 4 实时回放的结构化事件 |
| `console_log.txt` | 控制台文本日志 |

`ReportAgent.generate_report()` 的核心生成顺序：

```text
1. 创建 reports/{report_id}/
2. 初始化 ReportLogger -> agent_log.jsonl
3. 初始化 ReportConsoleLogger -> console_log.txt
4. 保存初始 meta.json
5. plan_outline()
6. 保存 outline.json
7. 对每个 section 调用 _generate_section_react()
8. 保存 section_XX.md
9. 写 section_complete 日志
10. assemble_full_report()
11. 保存 full_report.md
12. 更新 meta.json 为 completed
13. 写 report_complete 日志
```

当前 narrative report 有一个特殊处理：

```text
非 financial 报告会把规划出来的多个章节合并为一个章节：
Narrative Forecast Report
```

因此前端最后往往将完整叙事报告视作 `Full Report` 展示。

### 7.7 Step 4 失败恢复逻辑

`Step4Report.vue` 内有恢复逻辑：

1. 如果报告状态是 failed。
2. 先根据 `simulation_id` 查询是否已有 completed narrative report。
3. 如果有，跳转到已有 completed report。
4. 如果没有，重新调用：

```js
generateReport({
  simulation_id,
  force_regenerate: true,
  report_type: 'both'
})
```

5. 成功后 replace 当前路由到新的 `reportId`。

React 迁移建议：

- 将恢复逻辑抽成 `recoverReport(reportId, simulationId)`。
- 避免直接散落在组件里。
- 保持路由 replace，而不是 push，避免浏览器历史里留下失败 report。

### 7.8 Step 4 到 Step 5 跳转

触发组件：

```text
Step4Report.vue
```

触发函数：

```js
goToInteraction()
```

跳转：

```js
router.push({
  name: 'Interaction',
  params: { reportId }
})
```

React 迁移：

```ts
navigate(`/interaction/${reportId}`)
```

---

## 8. Step 5：报告交互

### 8.1 页面和组件

源文件：

- 页面：`frontend/src/pages/InteractionView.vue`
- 业务组件：`frontend/src/components/Step5Interaction.vue`
- 报告 API：`frontend/src/api/report.js`

路由：

```text
/interaction/:reportId
```

### 8.2 页面职责

`InteractionView.vue` 负责：

1. 读取 `reportId`。
2. 读取 report。
3. 从 report 反查 `simulation_id`。
4. 加载 simulation。
5. 加载 project。
6. 加载 graph。
7. 如果当前 report 是 financial report，尝试查找同 simulation 的 narrative report。
8. 如果当前 report 是 narrative report，尝试查找同 simulation 的 financial report。
9. 渲染 `Step5Interaction.vue`。

`Step5Interaction.vue` 负责：

1. 读取完整 report。
2. 优先使用 `markdown_content`。
3. 如果没有 `markdown_content`，从 outline section 中拼接。
4. 移除 Observed/Inferred/Simulated 标签。
5. 如果 report failed，尝试复用或重新生成。
6. 如果 report 仍在生成，读取 agent logs 拼接已生成 section。
7. 展示最终 Markdown 报告。

### 8.3 Step 5 前端状态

```ts
type Step5State = {
  reportOutline: ReportOutline | null
  generatedSections: Record<number, string>
  reportLoadError: string
  reportLoadElapsed: number
  isRecoveringFailedReport: boolean
}
```

加载超时：

```js
const REPORT_LOAD_TIMEOUT_MS = 30000
```

如果 30 秒内没有拿到 outline，会显示错误提示。

### 8.4 Step 5 报告加载逻辑

入口：

```js
loadReportData()
```

流程：

```text
getReport(reportId)
  -> if failed and no markdown_content
       recoverFailedReport()
  -> else applyMarkdownReport(report)
  -> if completed or has markdown_content
       emit completed
  -> else loadAgentLogs()
```

`applyMarkdownReport()` 的逻辑：

```text
report.markdown_content
  -> 直接作为 Full Report

否则：
report.outline.sections[].content
  -> 拼接成 Markdown
```

最终：

```ts
generatedSections = {
  1: fullMarkdown
}
```

### 8.5 Step 5 API 调用

#### 8.5.1 读取报告

```ts
GET /api/report/:reportId
```

#### 8.5.2 读取同 simulation 报告

```ts
GET /api/report/by-simulation/:simulationId?report_type=both
```

用于失败恢复和 narrative/financial 配对。

#### 8.5.3 读取 Agent 日志

```ts
GET /api/report/:reportId/agent-log?from_line=0
```

用于报告还没完整保存时，从日志恢复：

- `planning_complete`
- `section_complete`

#### 8.5.4 重新生成报告

```ts
POST /api/report/generate
```

请求：

```json
{
  "simulation_id": "sim_xxxx",
  "force_regenerate": true,
  "report_type": "both"
}
```

### 8.6 Step 5 展示规则

`Step5Interaction.vue` 会清理叙事层标签：

```text
Observed / Inferred / Simulated
Observed Facts
Inferred Drivers
Simulated Scenarios
Observed
Inferred
Simulated
```

迁移时注意：

- 如果新 React App 需要保留这些标签，不要照搬这个清理逻辑。
- 如果目标产品强调最终用户阅读体验，可以继续清理。

---

## 9. 后端核心数据结构总表

### 9.1 Project

源文件：

```text
backend/app/repositories/project_repository.py
```

用途：

保存 Step 1 的项目、文件、本体、图谱 ID、模拟需求。

保存路径：

```text
backend/uploads/projects/{project_id}/project.json
```

### 9.2 Task

源文件：

```text
backend/app/repositories/task_repository.py
```

用途：

保存异步任务状态，包括：

- graph build
- simulation prepare
- report generate

重要限制：

```text
TaskManager 是内存单例，不是持久化队列。
服务重启后 task_id 对应的内存状态会丢失。
```

React 迁移注意：

- 前端不要只依赖 task 状态。
- 需要像当前代码一样，在 task 丢失时从持久化结果反查：
  - project.status
  - simulation state/config files
  - report meta/full_report

### 9.3 SimulationState

源文件：

```text
backend/app/services/simulation_manager.py
```

用途：

保存 simulation 基础状态、Agent 准备结果、配置生成状态。

保存路径：

```text
backend/uploads/simulations/{simulation_id}/state.json
```

### 9.4 SimulationRunState

源文件：

```text
backend/app/services/simulation_runner.py
```

用途：

保存 Step 3 运行态：

- 当前轮次
- 双平台状态
- action 计数
- 进程 PID
- 最近行为
- 错误信息

保存路径：

```text
backend/uploads/simulations/{simulation_id}/run_state.json
```

### 9.5 AgentAction

源文件：

```text
backend/app/services/simulation_runner.py
```

用途：

表示推演中的单条 Agent 行为。

来源文件：

```text
backend/uploads/simulations/{simulation_id}/twitter/actions.jsonl
backend/uploads/simulations/{simulation_id}/reddit/actions.jsonl
```

### 9.6 Report

源文件：

```text
backend/app/services/report_agent.py
```

用途：

保存叙事报告或金融报告。

保存路径：

```text
backend/uploads/reports/{report_id}/meta.json
```

### 9.7 ReportOutline 和 ReportSection

源文件：

```text
backend/app/services/report_agent.py
```

用途：

保存报告大纲和章节。

保存路径：

```text
backend/uploads/reports/{report_id}/outline.json
backend/uploads/reports/{report_id}/section_XX.md
```

---

## 10. API 清单

### 10.1 Graph API

| 方法 | 路径 | 用途 | 前端封装 |
|---|---|---|---|
| `POST` | `/api/graph/ontology/generate` | 文件上传并生成 ontology | `generateOntology()` |
| `POST` | `/api/graph/ontology/generate-from-articles` | 文章输入并生成 ontology | `generateOntologyFromArticles()` |
| `POST` | `/api/graph/build` | 构建 Zep 图谱 | `buildGraph()` |
| `GET` | `/api/graph/task/:taskId` | 查询图谱构建任务 | `getTaskStatus()` |
| `GET` | `/api/graph/data/:graphId` | 获取图谱数据 | `getGraphData()` |
| `GET` | `/api/graph/project/:projectId` | 获取项目 | `getProject()` |

### 10.2 Simulation API

| 方法 | 路径 | 用途 | 前端封装 |
|---|---|---|---|
| `POST` | `/api/simulation/create` | 创建 simulation | `createSimulation()` |
| `POST` | `/api/simulation/prepare` | 准备 simulation | `prepareSimulation()` |
| `POST` | `/api/simulation/prepare/status` | 查询准备进度 | `getPrepareStatus()` |
| `GET` | `/api/simulation/:simulationId` | 获取 simulation | `getSimulation()` |
| `GET` | `/api/simulation/:simulationId/profiles/realtime` | 实时 profiles | `getSimulationProfilesRealtime()` |
| `GET` | `/api/simulation/:simulationId/config` | 获取配置 | `getSimulationConfig()` |
| `GET` | `/api/simulation/:simulationId/config/realtime` | 实时配置 | `getSimulationConfigRealtime()` |
| `POST` | `/api/simulation/start` | 启动推演 | `startSimulation()` |
| `POST` | `/api/simulation/stop` | 停止推演 | `stopSimulation()` |
| `GET` | `/api/simulation/:simulationId/run-status` | 运行状态 | `getRunStatus()` |
| `GET` | `/api/simulation/:simulationId/run-status/detail` | 运行详情和 actions | `getRunStatusDetail()` |
| `POST` | `/api/simulation/env-status` | 检查环境进程 | `getEnvStatus()` |
| `POST` | `/api/simulation/close-env` | 关闭环境进程 | `closeSimulationEnv()` |
| `GET` | `/api/simulation/history` | 首页历史记录 | `getSimulationHistory()` |
| `DELETE` | `/api/simulation/:simulationId` | 删除推演 | `deleteSimulation()` |

### 10.3 Report API

| 方法 | 路径 | 用途 | 前端封装 |
|---|---|---|---|
| `POST` | `/api/report/generate` | 生成报告 | `generateReport()` |
| `GET/POST` | `/api/report/generate/status` | 查询报告生成状态 | `getReportStatus()` |
| `GET` | `/api/report/:reportId` | 获取报告 | `getReport()` |
| `GET` | `/api/report/by-simulation/:simulationId` | 根据 simulation 获取报告 | `getReportBySimulation()` |
| `GET` | `/api/report/:reportId/agent-log` | 获取结构化日志 | `getAgentLog()` |
| `GET` | `/api/report/:reportId/console-log` | 获取控制台日志 | `getConsoleLog()` |
| `POST` | `/api/report/chat` | 与 Report Agent 对话 | `chatWithReport()` |

---

## 11. React 迁移建议

### 11.1 推荐目录结构

```text
src/
  app/
    router.tsx
  features/
    workflow/
      WorkflowShell.tsx
      WorkflowStepper.tsx
      workflowResolver.ts
      types.ts
    graph/
      GraphPanel.tsx
      graphApi.ts
      types.ts
    step1/
      Step1Page.tsx
      Step1GraphBuildPanel.tsx
      useStep1Project.ts
    step2/
      Step2Page.tsx
      Step2EnvSetupPanel.tsx
      usePrepareSimulation.ts
    step3/
      Step3Page.tsx
      Step3SimulationPanel.tsx
      useSimulationRun.ts
    step4/
      Step4ReportReplayPage.tsx
      Step4ReportPanel.tsx
      useReportGeneration.ts
    step5/
      Step5InteractionPage.tsx
      Step5InteractionPanel.tsx
      useReportMarkdown.ts
  shared/
    api/
      http.ts
    hooks/
      usePolling.ts
      useSystemLogs.ts
    ui/
      Button.tsx
      Panel.tsx
      StatusBadge.tsx
```

### 11.2 推荐状态机

React 版本可以把五步流程理解成一个跨页面状态机：

```ts
type WorkflowContext = {
  projectId?: string
  graphId?: string
  simulationId?: string
  reportId?: string
  narrativeReportId?: string
  financialReportId?: string
}
```

每个页面只需要维护自己的局部状态，但 Stepper 需要能根据当前 route 反查 context：

```text
reportId -> getReport(reportId) -> simulationId
simulationId -> getSimulation(simulationId) -> projectId
simulationId -> getSimulationReports(simulationId) -> reportId
projectId -> getProject(projectId) -> graphId
```

### 11.3 推荐 hooks

#### `useStep1Project(projectId)`

职责：

- 处理 `/process/new`
- 调用 ontology API
- 调用 build graph API
- 轮询 graph task
- 返回 projectData、graphData、phase、logs、error

#### `usePrepareSimulation(simulationId)`

职责：

- 自动调用 prepare API
- 轮询 prepare status
- 轮询 profiles
- 轮询 config
- 计算 autoGeneratedRounds
- 返回 phase、profiles、simulationConfig、canStart

#### `useSimulationRun(simulationId, maxRounds)`

职责：

- 自动启动 simulation
- 轮询 run-status
- 轮询 run-status/detail
- 去重 actions
- 暴露 stopSimulation()
- 暴露 generateReport()

#### `useReportGeneration(reportId, taskId, simulationId)`

职责：

- 轮询 report status
- 轮询 agent-log
- 轮询 console-log
- 还原 outline 和 sections
- hydrate completed report
- recover failed report

#### `useReportMarkdown(reportId)`

职责：

- Step 5 读取最终报告
- 优先使用 markdown_content
- fallback 到 outline sections
- fallback 到 agent-log
- 处理 30 秒超时

### 11.4 轮询频率保持一致

| 场景 | 当前频率 | React 建议 |
|---|---:|---|
| Graph build task | 2s | 保持 2s |
| Graph build 期间 graph data | 10s | 保持 10s |
| Step 2 prepare status | 2s | 保持 2s |
| Step 2 profiles realtime | 3s | 保持 3s |
| Step 2 config realtime | 2s | 保持 2s |
| Step 3 run-status | 2s | 保持 2s |
| Step 3 run-status/detail | 3s | 保持 3s |
| Step 3 graph refresh | 30s | 保持 30s |
| Step 4 report status | 2s | 保持 2s |
| Step 4 agent-log | 2s | 保持 2s |
| Step 4 console-log | 1.5s | 保持 1.5s |

### 11.5 错误和恢复策略

迁移时必须保留以下恢复能力：

1. Step 1 刷新页面后，如果 project 已经 `graph_building`，继续根据 `graph_build_task_id` 轮询。
2. Step 1 刷新页面后，如果 project 已经 `graph_completed`，直接加载 graph。
3. Step 2 如果 simulation 已经 prepared，直接加载已有 profiles 和 config。
4. Step 3 如果 simulation 已经 running，恢复状态而不是重复启动。
5. Step 3 如果 simulation 已经 completed/stopped，直接允许生成报告。
6. Step 4 如果 task 状态丢失，从 report 文件和 simulation reports 反查。
7. Step 4 如果 report failed，优先复用已有 completed report，再重新生成。
8. Step 5 如果 report 没有完整 Markdown，尝试从 agent-log 还原章节。

### 11.6 不建议直接照搬的地方

1. Vue 代码中 `MainView.vue` 的 `currentStep` 仍保留 1-5 的旧本地状态，但当前页面实际只承担 Step 1。React 应该用路由而不是本地 `currentStep++` 控制跨页面步骤。
2. `useWorkflowResolver.js` 里 `step1_2` 同时覆盖了旧设计的 Step 1-2，但现在 Step 2 已经在 `SimulationView.vue`。React 迁移时建议拆成 `step1` 和 `step2`。
3. `TaskManager` 是内存态，React 不能假设 task 永远可查。
4. Step 4 组件很大，迁移时应该拆成：
   - `ReportProgressTimeline`
   - `ReportSectionList`
   - `AgentLogPanel`
   - `ConsoleLogPanel`
   - `ReportRecoveryBoundary`
   - `ReportPersonaPanel`
5. Step 5 当前会删除 Observed/Inferred/Simulated 标签。是否保留取决于新产品需求。

---

## 12. 历史记录入口

虽然历史记录不是五步工作流主线，但迁移到新 App 时通常也需要恢复入口。

源文件：

- `frontend/src/pages/HomeV2.vue`
- `frontend/src/components/HistoryDatabase.vue`
- `frontend/src/api/simulation.js`
- `backend/app/controllers/simulation.py`

首页中历史区域：

```text
HomeV2.vue
  -> HistoryDatabase.vue
```

API：

```ts
GET /api/simulation/history?limit=20
```

后端会扫描：

```text
backend/uploads/simulations/
backend/uploads/reports/
backend/uploads/projects/
```

并返回每条 simulation 的：

```ts
type SimulationHistoryItem = {
  simulation_id: string
  project_id?: string
  report_id?: string
  narrative_report_id?: string
  financial_report_id?: string
  simulation_requirement?: string
  files?: Array<{ filename: string }>
  created_at?: string
  current_round?: number
  total_rounds?: number
  status?: string
}
```

历史弹窗支持跳转：

```text
Step 1 -> /process/:projectId
Step 2 -> /simulation/:simulationId
Step 5 -> /interaction/:reportId
```

当前历史入口没有直接跳 Step 3 或 Step 4 的主按钮，但可以根据 ID 自行扩展。

---

## 13. 最小迁移闭环

如果要在 React App 中先做一个可运行的最小闭环，建议按以下顺序迁移：

1. `http client`
2. `graphApi.ts`
3. `simulationApi.ts`
4. `reportApi.ts`
5. `WorkflowShell`
6. `WorkflowStepper`
7. Step 1 页面：文件上传上下文、ontology、graph build、create simulation
8. Step 2 页面：prepare、profiles、config、start button
9. Step 3 页面：start simulation、run-status、actions、generate report
10. Step 4 页面：report status、agent-log、console-log、sections
11. Step 5 页面：load markdown report

最小闭环中可以先不迁移：

- Unified Report
- financial report 展示
- persona chat
- dashboard widgets
- backtest/validation
- sentiment 前置页

---

## 14. 源文件索引

### 前端页面

```text
frontend/src/pages/MainView.vue
frontend/src/pages/SimulationView.vue
frontend/src/pages/SimulationRunView.vue
frontend/src/pages/ReportView.vue
frontend/src/pages/InteractionView.vue
```

### 前端业务组件

```text
frontend/src/components/Step1GraphBuild.vue
frontend/src/components/Step2EnvSetup.vue
frontend/src/components/Step3Simulation.vue
frontend/src/components/Step4Report.vue
frontend/src/components/Step5Interaction.vue
frontend/src/components/WorkflowStepper.vue
frontend/src/components/HistoryDatabase.vue
```

### 前端 API

```text
frontend/src/api/graph.js
frontend/src/api/articles.js
frontend/src/api/simulation.js
frontend/src/api/report.js
frontend/src/api/reportV2.js
```

其中 `reportV2.js` 主要服务 Unified/dashboard 展示，五步主流程不强依赖。

### 后端 Controller

```text
backend/app/controllers/graph.py
backend/app/controllers/articles.py
backend/app/controllers/simulation.py
backend/app/controllers/report.py
```

### 后端 Service 和 Repository

```text
backend/app/repositories/project_repository.py
backend/app/repositories/task_repository.py
backend/app/services/simulation_manager.py
backend/app/services/simulation_runner.py
backend/app/services/report_agent.py
```

### 后端保存目录

```text
backend/uploads/projects/
backend/uploads/simulations/
backend/uploads/reports/
```

---

## 15. 迁移验收清单

React 版本完成后，用下面清单验证：

- [ ] 能从 `/process/new` 或新 App 的上传入口创建 project。
- [ ] 能生成 ontology。
- [ ] 能自动启动 graph build。
- [ ] 刷新 Step 1 后能恢复 project 状态。
- [ ] graph completed 后能创建 simulation。
- [ ] 能进入 `/simulation/:simulationId`。
- [ ] Step 2 能自动 prepare simulation。
- [ ] 能看到 profiles 增量生成。
- [ ] 能看到 config 生成完成。
- [ ] 能使用自动轮数进入 Step 3。
- [ ] 能使用自定义 maxRounds 进入 Step 3。
- [ ] Step 3 能启动 parallel simulation。
- [ ] 能轮询 run-status。
- [ ] 能显示 Twitter/Reddit actions。
- [ ] 不到 40 轮时不能生成报告。
- [ ] 达到 40 轮或完成后能生成报告。
- [ ] 生成报告前若推演仍在运行，会先 stop simulation。
- [ ] 能进入 `/report/:reportId/replay`。
- [ ] Step 4 能轮询 report status。
- [ ] Step 4 能根据 agent-log 实时显示 outline 和 section。
- [ ] Step 4 完成后能读取 full_report.md。
- [ ] Step 4 能跳转 Step 5。
- [ ] Step 5 能读取 markdown_content。
- [ ] Step 5 能 fallback 到 outline sections。
- [ ] Step 5 能 fallback 到 agent-log。
- [ ] 服务重启导致 task 丢失时，前端能通过持久化文件恢复状态。

