"""跨运行知识演化端点（创新点 3）。

通过对最近两个快照做 diff，让 UI 能回答"自上次以来这个竞品有什么变化？"，
并浏览受跟踪的实体列表。
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException

from ..knowledge import compute_diff
from ..storage import get_store, normalize_entity_key

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


@router.get("/entities")
async def list_entities(market: Optional[str] = None):
    store = get_store()
    await store.init()
    return {"entities": await store.list_entities(market=market)}


@router.get("/history")
async def history(market: str, name: str, limit: int = 20):
    store = get_store()
    await store.init()
    key = normalize_entity_key(name, market)
    rows = await store.knowledge_history(key, limit=limit)
    return {
        "entity_key": key, "name": name, "market": market,
        "snapshots": [
            {"run_id": r["run_id"], "report_id": r["report_id"], "captured_at": r["captured_at"]}
            for r in rows
        ],
    }


@router.get("/diff")
async def diff(market: str, name: str):
    """对某个竞品最近两个快照做 diff。"""
    store = get_store()
    await store.init()
    key = normalize_entity_key(name, market)
    latest, previous = await store.two_latest_snapshots(key)
    if not latest:
        raise HTTPException(404, "no snapshots for that competitor")
    result = compute_diff(
        entity_key=key, name=name, market=market, latest=latest, previous=previous,
    )
    return result.model_dump(mode="json")
