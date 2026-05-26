"""Per-run trace recorder.

Each analysis run gets its own ``Tracer`` instance. Every agent decision —
prompt + input + output + tokens + timing — becomes a ``TraceEvent``. The
trace is then persisted (SQLite) and surfaced to the UI for "decision replay".
"""
from __future__ import annotations

import asyncio
import time
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class TraceEvent(BaseModel):
    id: str = Field(default_factory=lambda: f"ev_{uuid4().hex[:10]}")
    run_id: str
    parent_id: Optional[str] = None
    agent: str
    intent: str
    started_at: datetime
    ended_at: Optional[datetime] = None
    duration_ms: float = 0.0
    status: str = "ok"          # ok | error | rework
    prompt_system: str = ""
    prompt_user: str = ""
    response: str = ""
    decision: str = ""          # short human label for the DAG node
    extras: Dict[str, Any] = Field(default_factory=dict)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    model: str = ""


_CURRENT: ContextVar[Optional["Tracer"]] = ContextVar("current_tracer", default=None)


class Tracer:
    """Collects ``TraceEvent`` objects for one analysis run.

    Also exposes a thread-safe async queue so the FastAPI SSE endpoint can
    stream events to the frontend in real time.
    """

    def __init__(self, run_id: Optional[str] = None) -> None:
        self.run_id = run_id or f"run_{uuid4().hex[:12]}"
        self.events: List[TraceEvent] = []
        self._queue: asyncio.Queue[TraceEvent] = asyncio.Queue()
        self._listeners: List[Callable[[TraceEvent], Awaitable[None]]] = []
        self.started_at = datetime.now(timezone.utc)

    # ---- Recording ----
    @contextmanager
    def span(self, agent: str, intent: str, **extras: Any):
        ev = TraceEvent(
            run_id=self.run_id,
            agent=agent,
            intent=intent,
            started_at=datetime.now(timezone.utc),
            extras=extras,
        )
        t0 = time.perf_counter()
        try:
            yield ev
        except Exception as exc:
            ev.status = "error"
            ev.extras["error"] = repr(exc)
            self._finalize(ev, t0)
            raise
        else:
            self._finalize(ev, t0)

    def _finalize(self, ev: TraceEvent, t0: float) -> None:
        ev.ended_at = datetime.now(timezone.utc)
        ev.duration_ms = (time.perf_counter() - t0) * 1000.0
        self.events.append(ev)
        try:
            self._queue.put_nowait(ev)
        except asyncio.QueueFull:
            pass

    # ---- Streaming ----
    async def events_async(self):
        """Async generator that yields each event as it's recorded.

        Yields a sentinel ``None`` once the tracer is marked done so SSE
        callers can close the stream.
        """
        while True:
            ev = await self._queue.get()
            if ev is None:  # sentinel
                return
            yield ev

    def close(self) -> None:
        try:
            self._queue.put_nowait(None)  # type: ignore[arg-type]
        except Exception:
            pass

    # ---- Aggregates ----
    def total_tokens(self) -> int:
        return sum(e.total_tokens for e in self.events)

    def total_llm_calls(self) -> int:
        return sum(1 for e in self.events if e.total_tokens > 0 or e.prompt_user)

    def elapsed_seconds(self) -> float:
        if not self.events:
            return 0.0
        end = max((e.ended_at or e.started_at) for e in self.events)
        return (end - self.started_at).total_seconds()


# ---- Context-var helpers ----
@contextmanager
def use_tracer(tracer: Tracer):
    token = _CURRENT.set(tracer)
    try:
        yield tracer
    finally:
        _CURRENT.reset(token)


def current_tracer() -> Optional[Tracer]:
    return _CURRENT.get()


def get_tracer() -> Tracer:
    """Get the tracer bound to the current async context, or raise."""
    t = current_tracer()
    if t is None:
        raise RuntimeError("No tracer bound — wrap your call in `with use_tracer(...)`.")
    return t
