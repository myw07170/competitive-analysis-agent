"""Competitor knowledge schema.

This is the canonical structure every agent must conform to. Defined once,
enforced everywhere via Pydantic. Three pillars:

1. ``FunctionTree``  — hierarchical capability map.
2. ``PricingModel``  — tiered pricing + add-ons.
3. ``UserProfile``   — segment-level audience description.

Every leaf fact carries a ``SourceRef`` so the report is fully traceable.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, HttpUrl, field_validator


# ---------------------------------------------------------------------------
# Tolerant coercion helpers
#
# Some LLMs (especially Chinese-trained models) return a single descriptive
# string where the schema expects a list, or non-numeric prose where it
# expects a number. Rather than fail the whole run on cosmetic shape drift,
# we coerce here — and keep the original prose in a sensible place.
# ---------------------------------------------------------------------------
_LIST_SPLIT_RE = re.compile(r"[、,;,；\n]| {2,}|/| - ")


def _coerce_str_list(v: Any) -> Any:
    if v is None:
        return []
    if isinstance(v, list):
        return v
    if isinstance(v, str):
        parts = [p.strip() for p in _LIST_SPLIT_RE.split(v) if p.strip()]
        return parts or [v.strip()]
    return v


def _coerce_dict(v: Any) -> Any:
    if v is None:
        return {}
    if isinstance(v, dict):
        return v
    if isinstance(v, str):
        return {"notes": v}
    return v


def _coerce_optional_float(v: Any) -> Any:
    """Return float for numeric inputs, None for anything else (e.g. '按需', 'custom')."""
    if v is None or isinstance(v, (int, float)):
        return v
    if isinstance(v, str):
        # Pull the first number out of the string, otherwise None.
        m = re.search(r"-?\d+(?:\.\d+)?", v)
        return float(m.group(0)) if m else None
    return v


def _coerce_optional_str(v: Any) -> Any:
    """Stringify scalars; preserve None; pass through real strings.

    LLMs sometimes return a freeform 'string' field as a number (4.7) or bool
    (True). Convert to str so Pydantic doesn't reject the whole record.
    """
    if v is None:
        return None
    if isinstance(v, str):
        return v if v.strip() else None
    if isinstance(v, (int, float, bool)):
        return str(v)
    return v


# ---------------------------------------------------------------------------
# Source traceability
# ---------------------------------------------------------------------------
class SourceRef(BaseModel):
    """A traceable pointer to the origin of a fact.

    The frontend renders these as clickable badges next to every claim.
    """

    id: str = Field(default_factory=lambda: f"src_{uuid4().hex[:10]}")
    kind: str = Field(
        default="llm_prior",
        description="One of: web | doc | interview | questionnaire | llm_prior",
    )
    title: str = ""
    url: Optional[str] = None
    snippet: str = Field(default="", description="Verbatim excerpt that supports the claim")
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    confidence: float = Field(
        default=0.7, ge=0.0, le=1.0,
        description="Self-reported confidence the source actually supports the claim.",
    )

    @field_validator("kind", mode="before")
    @classmethod
    def _validate_kind(cls, v):
        allowed = {"web", "doc", "interview", "questionnaire", "llm_prior"}
        if v is None or v == "":
            return "llm_prior"
        if v not in allowed:
            # Fall back instead of crashing on free-text kinds the model invents.
            return "llm_prior"
        return v

    @field_validator("confidence", mode="before")
    @classmethod
    def _coerce_confidence(cls, v):
        """Models sometimes return strings ('high', '0.85'); coerce to float."""
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            import re as _re
            m = _re.search(r"-?\d+(?:\.\d+)?", v)
            if m:
                f = float(m.group(0))
                return f / 100 if f > 1 else f
            label_map = {"low": 0.3, "medium": 0.6, "high": 0.85, "very high": 0.95}
            return label_map.get(v.strip().lower(), 0.7)
        return 0.7

    @field_validator("url", mode="before")
    @classmethod
    def _coerce_url(cls, v):
        """Empty strings should become None — pydantic optional handling."""
        if isinstance(v, str) and not v.strip():
            return None
        return v


class Cited(BaseModel):
    """A value bound to its supporting source(s). Used as the leaf of every
    structured field, so the writer can render inline citations."""

    value: str
    sources: List[SourceRef] = Field(default_factory=list)

    def confidence(self) -> Optional[float]:
        """Aggregate confidence for this claim = max confidence across its sources.

        A claim is only as strong as its single best-supporting source. Returns
        ``None`` when the claim carries no source at all (so callers can treat
        "unsourced" distinctly from "low confidence").
        """
        if not self.sources:
            return None
        return max(s.confidence for s in self.sources)


class ConflictFlag(BaseModel):
    """A detected disagreement between sources (or internal inconsistency).

    Surfaced in the UI as a "⚠ 来源分歧 / source conflict" badge so a reviewer
    can see *where* the evidence disagrees rather than trusting a silently
    picked value. Produced deterministically by ``app.consistency``.
    """

    field: str = Field(description="Dotted path of the field in conflict, e.g. 'pricing.tiers[Pro].monthly_price'")
    kind: str = Field(default="value_mismatch",
                      description="value_mismatch | duplicate | unsupported | range")
    detail: str = ""
    values: List[str] = Field(default_factory=list, description="The disagreeing values as strings.")
    source_ids: List[str] = Field(default_factory=list)
    severity: str = Field(default="minor", description="major | minor | info")


# ---------------------------------------------------------------------------
# Pillar 1: Function tree
# ---------------------------------------------------------------------------
class FunctionNode(BaseModel):
    name: str
    description: str = ""
    category: Optional[str] = None
    maturity: Optional[str] = Field(
        default=None,
        description="One of: ga | beta | preview | rumored",
    )
    sources: List[SourceRef] = Field(default_factory=list)
    children: List["FunctionNode"] = Field(default_factory=list)

    @field_validator("children", mode="before")
    @classmethod
    def _coerce_children(cls, v):
        """Accept a plain string, a list of strings, or a list of dicts."""
        if v is None:
            return []
        if isinstance(v, str):
            return [{"name": v}]
        if isinstance(v, list):
            out = []
            for item in v:
                if isinstance(item, str):
                    out.append({"name": item})
                else:
                    out.append(item)
            return out
        return v


FunctionNode.model_rebuild()


class FunctionTree(BaseModel):
    root_name: str
    nodes: List[FunctionNode] = Field(default_factory=list)

    def leaf_count(self) -> int:
        def _walk(n: FunctionNode) -> int:
            if not n.children:
                return 1
            return sum(_walk(c) for c in n.children)
        return sum(_walk(n) for n in self.nodes)


# ---------------------------------------------------------------------------
# Pillar 2: Pricing model
# ---------------------------------------------------------------------------
class PricingTier(BaseModel):
    name: str
    monthly_price: Optional[float] = None
    annual_price: Optional[float] = None
    currency: str = "USD"
    seat_based: bool = True
    included_features: List[str] = Field(default_factory=list)
    limits: dict = Field(default_factory=dict, description="e.g. {storage_gb: 100, seats: 10}")
    sources: List[SourceRef] = Field(default_factory=list)

    @field_validator("monthly_price", "annual_price", mode="before")
    @classmethod
    def _coerce_price(cls, v):
        return _coerce_optional_float(v)

    @field_validator("included_features", mode="before")
    @classmethod
    def _coerce_features(cls, v):
        return _coerce_str_list(v)

    @field_validator("limits", mode="before")
    @classmethod
    def _coerce_limits(cls, v):
        return _coerce_dict(v)


class PricingModel(BaseModel):
    summary: str = ""
    tiers: List[PricingTier] = Field(default_factory=list)
    addons: List[PricingTier] = Field(default_factory=list)
    has_free_tier: bool = False
    has_enterprise: bool = False
    notes: str = ""
    sources: List[SourceRef] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Pillar 3: User profile
# ---------------------------------------------------------------------------
class UserSegment(BaseModel):
    name: str
    description: str = ""
    company_size: Optional[str] = Field(
        default=None,
        description="One of: smb | mid_market | enterprise | individual | mixed",
    )
    industries: List[str] = Field(default_factory=list)
    geographies: List[str] = Field(default_factory=list)
    use_cases: List[str] = Field(default_factory=list)
    pain_points: List[str] = Field(default_factory=list)
    representative_quotes: List[Cited] = Field(default_factory=list)
    sources: List[SourceRef] = Field(default_factory=list)

    @field_validator(
        "industries", "geographies", "use_cases", "pain_points",
        mode="before",
    )
    @classmethod
    def _coerce_list(cls, v):
        return _coerce_str_list(v)

    @field_validator("representative_quotes", mode="before")
    @classmethod
    def _coerce_quotes(cls, v):
        """Accept a plain string, a list of strings, or a list of dicts."""
        if v is None:
            return []
        if isinstance(v, str):
            return [{"value": v, "sources": []}]
        if isinstance(v, list):
            out = []
            for item in v:
                if isinstance(item, str):
                    out.append({"value": item, "sources": []})
                else:
                    out.append(item)
            return out
        return v


class UserProfile(BaseModel):
    primary_segment: Optional[str] = None
    segments: List[UserSegment] = Field(default_factory=list)
    estimated_user_base: Optional[str] = None
    nps_or_rating: Optional[str] = None
    sources: List[SourceRef] = Field(default_factory=list)

    @field_validator(
        "primary_segment", "estimated_user_base", "nps_or_rating",
        mode="before",
    )
    @classmethod
    def _stringify(cls, v):
        return _coerce_optional_str(v)


# ---------------------------------------------------------------------------
# SWOT (derived during analysis)
# ---------------------------------------------------------------------------
class SWOTAnalysis(BaseModel):
    strengths: List[Cited] = Field(default_factory=list)
    weaknesses: List[Cited] = Field(default_factory=list)
    opportunities: List[Cited] = Field(default_factory=list)
    threats: List[Cited] = Field(default_factory=list)

    @field_validator(
        "strengths", "weaknesses", "opportunities", "threats",
        mode="before",
    )
    @classmethod
    def _coerce_cited_list(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            return [{"value": v, "sources": []}]
        if isinstance(v, list):
            out = []
            for item in v:
                if isinstance(item, str):
                    out.append({"value": item, "sources": []})
                else:
                    out.append(item)
            return out
        return v


# ---------------------------------------------------------------------------
# Top-level competitor record
# ---------------------------------------------------------------------------
class CompetitorKnowledge(BaseModel):
    """The schema all competitor data must conform to."""

    name: str
    aliases: List[str] = Field(default_factory=list)
    homepage: Optional[str] = None
    short_description: str = ""
    market_position: Optional[str] = None

    @field_validator("homepage", "market_position", mode="before")
    @classmethod
    def _stringify_optional(cls, v):
        return _coerce_optional_str(v)

    @field_validator("short_description", mode="before")
    @classmethod
    def _stringify_required(cls, v):
        if v is None:
            return ""
        if isinstance(v, str):
            return v
        return str(v)

    @field_validator("aliases", mode="before")
    @classmethod
    def _aliases_list(cls, v):
        return _coerce_str_list(v)

    function_tree: FunctionTree = Field(
        default_factory=lambda: FunctionTree(root_name="Capabilities")
    )
    pricing: PricingModel = Field(default_factory=PricingModel)
    user_profile: UserProfile = Field(default_factory=UserProfile)
    swot: Optional[SWOTAnalysis] = None

    sources: List[SourceRef] = Field(default_factory=list)
    conflicts: List[ConflictFlag] = Field(
        default_factory=list,
        description="Cross-source disagreements detected for this competitor (see app.consistency).",
    )
    schema_version: str = "1.1.0"

    def source_count(self) -> int:
        """How many unique sources back this competitor's data."""
        seen: set[str] = set()

        def _add(refs: List[SourceRef]) -> None:
            for r in refs:
                if r.id not in seen:
                    seen.add(r.id)

        _add(self.sources)
        _add(self.pricing.sources)
        _add(self.user_profile.sources)
        for tier in self.pricing.tiers + self.pricing.addons:
            _add(tier.sources)
        for seg in self.user_profile.segments:
            _add(seg.sources)

        def _walk_fn(node: FunctionNode) -> None:
            _add(node.sources)
            for c in node.children:
                _walk_fn(c)

        for n in self.function_tree.nodes:
            _walk_fn(n)
        return len(seen)

    def all_source_refs(self) -> List[SourceRef]:
        """Flatten every SourceRef attached anywhere on this competitor."""
        out: List[SourceRef] = []
        out.extend(self.sources)
        out.extend(self.pricing.sources)
        out.extend(self.user_profile.sources)
        for tier in self.pricing.tiers + self.pricing.addons:
            out.extend(tier.sources)
        for seg in self.user_profile.segments:
            out.extend(seg.sources)
            for q in seg.representative_quotes:
                out.extend(q.sources)

        def _walk_fn(node: FunctionNode) -> None:
            out.extend(node.sources)
            for c in node.children:
                _walk_fn(c)

        for n in self.function_tree.nodes:
            _walk_fn(n)
        if self.swot:
            for bucket in (self.swot.strengths, self.swot.weaknesses,
                           self.swot.opportunities, self.swot.threats):
                for item in bucket:
                    out.extend(item.sources)
        return out

    def avg_confidence(self) -> float:
        """Mean confidence across every source backing this competitor.

        Drives the "confidence-aware" orchestration: a competitor whose evidence
        is, on average, weak becomes a candidate for targeted re-collection.
        """
        refs = self.all_source_refs()
        if not refs:
            return 0.0
        return round(sum(r.confidence for r in refs) / len(refs), 3)

    def low_confidence_claims(self, threshold: float) -> List[str]:
        """Dotted paths of structured claims whose best source is below ``threshold``.

        Used by QC to raise targeted, confidence-driven rework findings.
        """
        weak: List[str] = []

        def _check(path: str, refs: List[SourceRef]) -> None:
            if refs and max(r.confidence for r in refs) < threshold:
                weak.append(path)

        for i, tier in enumerate(self.pricing.tiers):
            _check(f"pricing.tiers[{i}]", tier.sources)
        for i, seg in enumerate(self.user_profile.segments):
            _check(f"user_profile.segments[{i}]", seg.sources)
        if self.swot:
            for label, bucket in (("strengths", self.swot.strengths),
                                  ("weaknesses", self.swot.weaknesses),
                                  ("opportunities", self.swot.opportunities),
                                  ("threats", self.swot.threats)):
                for j, item in enumerate(bucket):
                    _check(f"swot.{label}[{j}]", item.sources)
        return weak
