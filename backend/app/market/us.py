"""美国市场画像。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from .base import MarketProfile


def _default_seeds() -> List[str]:
    return [
        "{product} competitors",
        "{product} alternatives",
        "{product} pricing",
        "{product} reviews",
        "{product} features",
        "{product} vs",
    ]


@dataclass
class USMarket(MarketProfile):
    code: str = "us"
    display_name: str = "United States"
    locale: str = "en-US"
    language: str = "en"
    currency: str = "USD"
    flag: str = "🇺🇸"
    search_seeds: List[str] = field(default_factory=_default_seeds)
    preferred_search_provider: str = "tavily"
    allowed_source_domains: List[str] = field(default_factory=lambda: [
        "g2.com", "capterra.com", "trustradius.com", "producthunt.com",
        "techcrunch.com", "theverge.com", "wired.com", "stackshare.io",
        "gartner.com", "forrester.com", "reddit.com", "medium.com",
    ])
    blocked_source_domains: List[str] = field(default_factory=list)
