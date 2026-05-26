"""Trace endpoints — used by the "decision replay" panel."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..storage import get_store

router = APIRouter(prefix="/api/traces", tags=["traces"])


@router.get("/{run_id}")
async def get_trace(run_id: str):
    store = get_store()
    await store.init()
    events = await store.get_trace(run_id)
    if not events:
        raise HTTPException(404, "no trace for that run")
    return {
        "run_id": run_id,
        "events": [e.model_dump(mode="json") for e in events],
    }
