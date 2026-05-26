"""Final report schema — what the Writer agent produces and the API returns."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from pydantic import BaseModel, Field

from .competitor import CompetitorKnowledge, SourceRef


class ReportSection(BaseModel):
    heading: str
    body_md: str = Field(description="Markdown body. May contain [^src_xxx] citations.")
    sources: List[SourceRef] = Field(default_factory=list)


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

    metrics: ReportMetrics = Field(default_factory=ReportMetrics)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # All sources used across the report — flattened for the citation panel.
    all_sources: List[SourceRef] = Field(default_factory=list)

    schema_version: str = "1.0.0"
