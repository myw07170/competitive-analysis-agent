"""主动学习闭环：把人工修正转化为对智能体的引导。

当运营方编辑一份生成的报告（``app.api.reports.patch_report``）时，该编辑被存为一个
:class:`Correction`。下次采集器或撰写器为同一市场运行时，最近的修正会被提炼成一段
简短的"经验教训"块，注入系统 prompt。久而久之，这应当把 ``manual_correction_rate``
拉低——一个真实的反馈闭环，而非一次性的编辑。

引导会被短暂缓存，使一次运行中密集的智能体调用不会频繁冲击 SQLite。
"""
from __future__ import annotations

import time
from typing import Dict, List, Optional, Tuple

from .observability.logger import get_logger
from .schema.report import Correction
from .storage import get_store

log = get_logger("learning")

_CACHE: Dict[str, Tuple[float, str]] = {}
_TTL_SECONDS = 30.0
_MAX_HINTS = 6


def _format_hint(c: Correction) -> str:
    path = c.target_path or "(field)"
    if c.note:
        return f"- At `{path}`: {c.note.strip()}"
    before = (c.before or "").strip()
    after = (c.after or "").strip()
    if before and after:
        return f"- At `{path}`: prefer “{after[:80]}” over “{before[:80]}”."
    if after:
        return f"- At `{path}`: a reviewer corrected this to “{after[:80]}”."
    return f"- At `{path}`: a reviewer flagged the generated value as wrong."


async def recent_guidance(market: str) -> str:
    """返回该市场经验教训的 markdown 块（可能为空）。

    可从任意智能体安全调用；失败时降级为空字符串，因此存储抖动绝不会中断一次运行。
    """
    now = time.monotonic()
    cached = _CACHE.get(market)
    if cached and (now - cached[0]) < _TTL_SECONDS:
        return cached[1]

    block = ""
    try:
        store = get_store()
        await store.init()
        corrections: List[Correction] = await store.list_corrections(market=market, limit=_MAX_HINTS)
        if corrections:
            lines = [_format_hint(c) for c in corrections]
            block = (
                "\n[Lessons learned from human reviewers — apply these and avoid "
                "repeating past mistakes]:\n" + "\n".join(lines) + "\n"
            )
    except Exception as exc:  # pragma: no cover - 防御性
        log.warning(f"recent_guidance failed for market={market!r}: {exc!r}")
        block = ""

    _CACHE[market] = (now, block)
    return block


def invalidate_cache(market: Optional[str] = None) -> None:
    """丢弃缓存的引导，使刚保存的修正能立即被拾取。"""
    if market is None:
        _CACHE.clear()
    else:
        _CACHE.pop(market, None)
