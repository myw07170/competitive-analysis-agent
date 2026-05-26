"""Schema smoke tests — make sure required fields are required and optional are optional."""
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


def test_source_ref_rejects_bad_kind():
    with pytest.raises(ValidationError):
        SourceRef(kind="bogus")


def test_source_count_dedupes_by_id():
    s = SourceRef(kind="web", title="t", url="https://example.com")
    c = CompetitorKnowledge(
        name="X",
        sources=[s],
        pricing=PricingModel(sources=[s]),    # same id, counted once
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
    # Leaves of root = a + b1 + b2 = 3 (b itself is not a leaf because it has children)
    assert tree.leaf_count() == 3
