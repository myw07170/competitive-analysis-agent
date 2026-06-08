# 竞品知识 Schema

标准 schema 定义在 [`backend/app/schema/competitor.py`](../backend/app/schema/competitor.py)。每一个智能体的输入与输出都会对照它进行校验。

## 1. `CompetitorKnowledge`

```python
class CompetitorKnowledge(BaseModel):
    name: str
    aliases: List[str]
    homepage: Optional[str]
    short_description: str
    market_position: Optional[str]

    function_tree: FunctionTree            # 支柱 1
    pricing: PricingModel                  # 支柱 2
    user_profile: UserProfile              # 支柱 3
    swot: Optional[SWOTAnalysis]           # 由分析师补充

    sources: List[SourceRef]               # 顶层溯源
    conflicts: List[ConflictFlag]          # 跨来源分歧（见 §9）
    schema_version: str = "1.1.0"
```

置信度辅助方法：
* `avg_confidence()` —— 该竞品上每个 `SourceRef` 置信度的均值（驱动 `avg_confidence` 指标）。
* `low_confidence_claims(threshold)` —— 那些其最佳来源低于 `threshold` 的结构化断言的点分路径（驱动置信度感知的返工）。

## 2. 支柱 1 —— `FunctionTree`

层级化的能力图谱。

```python
class FunctionNode:
    name: str
    description: str
    category: Optional[str]
    maturity: Optional[Literal["ga", "beta", "preview", "rumored"]]
    sources: List[SourceRef]
    children: List[FunctionNode]   # 递归

class FunctionTree:
    root_name: str
    nodes: List[FunctionNode]
```

设计要点：
* 自引用——允许任意深度而无需改 schema。
* 每个节点都携带自己的 `sources`，因此一个叶子可以被独立溯源。

## 3. 支柱 2 —— `PricingModel`

```python
class PricingTier:
    name: str
    monthly_price: Optional[float]
    annual_price: Optional[float]
    currency: str               # "USD"、"CNY"、...
    seat_based: bool
    included_features: List[str]
    limits: dict                # {"storage_gb": 100, "seats": 10}
    sources: List[SourceRef]

class PricingModel:
    summary: str
    tiers: List[PricingTier]
    addons: List[PricingTier]
    has_free_tier: bool
    has_enterprise: bool
    notes: str
    sources: List[SourceRef]
```

设计要点：
* `monthly_price` 与 `annual_price` 均为可选——有些档位只能询价。
* `currency` 是必填（对应评分细则中对一致性的要求）。
* `limits` 是一个自由字典，便于不同垂直领域以各自习惯的方式表达约束。

## 4. 支柱 3 —— `UserProfile`

```python
class UserSegment:
    name: str
    description: str
    company_size: Optional[Literal["smb", "mid_market", "enterprise", "individual", "mixed"]]
    industries: List[str]
    geographies: List[str]
    use_cases: List[str]
    pain_points: List[str]
    representative_quotes: List[Cited]
    sources: List[SourceRef]

class UserProfile:
    primary_segment: Optional[str]
    segments: List[UserSegment]
    estimated_user_base: Optional[str]
    nps_or_rating: Optional[str]
    sources: List[SourceRef]
```

`representative_quotes` 是 `Cited` 值——每条引述都绑定到它的来源。正是这一点让 UI 能从一条引述点击跳转回产生它的访谈记录。

## 5. `SourceRef` —— 可溯源性的基本单元

```python
class SourceRef:
    id: str = "src_xxx"
    kind: Literal["web", "doc", "interview", "questionnaire", "llm_prior"]
    title: str
    url: Optional[str]
    snippet: str           # 逐字摘录
    retrieved_at: datetime
    confidence: float      # 0..1
```

规则：
* `CompetitorKnowledge` 实例中的每条事实都必须挂在至少一个 `SourceRef` 上。
* 当 LLM 在没有外部证据的情况下推断某条事实时，该来源必须声明 `kind="llm_prior"` 且 `confidence <= 0.6`。
* `confidence >= 0.9` 仅保留给来自实际抓取页面的逐字引用。

## 6. Cited<T>

```python
class Cited:
    value: str
    sources: List[SourceRef]
```

用于 SWOT 条目和代表性引述内部——任何需要一条单独事实拥有不同于其父节点溯源的地方。

## 7. 版本管理

`CompetitorKnowledge.schema_version` 随每份保存的报告持久化。当前版本为 **`1.1.0`**（新增了 `conflicts`、置信度辅助方法，以及报告级的可信度 / 修正指标）。未来的 schema 升级：

| 升级类型 | 示例 | 会发生什么 |
| --- | --- | --- |
| 补丁 Patch | "1.1.0" → "1.1.1" | 新增一个可选字段。旧报告仍然有效。 |
| 次要 Minor | "1.1.0" → "1.2.0" | 新增一个带默认值的字段。旧报告自动迁移（Pydantic 默认值）。 |
| 重大 Major | "1.1.0" → "2.0.0" | 破坏性变更。配套一个位于 `backend/app/scripts/` 的一次性迁移脚本。 |

[`MetaEvaluator`](../backend/app/meta.py) 会根据历史字段完整度提出数据驱动的 `SchemaSuggestion`（弃用 / 改为可选 / 收紧 prompt）——这是决定下一次升级的输入。

## 8. 为什么是"功能树 + 定价模型 + 用户画像"？

这三大支柱契合产品经理在实践中真正组织竞品分析的方式：

* **功能树**回答*"它能做什么？"*——可跨市场比较。
* **定价模型**回答*"谁负担得起？"*——驱动市场定位。
* **用户画像**回答*"谁已经在用？"*——驱动 go-to-market 策略。

SWOT、建议、市场综述都是从这三者*派生*出来的——见撰写器智能体的 prompt。

## 9. 可信度与反馈模型（v1.1）

定义于 [`schema/competitor.py`](../backend/app/schema/competitor.py) 和 [`schema/report.py`](../backend/app/schema/report.py)。

```python
class ConflictFlag:               # 跨来源分歧（创新点 2）
    field: str                    # 例如 "pricing.tiers[Pro].monthly_price"
    kind: str                     # value_mismatch | duplicate | unsupported | range
    detail: str
    values: List[str]             # 相互分歧的值
    source_ids: List[str]
    severity: str                 # major | minor | info

class Correction:                 # 人在回路编辑（创新点 5）
    id: str
    report_id: str
    market: str
    target_path: str              # 被编辑的点分路径
    before: str
    after: str
    note: str
    author: str
    created_at: datetime

class SchemaSuggestion:           # 智能体自评（创新点 4）
    field: str
    action: str                   # deprecate | make_optional | tighten_prompt | add_field | split_field
    rationale: str
    evidence: Dict[str, float]
    confidence: float

class KnowledgeDiff:              # 跨运行演化（创新点 3）
    entity_key: str
    name: str
    market: str
    changes: List[KnowledgeChange]  # path / change(added|removed|changed) / before / after
    summary: str
```

### `ReportMetrics`（已扩展）

在原有的耗时 / token / 完整度字段之外，v1.1 新增了：

| 字段 | 含义 |
| --- | --- |
| `avg_confidence` | 所有交付内容上来源置信度的均值。 |
| `low_confidence_claims` | 低于 `MIN_CONFIDENCE` 的断言数量。 |
| `conflict_count` | 检测到的跨来源分歧数量。 |
| `manual_correction_rate` | 被人工编辑过的结构化断言比例——团队要努力压低的 KPI。 |
| `corrected_fields` | 应用的人工编辑的绝对数量。 |
