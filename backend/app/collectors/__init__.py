"""External data collectors used by the Collector agent.

* :mod:`search`  — pluggable web search backend.
* :mod:`web`     — robots.txt-respecting page fetcher.
* :mod:`robots`  — robots.txt cache.
"""
from .search import SearchHit, search
from .web import fetch_page

__all__ = ["SearchHit", "search", "fetch_page"]
