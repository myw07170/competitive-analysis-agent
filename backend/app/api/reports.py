"""报告读取 + 人在回路编辑端点。"""
from __future__ import annotations

import re
from typing import Any, List, Tuple

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from ..learning import invalidate_cache
from ..report_html import render_report_html
from ..schema.report import Correction, FinalReport
from ..storage import get_store

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/")
async def list_reports(limit: int = 50):
    store = get_store()
    await store.init()
    return {"reports": await store.list_reports(limit=limit)}


@router.get("/{report_id}")
async def get_report(report_id: str):
    store = get_store()
    await store.init()
    report = await store.get_report(report_id)
    if not report:
        raise HTTPException(404, "report not found")
    return report.model_dump(mode="json")


@router.delete("/{report_id}")
async def delete_report(report_id: str):
    """删除一份报告及其所有关联记录（包括其追踪）。"""
    store = get_store()
    await store.init()
    deleted = await store.delete_report(report_id)
    if not deleted:
        raise HTTPException(404, "report not found")
    return {"ok": True, "id": report_id}


# ---------------------------------------------------------------------------
# 人在回路编辑
# ---------------------------------------------------------------------------
class ReportEdit(BaseModel):
    target_path: str
    value: Any
    note: str = ""
    author: str = "operator"


class PatchReportRequest(BaseModel):
    edits: List[ReportEdit]


_TOKEN = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)(?:\[(\d+)\])?")


def _split_path(path: str) -> List[Tuple[str, Any]]:
    steps: List[Tuple[str, Any]] = []
    for part in path.split("."):
        m = _TOKEN.fullmatch(part)
        if not m:
            raise ValueError(f"invalid path segment: {part!r}")
        steps.append(("key", m.group(1)))
        if m.group(2) is not None:
            steps.append(("idx", int(m.group(2))))
    return steps


def _resolve_parent(root: Any, steps: List[Tuple[str, Any]]) -> Tuple[Any, Any]:
    cur = root
    for _, val in steps[:-1]:
        cur = cur[val]
    return cur, steps[-1][1]


def _count_claims(report: FinalReport) -> int:
    """可编辑结构化断言的近似数量 —— 人工修正率的分母。"""
    n = 1 + len(report.sections)  # 执行摘要 + 每个章节
    items = list(report.competitors) + ([report.target_product] if report.target_product else [])
    for c in items:
        n += 3  # short_description、market_position、homepage
        n += max(c.function_tree.leaf_count(), len(c.function_tree.nodes))
        n += len(c.pricing.tiers)
        n += len(c.user_profile.segments)
        if c.swot:
            n += sum(len(b) for b in (c.swot.strengths, c.swot.weaknesses,
                                      c.swot.opportunities, c.swot.threats))
    return max(n, 1)


@router.patch("/{report_id}")
async def patch_report(report_id: str, req: PatchReportRequest):
    """对一份生成的报告应用人工编辑（人在回路修正）。

    每次编辑把一个点分的 ``target_path`` 设为新值，记录一条 :class:`Correction`
    （前 / 后）用于审计轨迹与主动学习闭环，并重新计算报告的
    ``manual_correction_rate`` 指标。
    """
    store = get_store()
    await store.init()
    report = await store.get_report(report_id)
    if not report:
        raise HTTPException(404, "report not found")
    if not req.edits:
        raise HTTPException(400, "no edits provided")

    root = report.model_dump(mode="json")
    corrections: List[Correction] = []
    for edit in req.edits:
        try:
            steps = _split_path(edit.target_path)
            parent, key = _resolve_parent(root, steps)
            before = parent[key]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise HTTPException(400, f"bad target_path {edit.target_path!r}: {exc}")
        parent[key] = edit.value
        corrections.append(Correction(
            report_id=report_id, market=report.market, target_path=edit.target_path,
            before="" if before is None else str(before),
            after="" if edit.value is None else str(edit.value),
            note=edit.note, author=edit.author,
        ))

    # 持久化前重新校验编辑后的文档。
    try:
        edited = FinalReport.model_validate(root)
    except Exception as exc:
        raise HTTPException(400, f"edit produced an invalid report: {exc}")

    # 把修正追加到报告审计轨迹 + 全局修正表。
    edited.corrections = list(report.corrections) + corrections
    for c in corrections:
        await store.save_correction(c)

    total_corrections = await store.count_corrections_for_report(report_id)
    claims = _count_claims(edited)
    edited.metrics.corrected_fields = total_corrections
    edited.metrics.manual_correction_rate = round(min(total_corrections / claims, 1.0), 3)

    await store.save_report(edited)
    # 新的经验教训应立即送达下一次运行。
    invalidate_cache(report.market)

    return {
        "ok": True,
        "id": report_id,
        "applied": len(corrections),
        "manual_correction_rate": edited.metrics.manual_correction_rate,
        "report": edited.model_dump(mode="json"),
    }


@router.get("/{report_id}/html")
async def get_report_html(report_id: str, download: int = 0):
    """以单个自包含的 HTML 文档形式返回报告。"""
    store = get_store()
    await store.init()
    report = await store.get_report(report_id)
    if not report:
        raise HTTPException(404, "report not found")
    body = render_report_html(report)
    headers = {}
    if download:
        safe_product = re.sub(r"[^A-Za-z0-9._-]+", "_", report.product).strip("_") or "report"
        filename = f"competitive_report_{safe_product}_{report.id}.html"
        headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return Response(content=body, media_type="text/html; charset=utf-8", headers=headers)
