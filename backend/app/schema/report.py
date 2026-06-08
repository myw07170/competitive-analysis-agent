"""Final report schema — what the Writer agent produces and the API returns."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from .competitor import CompetitorKnowledge, SourceRef


class ReportSection(BaseModel):
    heading: str
    body_md: str = Field(description="Markdown body. May contain [^src_xxx] citations.")
    sources: List[SourceRef] = Field(default_factory=list)


class ComparisonCell(BaseModel):
    """One cell in a multi-competitor comparison table."""

    competitor: str
    value: str = ""
    detail: Optional[str] = None


class ComparisonRow(BaseModel):
    """One row in a comparison table (one capability / tier / segment, all competitors)."""

    label: str
    category: Optional[str] = None
    cells: List[ComparisonCell] = Field(default_factory=list)


class ComparisonMatrix(BaseModel):
    """Structured multi-competitor comparison — rendered as a real chart/table in the UI.

    Built deterministically from the CompetitorKnowledge records so the comparison
    is never lost to LLM markdown drift.

    The first entry in ``competitors`` is the user's own product when
    ``self_name`` is set; the frontend renders it in a distinct accent color.
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
    """Operational metrics surfaced to the UI — closes the business loop."""

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
    # --- credibility / confidence ---
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
    # --- human-in-the-loop ---
    manual_correction_rate: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="Fraction of structured claims a human edited after generation. "
                    "The operational KPI the team drives down over time.",
    )
    corrected_fields: int = 0


class Correction(BaseModel):
    """One human edit applied to a generated report (human-in-the-loop).

    Stored both on the report (for audit) and in a global corrections table that
    feeds the active-learning loop (`app.learning`).
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
    """A data-driven suggestion to evolve the competitor schema (Agent self-eval).

    Produced by ``app.meta.MetaEvaluator`` from aggregate field-completeness and
    recurring QC findings across historical reports.
    """

    field: str
    action: str = Field(description="deprecate | make_optional | tighten_prompt | add_field | split_field")
    rationale: str = ""
    evidence: Dict[str, float] = Field(default_factory=dict)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class KnowledgeChange(BaseModel):
    """A single field-level change between two snapshots of the same competitor."""

    path: str
    change: str = Field(description="added | removed | changed")
    before: Optional[str] = None
    after: Optional[str] = None


class KnowledgeDiff(BaseModel):
    """Diff between the two most recent snapshots of one competitor (evolution view)."""

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

    # All sources used across the report — flattened for the citation panel.
    all_sources: List[SourceRef] = Field(default_factory=list)

    # Human-in-the-loop edits applied after generation (audit trail).
    corrections: List[Correction] = Field(default_factory=list)

    schema_version: str = "1.1.0"
