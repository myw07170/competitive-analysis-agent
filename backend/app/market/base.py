"""市场画像基类 —— 定义每个市场都必须声明的内容。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class MarketProfile:
    code: str
    display_name: str
    locale: str             # IETF 标签，例如 zh-CN / en-US
    language: str           # zh | en | ...
    currency: str           # CNY | USD | ...
    flag: str = ""
    search_seeds: List[str] = field(default_factory=list)
    preferred_search_provider: str = "none"
    allowed_source_domains: List[str] = field(default_factory=list)
    blocked_source_domains: List[str] = field(default_factory=list)

    def search_queries(self, product: str) -> List[str]:
        """为给定产品生成按领域调优的搜索查询。"""
        return [seed.format(product=product) for seed in self.search_seeds]
