"""mock 模式下的端到端编排测试。

覆盖完整的 DAG（identify → collect → analyze → write → qc → done），
包括至少一次返工循环（mock QC 在迭代 0 返回 "rework"，在迭代 1 返回 "approve"）。
"""
from __future__ import annotations

from app.observability.tracer import Tracer
from app.orchestration import AnalysisRequest, run_analysis


async def test_us_full_run():
    req = AnalysisRequest(product="Notion", market="us")
    tracer = Tracer()
    report = await run_analysis(req, tracer)

    assert report.product == "Notion"
    assert report.market == "us"
    assert report.locale == "en-US"
    assert report.competitors, "should have at least one competitor"
    # mock 后端的市场检测应给出美国市场的竞品。
    assert any(c.name in {"Notion", "Coda", "ClickUp"} for c in report.competitors)
    for c in report.competitors:
        assert c.function_tree.nodes, f"{c.name} has empty function tree"
        assert c.pricing.tiers, f"{c.name} has no pricing tiers"
        assert c.user_profile.segments, f"{c.name} has no user segments"
        assert c.swot is not None, f"{c.name} missing SWOT"

    # QC mock 总是拒绝迭代 0 —— 因此报告应体现一次返工。
    assert report.metrics.qc_iterations >= 1
    assert report.metrics.total_llm_calls > 0
    # 新的可信度指标已填充。
    assert 0.0 <= report.metrics.avg_confidence <= 1.0
    assert report.metrics.manual_correction_rate == 0.0
    assert report.metrics.conflict_count >= 0


async def test_cn_full_run():
    req = AnalysisRequest(product="飞书", market="cn")
    tracer = Tracer()
    report = await run_analysis(req, tracer)

    assert report.market == "cn"
    assert report.locale == "zh-CN"
    assert report.competitors
