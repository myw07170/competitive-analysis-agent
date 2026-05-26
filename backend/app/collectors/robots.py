"""Tiny robots.txt enforcer.

We deliberately do not pull in `protego` or the like — for our usage pattern
(occasional checks, friendly cache) the stdlib ``urllib.robotparser`` is plenty.
"""
from __future__ import annotations

import asyncio
from typing import Dict
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from ..config import get_settings
from ..observability.logger import get_logger

log = get_logger("collectors.robots")

_CACHE: Dict[str, RobotFileParser] = {}
_LOCKS: Dict[str, asyncio.Lock] = {}


async def _load(host_base: str) -> RobotFileParser:
    parser = _CACHE.get(host_base)
    if parser is not None:
        return parser
    lock = _LOCKS.setdefault(host_base, asyncio.Lock())
    async with lock:
        # Double-checked: another coroutine may have populated while we waited.
        parser = _CACHE.get(host_base)
        if parser is not None:
            return parser
        parser = RobotFileParser()
        parser.set_url(host_base + "/robots.txt")
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(parser.url,
                                        headers={"User-Agent": get_settings().user_agent})
                if resp.status_code >= 400:
                    parser.parse([])     # treat as allow-all
                else:
                    parser.parse(resp.text.splitlines())
        except Exception as exc:
            log.warning(f"robots.txt fetch failed for {host_base}: {exc!r}; allowing.")
            parser.parse([])
        _CACHE[host_base] = parser
        return parser


async def can_fetch(url: str) -> bool:
    if not get_settings().respect_robots:
        return True
    parts = urlsplit(url)
    if not parts.scheme or not parts.netloc:
        return False
    host_base = f"{parts.scheme}://{parts.netloc}"
    parser = await _load(host_base)
    ua = get_settings().user_agent
    return parser.can_fetch(ua, url)
