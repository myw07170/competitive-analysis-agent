"""Analysis endpoints — kick off a run, stream events, fetch state."""
from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from ..market import get_market, list_markets
from ..observability.tracer import Tracer
from ..orchestration import AnalysisRequest, dag_definition, run_analysis

router = APIRouter(prefix="/api/analysis", tags=["analysis"])

# In-process registry: run_id -> Tracer (for SSE listeners) + asyncio.Task.
_RUNS: Dict[str, Dict[str, Any]] = {}


class AnalysisStartResponse(BaseModel):
    run_id: str
    market: str
    locale: str
    product: str


@router.get("/markets")
def get_markets() -> Dict[str, Any]:
    return {"markets": list_markets()}


@router.get("/dag")
def get_dag() -> Dict[str, Any]:
    """Static DAG metadata (nodes + edges) for the frontend visualization."""
    return dag_definition()


@router.post("/start", response_model=AnalysisStartResponse)
async def start_analysis(req: AnalysisRequest) -> AnalysisStartResponse:
    try:
        market = get_market(req.market)
    except KeyError as e:
        raise HTTPException(400, str(e))

    tracer = Tracer()
    _RUNS[tracer.run_id] = {"tracer": tracer, "task": None, "report_id": None}

    async def _run() -> None:
        try:
            report = await run_analysis(req, tracer)
            _RUNS[tracer.run_id]["report_id"] = report.id
        except Exception as exc:
            _RUNS[tracer.run_id]["error"] = repr(exc)
        finally:
            tracer.close()

    task = asyncio.create_task(_run())
    _RUNS[tracer.run_id]["task"] = task

    return AnalysisStartResponse(
        run_id=tracer.run_id,
        market=market.code,
        locale=market.locale,
        product=req.product,
    )


@router.get("/stream/{run_id}")
async def stream_run(run_id: str) -> EventSourceResponse:
    """SSE: streams one event per trace span as the DAG executes."""
    entry = _RUNS.get(run_id)
    if not entry:
        raise HTTPException(404, "unknown run")
    tracer: Tracer = entry["tracer"]

    async def _gen():
        # Replay already-recorded events first (in case the client connects late).
        for ev in list(tracer.events):
            yield {"event": "trace", "data": ev.model_dump_json()}

        async for ev in tracer.events_async():
            yield {"event": "trace", "data": ev.model_dump_json()}

        # When the queue's sentinel fires, emit a final 'done' event.
        report_id = _RUNS.get(run_id, {}).get("report_id")
        err = _RUNS.get(run_id, {}).get("error")
        yield {
            "event": "done",
            "data": json.dumps({"run_id": run_id, "report_id": report_id, "error": err}),
        }

    return EventSourceResponse(_gen())


@router.get("/status/{run_id}")
def run_status(run_id: str) -> Dict[str, Any]:
    entry = _RUNS.get(run_id)
    if not entry:
        raise HTTPException(404, "unknown run")
    task: Optional[asyncio.Task] = entry.get("task")
    return {
        "run_id": run_id,
        "finished": bool(task and task.done()),
        "report_id": entry.get("report_id"),
        "error": entry.get("error"),
        "event_count": len(entry["tracer"].events),
    }
