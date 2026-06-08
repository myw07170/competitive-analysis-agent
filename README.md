# 🎯 AI 驱动的竞品分析智能体系统

> 一个多智能体协作系统，将竞品分析的端到端流程自动化——从公开信息采集到结构化竞品报告，并内置跨智能体的审查与反馈闭环。

[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org)
[![LangGraph](https://img.shields.io/badge/orchestration-LangGraph-orange.svg)](https://langchain-ai.github.io/langgraph/)
[![React](https://img.shields.io/badge/frontend-React%2018-61dafb.svg)](https://react.dev)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

---

## 1. 项目简介

给定一个产品名称和一个目标市场（🇨🇳 中国 / 🇺🇸 美国），系统会启动一支由多个专职智能体组成的"数字调研团队"，它们协作完成以下工作：

1. **采集（Collect）** 竞品的公开信息（网络搜索、遵循 robots.txt 的网页抓取、问卷式综合、模拟用户访谈）。
2. **结构化（Structure）** 把信息对齐到一套严格的竞品知识 **Schema**（功能树、定价模型、用户画像）。
3. **分析（Analyze）** 竞品（SWOT、市场定位、差异化）。
4. **撰写（Write）** 一份精炼且可溯源的报告。
5. **质量管控（QC）** 输出结果——QC 智能体同时审查采集到的知识和最终报告，然后把问题退回给**具体的**上游负责智能体（采集 / 分析 / 撰写）进行**真实、定向**的返工，而非伪装的循环。

每一条结论都**可溯源**（URL / 文档 / 访谈 ID）并附带置信度分数，每一个智能体决策都可通过结构化日志和追踪记录被**观测**。审阅者可以**就地编辑任意字段**（人在回路 / human-in-the-loop），而这些编辑会进入一个**主动学习闭环**，对后续运行产生引导。

---

## 2. 对照评分维度的亮点

| 评分维度 | 本项目如何应对 |
| --- | --- |
| **多智能体协作与可信度（35%）** | 四个职责互不重叠的专职智能体；带可视化的 LangGraph DAG；**结构化的智能体间协议**——每一次交接都是一个经校验的 Pydantic 对象（`CompetitorKnowledge`、`QCReport`），QC 返工以带类型的 `AgentMessage(intent="request_rework")` 形式派发并记入追踪；**真实、按角色定向的反馈闭环**——QC 同时审查采集到的知识*与最终报告*，再把返工路由到拥有该缺陷的智能体（采集 / 分析 / 撰写），并只重新采集被标记的竞品；严格的 schema 校验；每条事实都携带带置信度的 `SourceRef`。 |
| **技术深度与工程能力（25%）** | 端到端技术栈（采集 → 编排 → 知识存储 → API → 前端）；每个智能体的追踪记录含 prompt / 输入 / 输出 / token；**置信度感知的编排**、**跨来源冲突检测**、自一致性投票、引用强制校验；每个竞品并发采集；**DAG 检查点 + 断点续跑**；外置的运行注册表；重试 / 超时 / 兜底封装；用于稳定演示的 mock 模式。 |
| **业务价值与用户体验（20%）** | 贴合真实工作流（输入 → DAG 进度 → 报告 → 追踪 → **人在回路编辑** → 回放）；可量化指标（耗时、来源覆盖率、schema 完整度、平均置信度、冲突数、**人工修正率**）记录于 `metrics`；**跨运行的知识演化**（对比同一竞品在不同运行间的变化）；**智能体自评**并提出 schema 变更建议；市场可插拔架构（今天支持 CN / US，可扩展至任意市场）。 |
| **代码质量与文档（10%）** | 模块化布局、带类型注解的 Python、完整记录的智能体协议、架构图、部署指南、扩展指南；后端 `pytest` 测试套件 + 前端类型检查 / 构建均在 **CI** 中运行（`.github/workflows/ci.yml`）。 |
| **合规与材料（10%）** | 每次抓取都有 `robots.txt` 守卫，采集器遵守 ToS，纯合成的访谈 / 问卷数据均明确标注（真实数据导入 + 强制 PII 脱敏环节**作为 v1.1 计划项**列出，见 [`docs/compliance.md`](docs/compliance.md) §4）；声明使用的 LLM（火山方舟 Volcengine Ark）与搜索服务商；完整的提交材料（方案、视频脚本、代码仓库）。 |

---

## 2.1 已实现能力（v1.1）

在基础流水线之上，系统还实现了：

- **按角色定向的反馈闭环**——`qc` 会根据哪个智能体对阻塞性问题负责，把返工路由回 `collect`、`analyze` **或** `write`（[`orchestration/graph.py:_route_after_qc`](backend/app/orchestration/graph.py)）。只重新采集被标记的竞品（"定向返工"），且每个智能体只收到发给它的那部分 QC 结论，以带类型的 `AgentMessage` 承载。
- **置信度感知的编排**——每条断言汇总其来源的置信度；证据薄弱的断言成为重新采集的候选项。以 `avg_confidence` / `low_confidence_claims` 指标呈现。
- **自一致性 + 跨来源冲突检测**——竞品识别可在 N 个样本间做多数投票；定价 / 币种 / 能力上的矛盾会被标记为 `ConflictFlag` 并渲染成"⚠ 来源冲突"徽标（[`consistency.py`](backend/app/consistency.py)）。
- **人在回路编辑**——`PATCH /api/reports/{id}` 应用字段编辑，记录一条 `Correction` 审计轨迹，并重新计算**人工修正率** KPI。
- **主动学习**——把近期的修正提炼为"经验教训"，注入采集器 / 撰写器的 prompt（[`learning.py`](backend/app/learning.py)）。
- **跨运行的知识演化**——每次运行都按归一化的实体键给每个竞品打快照；`GET /api/knowledge/diff` 展示自上次以来发生的变化（[`knowledge.py`](backend/app/knowledge.py)）。
- **智能体自评 / 动态 schema**——`GET /api/meta/suggestions` 把字段完整度 + 反复出现的修正 / 冲突汇总为 schema 演进建议（[`meta.py`](backend/app/meta.py)）。
- **DAG 检查点 + 续跑**——每个节点都对 `GraphState` 打检查点；被中断的运行可通过 `POST /api/analysis/resume/{run_id}` 从最近完成的阶段恢复。
- **并发 + 持久化**——每个竞品的采集 / 分析并发执行（受限信号量约束）；运行注册表被持久化，因此状态 / 追踪能在重启后存活。

## 3. 架构总览

```
┌────────────────────────────────────────────────────────────────────┐
│                         React + Vite 前端                           │
│   分析表单 │ DAG 流程图 │ 报告视图 │ 追踪查看器 │ i18n              │
└──────────────────────────────┬─────────────────────────────────────┘
                               │  REST / SSE
┌──────────────────────────────▼─────────────────────────────────────┐
│                           FastAPI 后端                              │
│  /api/analysis  /api/reports  /api/traces  /api/stream             │
└──────────────────────────────┬─────────────────────────────────────┘
                               │
              ┌────────────────▼────────────────┐
              │   LangGraph 编排器（DAG）       │
              └────────────────┬────────────────┘
                               │
   ┌──────────┬───────────┬────┴────┬────────────┐
   ▼          ▼           ▼         ▼            ▼
 采集器     分析师     撰写器    QC 智能体   （重新路由）
   │          │           │         │
   ▼          ▼           ▼         ▼
 ┌─────────────────────────────────────────────┐
 │  知识存储（SQLite）│ 追踪存储                │
 └─────────────────────────────────────────────┘
                               │
   ┌───────────────────────────┴───────────────────────────┐
   ▼                                                       ▼
 火山方舟 Ark LLM                              可插拔的网络搜索
 （豆包 / 自定义模型）                          （Tavily / Bing / Serper）
```

完整图示、时序流程与状态机细节：见 [`docs/architecture.md`](docs/architecture.md)。

---

## 4. 依赖环境

- Python **3.10+**
- Node **18+** 与 **pnpm**（或 npm / yarn）
- 一个**火山方舟 Ark** 的 API Key + 一个模型 endpoint ID（例如豆包 Doubao）。你也可以在没有 Key 的情况下以 **mock 模式**启动。

> 提示：在 mock 模式下无需联网、无需 API Key，完整的 DAG / 追踪 / 报告界面依然可端到端运行，非常适合首次体验和离线开发。

---

## 5. 启动步骤

### 5.1 后端

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 复制并填写环境变量
Copy-Item .env.example .env
notepad .env       # 设置 ARK_API_KEY 与 ARK_MODEL_ID，或保持 VOLC_MOCK=1

python main.py     # 在 http://127.0.0.1:8000 启动 FastAPI
```

### 5.2 前端

```powershell
cd frontend
pnpm install
pnpm dev           # 在 http://127.0.0.1:5173 启动 Vite
```

打开 `http://127.0.0.1:5173`，选择 **🇨🇳 中国市场** 或 **🇺🇸 美国市场**，输入一个产品（例如 "Notion" 或 "飞书"），即可看到 DAG 逐节点点亮。

### 5.3 一键演示（无界面）

```powershell
cd backend
python -m app.scripts.demo --product "Notion" --market us
```

---

## 6. 配置说明

所有配置均通过环境变量（或 `.env` 文件）提供。完整清单见 [`backend/.env.example`](backend/.env.example)，最关键的几项如下：

| 变量 | 默认值 | 用途 |
| --- | --- | --- |
| `ARK_API_KEY` | 空 | 火山方舟 API Key |
| `ARK_MODEL_ID` | 空 | Endpoint / 模型 ID（例如 `ep-202401XX-xxxxx`） |
| `ARK_BASE_URL` | `https://ark.cn-beijing.volces.com/api/v3` | Ark 接入地址 |
| `ARK_TIMEOUT` | `60` | 单次 LLM 调用超时（秒） |
| `ARK_MAX_RETRIES` | `2` | LLM 调用最大重试次数 |
| `VOLC_MOCK` | `0` | 置为 `1` 可在有 Key 的情况下也强制走 mock 模式 |
| `SEARCH_PROVIDER` | `none` | `tavily` / `serper` / `bing` / `none` |
| `MAX_QC_ITERATIONS` | `2` | 最大返工循环次数 |
| `MIN_SOURCES_PER_COMPETITOR` | `3` | QC 的来源数量阈值 |
| `COLLECTOR_CONCURRENCY` | `3` | 每竞品采集 / 分析的并行度（1 = 串行） |
| `MIN_CONFIDENCE` | `0.55` | 低于此置信度的断言将触发置信度感知的重新采集 |
| `SELF_CONSISTENCY_SAMPLES` | `1` | 竞品识别的 N 样本多数投票（1 = 关闭） |
| `ENABLE_CONFLICT_DETECTION` | `1` | 跨来源冲突标记 |
| `RESPECT_ROBOTS` | `1` | 仅在受控测试环境中才置为 `0` |
| `USER_AGENT` | `CompetitiveAnalysisAgent/1.0 (+https://example.com/contact)` | 抓取与 robots.txt 请求使用的 UA（生产环境请替换为真实联系 URL） |
| `CRAWL_RATE_LIMIT_PER_HOST` | `1.0` | 每个域名的限速（次 / 秒） |
| `HOST` / `PORT` | `127.0.0.1` / `8000` | 后端监听地址与端口 |
| `DATA_DIR` | `./data` | SQLite 与报告数据目录 |

配置项的完整说明、API 端点清单与生产部署细节，见 [`docs/deployment.md`](docs/deployment.md)。

---

## 7. 目录结构

```
competitive-analysis-agent/
├── README.md                       # ← 你正在看的文件
├── docs/                           # 架构、智能体、schema、部署、扩展等文档
├── backend/                        # FastAPI + LangGraph 智能体系统
│   ├── main.py
│   ├── requirements.txt
│   ├── .env.example
│   └── app/
│       ├── api/                    # REST 端点 + SSE
│       ├── agents/                 # 采集器 / 分析师 / 撰写器 / QC
│       ├── orchestration/          # LangGraph DAG + 状态机
│       ├── schema/                 # Pydantic schema（竞品 / 消息 / 报告）
│       ├── llm/                    # 火山方舟 Ark 客户端
│       ├── collectors/             # 网络搜索 + 遵循 robots.txt 的抓取器
│       ├── market/                 # 市场画像（CN / US，可插拔）
│       ├── i18n/                   # 服务端多语言文案
│       ├── observability/          # 结构化日志 + 追踪存储
│       ├── storage/                # SQLite 知识存储
│       └── prompts/                # 按智能体、按语言的系统 prompt
├── frontend/                       # React 18 + Vite + TS + Tailwind
│   └── src/
│       ├── pages/
│       ├── components/             # DAGFlow、ReportView、TraceViewer、SourceBadge
│       ├── api/
│       └── i18n/                   # zh / en 文案包
└── scripts/                        # 便捷启动脚本
```

完整的逐文件说明见 [`docs/project-structure.md`](docs/project-structure.md)。

---

## 8. 扩展到新市场（例如 EU、JP、SEA）

市场层是一个清晰的插件点。新增一个市场只需：

1. 创建 `backend/app/market/<code>.py`，实现 `MarketProfile`（搜索后端、搜索种子词、locale、合规覆盖项）。
2. 在 `backend/app/i18n/locales.py` 和 `frontend/src/i18n/<code>.ts` 中各加一份语言包。
3. 在 `backend/app/market/__init__.py` 和 `frontend/src/api/client.ts` 中注册该市场。
4. （可选）添加特定领域的来源白名单。

智能体、schema、编排器与 UI 组件全都与市场无关——它们都从当前激活的 `MarketProfile` 读取配置。完整示例见 [`docs/extension.md`](docs/extension.md)。

---

## 9. 文档

- [`docs/architecture.md`](docs/architecture.md) — 系统架构、DAG、时序图
- [`docs/agents.md`](docs/agents.md) — 智能体角色规格与消息协议
- [`docs/schema.md`](docs/schema.md) — 竞品知识 schema（功能树、定价、用户画像）
- [`docs/deployment.md`](docs/deployment.md) — 本地开发 + 生产部署
- [`docs/extension.md`](docs/extension.md) — 如何新增市场、智能体、数据源
- [`docs/compliance.md`](docs/compliance.md) — robots.txt、ToS、PII 处理
- [`docs/demo-script.md`](docs/demo-script.md) — 演示视频脚本
- [`docs/project-structure.md`](docs/project-structure.md) — 仓库逐文件导览

---

## 10. 合规说明

- 对每一个外部 URL 都会获取并遵守 **robots.txt**。
- 采集器在 User-Agent 中以 `CompetitiveAnalysisAgent/1.0` 标识自己，并附带联系 URL。
- 问卷与访谈数据均由 LLM **合成**并明确标注为合成数据（`kind="interview" / "questionnaire"`，低置信度）。当前**没有任何真实 PII 的接入路径**。一个以强制 PII 脱敏环节为前置门槛的真实数据导入功能，**作为 v1.1 计划能力列出**——见 [`docs/compliance.md`](docs/compliance.md) §4。代码库目前尚未提供该脱敏代码，文档也不再声称已具备。
- 系统以火山方舟 Ark 作为唯一的 LLM 提供方。搜索服务商可配置，并遵守各自的 ToS。

完整细节见 [`docs/compliance.md`](docs/compliance.md)。

---

## 11. 许可证

MIT —— 见 [`LICENSE`](LICENSE)。
