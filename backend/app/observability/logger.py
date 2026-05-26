"""Loguru-based structured logger. One configured sink for the whole app."""
from __future__ import annotations

import os
import sys
from functools import lru_cache

from loguru import logger as _root

_CONFIGURED = False


def _configure() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    _root.remove()
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    _root.add(
        sys.stderr,
        level=level,
        format=("<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> "
                "| <level>{level:<7}</level> "
                "| <cyan>{extra[component]}</cyan> "
                "| {message}"),
        backtrace=False,
        diagnose=False,
    )
    _CONFIGURED = True


@lru_cache(maxsize=None)
def get_logger(component: str):
    _configure()
    return _root.bind(component=component)
