"""QC 智能体确定性检查测试。

我们直接走确定性路径（无需 LLM）。这验证了评分细则视为"真实"反馈的那部分 QC ——
包括按角色路由的采集器 / 分析师 / 撰写器检查。
"""
from __future__ import annotations

from app.agents.qc import QCAgent, _looks_placeholder
from app.config import get_settings
from app.market import get_market
from app.schema import (
    AgentRole,
    CompetitorKnowledge,
    FunctionTree,
    PricingModel,
    PricingTier,
    Severity,
    SourceRef,
    UserProfile,
    UserSegment,
)
from app.schema.competitor import FunctionNode


def _full_competitor() -> CompetitorKnowledge:
    s = [
        SourceRef(kind="web", title=f"t{i}", url=f"https://real-vendor-{i}.io",
                  snippet="...", confidence=0.8)
        for i in range(3)
    ]
    return CompetitorKnowledge(
        name="X",
        homepage="https://real-vendor.io",
        function_tree=FunctionTree(
            root_name="caps",
            nodes=[FunctionNode(name="a", sources=[s[0]])],
        ),
        pricing=PricingModel(
            tiers=[PricingTier(name="Free", monthly_price=0, currency="USD", sources=[s[0], s[1]])],
        ),
        user_profile=UserProfile(
            segments=[UserSegment(name="SMB", sources=[s[2]])],
        ),
        sources=s,
    )


def _labelled(c: CompetitorKnowledge):
    return [("competitors[0]", c)]


def _collector(c, min_sources):
    qc = QCAgent(get_market("us"))
    return qc._collector_checks(_labelled(c), min_sources, get_settings().min_confidence)


def test_placeholder_url_detection():
    assert _looks_placeholder("http://example.com/foo")
    assert _looks_placeholder("https://localhost:8080")
    assert not _looks_placeholder("https://g2.com/products/notion")


def test_full_competitor_passes():
    findings = _collector(_full_competitor(), get_settings().min_sources_per_competitor)
    # 对一个完全填充的竞品，确定性的采集器结论应为 0 条。
    assert findings == []


def test_missing_pricing_tier_is_major():
    c = _full_competitor()
    c.pricing.tiers = []
    findings = _collector(c, 3)
    assert any(f.severity == Severity.MAJOR and "pricing.tiers" in f.target_path
               for f in findings)


def test_low_source_count_is_major():
    c = _full_competitor()
    c.sources = []
    c.pricing.tiers = [PricingTier(name="Free", currency="USD",
                                   sources=[SourceRef(kind="web", title="x")])]
    findings = _collector(c, 5)
    assert any(f.severity == Severity.MAJOR and "sources" in f.target_path
               for f in findings)


def test_empty_function_tree_is_blocker():
    c = _full_competitor()
    c.function_tree.nodes = []
    findings = _collector(c, 3)
    assert any(f.severity == Severity.BLOCKER and "function_tree" in f.target_path
               for f in findings)


def test_missing_swot_routes_to_analyst():
    qc = QCAgent(get_market("us"))
    c = _full_competitor()  # 未设置 swot
    findings = qc._analyst_checks(_labelled(c))
    assert any(f.target_agent == AgentRole.ANALYST and f.severity == Severity.MAJOR
               and "swot" in f.target_path for f in findings)
