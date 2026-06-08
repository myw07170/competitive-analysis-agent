"""Agent self-evaluation endpoints (Innovation-4) + correction transparency."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter

from ..meta import MetaEvaluator
from ..storage import get_store

router = APIRouter(prefix="/api/meta", tags=["meta"])


@router.get("/suggestions")
async def suggestions(limit: int = 200):
    """Data-driven schema-evolution suggestions from historical reports."""
    return await MetaEvaluator().evaluate(limit=limit)


@router.get("/corrections")
async def corrections(market: Optional[str] = None, limit: int = 50):
    """Recent human corrections feeding the active-learning loop."""
    store = get_store()
    await store.init()
    rows = await store.list_corrections(market=market, limit=limit)
    return {"corrections": [c.model_dump(mode="json") for c in rows]}
