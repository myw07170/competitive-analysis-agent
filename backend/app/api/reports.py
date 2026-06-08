"""Report read + human-in-the-loop edit endpoints."""
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
    """Delete a report and all of its associated records (including its trace)."""
    store = get_store()
    await store.init()
    deleted = await store.delete_report(report_id)
    if not deleted:
        raise HTTPException(404, "report not found")
    return {"ok": True, "id": report_id}


# ---------------------------------------------------------------------------
# Human-in-the-loop editing
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
    """Approximate count of editable structured claims — the manual-correction denominator."""
    n = 1 + len(report.sections)  # executive summary + each section
    items = list(report.competitors) + ([report.target_product] if report.target_product else [])
    for c in items:
        n += 3  # short_description, market_position, homepage
        n += max(c.function_tree.leaf_count(), len(c.function_tree.nodes))
        n += len(c.pricing.tiers)
        n += len(c.user_profile.segments)
        if c.swot:
            n += sum(len(b) for b in (c.swot.strengths, c.swot.weaknesses,
                                      c.swot.opportunities, c.swot.threats))
    return max(n, 1)


@router.patch("/{report_id}")
async def patch_report(report_id: str, req: PatchReportRequest):
    """Apply human edits to a generated report (human-in-the-loop correction).

    Each edit sets a dotted ``target_path`` to a new value, records a
    :class:`Correction` (before/after) for the audit trail and the active-learning
    loop, and the report's ``manual_correction_rate`` metric is recomputed.
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

    # Re-validate the edited document before persisting.
    try:
        edited = FinalReport.model_validate(root)
    except Exception as exc:
        raise HTTPException(400, f"edit produced an invalid report: {exc}")

    # Append corrections to the report audit trail + global corrections table.
    edited.corrections = list(report.corrections) + corrections
    for c in corrections:
        await store.save_correction(c)

    total_corrections = await store.count_corrections_for_report(report_id)
    claims = _count_claims(edited)
    edited.metrics.corrected_fields = total_corrections
    edited.metrics.manual_correction_rate = round(min(total_corrections / claims, 1.0), 3)

    await store.save_report(edited)
    # New lessons learned should reach the next run immediately.
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
    """Return the report as a single self-contained HTML document."""
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
