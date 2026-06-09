# 架构设计

## 1. 设计目标

1. **可复现性**——给定相同的产品 + 市场，系统应当走过相同的 DAG。随机性只存在于 LLM 采样中；智能体协作的*结构*是确定性的。
2. **可溯源性**——最终报告中的每一条结论都能追溯到 (a) 写下它的智能体，以及 (b) 支撑它的来源。
3. **可扩展性**——新增市场、新增数据源、新增智能体都无需改动编排器或 schema。

## 2. 高层架构

```
┌──────────────────────────────────────────────────────────────────────────┐
│                          React + Vite 前端                                │
│   AnalysisForm    DAGFlow (reactflow)    ReportView    TraceList         │
│   i18n（zh-CN | en-US，可扩展）                                          │
└──────────────────────────────┬───────────────────────────────────────────┘
                               │ REST + Server-Sent Events
┌──────────────────────────────▼───────────────────────────────────────────┐
│                            FastAPI 后端                                   │
│   /api/analysis/{start,stream,status,dag,markets}                        │
│   /api/reports/{...}     /api/traces/{run_id}     /api/health            │
└──────────────────────────────┬───────────────────────────────────────────┘
                               │
              ┌────────────────▼─────────────────┐
              │  LangGraph 编排器（DAG）         │
              │  identify → collect → analyze →  │
              │            write → qc → done/↺   │
              └────────────────┬─────────────────┘
                               │
   ┌──────────┬───────────┬────┴────┬────────────┐
   ▼          ▼           ▼         ▼            ▼
 采集器     分析师     撰写器    QC 智能体   （条件重新路由）
   │          │           │         │
   ▼          ▼           ▼         ▼
 ┌─────────────────────────────────────────────┐
 │ SQLite（报告 + 追踪）                        │
 └─────────────────────────────────────────────┘
                               │
   ┌───────────────────────────┴───────────────────────────┐
   ▼                                                       ▼
 火山方舟 Ark LLM                              网络搜索后端
 （豆包 / 自定义 endpoint）                     （Tavily / Bing / Serper）
                                               + 遵循 robots.txt 的抓取器
```

## 3. DAG 状态机

```
                                 ┌──────────────┐
                                 │   identify   │   （采集器）
                                 └──────┬───────┘
                                        ▼
            ┌──────────────────▶┌──────────────┐
            │ 返工→采集器        │   collect    │
            │                    └──────┬───────┘
            │                           ▼
            │ 返工→分析师       ┌──────────────┐
            ├──────────────────▶│   analyze    │   （分析师）
            │                    └──────┬───────┘
            │                           ▼
            │ 返工→撰写器       ┌──────────────┐
            ├──────────────────▶│    write     │   （撰写器）
            │                    └──────┬───────┘
            │                           ▼
            │                    ┌──────────────┐
            │   按角色定向        │      qc      │   （QC——同时审查知识
            └────────────────────┤   判定？     │         与最终报告）
                                 └──────┬───────┘
                                        │ approve / approve_with_notes
                                        ▼
                                 ┌──────────────┐
                                 │    done      │
                                 └──────────────┘
```

* 循环上限：`MAX_QC_ITERATIONS`（默认 `2`）。超过后，运行以 QC 当时给出的结论收尾；若返工预算耗尽仍残留阻塞 / 重大问题，最终结论记为"未通过"（`metrics.qc_status="failed"`），并连同未解决的问题清单（`report.qc_findings`）一起呈现在结果页，而非伪装成"一切正常"。
* **按角色定向的路由**（[`_route_after_qc`](../backend/app/orchestration/graph.py)）：QC 产出带 `target_agent`（采集器 / 分析师 / 撰写器）标签的结论。运行会从*拥有阻塞 / 重大问题的最早阶段*重新进入——缺失 SWOT 会重跑 `analyze`，引用断链会重跑 `write`，来源覆盖不足会重跑 `collect`。它**不会**盲目地从 `collect` 重启。
* **定向返工**：采集器返工时，只重新采集被 QC 标记的竞品（其余沿用），并且每个竞品的 `gather` 调用只收到 `target_path` 指向它的那些结论。QC → 智能体的交接是一个带类型的 `AgentMessage(intent="request_rework")`，写入结构化消息流（`GraphState.messages`）。
* **置信度感知**：仅由低置信度来源（低于 `MIN_CONFIDENCE`）支撑的断言本身也会被标记，因此循环追求的是更强的证据，而不只是补齐缺失字段。
* mock 后端在返工那一遍会返回明显更丰富的载荷，使循环在无 Key 的演示中也能*可度量地*改善（更多来源、更少 schema 缺口）；在实跑模式下，确定性检查（来源数量、空字段、冲突、低置信度）为循环提供了客观的改进判据。

## 4. 数据流

```
   用户输入
       │
       ▼
   AnalysisRequest{ product, market, extra_competitors }
       │
       ▼  （编排器）
   GraphState
   ├── competitor_names: ["Notion", "Coda", "ClickUp"]
   ├── competitors: [CompetitorKnowledge × N]
   ├── qc_history: [QCReport × 迭代次数]
   ├── last_qc: QCReport
   └── report: FinalReport
       │
       ▼
   FinalReport（Pydantic）
       │
       ▼
   SQLite + 前端
```

编排器从不原地修改某个 schema 实例——每个节点都产出一个新的带类型的值，由状态图层把它合并回去。正是这一点让追踪成为一个忠实的回放工具。

## 5. 时序图：一次完整运行

```
用户           前端           FastAPI           编排器           采集器   分析师  撰写器   QC     LLM/搜索
 │   提交         │              │                    │              │         │        │     │         │
 │ ─────────────▶ │  POST /start │                    │              │         │        │     │         │
 │                │ ────────────▶│ build_graph()      │              │         │        │     │         │
 │                │              │ ainvoke ──────────▶│              │         │        │     │         │
 │                │              │                    │ identify ───▶│         │        │     │         │
 │                │              │                    │              │ ◀──────────────────────────────▶│
 │                │              │                    │ collect ────▶│         │        │     │         │
 │                │              │                    │              │ ─搜索 + robots ──▶│             │
 │                │              │                    │ analyze ────────────▶ │         │     │         │
 │                │              │                    │ write ────────────────────────▶ │     │         │
 │                │              │                    │ qc ────────────────────────────────▶ │         │
 │                │              │                    │ ◀─ 判定：返工 ─────────────────────  │         │
 │                │              │                    │ collect（带返工备注）────────▶│             │
 │                │              │                    │ 再次 analyze / write / qc                     │
 │                │              │                    │ ◀─ 判定：通过 ──────────────────────────────  │
 │                │ ◀─ SSE：追踪事件随发生即时推送 ────┤                                              │
 │                │ ◀─ SSE：done(report_id)            │                                             │
```

## 6. 各评分维度在何处得到满足

| 评分项（出自评分细则） | 文件 / 模块 | 如何满足 |
| --- | --- | --- |
| 清晰的角色分工 | [`backend/app/agents/`](../backend/app/agents/) | 四个智能体文件；`BaseAgent` 是唯一共享逻辑。 |
| 可视化 DAG | [`backend/app/orchestration/state.py`](../backend/app/orchestration/state.py) + [`frontend/src/components/DAGFlow.tsx`](../frontend/src/components/DAGFlow.tsx) | 静态 DAG 元数据由 `/api/analysis/dag` 提供，经 ReactFlow 渲染。 |
| 结构化（类函数调用风格）的消息传递 | [`backend/app/schema/messages.py`](../backend/app/schema/messages.py) + 在每个边界上做 Pydantic 校验；`AgentMessage` 现在承载 QC → 智能体的返工请求（[`graph.py:_emit_rework_messages`](../backend/app/orchestration/graph.py)） | 智能体间载荷是带类型的对象，绝非裸文本；返工以带类型的 `AgentMessage(intent="request_rework")` 派发，写入结构化消息流（`GraphState.messages`）。 |
| 真实、按角色定向的反馈闭环 | [`backend/app/orchestration/graph.py:_route_after_qc`](../backend/app/orchestration/graph.py)；QC 同时审查知识**与**报告（[`agents/qc.py`](../backend/app/agents/qc.py)） | QC 结论路由到采集器、分析师**或**撰写器；只重新采集被标记的竞品，每个竞品携带各自的结论切片。mock 后端在返工那一遍返回明显更丰富的数据。 |
| Schema 一致性 | [`backend/app/schema/competitor.py`](../backend/app/schema/competitor.py) | 对每个智能体输出都调用 Pydantic 的 `CompetitorKnowledge.model_validate`。 |
| 来源可溯源 | `SourceRef` 是每个携带事实的 schema 节点的必填字段。前端渲染 `SourceBadge`。 | 每个 Cited / SourceRef 都有 kind、可选 URL、片段、置信度。 |
| 可观测性 | [`backend/app/observability/tracer.py`](../backend/app/observability/tracer.py) + `/api/traces/{run_id}` | 每次智能体调用对应一条追踪事件，捕获 prompt / 输入 / 输出 / token / 耗时。 |
| 合规 | [`backend/app/collectors/robots.py`](../backend/app/collectors/robots.py)、[`docs/compliance.md`](compliance.md) | robots.txt 强制执行、按域名限速、可配置 User-Agent。 |

## 7. 性能与韧性

* **重试**：LLM 调用使用指数退避（tenacity）。超时和 5xx 会重试；客户端错误不会。
* **mock 兜底**：未设置 API Key 时，系统会静默切换到 mock——便于演示和离线开发。
* **抑制幻觉**：一套分层策略——(1) 确定性 QC 检查捕获占位 URL（`example.com`、`localhost`）、来源过少、字段缺失；(2) **引用强制校验**确认报告中的每个 `[^src_xxx]` 都能解析到真实来源；(3) **置信度聚合**标记仅由弱来源支撑的断言；(4) **跨来源冲突检测**暴露矛盾；(5) 可选的**自一致性投票**（`SELF_CONSISTENCY_SAMPLES > 1`）在多个样本间对竞品识别做多数投票。
* **并发**：每个竞品的采集与分析在受限信号量（`COLLECTOR_CONCURRENCY`，默认 3）下并发执行。
* **上下文分片**：撰写器 prompt 把每个竞品的 JSON 截断到 12 KB，分析师截断到 6 KB。长上下文被分块处理而非丢弃。
* **续跑**：每个节点都对 `GraphState` 打检查点；被中断的运行从最近完成的阶段恢复，而非重头开始。

## 8. 已实现的进阶能力（v1.1）

| 能力 | 位置 | 说明 |
| --- | --- | --- |
| 按角色定向的反馈闭环 | [`orchestration/graph.py`](../backend/app/orchestration/graph.py) `_route_after_qc` | 返工路由到采集器 / 分析师 / 撰写器。 |
| 定向返工 + 结构化 `AgentMessage` | `graph.py` `n_collect`、`_emit_rework_messages` | 只重新采集被标记的竞品；带类型的消息记入追踪。 |
| 置信度感知的编排 | `competitor.py` `low_confidence_claims`、`qc.py` | 证据薄弱的断言成为重新采集候选项。 |
| 自一致性投票 | [`consistency.py`](../backend/app/consistency.py) `majority_vote`、`collector.py` | 对竞品识别做 N 样本多数投票（`SELF_CONSISTENCY_SAMPLES`）。 |
| 跨来源冲突检测 | [`consistency.py`](../backend/app/consistency.py) `detect_conflicts` | `ConflictFlag` → QC 结论 + "⚠ 冲突" UI 徽标。 |
| 人在回路编辑 | [`api/reports.py`](../backend/app/api/reports.py) `PATCH` | 记录 `Correction`，更新 `manual_correction_rate`。 |
| 主动学习 | [`learning.py`](../backend/app/learning.py) | 修正 → "经验教训"注入 prompt。 |
| 跨运行的知识演化 | [`knowledge.py`](../backend/app/knowledge.py)、[`api/knowledge.py`](../backend/app/api/knowledge.py) | 以实体键打快照；结构化 diff 端点。 |
| 智能体自评 / schema 建议 | [`meta.py`](../backend/app/meta.py)、[`api/meta.py`](../backend/app/api/meta.py) | 字段完整度 + 反复出现的修正 → 建议。 |
| DAG 检查点 + 续跑 | `graph.py` `_wrap_checkpointed`、`resume_analysis` | 每节点 `GraphState` 快照；`POST /api/analysis/resume/{run_id}`。 |
| 并发 | `graph.py` `_bounded_gather` | 每竞品采集 / 分析并发执行（`COLLECTOR_CONCURRENCY`）。 |
| 持久化的运行注册表 | [`api/analysis.py`](../backend/app/api/analysis.py)、`storage/store.py` | 状态 + 追踪在重启后存活；`/status` 与 `/stream` 回退到 SQLite。 |

## 9. 未来扩展

* **更多市场**——见 [`extension.md`](extension.md)。
* **更多智能体**——新增 `app/agents/<role>.py`，在 `app/orchestration/state.py` 和 `app/orchestration/graph.py` 中注册一个新的 DAG 节点 + 边。前端会自动从 `/api/analysis/dag` 拾取新节点。
* **基于嵌入的实体消歧**——跨运行知识存储目前使用归一化名称作为键；一个嵌入索引能捕获改名 / 别名。
* **自动应用的 schema 演进**——`MetaEvaluator` 如今只是提出变更建议；未来版本可以自动应用被采纳的建议并自动提升 `schema_version`。
