"""Schema 冒烟测试 —— 确保必填字段必填、可选字段可选。"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schema import (
    CompetitorKnowledge,
    FunctionTree,
    PricingModel,
    SourceRef,
    UserProfile,
)


def test_minimal_competitor_round_trips():
    c = CompetitorKnowledge(name="X")
    j = c.model_dump_json()
    c2 = CompetitorKnowledge.model_validate_json(j)
    assert c2.name == "X"
    assert c2.function_tree.nodes == []
    assert c2.source_count() == 0


def test_source_ref_coerces_bad_kind():
    # 对于模型臆造的自由文本 kind，schema 刻意回退而非崩溃 ——
    # 因此一个无效的 kind 会变成 "llm_prior"，而不是报错。
    assert SourceRef(kind="bogus").kind == "llm_prior"
    assert SourceRef(kind="web").kind == "web"


def test_source_count_dedupes_by_id():
    s = SourceRef(kind="web", title="t", url="https://example.com")
    c = CompetitorKnowledge(
        name="X",
        sources=[s],
        pricing=PricingModel(sources=[s]),    # 相同 id，只计一次
        user_profile=UserProfile(sources=[s]),
    )
    assert c.source_count() == 1


def test_function_tree_leaf_count():
    from app.schema.competitor import FunctionNode
    root = FunctionNode(name="root", children=[
        FunctionNode(name="a"),
        FunctionNode(name="b", children=[FunctionNode(name="b1"), FunctionNode(name="b2")]),
    ])
    tree = FunctionTree(root_name="x", nodes=[root])
    # root 的叶子 = a + b1 + b2 = 3（b 本身有子节点，因此不是叶子）
    assert tree.leaf_count() == 3
