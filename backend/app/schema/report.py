"""Final report schema — what the Writer agent produces and the API returns."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

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
    """

    competitors: List[str] = Field(default_factory=list)
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


class FinalReport(BaseModel):
    id: str
    product: str = Field(description="The user-provided product being analyzed.")
    market: str = Field(description="cn | us | <future-market-code>")
    locale: str = Field(description="zh-CN | en-US | ...")

    title: str
    executive_summary_md: str = ""
    sections: List[ReportSection] = Field(default_factory=list)
    competitors: List[CompetitorKnowledge] = Field(default_factory=list)
    comparison: ComparisonMatrix = Field(default_factory=ComparisonMatrix)

    metrics: ReportMetrics = Field(default_factory=ReportMetrics)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # All sources used across the report — flattened for the citation panel.
    all_sources: List[SourceRef] = Field(default_factory=list)

    schema_version: str = "1.0.0"
