"""智能体自评端点（创新点 4）+ 修正透明度。"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter

from ..meta import MetaEvaluator
from ..storage import get_store

router = APIRouter(prefix="/api/meta", tags=["meta"])


@router.get("/suggestions")
async def suggestions(limit: int = 200):
    """来自历史报告的数据驱动 schema 演进建议。"""
    return await MetaEvaluator().evaluate(limit=limit)


@router.get("/corrections")
async def corrections(market: Optional[str] = None, limit: int = 50):
    """为主动学习闭环提供输入的近期人工修正。"""
    store = get_store()
    await store.init()
    rows = await store.list_corrections(market=market, limit=limit)
    return {"corrections": [c.model_dump(mode="json") for c in rows]}
