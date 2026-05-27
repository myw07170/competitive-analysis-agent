"""Report read endpoints."""
from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from ..report_html import render_report_html
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


@router.get("/{report_id}/html")
async def get_report_html(report_id: str, download: int = 0):
    """Return the report as a single self-contained HTML document.

    ``?download=1`` adds a ``Content-Disposition: attachment`` header so the
    browser saves the file instead of rendering it inline.
    """
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
