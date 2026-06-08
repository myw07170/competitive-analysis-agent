"""每次运行的追踪记录器。

每次分析运行都获得自己的 ``Tracer`` 实例。每个智能体决策 ——
prompt + 输入 + 输出 + token + 计时 —— 都会成为一个 ``TraceEvent``。
随后追踪被持久化（SQLite）并呈现给 UI，用于"决策回放"。
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
    decision: str = ""          # 给 DAG 节点的简短人类可读标签
    extras: Dict[str, Any] = Field(default_factory=dict)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    model: str = ""


_CURRENT: ContextVar[Optional["Tracer"]] = ContextVar("current_tracer", default=None)


class Tracer:
    """为一次分析运行收集 ``TraceEvent`` 对象。

    同时暴露一个线程安全的异步队列，使 FastAPI 的 SSE 端点能把事件实时流式
    推送到前端。
    """

    def __init__(self, run_id: Optional[str] = None) -> None:
        self.run_id = run_id or f"run_{uuid4().hex[:12]}"
        self.events: List[TraceEvent] = []
        self._queue: asyncio.Queue[TraceEvent] = asyncio.Queue()
        self._listeners: List[Callable[[TraceEvent], Awaitable[None]]] = []
        self.started_at = datetime.now(timezone.utc)

    # ---- 记录 ----
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

    # ---- 流式推送 ----
    async def events_async(self):
        """异步生成器，在每个事件被记录时逐个 yield。

        一旦 tracer 被标记为完成，便 yield 一个哨兵值 ``None``，
        使 SSE 调用方可以关闭流。
        """
        while True:
            ev = await self._queue.get()
            if ev is None:  # 哨兵
                return
            yield ev

    def close(self) -> None:
        try:
            self._queue.put_nowait(None)  # type: ignore[arg-type]  # 推入哨兵以结束流
        except Exception:
            pass

    # ---- 聚合统计 ----
    def total_tokens(self) -> int:
        return sum(e.total_tokens for e in self.events)

    def total_llm_calls(self) -> int:
        return sum(1 for e in self.events if e.total_tokens > 0 or e.prompt_user)

    def elapsed_seconds(self) -> float:
        if not self.events:
            return 0.0
        end = max((e.ended_at or e.started_at) for e in self.events)
        return (end - self.started_at).total_seconds()


# ---- 上下文变量辅助 ----
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
    """获取绑定到当前异步上下文的 tracer，否则抛出异常。"""
    t = current_tracer()
    if t is None:
        raise RuntimeError("No tracer bound — wrap your call in `with use_tracer(...)`.")
    return t
