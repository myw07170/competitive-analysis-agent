"""Chinese market profile."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from .base import MarketProfile


def _default_seeds() -> List[str]:
    return [
        "{product} 竞品 对比",
        "{product} 替代品",
        "{product} 价格 定价",
        "{product} 用户评价",
        "{product} 功能 介绍",
        "{product} 公司 背景",
    ]


@dataclass
class ChinaMarket(MarketProfile):
    code: str = "cn"
    display_name: str = "中国大陆市场"
    locale: str = "zh-CN"
    language: str = "zh"
    currency: str = "CNY"
    flag: str = "🇨🇳"
    search_seeds: List[str] = field(default_factory=_default_seeds)
    preferred_search_provider: str = "bing"
    allowed_source_domains: List[str] = field(default_factory=lambda: [
        "zhihu.com", "csdn.net", "36kr.com", "sspai.com", "iresearch.cn",
        "feishu.cn", "dingtalk.com", "yuque.com", "tencent.com", "aliyun.com",
        "baidu.com", "weibo.com", "infoq.cn", "geekpark.net",
    ])
    blocked_source_domains: List[str] = field(default_factory=list)
