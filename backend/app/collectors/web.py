"""Robots-respecting page fetcher with per-host rate limiting."""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Dict, Optional
from urllib.parse import urlsplit

import httpx
from bs4 import BeautifulSoup

from ..config import get_settings
from ..observability.logger import get_logger
from .robots import can_fetch

log = get_logger("collectors.web")


@dataclass
class FetchedPage:
    url: str
    status_code: int
    title: str
    text: str
    truncated: bool = False
    blocked_by_robots: bool = False


_LAST_FETCH: Dict[str, float] = {}
_LOCKS: Dict[str, asyncio.Lock] = {}


async def _respect_rate_limit(host: str) -> None:
    settings = get_settings()
    interval = 1.0 / max(settings.crawl_rate_limit_per_host, 0.1)
    lock = _LOCKS.setdefault(host, asyncio.Lock())
    async with lock:
        last = _LAST_FETCH.get(host, 0.0)
        wait = interval - (time.monotonic() - last)
        if wait > 0:
            await asyncio.sleep(wait)
        _LAST_FETCH[host] = time.monotonic()


async def fetch_page(url: str, *, max_chars: int = 8000) -> Optional[FetchedPage]:
    """Fetch a page, return None on hard failure.

    Honors robots.txt, applies a per-host rate limit, extracts plain text
    via BeautifulSoup, and truncates to ``max_chars`` (with a flag).
    """
    if not await can_fetch(url):
        log.info(f"blocked by robots: {url}")
        return FetchedPage(url=url, status_code=0, title="", text="", blocked_by_robots=True)

    host = urlsplit(url).netloc
    await _respect_rate_limit(host)

    settings = get_settings()
    headers = {"User-Agent": settings.user_agent, "Accept": "text/html,application/xhtml+xml"}
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
    except Exception as exc:
        log.warning(f"fetch failed {url}: {exc!r}")
        return None

    if resp.status_code >= 400:
        return FetchedPage(url=str(resp.url), status_code=resp.status_code, title="", text="")

    content_type = resp.headers.get("content-type", "").lower()
    if "html" not in content_type and "xml" not in content_type:
        # Probably JSON/PDF/binary — skip
        return FetchedPage(url=str(resp.url), status_code=resp.status_code,
                           title="", text=resp.text[:max_chars])

    soup = BeautifulSoup(resp.text, "lxml")
    title = soup.title.string.strip() if soup.title and soup.title.string else ""
    for tag in soup(["script", "style", "noscript", "header", "footer", "nav"]):
        tag.decompose()
    text = " ".join(soup.get_text(separator=" ").split())
    truncated = len(text) > max_chars
    text = text[:max_chars]

    return FetchedPage(url=str(resp.url), status_code=resp.status_code,
                       title=title, text=text, truncated=truncated)
