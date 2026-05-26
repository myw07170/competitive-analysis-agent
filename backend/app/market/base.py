"""Market profile base class — defines what every market must declare."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class MarketProfile:
    code: str
    display_name: str
    locale: str             # IETF tag, e.g. zh-CN / en-US
    language: str           # zh | en | ...
    currency: str           # CNY | USD | ...
    flag: str = ""
    search_seeds: List[str] = field(default_factory=list)
    preferred_search_provider: str = "none"
    allowed_source_domains: List[str] = field(default_factory=list)
    blocked_source_domains: List[str] = field(default_factory=list)

    def search_queries(self, product: str) -> List[str]:
        """Generate domain-tuned search queries for a given product."""
        return [seed.format(product=product) for seed in self.search_seeds]
