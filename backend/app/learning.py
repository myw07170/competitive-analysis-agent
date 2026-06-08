"""Active-learning loop: turn human corrections into agent guidance.

When an operator edits a generated report (``app.api.reports.patch_report``),
the edit is stored as a :class:`Correction`. The next time the Collector or
Writer runs for the same market, the most recent corrections are distilled into
a short "lessons learned" block injected into the system prompt. Over time this
should pull the ``manual_correction_rate`` down — a real feedback loop, not a
one-off edit.

The guidance is cached briefly so a burst of agent calls in one run does not
hammer SQLite.
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
    """Return a markdown block of lessons learned for this market (may be empty).

    Safe to call from any agent; failures degrade to an empty string so a
    storage hiccup never breaks a run.
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
    except Exception as exc:  # pragma: no cover - defensive
        log.warning(f"recent_guidance failed for market={market!r}: {exc!r}")
        block = ""

    _CACHE[market] = (now, block)
    return block


def invalidate_cache(market: Optional[str] = None) -> None:
    """Drop cached guidance so a freshly-saved correction is picked up at once."""
    if market is None:
        _CACHE.clear()
    else:
        _CACHE.pop(market, None)
