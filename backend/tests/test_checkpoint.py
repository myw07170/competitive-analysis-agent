"""DAG 检查点 + 续跑（创新点 6）。"""
from __future__ import annotations

from app.observability.tracer import Tracer
from app.orchestration import AnalysisRequest, resume_analysis, run_analysis
from app.storage import get_store


async def test_checkpoint_written_each_node():
    tracer = Tracer()
    report = await run_analysis(AnalysisRequest(product="Notion", market="us"), tracer)
    store = get_store()
    ck = await store.latest_checkpoint(report.run_id)
    assert ck is not None
    assert ck["node"] == "qc"  # qc 是最后执行的阶段


async def test_resume_from_checkpoint_produces_report():
    tracer = Tracer()
    report = await run_analysis(AnalysisRequest(product="Notion", market="us"), tracer)
    # 续跑从最后一个完成节点的下一个阶段重新进入，并重跑至完成
    # （恢复点之前的阶段会被跳过）。
    resumed = await resume_analysis(report.run_id, Tracer(run_id=report.run_id))
    assert resumed.competitors
    assert resumed.run_id == report.run_id
