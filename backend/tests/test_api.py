"""基于 ASGI 应用的端到端 API 测试（mock 模式）。

覆盖前端所用的完整接口：start → 轮询 → report → 人工编辑（PATCH）
→ 知识 diff → meta 建议 → 续跑守卫。
"""
from __future__ import annotations

import asyncio

from httpx import ASGITransport, AsyncClient

from main import app


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _run_to_completion(ac: AsyncClient, product="Notion", market="us") -> str:
    r = await ac.post("/api/analysis/start", json={"product": product, "market": market})
    assert r.status_code == 200
    run_id = r.json()["run_id"]
    for _ in range(150):
        s = (await ac.get(f"/api/analysis/status/{run_id}")).json()
        if s["finished"]:
            assert not s.get("error"), s.get("error")
            return s["report_id"]
        await asyncio.sleep(0.05)
    raise AssertionError("run did not finish in time")


async def test_health_reports_mock_mode():
    async with _client() as ac:
        r = await ac.get("/api/health")
        assert r.status_code == 200
        assert r.json()["mock_mode"] is True


async def test_full_run_edit_and_metrics():
    async with _client() as ac:
        report_id = await _run_to_completion(ac)
        rep = (await ac.get(f"/api/reports/{report_id}")).json()
        assert rep["competitors"]
        # 新的可信度指标已存在。
        for k in ("avg_confidence", "conflict_count", "manual_correction_rate"):
            assert k in rep["metrics"]

        # 人在回路编辑。
        pr = await ac.patch(f"/api/reports/{report_id}", json={
            "edits": [{"target_path": "competitors[0].market_position",
                       "value": "EDITED position", "note": "fix"}],
        })
        assert pr.status_code == 200
        body = pr.json()
        assert body["manual_correction_rate"] > 0

        rep2 = (await ac.get(f"/api/reports/{report_id}")).json()
        assert rep2["competitors"][0]["market_position"] == "EDITED position"
        assert rep2["metrics"]["manual_correction_rate"] > 0
        assert len(rep2["corrections"]) >= 1

        # 非法路径被拒绝。
        bad = await ac.patch(f"/api/reports/{report_id}", json={
            "edits": [{"target_path": "missing[9].x", "value": "y"}]})
        assert bad.status_code == 400


async def test_knowledge_and_meta_endpoints():
    async with _client() as ac:
        await _run_to_completion(ac, product="Notion", market="us")
        kd = await ac.get("/api/knowledge/diff", params={"market": "us", "name": "Notion"})
        assert kd.status_code == 200
        assert "summary" in kd.json()

        ents = (await ac.get("/api/knowledge/entities", params={"market": "us"})).json()
        assert any(e["name"] == "Notion" for e in ents["entities"])

        meta = (await ac.get("/api/meta/suggestions")).json()
        assert meta["n_competitors"] >= 1
        assert "field_completeness" in meta


async def test_resume_unknown_run_is_404():
    async with _client() as ac:
        r = await ac.post("/api/analysis/resume/does-not-exist")
        assert r.status_code == 404
