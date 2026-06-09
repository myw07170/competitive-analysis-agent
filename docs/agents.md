# 智能体与消息协议

本文档规定四个智能体各自的角色、输入、输出与消息协议。

## 1. 智能体名册

| 智能体 | 文件 | 角色 | 读取自 | 写入到 |
| --- | --- | --- | --- | --- |
| 采集器 Collector | [`backend/app/agents/collector.py`](../backend/app/agents/collector.py) | 识别竞品并逐个竞品采集结构化知识 | 用户请求、网络搜索、遵循 robots 的抓取器、LLM | `GraphState.competitor_names`、`GraphState.competitors` |
| 分析师 Analyst | [`backend/app/agents/analyst.py`](../backend/app/agents/analyst.py) | 为每个竞品生成 SWOT | `GraphState.competitors` | `competitor.swot` |
| 撰写器 Writer | [`backend/app/agents/writer.py`](../backend/app/agents/writer.py) | 综合生成最终报告 | `GraphState.competitors`（含 SWOT） | `GraphState.report` |
| 质量管控 QC | [`backend/app/agents/qc.py`](../backend/app/agents/qc.py) | 批评结构 / 覆盖度 / 幻觉 / 置信度 / 冲突；路由返工 | `GraphState.competitors`、`GraphState.report` | `GraphState.qc_history`、`GraphState.last_qc`、`GraphState.messages` |

这些职责**互不重叠**：

* 只有采集器与外部来源交互。
* 只有分析师写 SWOT。
* 只有撰写器产出最终报告的正文。
* 只有 QC 智能体做出"返工或通过"的决策。

## 2. 消息协议

智能体间的通信由 `GraphState` 中介——绝不通过直接 import——但每个载荷都是带类型的。具体来说：

```python
class AgentMessage(BaseModel):
    id: str
    sender: AgentRole
    receiver: AgentRole
    intent: str              # 被调用的函数名
    payload: Dict[str, Any]  # 按接收方的 schema 校验
    correlation_id: str | None
    created_at: datetime
```

对于 QC → 上游的反馈闭环，QC 载荷是一个 `QCReport`，其中包含一组 `QCFinding`。每条结论携带 `target_agent`（采集器 / 分析师 / 撰写器）、`target_path`（类 JSONPath）、`severity`、`issue` 和 `suggested_fix`。当 QC 请求返工时，编排器会**为每个接收智能体构建一条带类型的 `AgentMessage(intent="request_rework")`**（[`graph.py:_emit_rework_messages`](../backend/app/orchestration/graph.py)），把它们存入 `GraphState.messages` 这一结构化消息流——因此这次交接是带类型、可检视的对象，而不只是一个内部字符串。随后每个接收智能体只用发给它的那部分结论被重新执行（对采集器而言，只针对它标记的那些竞品）。

Schema 定义在 [`backend/app/schema/messages.py`](../backend/app/schema/messages.py)。

## 3. 采集器智能体（Collector）

### 输入
* `product: str` —— 目标产品
* `market: MarketProfile` —— 决定语言、币种、来源白名单、搜索查询
* `iteration: int` —— 每次返工时递增
* `rework_notes: str | None` —— 上一轮 QC 结论的拼接文本

### 步骤
1. **识别竞品**（`intent="collector.identify_competitors"`）—— top-3 列表。
2. **采集竞品**（`intent="collector.gather_competitor"` 或 `"collector.rework"`）—— 对每个竞品：
   1. 通过配置的后端运行市场调优后的搜索查询。
   2. 用遵循 robots 的抓取器抓取前 2 条命中。
   3. 把得到的证据块注入 LLM prompt。
   4. 接收一个 JSON 形式的 `CompetitorKnowledge`。校验。失败则抛错。

### 输出
`List[CompetitorKnowledge]` —— 符合 schema，每条事实都带来源标记。

### 自校验保障
* Pydantic 严格校验会拒绝部分成形的竞品对象，避免下游崩溃。
* 在 mock 模式下，返工意图（`collector.rework`）会返回一个*更丰富*的 mock 载荷（额外的定价来源），让循环可见地改进输出。

## 4. 分析师智能体（Analyst）

### 输入
* `product: str`
* `competitor: CompetitorKnowledge`
* `rework_notes: str | None` —— 发给分析师的 QC 结论（这样 QC 才能把返工路由到这里）

### 步骤
1. 把竞品序列化为 JSON，截断到 6 KB，放入 prompt。
2. 请求 `SWOTAnalysis` —— 每个象限 2~5 条，每条都由 `SourceRef` 支撑。
3. 经 Pydantic 校验。

### 输出
`SWOTAnalysis`，挂到 `competitor.swot`。

### 自校验保障
* 系统 prompt 禁止引入新事实；只能引用已存在于竞品数据块中的来源。
* 若分析师必须推断，则必须用 `kind="llm_prior"` 且 `confidence<=0.6` 标记该来源。

## 5. 撰写器智能体（Writer）

### 输入
* `product: str`
* `report_id: str`
* `competitors: List[CompetitorKnowledge]`（已挂 SWOT）
* `target_product: CompetitorKnowledge | None` —— 用户自己的产品，用于并排对比
* `rework_notes: str | None` —— 发给撰写器的 QC 结论（例如引用断链、覆盖不足）

### 步骤
1. 构建一个区分语言的 prompt，带本地化的章节标题。
2. 注入前把竞品 JSON 截断到 12 KB。
3. 请求报告 JSON（`title`、`executive_summary_md`、`sections`）。
4. 把所有竞品数据块里的来源扁平化汇入 `FinalReport.all_sources`。

### 输出
`FinalReport` —— 返回给前端的标准产物。

## 6. QC 智能体

QC 智能体把**确定性**检查（Python）与一次 **LLM 批评**结合起来，再合并二者。

### 确定性检查（Python）
* 每个竞品的来源数 ≥ `MIN_SOURCES_PER_COMPETITOR`。
* 功能树非空。
* 每个定价档位至少有一个来源。
* 来源中没有占位 / 本地主机 URL。
* 用户画像至少有一个细分。

### LLM 批评
* 同样的检查以软性批评的形式表达。
* 被要求检测语言不匹配、文风不一致，以及上面未捕获的明显 schema 形态错误。

### QC 审查什么
QC **同时**审查采集到的 `CompetitorKnowledge` *与*最终的 `FinalReport`，产出按角色路由的结论：
* **采集器负责**——来源数、空功能树、缺失 / 无来源的定价档位、占位 URL、缺失用户细分、**低置信度断言**（低于 `MIN_CONFIDENCE`），以及**跨来源冲突**（来自 [`consistency.py`](../backend/app/consistency.py) 的 `ConflictFlag`）。
* **分析师负责**——缺失 SWOT、空的 SWOT 象限、无来源的 SWOT 条目。
* **撰写器负责**——空的执行摘要、**断链的 `[^src_xxx]` 引用**（指向未知来源 ID）、未在叙述中覆盖的竞品。

### 输出
`QCReport`，含三种判定之一：
* `approve` —— 无结论；或仅有 `info` 级别。
* `approve_with_notes` —— 仅有轻微结论；报告照发。
* `rework` —— 至少一个阻塞项，或 ≥ 1 个重大项。路由到**拥有阻塞 / 重大问题的最早阶段**——`collect`、`analyze` 或 `write`（见 [`_route_after_qc`](../backend/app/orchestration/graph.py)），而非盲目退回 `collect`。

### 循环上限
编排器把迭代次数封顶在 `MAX_QC_ITERATIONS`（默认 2）。超过后无论 QC 怎么判，运行都会收尾——报告附上最终 QC 备注后照发。

## 8. 元评估器（智能体自评）

[`MetaEvaluator`](../backend/app/meta.py) 不属于单次运行的 DAG；它按需运行（`GET /api/meta/suggestions`），横跨**所有历史报告**。它把字段完整度、反复出现的人工修正、反复出现的来源冲突汇总为 `SchemaSuggestion`（弃用 / 改为可选 / 收紧 prompt）。这闭合了"智能体自评 / 动态 schema 演进"的循环：`schema_version` 随每份报告持久化，因此被采纳的建议可以向前滚动而不使历史失效。

## 9. 主动学习

人工编辑（`PATCH /api/reports/{id}`）被存为 `Correction`。[`learning.recent_guidance`](../backend/app/learning.py) 把某个市场最近的修正提炼为一段"经验教训"，在下次运行时注入采集器 / 撰写器的系统 prompt——因此 `manual_correction_rate` KPI 应当随时间下降。

## 7. Prompt

系统 prompt 被外置以便审计：

* [`backend/app/prompts/collector.py`](../backend/app/prompts/collector.py)
* [`backend/app/prompts/analyst.py`](../backend/app/prompts/analyst.py)
* [`backend/app/prompts/writer.py`](../backend/app/prompts/writer.py)
* [`backend/app/prompts/qc.py`](../backend/app/prompts/qc.py)

每个 prompt 都：
* 以智能体的角色定义开头（边界约束）。
* 列出明确的硬性规则（不得用占位 URL、不得编造事实等）。
* 内联声明输出 JSON 的形态，让模型在同一轮就拿到 schema。
* 通过 `{language}` 固定**响应语言**——由当前激活的 `MarketProfile` 驱动。
