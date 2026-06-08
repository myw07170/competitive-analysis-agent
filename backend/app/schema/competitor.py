"""竞品知识 schema。

这是每个智能体都必须遵循的标准结构。定义一次，处处通过 Pydantic 强制执行。
三大支柱：

1. ``FunctionTree``  —— 层级化的能力图谱。
2. ``PricingModel``  —— 分档定价 + 附加项。
3. ``UserProfile``   —— 细分层面的受众描述。

每个叶子事实都携带一个 ``SourceRef``，因此报告完全可溯源。
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, HttpUrl, field_validator


# ---------------------------------------------------------------------------
# 宽容的类型强制转换辅助函数
#
# 某些 LLM（尤其是中文训练的模型）会在 schema 期望列表处返回单个描述性字符串，
# 或在期望数字处返回非数字的文字。与其因表层的形态漂移而让整次运行失败，
# 不如在这里做强制转换——并把原始文字保留在合理的位置。
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
    """数值输入返回 float，其他一律返回 None（例如 '按需'、'custom'）。"""
    if v is None or isinstance(v, (int, float)):
        return v
    if isinstance(v, str):
        # 从字符串中取出第一个数字，否则返回 None。
        m = re.search(r"-?\d+(?:\.\d+)?", v)
        return float(m.group(0)) if m else None
    return v


def _coerce_optional_str(v: Any) -> Any:
    """把标量转为字符串；保留 None；真正的字符串原样通过。

    LLM 有时会把一个自由格式的 'string' 字段返回为数字（4.7）或布尔值（True）。
    转为 str，使 Pydantic 不至于拒绝整条记录。
    """
    if v is None:
        return None
    if isinstance(v, str):
        return v if v.strip() else None
    if isinstance(v, (int, float, bool)):
        return str(v)
    return v


# ---------------------------------------------------------------------------
# 来源可溯源性
# ---------------------------------------------------------------------------
class SourceRef(BaseModel):
    """指向某条事实出处的可溯源指针。

    前端会把它们渲染为每条断言旁可点击的徽标。
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
            # 对于模型臆造的自由文本 kind，回退而非崩溃。
            return "llm_prior"
        return v

    @field_validator("confidence", mode="before")
    @classmethod
    def _coerce_confidence(cls, v):
        """模型有时返回字符串（'high'、'0.85'）；强制转为 float。"""
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
        """空字符串应变为 None —— 配合 pydantic 的可选字段处理。"""
        if isinstance(v, str) and not v.strip():
            return None
        return v


class Cited(BaseModel):
    """绑定到其支撑来源的一个值。用作每个结构化字段的叶子，
    使撰写器能渲染内联引用。"""

    value: str
    sources: List[SourceRef] = Field(default_factory=list)

    def confidence(self) -> Optional[float]:
        """该断言的聚合置信度 = 其各来源置信度的最大值。

        一条断言的强度取决于它唯一最强的支撑来源。当断言完全没有来源时返回
        ``None``（这样调用方可以把"无来源"与"低置信度"区别对待）。
        """
        if not self.sources:
            return None
        return max(s.confidence for s in self.sources)


class ConflictFlag(BaseModel):
    """检测到的来源间分歧（或内部不一致）。

    在 UI 中呈现为"⚠ 来源分歧 / source conflict"徽标，使审阅者能看到证据在*哪里*
    分歧，而非信任一个被默默选中的值。由 ``app.consistency`` 确定性地产出。
    """

    field: str = Field(description="Dotted path of the field in conflict, e.g. 'pricing.tiers[Pro].monthly_price'")
    kind: str = Field(default="value_mismatch",
                      description="value_mismatch | duplicate | unsupported | range")
    detail: str = ""
    values: List[str] = Field(default_factory=list, description="The disagreeing values as strings.")
    source_ids: List[str] = Field(default_factory=list)
    severity: str = Field(default="minor", description="major | minor | info")


# ---------------------------------------------------------------------------
# 支柱 1：功能树
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
        """接受纯字符串、字符串列表或字典列表。"""
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
# 支柱 2：定价模型
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
# 支柱 3：用户画像
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
        """接受纯字符串、字符串列表或字典列表。"""
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
# SWOT（在分析阶段派生）
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
# 顶层竞品记录
# ---------------------------------------------------------------------------
class CompetitorKnowledge(BaseModel):
    """所有竞品数据都必须遵循的 schema。"""

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
        """有多少个去重后的来源支撑该竞品的数据。"""
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
        """扁平化该竞品上任意位置挂载的每一个 SourceRef。"""
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
        """支撑该竞品的每个来源置信度的均值。

        驱动"置信度感知"的编排：证据平均偏弱的竞品会成为定向重新采集的候选项。
        """
        refs = self.all_source_refs()
        if not refs:
            return 0.0
        return round(sum(r.confidence for r in refs) / len(refs), 3)

    def low_confidence_claims(self, threshold: float) -> List[str]:
        """其最佳来源低于 ``threshold`` 的结构化断言的点分路径。

        供 QC 用于提出定向的、由置信度驱动的返工结论。
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
