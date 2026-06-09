"""跨来源冲突检测 + 自一致性投票（创新点 2）。"""
from __future__ import annotations

from app.consistency import detect_conflicts, majority_vote
from app.schema import CompetitorKnowledge, PricingModel, PricingTier
from app.schema.competitor import FunctionNode, FunctionTree


def test_duplicate_tier_price_is_conflict():
    c = CompetitorKnowledge(name="X", pricing=PricingModel(tiers=[
        PricingTier(name="Pro", monthly_price=10, currency="USD"),
        PricingTier(name="Pro", monthly_price=20, currency="USD"),
    ]))
    flags = detect_conflicts(c)
    assert any(f.kind == "value_mismatch" and "pro" in f.field.lower() for f in flags)


def test_free_tier_without_zero_priced_tier():
    c = CompetitorKnowledge(name="X", pricing=PricingModel(
        has_free_tier=True,
        tiers=[PricingTier(name="Pro", monthly_price=10, currency="USD")],
    ))
    flags = detect_conflicts(c)
    assert any(f.field == "pricing.has_free_tier" for f in flags)


def test_currency_drift_flagged():
    c = CompetitorKnowledge(name="X", pricing=PricingModel(tiers=[
        PricingTier(name="A", monthly_price=10, currency="USD"),
        PricingTier(name="B", monthly_price=20, currency="CNY"),
    ]))
    flags = detect_conflicts(c)
    assert any("currency" in f.field for f in flags)


def test_duplicate_capability_flagged():
    c = CompetitorKnowledge(name="X", function_tree=FunctionTree(
        root_name="r", nodes=[FunctionNode(name="Docs"), FunctionNode(name="docs")],
    ))
    flags = detect_conflicts(c)
    assert any(f.kind == "duplicate" for f in flags)


def test_clean_competitor_has_no_conflicts():
    c = CompetitorKnowledge(name="X", pricing=PricingModel(
        has_free_tier=True,
        tiers=[
            PricingTier(name="Free", monthly_price=0, currency="USD"),
            PricingTier(name="Pro", monthly_price=10, currency="USD"),
        ],
    ))
    assert detect_conflicts(c) == []


def test_majority_vote_single_sample_passthrough():
    assert majority_vote([["A", "B", "C", "D", "E"]], keep=3) == ["A", "B", "C"]


def test_majority_vote_keeps_consensus():
    samples = [["A", "B", "C"], ["A", "B", "X"], ["A", "B", "Y"]]
    voted = majority_vote(samples, keep=4)
    assert voted == ["A", "B"]  # 只有 A 和 B 出现在多数样本中
