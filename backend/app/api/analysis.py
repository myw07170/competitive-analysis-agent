"""Analysis endpoints — kick off a run, stream events, fetch state, resume.

The in-process ``_RUNS`` registry holds the live ``Tracer`` (needed for the SSE
queue), but every run is *also* persisted to the ``runs`` table so status and
the trace survive a process restart or a second worker (P1-7). ``/status`` and
``/stream`` fall back to the database when a run is not in local memory.
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

# In-process registry: run_id -> {tracer, task, report_id, error}.
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
    """Static DAG metadata (nodes + edges) for the frontend visualization."""
    return dag_definition()


def _spawn(tracer: Tracer, req: AnalysisRequest, *, resume: bool) -> None:
    """Register + launch a run (fresh or resumed) and persist its lifecycle."""
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
    """Resume an interrupted run from its last checkpoint (Innovation-6)."""
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
    # Reuse the same run_id so the resumed trace continues the original.
    tracer = Tracer(run_id=run_id)
    req = AnalysisRequest(product=record["product"], market=record["market"])
    _spawn(tracer, req, resume=True)
    return AnalysisStartResponse(
        run_id=run_id, market=market.code, locale=market.locale, product=record["product"],
    )


@router.get("/stream/{run_id}")
async def stream_run(run_id: str) -> EventSourceResponse:
    """SSE: streams one event per trace span as the DAG executes.

    Live runs stream from the in-memory tracer queue; for a run that is no
    longer in memory (e.g. after a restart) we replay the persisted trace and
    emit a terminal ``done``.
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
    # Fall back to the persisted run registry.
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
