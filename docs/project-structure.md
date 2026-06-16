# 项目结构

供审阅者使用的仓库地图。

```
competitive-analysis-agent/
│
├── README.md                       # 快速上手 + 评分细则映射
├── LICENSE                         # MIT
├── AI_USAGE.md                     # 声明的 AI 工具使用
├── .gitignore
│
├── docs/
│   ├── agents.md                   # 各智能体契约 + 消息协议
│   ├── schema.md                   # 竞品知识 schema
│   ├── deployment.md               # 本地开发 + 生产部署
│   ├── extension.md                # 新增市场 / 智能体 / 数据源
│   └── project-structure.md        # ← 你正在看的文件
│
├── backend/
│   ├── main.py                     # FastAPI 应用工厂 + uvicorn 入口
│   ├── requirements.txt
│   ├── pytest.ini
│   ├── .env.example
│   │
│   ├── app/
│   │   ├── config.py               # Pydantic Settings（环境变量驱动）
│   │   ├── consistency.py          # 冲突检测 + 自一致性投票
│   │   ├── knowledge.py            # 跨运行竞品 diff
│   │   ├── meta.py                 # 智能体自评 → schema 建议
│   │   ├── learning.py             # 修正 → 主动学习 prompt 引导
│   │   ├── report_html.py          # 独立自包含的 HTML 导出
│   │   │
│   │   ├── api/
│   │   │   ├── analysis.py         # /api/analysis/{start,stream,dag,markets,status,resume}
│   │   │   ├── reports.py          # /api/reports/{...}，含 PATCH（人工编辑）
│   │   │   ├── traces.py           # /api/traces/{run_id}
│   │   │   ├── knowledge.py        # /api/knowledge/{entities,history,diff}
│   │   │   └── meta.py             # /api/meta/{suggestions,corrections}
│   │   │
│   │   ├── agents/
│   │   │   ├── base.py             # LLM 调用 + JSON 解析 / 修复 + 追踪
│   │   │   ├── collector.py        # 识别（+ 自一致性）+ 采集（网页证据 + 引导）
│   │   │   ├── analyst.py          # SWOT 分析（支持返工）
│   │   │   ├── writer.py           # 最终报告综合（支持返工）
│   │   │   └── qc.py               # 确定性 + LLM 批评 → 按角色路由的返工
│   │   │
│   │   ├── orchestration/
│   │   │   ├── graph.py            # LangGraph DAG：按角色定向返工、并发、检查点
│   │   │   └── state.py            # GraphState + 给前端的静态 DAG 元数据
│   │   │
│   │   ├── schema/
│   │   │   ├── competitor.py       # 三支柱 schema + SourceRef + ConflictFlag + 置信度
│   │   │   ├── messages.py         # AgentMessage / QCReport / QCFinding
│   │   │   └── report.py           # FinalReport + ReportMetrics + Correction + SchemaSuggestion + KnowledgeDiff
│   │   │
│   │   ├── llm/
│   │   │   ├── volcengine.py       # Ark 异步客户端 + 重试
│   │   │   └── mocks.py            # 用于演示模式的内置预设响应
│   │   │
│   │   ├── collectors/
│   │   │   ├── search.py           # 可插拔的 Tavily / Serper / Bing
│   │   │   ├── web.py              # 遵循 robots 的抓取器 + 限速
│   │   │   └── robots.py           # robots.txt 缓存
│   │   │
│   │   ├── prompts/
│   │   │   ├── collector.py        # system + user prompt 模板
│   │   │   ├── analyst.py
│   │   │   ├── writer.py
│   │   │   └── qc.py
│   │   │
│   │   ├── market/
│   │   │   ├── base.py             # MarketProfile dataclass
│   │   │   ├── cn.py               # 🇨🇳 ChinaMarket
│   │   │   ├── us.py               # 🇺🇸 USMarket
│   │   │   └── __init__.py         # 注册表 + get_market(code)
│   │   │
│   │   ├── i18n/
│   │   │   └── locales.py          # 服务端标签文案（zh-CN / en-US）
│   │   │
│   │   ├── observability/
│   │   │   ├── logger.py           # Loguru sink
│   │   │   └── tracer.py           # 每次运行的 TraceEvent 记录器 + SSE 队列
│   │   │
│   │   ├── storage/
│   │   │   └── store.py            # SQLite：报告、追踪、知识快照、
│   │   │                           #   修正、运行注册表、检查点
│   │   │
│   │   └── scripts/
│   │       └── demo.py             # 一键 CLI：产出一份完整报告
│   │
│   └── tests/
│       ├── conftest.py             # mock 模式 + 隔离的数据目录
│       ├── test_schema.py
│       ├── test_qc.py              # 确定性检查，含角色路由
│       ├── test_consistency.py     # 冲突检测 + 多数投票
│       ├── test_json_repair.py     # JSON 恢复流水线
│       ├── test_knowledge.py       # 跨运行 diff
│       ├── test_routing.py         # 按角色定向的返工路由
│       ├── test_learning.py        # 主动学习引导
│       ├── test_robots.py          # 合规辅助函数
│       ├── test_checkpoint.py      # 检查点 + 续跑
│       ├── test_api.py             # 端到端 ASGI（start→edit→knowledge→meta）
│       └── test_orchestration.py   # 完整 DAG、mock 模式，含返工循环
│
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── tailwind.config.js
│   ├── postcss.config.js
│   ├── index.html
│   │
│   └── src/
│       ├── main.tsx                # 入口 + 路由
│       ├── App.tsx                 # 外壳 + 导航 + 健康状态标识
│       ├── index.css               # Tailwind + DAG 节点样式
│       │
│       ├── pages/
│       │   ├── Home.tsx            # 表单 + DAG + 实时追踪列表 + 续跑按钮
│       │   ├── Report.tsx          # 标签页：报告 / 对比 / 竞品 /
│       │   │                       #   演化 / 追踪 / 来源；就地编辑 + 冲突
│       │   └── History.tsx         # 历史报告列表 + 元自评面板
│       │
│       ├── components/
│       │   ├── AnalysisForm.tsx    # 产品 + 市场选项选择器
│       │   ├── AgentFlow.tsx       # 智能体流 + 决策追踪回放（按返工轮次）
│       │   ├── ComparisonView.tsx  # 图表 + 对比表
│       │   ├── TraceList.tsx       # 可展开的逐事件下钻
│       │   └── SourceBadge.tsx     # 内联引用标签
│       │
│       ├── api/
│       │   └── client.ts           # REST + SSE 客户端
│       │
│       └── i18n/
│           ├── index.ts            # marketToLocale + makeT
│           ├── zh.ts               # 🇨🇳 zh-CN 文案包
│           └── en.ts               # 🇺🇸 en-US 文案包
│
├── .github/
│   └── workflows/
│       └── ci.yml                  # 后端 pytest + 前端类型检查 / 构建
│
└── scripts/
    ├── start-backend.ps1           # venv 配置 + python main.py
    ├── start-frontend.ps1          # pnpm/npm install + dev
    └── run-demo.ps1                # CLI 演示包装脚本
```

## 文件数量小结

| 区域 | 文件数 |
| --- | --- |
| 文档 | 8 |
| 后端 Python | ~40 |
| 前端 TS/TSX | ~13 |
| 配置 | 7 |
| 脚本 | 3 |
| 测试 | 11 |

## 审阅者阅读顺序

如果你有 20 分钟，按以下顺序阅读：

1. [`README.md`](../README.md) —— 是什么 + 为什么 + 如何运行。
2. [`docs/architecture.md`](architecture.md) —— DAG 以及各评分项在何处得到满足。
3. [`backend/app/schema/competitor.py`](../backend/app/schema/competitor.py) —— schema 即契约。
4. [`backend/app/orchestration/graph.py`](../backend/app/orchestration/graph.py) —— DAG 与反馈闭环。
5. [`backend/app/agents/qc.py`](../backend/app/agents/qc.py) —— 确定性 + LLM 的混合批评。
6. [`docs/extension.md`](extension.md) —— 系统如何保持开放可扩展。
