"""采集器智能体使用的外部数据采集器。

* :mod:`search`  —— 可插拔的网络搜索后端。
* :mod:`web`     —— 遵循 robots.txt 的页面抓取器。
* :mod:`robots`  —— robots.txt 缓存。
"""
from .search import SearchHit, search
from .web import fetch_page

__all__ = ["SearchHit", "search", "fetch_page"]
