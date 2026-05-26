"""Report read endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

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
