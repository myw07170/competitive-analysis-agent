"""市场画像注册表 —— 新增地区的扩展点。

新增一个市场（例如 ``jp``）：

1. 创建 ``app/market/jp.py``，继承 :class:`MarketProfile`。
2. 在下方的 ``REGISTRY`` 中注册它。
3. 在 ``app/i18n/locales.py`` 中添加一份语言包。
4. 在 ``frontend/src/i18n/jp.ts`` 中添加一份前端 i18n 语言包。

其余一切 —— 智能体、schema、编排器、UI —— 都从当前激活的画像读取并自动适配。
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
