"""分析端点 —— 启动一次运行、流式推送事件、获取状态、续跑。

进程内的 ``_RUNS`` 注册表持有实时的 ``Tracer``（SSE 队列所需），但每次运行*同时*
持久化到 ``runs`` 表，使状态与追踪在进程重启或第二个 worker 下也能存活（P1-7）。
当某次运行不在本地内存中时，``/status`` 与 ``/stream`` 会回退到数据库。
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from ..market import get_market, list_markets
from ..observability.tracer import Tracer
from ..orchestration import AnalysisRequest, dag_definition, resume_analysis, run_analysis
from ..storage import get_store

router = APIRouter(prefix="/api/analysis", tags=["analysis"])

# 进程内注册表：run_id -> {tracer, task, report_id, error}。
_RUNS: Dict[str, Dict[str, Any]] = {}


class AnalysisStartResponse(BaseModel):
    run_id: str
    market: str
    locale: str
    product: str


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.get("/markets")
def get_markets() -> Dict[str, Any]:
    return {"markets": list_markets()}


@router.get("/dag")
def get_dag() -> Dict[str, Any]:
    """供前端可视化使用的静态 DAG 元数据（节点 + 边）。"""
    return dag_definition()


def _spawn(tracer: Tracer, req: AnalysisRequest, *, resume: bool) -> None:
    """注册并启动一次运行（全新或续跑），并持久化其生命周期。"""
    _RUNS[tracer.run_id] = {"tracer": tracer, "task": None, "report_id": None}

    async def _run() -> None:
        store = get_store()
        await store.init()
        await store.save_run(
            run_id=tracer.run_id, product=req.product, market=req.market,
            status="running", started_at=_now(), updated_at=_now(),
        )
        try:
            if resume:
                report = await resume_analysis(tracer.run_id, tracer)
            else:
                report = await run_analysis(req, tracer)
            _RUNS[tracer.run_id]["report_id"] = report.id
            await store.update_run(tracer.run_id, status="done", updated_at=_now(),
                                   report_id=report.id)
        except Exception as exc:  # noqa: BLE001
            _RUNS[tracer.run_id]["error"] = repr(exc)
            await store.update_run(tracer.run_id, status="error", updated_at=_now(),
                                   error=repr(exc))
        finally:
            tracer.close()

    _RUNS[tracer.run_id]["task"] = asyncio.create_task(_run())


@router.post("/start", response_model=AnalysisStartResponse)
async def start_analysis(req: AnalysisRequest) -> AnalysisStartResponse:
    try:
        market = get_market(req.market)
    except KeyError as e:
        raise HTTPException(400, str(e))

    tracer = Tracer()
    _spawn(tracer, req, resume=False)
    return AnalysisStartResponse(
        run_id=tracer.run_id,
        market=market.code,
        locale=market.locale,
        product=req.product,
    )


@router.post("/resume/{run_id}", response_model=AnalysisStartResponse)
async def resume_run(run_id: str) -> AnalysisStartResponse:
    """从最近的检查点恢复一次被中断的运行（创新点 6）。"""
    store = get_store()
    await store.init()
    record = await store.get_run(run_id)
    if not record:
        raise HTTPException(404, "unknown run")
    if record["status"] == "done":
        raise HTTPException(409, "run already completed")
    ckpt = await store.latest_checkpoint(run_id)
    if not ckpt:
        raise HTTPException(409, "no checkpoint to resume from")

    market = get_market(record["market"])
    # 复用同一个 run_id，使续跑的追踪延续原始追踪。
    tracer = Tracer(run_id=run_id)
    req = AnalysisRequest(product=record["product"], market=record["market"])
    _spawn(tracer, req, resume=True)
    return AnalysisStartResponse(
        run_id=run_id, market=market.code, locale=market.locale, product=record["product"],
    )


@router.get("/stream/{run_id}")
async def stream_run(run_id: str) -> EventSourceResponse:
    """SSE：随 DAG 执行，为每个追踪 span 流式推送一个事件。

    实时运行从内存中的 tracer 队列流式推送；对于已不在内存中的运行
    （例如重启之后），我们回放已持久化的追踪并发出一个终态 ``done``。
    """
    entry = _RUNS.get(run_id)
    if not entry:
        store = get_store()
        await store.init()
        record = await store.get_run(run_id)
        if not record:
            raise HTTPException(404, "unknown run")
        events = await store.get_trace(run_id)

        async def _replay():
            for ev in events:
                yield {"event": "trace", "data": ev.model_dump_json()}
            yield {
                "event": "done",
                "data": json.dumps({
                    "run_id": run_id, "report_id": record.get("report_id"),
                    "error": record.get("error"),
                }),
            }
        return EventSourceResponse(_replay())

    tracer: Tracer = entry["tracer"]

    async def _gen():
        for ev in list(tracer.events):
            yield {"event": "trace", "data": ev.model_dump_json()}
        async for ev in tracer.events_async():
            yield {"event": "trace", "data": ev.model_dump_json()}
        report_id = _RUNS.get(run_id, {}).get("report_id")
        err = _RUNS.get(run_id, {}).get("error")
        yield {
            "event": "done",
            "data": json.dumps({"run_id": run_id, "report_id": report_id, "error": err}),
        }

    return EventSourceResponse(_gen())


@router.get("/status/{run_id}")
async def run_status(run_id: str) -> Dict[str, Any]:
    entry = _RUNS.get(run_id)
    if entry:
        task: Optional[asyncio.Task] = entry.get("task")
        return {
            "run_id": run_id,
            "finished": bool(task and task.done()),
            "report_id": entry.get("report_id"),
            "error": entry.get("error"),
            "event_count": len(entry["tracer"].events),
            "resumable": False,
        }
    # 回退到已持久化的运行注册表。
    store = get_store()
    await store.init()
    record = await store.get_run(run_id)
    if not record:
        raise HTTPException(404, "unknown run")
    ckpt = await store.latest_checkpoint(run_id)
    return {
        "run_id": run_id,
        "finished": record["status"] in ("done", "error"),
        "status": record["status"],
        "report_id": record.get("report_id"),
        "error": record.get("error"),
        "resumable": record["status"] == "error" and ckpt is not None,
        "last_node": ckpt["node"] if ckpt else None,
    }
