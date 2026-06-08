"""DAG checkpoint + resume (Innovation-6)."""
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
    assert ck["node"] == "qc"  # qc is the last stage executed


async def test_resume_from_checkpoint_produces_report():
    tracer = Tracer()
    report = await run_analysis(AnalysisRequest(product="Notion", market="us"), tracer)
    # Resume re-enters at the stage following the last completed node and
    # re-runs to completion (stages before the resume point are skipped).
    resumed = await resume_analysis(report.run_id, Tracer(run_id=report.run_id))
    assert resumed.competitors
    assert resumed.run_id == report.run_id
