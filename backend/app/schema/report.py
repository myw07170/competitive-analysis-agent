"""最终报告 schema —— 撰写器智能体产出、并由 API 返回的内容。"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from .competitor import CompetitorKnowledge, SourceRef
from .messages import QCFinding


class ReportSection(BaseModel):
    heading: str
    body_md: str = Field(description="Markdown body. May contain [^src_xxx] citations.")
    sources: List[SourceRef] = Field(default_factory=list)


class ComparisonCell(BaseModel):
    """多竞品对比表中的一个单元格。"""

    competitor: str
    value: str = ""
    detail: Optional[str] = None


class ComparisonRow(BaseModel):
    """对比表中的一行（某个能力 / 档位 / 细分，覆盖所有竞品）。"""

    label: str
    category: Optional[str] = None
    cells: List[ComparisonCell] = Field(default_factory=list)


class ComparisonMatrix(BaseModel):
    """结构化的多竞品对比 —— 在 UI 中渲染为真正的图表 / 表格。

    确定性地从 CompetitorKnowledge 记录构建，因此对比绝不会因 LLM 的 markdown 漂移而丢失。

    当设置了 ``self_name`` 时，``competitors`` 中的第一项是用户自己的产品；
    前端会用一个独特的强调色渲染它。
    """

    competitors: List[str] = Field(default_factory=list)
    self_name: Optional[str] = Field(
        default=None,
        description="Name of the user's own product (i.e. the analysis subject).",
    )
    feature_rows: List[ComparisonRow] = Field(default_factory=list)
    pricing_rows: List[ComparisonRow] = Field(default_factory=list)
    user_rows: List[ComparisonRow] = Field(default_factory=list)
    keywords: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="Keyword cards per competitor: name -> list of short keyword strings.",
    )
    function_coverage: Dict[str, int] = Field(
        default_factory=dict,
        description="Leaf-feature count per competitor (for bar chart).",
    )
    source_counts: Dict[str, int] = Field(
        default_factory=dict,
        description="Unique source count per competitor.",
    )
    pricing_floor: Dict[str, Optional[float]] = Field(
        default_factory=dict,
        description="Cheapest paid monthly price per competitor (or null).",
    )


class ReportMetrics(BaseModel):
    """呈现给 UI 的运营指标 —— 闭合业务闭环。"""

    elapsed_seconds: float = 0.0
    total_tokens: int = 0
    total_llm_calls: int = 0
    schema_completeness: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="Fraction of schema fields with at least one value + source.",
    )
    avg_sources_per_competitor: float = 0.0
    qc_iterations: int = 0
    rework_count: int = 0
    # --- 质量控制最终结论 ---
    qc_status: Literal["passed", "passed_with_notes", "failed"] = Field(
        default="passed",
        description="Final QC outcome. 'failed' means blocker/major findings remained "
                    "unresolved after the rework budget was exhausted; "
                    "'passed_with_notes' means only minor/info findings remained.",
    )
    unresolved_findings: int = Field(
        default=0,
        description="Count of blocker/major QC findings still open in the final review.",
    )
    # --- 可信度 / 置信度 ---
    avg_confidence: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="Mean source confidence across everything shipped in the report.",
    )
    low_confidence_claims: int = Field(
        default=0, description="Count of structured claims below the confidence threshold."
    )
    conflict_count: int = Field(
        default=0, description="Cross-source disagreements detected across the report."
    )
    # --- 人在回路 ---
    manual_correction_rate: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="Fraction of structured claims a human edited after generation. "
                    "The operational KPI the team drives down over time.",
    )
    corrected_fields: int = 0


class Correction(BaseModel):
    """应用到生成报告上的一次人工编辑（人在回路）。

    既存储在报告上（用于审计），也存储在一个全局修正表中，
    后者为主动学习闭环（`app.learning`）提供输入。
    """

    id: str = Field(default_factory=lambda: f"cor_{uuid4().hex[:10]}")
    report_id: str
    market: str = ""
    target_path: str = Field(description="Dotted path of the field edited, e.g. 'competitors[0].pricing.summary'")
    before: str = ""
    after: str = ""
    note: str = ""
    author: str = "operator"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SchemaSuggestion(BaseModel):
    """一条用于演进竞品 schema 的数据驱动建议（智能体自评）。

    由 ``app.meta.MetaEvaluator`` 根据历史报告中字段完整度的聚合
    与反复出现的 QC 结论产出。
    """

    field: str
    action: str = Field(description="deprecate | make_optional | tighten_prompt | add_field | split_field")
    rationale: str = ""
    evidence: Dict[str, float] = Field(default_factory=dict)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class KnowledgeChange(BaseModel):
    """同一竞品两个快照之间单个字段级别的变化。"""

    path: str
    change: str = Field(description="added | removed | changed")
    before: Optional[str] = None
    after: Optional[str] = None


class KnowledgeDiff(BaseModel):
    """某竞品最近两个快照之间的 diff（演化视图）。"""

    entity_key: str
    name: str
    market: str
    from_run_id: str = ""
    to_run_id: str = ""
    from_captured_at: Optional[str] = None
    to_captured_at: Optional[str] = None
    changes: List[KnowledgeChange] = Field(default_factory=list)
    summary: str = ""


class FinalReport(BaseModel):
    id: str
    run_id: str = Field(
        default="",
        description="Tracer run id that produced this report — links the report to its decision trace.",
    )
    product: str = Field(description="The user-provided product being analyzed.")
    market: str = Field(description="cn | us | <future-market-code>")
    locale: str = Field(description="zh-CN | en-US | ...")

    title: str
    executive_summary_md: str = ""
    sections: List[ReportSection] = Field(default_factory=list)
    competitors: List[CompetitorKnowledge] = Field(default_factory=list)
    target_product: Optional[CompetitorKnowledge] = Field(
        default=None,
        description="Knowledge collected for the user's own product (the analysis subject), "
                    "included alongside competitors in the comparison.",
    )
    comparison: ComparisonMatrix = Field(default_factory=ComparisonMatrix)

    metrics: ReportMetrics = Field(default_factory=ReportMetrics)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # 最终一轮 QC 审查的结论 —— 当质量控制最终未通过（返工预算耗尽仍有
    # 阻塞 / 重大问题）时，前端据此呈现"未通过"的原因。
    qc_findings: List[QCFinding] = Field(default_factory=list)

    # 报告中用到的所有来源 —— 为引用面板扁平化。
    all_sources: List[SourceRef] = Field(default_factory=list)

    # 生成后应用的人在回路编辑（审计轨迹）。
    corrections: List[Correction] = Field(default_factory=list)

    schema_version: str = "1.1.0"
