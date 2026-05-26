"""Market profile registry — the extension point for new geographies.

To add a new market (e.g. ``jp``):

1. Create ``app/market/jp.py`` subclassing :class:`MarketProfile`.
2. Register it in ``REGISTRY`` below.
3. Add a locale bundle in ``app/i18n/locales.py``.
4. Add a frontend i18n bundle in ``frontend/src/i18n/jp.ts``.

Everything else — agents, schema, orchestrator, UI — reads from the active
profile and adapts automatically.
"""
from __future__ import annotations

from typing import Dict, List

from .base import MarketProfile
from .cn import ChinaMarket
from .us import USMarket

REGISTRY: Dict[str, MarketProfile] = {
    "cn": ChinaMarket(),
    "us": USMarket(),
}


def get_market(code: str) -> MarketProfile:
    if code not in REGISTRY:
        raise KeyError(f"Unknown market code: {code!r}. Known: {list(REGISTRY)}")
    return REGISTRY[code]


def list_markets() -> List[dict]:
    return [
        {"code": code, "display_name": p.display_name, "locale": p.locale,
         "currency": p.currency, "flag": p.flag}
        for code, p in REGISTRY.items()
    ]


__all__ = ["MarketProfile", "get_market", "list_markets", "REGISTRY"]
