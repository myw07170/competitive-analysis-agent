"""遵循 robots、带每主机限速的页面抓取器。"""
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
    """抓取一个页面，硬性失败时返回 None。

    遵守 robots.txt，应用每主机限速，通过 BeautifulSoup 提取纯文本，
    并截断到 ``max_chars``（并设置标志位）。
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
        # 很可能是 JSON/PDF/二进制 —— 跳过
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
