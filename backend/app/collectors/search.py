"""Pluggable web-search backend.

Implements three providers (Tavily, Serper, Bing). All return a uniform
``SearchHit``. If no provider is configured (or its key is missing), we
return an empty list and the agent falls back to LLM-only collection.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import httpx

from ..config import get_settings
from ..observability.logger import get_logger

log = get_logger("collectors.search")


@dataclass
class SearchHit:
    title: str
    url: str
    snippet: str
    provider: str


async def search(query: str, *, limit: int = 5,
                 provider_override: Optional[str] = None) -> List[SearchHit]:
    settings = get_settings()
    provider = provider_override or settings.search_provider
    if provider == "none":
        return []
    try:
        if provider == "tavily":
            return await _tavily(query, limit=limit)
        if provider == "serper":
            return await _serper(query, limit=limit)
        if provider == "bing":
            return await _bing(query, limit=limit)
    except Exception as exc:
        log.warning(f"search provider {provider} failed: {exc!r}; returning empty list")
        return []
    return []


# ---------------------------------------------------------------------------
# Tavily
# ---------------------------------------------------------------------------
async def _tavily(query: str, *, limit: int) -> List[SearchHit]:
    settings = get_settings()
    if not settings.tavily_api_key:
        return []
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            "https://api.tavily.com/search",
            json={
                "api_key": settings.tavily_api_key,
                "query": query,
                "max_results": limit,
                "include_answer": False,
            },
        )
        resp.raise_for_status()
        data = resp.json()
    hits: List[SearchHit] = []
    for r in (data.get("results") or [])[:limit]:
        hits.append(SearchHit(
            title=r.get("title", ""),
            url=r.get("url", ""),
            snippet=r.get("content", "")[:500],
            provider="tavily",
        ))
    return hits


# ---------------------------------------------------------------------------
# Serper
# ---------------------------------------------------------------------------
async def _serper(query: str, *, limit: int) -> List[SearchHit]:
    settings = get_settings()
    if not settings.serper_api_key:
        return []
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            "https://google.serper.dev/search",
            json={"q": query, "num": limit},
            headers={"X-API-KEY": settings.serper_api_key, "Content-Type": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()
    hits: List[SearchHit] = []
    for r in (data.get("organic") or [])[:limit]:
        hits.append(SearchHit(
            title=r.get("title", ""),
            url=r.get("link", ""),
            snippet=r.get("snippet", "")[:500],
            provider="serper",
        ))
    return hits


# ---------------------------------------------------------------------------
# Bing
# ---------------------------------------------------------------------------
async def _bing(query: str, *, limit: int) -> List[SearchHit]:
    settings = get_settings()
    if not settings.bing_api_key:
        return []
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            "https://api.bing.microsoft.com/v7.0/search",
            params={"q": query, "count": limit, "responseFilter": "Webpages"},
            headers={"Ocp-Apim-Subscription-Key": settings.bing_api_key},
        )
        resp.raise_for_status()
        data = resp.json()
    pages = ((data.get("webPages") or {}).get("value") or [])[:limit]
    return [
        SearchHit(
            title=p.get("name", ""),
            url=p.get("url", ""),
            snippet=p.get("snippet", "")[:500],
            provider="bing",
        )
        for p in pages
    ]
