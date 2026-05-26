"""QC agent deterministic-checks tests.

We exercise the deterministic path directly (no LLM needed). This validates
the part of QC that the rubric considers "real" feedback.
"""
from __future__ import annotations

import pytest

from app.agents.qc import QCAgent, _looks_placeholder
from app.config import get_settings
from app.market import get_market
from app.schema import (
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
        SourceRef(kind="web", title=f"t{i}", url=f"https://real-vendor-{i}.example.org",
                  snippet="...", confidence=0.8)
        for i in range(3)
    ]
    return CompetitorKnowledge(
        name="X",
        homepage="https://real-vendor.example.org",
        function_tree=FunctionTree(
            root_name="caps",
            nodes=[FunctionNode(name="a", sources=[s[0]])],
        ),
        pricing=PricingModel(
            tiers=[PricingTier(name="Free", currency="USD", sources=[s[0], s[1]])],
        ),
        user_profile=UserProfile(
            segments=[UserSegment(name="SMB", sources=[s[2]])],
        ),
        sources=s,
    )


def test_placeholder_url_detection():
    assert _looks_placeholder("http://example.com/foo")
    assert _looks_placeholder("https://localhost:8080")
    assert not _looks_placeholder("https://g2.com/products/notion")


def test_full_competitor_passes():
    qc = QCAgent(get_market("us"))
    findings = qc._deterministic_checks([_full_competitor()],
                                        get_settings().min_sources_per_competitor)
    # Should be 0 deterministic findings on a fully-populated competitor.
    assert findings == []


def test_missing_pricing_tier_is_major():
    c = _full_competitor()
    c.pricing.tiers = []
    qc = QCAgent(get_market("us"))
    findings = qc._deterministic_checks([c], 3)
    assert any(f.severity == Severity.MAJOR
               and "pricing.tiers" in f.target_path for f in findings)


def test_low_source_count_is_major():
    c = _full_competitor()
    c.sources = []
    c.pricing.tiers = [PricingTier(name="Free", currency="USD",
                                   sources=[SourceRef(kind="web", title="x")])]
    qc = QCAgent(get_market("us"))
    findings = qc._deterministic_checks([c], 5)
    assert any(f.severity == Severity.MAJOR
               and "sources" in f.target_path for f in findings)


def test_empty_function_tree_is_blocker():
    c = _full_competitor()
    c.function_tree.nodes = []
    qc = QCAgent(get_market("us"))
    findings = qc._deterministic_checks([c], 3)
    assert any(f.severity == Severity.BLOCKER
               and "function_tree" in f.target_path for f in findings)
