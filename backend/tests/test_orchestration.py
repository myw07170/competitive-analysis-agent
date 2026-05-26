"""End-to-end orchestration test in mock mode.

Exercises the full DAG (identify → collect → analyze → write → qc → done),
including at least one rework loop (the mock QC returns "rework" on iteration 0
and "approve" on iteration 1).
"""
from __future__ import annotations

import os

import pytest

os.environ["VOLC_MOCK"] = "1"
os.environ["DATA_DIR"] = "./.test-data"

from app.observability.tracer import Tracer  # noqa: E402
from app.orchestration import AnalysisRequest, run_analysis  # noqa: E402


@pytest.mark.asyncio
async def test_us_full_run():
    req = AnalysisRequest(product="Notion", market="us")
    tracer = Tracer()
    report = await run_analysis(req, tracer)

    assert report.product == "Notion"
    assert report.market == "us"
    assert report.locale == "en-US"
    assert report.competitors, "should have at least one competitor"
    for c in report.competitors:
        assert c.function_tree.nodes, f"{c.name} has empty function tree"
        assert c.pricing.tiers, f"{c.name} has no pricing tiers"
        assert c.user_profile.segments, f"{c.name} has no user segments"
        assert c.swot is not None, f"{c.name} missing SWOT"

    # The QC mock always rejects iteration 0 — so the report should reflect a rework.
    assert report.metrics.qc_iterations >= 1
    assert report.metrics.total_llm_calls > 0


@pytest.mark.asyncio
async def test_cn_full_run():
    req = AnalysisRequest(product="飞书", market="cn")
    tracer = Tracer()
    report = await run_analysis(req, tracer)

    assert report.market == "cn"
    assert report.locale == "zh-CN"
    assert report.competitors
