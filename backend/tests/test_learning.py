"""主动学习闭环（创新点 5）：修正转化为对智能体的引导。"""
from __future__ import annotations

from app.learning import invalidate_cache, recent_guidance
from app.schema.report import Correction
from app.storage import get_store


async def test_guidance_reflects_saved_corrections():
    store = get_store()
    await store.init()
    invalidate_cache("us")

    await store.save_correction(Correction(
        report_id="rpt_test", market="us",
        target_path="competitors[0].pricing.summary",
        before="vague", after="Free + 3 paid tiers, seat-based",
        note="state the tier count explicitly",
    ))
    invalidate_cache("us")

    guidance = await recent_guidance("us")
    assert "Lessons learned" in guidance
    assert "pricing.summary" in guidance


async def test_guidance_empty_for_unknown_market():
    invalidate_cache("xx")
    assert await recent_guidance("xx") == ""
