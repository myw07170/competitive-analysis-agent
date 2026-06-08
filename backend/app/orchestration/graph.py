"""LangGraph DAG for the competitive-analysis pipeline.

State machine
=============

    [identify] → [collect] → [analyze] → [write] → [qc]
                    ▲            ▲          ▲        │
                    └────────────┴──────────┴── rework (routed to the agent
                                                 that actually owns the defect)
                                                          │
                                                          └─── approve → END

What makes the loop *real* (not pseudo):

* QC reviews the collected knowledge AND the final report, and produces
  role-routed findings (collector / analyst / writer).
* ``_route_after_qc`` sends the run back to the **earliest stage that owns a
  blocking/major finding** — so an analyst defect re-runs from ``analyze``, a
  writer defect from ``write``, not blindly from ``collect``.
* Rework is **targeted**: only the flagged competitors are re-collected, and
  each agent receives the slice of findings addressed to it, carried as a typed
  :class:`AgentMessage` (recorded in the trace), not a blob of natural language.
* Collection/analysis run **concurrently** (bounded by a semaphore).
* Every node checkpoints the state so a failed run can be resumed.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional, TypedDict
from uuid import uuid4

from langgraph.graph import END, StateGraph

from ..agents import AnalystAgent, CollectorAgent, QCAgent, WriterAgent
from ..config import get_settings
from ..consistency import annotate_conflicts
from ..market import MarketProfile, get_market
from ..observability.logger import get_logger
from ..observability.tracer import Tracer, get_tracer, use_tracer
from ..schema import (
    AgentMessage,
    AgentRole,
    CompetitorKnowledge,
    FinalReport,
)
from ..schema.report import ReportMetrics
from ..storage import get_store, normalize_entity_key
from .state import AnalysisRequest

log = get_logger("orchestration")

# Linear stage order (excludes the terminal "done"). Used for resume-skip and
# for choosing the earliest stage to re-enter on rework.
STAGE_ORDER = ["identify", "collect", "analyze", "write", "qc"]
_AGENT_TO_STAGE = {
    AgentRole.COLLECTOR.value: "collect",
    AgentRole.ANALYST.value: "analyze",
    AgentRole.WRITER.value: "write",
}


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
class GraphState(TypedDict, total=False):
    request: Dict[str, Any]
    market_code: str
    iteration: int
    competitor_names: List[str]
    competitors: List[Dict[str, Any]]
    target_product: Optional[Dict[str, Any]]
    skipped_competitors: List[Dict[str, str]]
    qc_history: List[Dict[str, Any]]
    qc_competitor_names: List[str]
    last_qc: Optional[Dict[str, Any]]
    messages: List[Dict[str, Any]]
    report: Optional[Dict[str, Any]]
    run_id: str
    resume_from: Optional[str]


# ---------------------------------------------------------------------------
# Rework-note helpers (structured → per-agent / per-competitor slices)
# ---------------------------------------------------------------------------
def _findings(last_qc: Dict[str, Any]) -> List[Dict[str, Any]]:
    return (last_qc or {}).get("findings", []) or []


def _format_findings(findings: List[Dict[str, Any]]) -> Optional[str]:
    if not findings:
        return None
    return "\n".join(
        f"- [{f.get('severity')}] {f.get('target_path')}: {f.get('issue')} "
        f"| fix: {f.get('suggested_fix', '')}"
        for f in findings
    )


def _collector_notes_for(last_qc: Dict[str, Any], label: str) -> Optional[str]:
    """Notes for one competitor label ('competitors[2]' or 'target_product')."""
    out = [
        f for f in _findings(last_qc)
        if f.get("target_agent") == AgentRole.COLLECTOR.value
        and (f.get("target_path", "") + ".").startswith(label + ".")
    ]
    return _format_findings(out)


def _role_notes(last_qc: Dict[str, Any], role: AgentRole) -> Optional[str]:
    return _format_findings(
        [f for f in _findings(last_qc) if f.get("target_agent") == role.value]
    )


def _flagged_collector_labels(last_qc: Dict[str, Any]) -> set:
    """Labels ('competitors[i]' / 'target_product') with collector findings."""
    labels: set = set()
    for f in _findings(last_qc):
        if f.get("target_agent") != AgentRole.COLLECTOR.value:
            continue
        path = f.get("target_path", "")
        if path.startswith("target_product"):
            labels.add("target_product")
        elif path.startswith("competitors["):
            labels.add(path.split(".", 1)[0])  # 'competitors[2]'
    return labels


# ---------------------------------------------------------------------------
# Node implementations
# ---------------------------------------------------------------------------
def _make_nodes(market: MarketProfile):
    collector = CollectorAgent(market)
    analyst = AnalystAgent(market)
    writer = WriterAgent(market)
    qc = QCAgent(market)
    settings = get_settings()
    concurrency = settings.collector_concurrency

    async def _bounded_gather(factories: List[Callable[[], Awaitable[Any]]]) -> List[Any]:
        """Run coroutine factories concurrently, bounded by the configured limit."""
        sem = asyncio.Semaphore(concurrency)

        async def _run(make: Callable[[], Awaitable[Any]]) -> Any:
            async with sem:
                return await make()

        return await asyncio.gather(*[_run(m) for m in factories], return_exceptions=True)

    async def n_identify(state: GraphState) -> GraphState:
        product = state["request"]["product"]
        extra: List[str] = state["request"].get("extra_competitors") or []
        comps = await collector.identify_competitors(product)
        names: List[str] = [c["name"] for c in comps if "name" in c]
        seen = set()
        merged: List[str] = []
        for n in names + extra:
            if n and n not in seen:
                merged.append(n)
                seen.add(n)
        return {**state, "competitor_names": merged[:4]}

    async def n_collect(state: GraphState) -> GraphState:
        product = state["request"]["product"]
        iteration = state.get("iteration", 0)
        last_qc = state.get("last_qc") or {}
        names = list(state.get("competitor_names", []))
        prev_names = list(state.get("qc_competitor_names", [])) or names

        # Targeted rework: on iterations > 0 only re-collect the competitors
        # QC actually flagged; everything else is carried over untouched.
        flagged = _flagged_collector_labels(last_qc) if iteration > 0 else None

        # --- self / target product ---
        target_product = state.get("target_product")
        self_flagged = (flagged is None) or ("target_product" in flagged)
        if target_product is None or (iteration > 0 and self_flagged):
            try:
                self_ck = await collector.gather_competitor(
                    product=product, competitor_name=product, iteration=iteration,
                    rework_notes=_collector_notes_for(last_qc, "target_product"),
                )
                target_product = self_ck.model_dump(mode="json")
            except Exception as exc:
                log.warning(f"collector failed for self={product!r} (it={iteration}): {exc!r}")

        # --- competitors (concurrent) ---
        def _needs(i: int, name: str) -> bool:
            if flagged is None:
                return True
            label = f"competitors[{i}]"
            # Map current index back to the label QC used (prev order).
            try:
                prev_idx = prev_names.index(name)
                label = f"competitors[{prev_idx}]"
            except ValueError:
                pass
            return label in flagged

        to_collect = [(i, n) for i, n in enumerate(names) if _needs(i, n)]

        def _make(i: int, name: str) -> Callable[[], Awaitable[CompetitorKnowledge]]:
            try:
                prev_idx = prev_names.index(name)
                label = f"competitors[{prev_idx}]"
            except ValueError:
                label = f"competitors[{i}]"
            notes = _collector_notes_for(last_qc, label)

            async def _go() -> CompetitorKnowledge:
                return await collector.gather_competitor(
                    product=product, competitor_name=name,
                    iteration=iteration, rework_notes=notes,
                )
            return _go

        results = await _bounded_gather([_make(i, n) for i, n in to_collect])

        previous_by_name: Dict[str, Dict[str, Any]] = {
            c.get("name"): c for c in state.get("competitors", []) if c.get("name")
        }
        skipped: List[Dict[str, str]] = list(state.get("skipped_competitors", []))
        fresh: List[Dict[str, Any]] = []
        for (i, name), res in zip(to_collect, results):
            if isinstance(res, Exception):
                log.warning(f"collector failed for {name!r} (it={iteration}): {res!r}")
                skipped.append({"name": name, "error": str(res)[:300], "iteration": str(iteration)})
            else:
                fresh.append(res.model_dump(mode="json"))

        merged_by_name: Dict[str, Dict[str, Any]] = dict(previous_by_name)
        for c in fresh:
            if c.get("name"):
                merged_by_name[c["name"]] = c
        merged = [merged_by_name[n] for n in names if n in merged_by_name]

        if not merged:
            raise RuntimeError(
                f"Collector produced 0 valid competitors out of {len(names)}. Skipped: {skipped}"
            )
        if iteration > 0:
            log.info(f"targeted rework: re-collected {len(fresh)} of {len(names)} competitors")

        return {
            **state,
            "competitors": merged,
            "skipped_competitors": skipped,
            "target_product": target_product,
        }

    async def n_analyze(state: GraphState) -> GraphState:
        product = state["request"]["product"]
        last_qc = state.get("last_qc") or {}
        notes = _role_notes(last_qc, AgentRole.ANALYST)
        raw_comps = state.get("competitors", [])

        async def _analyze_one(raw: Dict[str, Any]) -> Dict[str, Any]:
            ck = CompetitorKnowledge.model_validate(raw)
            try:
                ck.swot = await analyst.analyze(product=product, competitor=ck, rework_notes=notes)
            except Exception as exc:
                log.warning(f"analyst failed for {ck.name!r}: {exc!r}; continuing without SWOT")
            if settings.enable_conflict_detection:
                annotate_conflicts(ck)
            return ck.model_dump(mode="json")

        out = await _bounded_gather([lambda r=r: _analyze_one(r) for r in raw_comps])
        out = [o for o in out if not isinstance(o, Exception)]

        target_product = state.get("target_product")
        if target_product:
            try:
                tck = CompetitorKnowledge.model_validate(target_product)
                tck.swot = await analyst.analyze(product=product, competitor=tck, rework_notes=notes)
                if settings.enable_conflict_detection:
                    annotate_conflicts(tck)
                target_product = tck.model_dump(mode="json")
            except Exception as exc:
                log.warning(f"analyst failed for self={product!r}: {exc!r}; continuing without SWOT")

        return {**state, "competitors": out, "target_product": target_product}

    async def n_write(state: GraphState) -> GraphState:
        product = state["request"]["product"]
        last_qc = state.get("last_qc") or {}
        comps = [CompetitorKnowledge.model_validate(c) for c in state.get("competitors", [])]
        tp_raw = state.get("target_product")
        target_product = CompetitorKnowledge.model_validate(tp_raw) if tp_raw else None
        report: FinalReport = await writer.write(
            product=product,
            report_id=f"rpt_{uuid4().hex[:10]}",
            competitors=comps,
            target_product=target_product,
            rework_notes=_role_notes(last_qc, AgentRole.WRITER),
        )
        return {**state, "report": report.model_dump(mode="json")}

    async def n_qc(state: GraphState) -> GraphState:
        iteration = state.get("iteration", 0)
        comps = [CompetitorKnowledge.model_validate(c) for c in state.get("competitors", [])]
        tp_raw = state.get("target_product")
        target_product = CompetitorKnowledge.model_validate(tp_raw) if tp_raw else None
        report = FinalReport.model_validate(state["report"]) if state.get("report") else None

        qc_report = await qc.review(
            iteration=iteration, competitors=comps,
            report=report, target_product=target_product,
        )

        # Emit structured, typed rework requests (the inter-agent protocol) and
        # record each as a trace event so the handoff is observable.
        messages = list(state.get("messages", []))
        if qc_report.needs_rework:
            messages += _emit_rework_messages(qc_report)

        history = list(state.get("qc_history", []))
        history.append(qc_report.model_dump(mode="json"))
        return {
            **state,
            "qc_history": history,
            "qc_competitor_names": [c.name for c in comps],
            "last_qc": qc_report.model_dump(mode="json"),
            "messages": messages,
            "iteration": iteration + (1 if qc_report.needs_rework else 0),
        }

    return n_identify, n_collect, n_analyze, n_write, n_qc


def _emit_rework_messages(qc_report) -> List[Dict[str, Any]]:
    """Build one typed AgentMessage per receiving agent and trace it."""
    by_agent: Dict[str, List[Dict[str, Any]]] = {}
    for f in qc_report.findings:
        if f.severity.value in ("blocker", "major"):
            by_agent.setdefault(f.target_agent.value, []).append(f.model_dump(mode="json"))

    out: List[Dict[str, Any]] = []
    tracer = get_tracer()
    for agent_value, findings in by_agent.items():
        try:
            receiver = AgentRole(agent_value)
        except ValueError:
            receiver = AgentRole.COLLECTOR
        msg = AgentMessage(
            sender=AgentRole.QC,
            receiver=receiver,
            intent="request_rework",
            payload={"iteration": qc_report.iteration, "findings": findings},
        )
        out.append(msg.model_dump(mode="json"))
        with tracer.span("qc", "qc.request_rework") as ev:
            ev.decision = f"request_rework → {receiver.value} ({len(findings)} findings)"
            ev.response = msg.model_dump_json()
            ev.extras["protocol"] = "AgentMessage"
            ev.extras["receiver"] = receiver.value
    return out


# ---------------------------------------------------------------------------
# Conditional routing (role-targeted)
# ---------------------------------------------------------------------------
def _route_after_qc(state: GraphState) -> str:
    last = state.get("last_qc") or {}
    decision = last.get("decision", "approve")
    settings = get_settings()
    if decision != "rework" or state.get("iteration", 0) > settings.max_qc_iterations:
        log.info(f"QC decision={decision} — finishing")
        return "done"

    # Re-enter at the earliest stage that owns a blocking/major finding.
    severe_stages = {
        _AGENT_TO_STAGE.get(f.get("target_agent"))
        for f in _findings(last)
        if f.get("severity") in ("blocker", "major")
    }
    severe_stages.discard(None)
    for stage in ("collect", "analyze", "write"):
        if stage in severe_stages:
            log.info(f"QC rework → re-enter at '{stage}' (iteration={state.get('iteration')})")
            return stage
    return "collect"


# ---------------------------------------------------------------------------
# Checkpointing wrapper (resume support)
# ---------------------------------------------------------------------------
def _wrap_checkpointed(name: str, fn, seq: Dict[str, int]):
    async def _node(state: GraphState) -> GraphState:
        resume_from = state.get("resume_from")
        if resume_from and STAGE_ORDER.index(name) < STAGE_ORDER.index(resume_from):
            return state  # already completed in the interrupted run — skip
        new_state = await fn(state)
        if resume_from:
            new_state = {**new_state, "resume_from": None}
        await _save_checkpoint(name, new_state, seq)
        return new_state
    return _node


async def _save_checkpoint(node: str, state: GraphState, seq: Dict[str, int]) -> None:
    run_id = state.get("run_id")
    if not run_id:
        return
    seq["n"] = seq.get("n", 0) + 1
    try:
        store = get_store()
        await store.init()
        await store.save_checkpoint(
            run_id=run_id, node=node, seq=seq["n"],
            state_json=json.dumps(state, default=str, ensure_ascii=False),
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
    except Exception as exc:  # pragma: no cover - checkpoint must never break a run
        log.warning(f"checkpoint save failed (node={node}): {exc!r}")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def build_graph(market: MarketProfile):
    n_identify, n_collect, n_analyze, n_write, n_qc = _make_nodes(market)
    seq: Dict[str, int] = {"n": 0}

    g = StateGraph(GraphState)
    g.add_node("identify", _wrap_checkpointed("identify", n_identify, seq))
    g.add_node("collect", _wrap_checkpointed("collect", n_collect, seq))
    g.add_node("analyze", _wrap_checkpointed("analyze", n_analyze, seq))
    g.add_node("write", _wrap_checkpointed("write", n_write, seq))
    g.add_node("qc", _wrap_checkpointed("qc", n_qc, seq))

    g.set_entry_point("identify")
    g.add_edge("identify", "collect")
    g.add_edge("collect", "analyze")
    g.add_edge("analyze", "write")
    g.add_edge("write", "qc")
    g.add_conditional_edges(
        "qc", _route_after_qc,
        {"collect": "collect", "analyze": "analyze", "write": "write", "done": END},
    )
    return g.compile()


async def run_analysis(req: AnalysisRequest, tracer: Tracer) -> FinalReport:
    """Run the full DAG and return the persisted final report."""
    market = get_market(req.market)
    graph = build_graph(market)
    initial: GraphState = {
        "request": req.model_dump(),
        "market_code": market.code,
        "iteration": 0,
        "competitor_names": [],
        "competitors": [],
        "qc_history": [],
        "messages": [],
        "last_qc": None,
        "report": None,
        "run_id": tracer.run_id,
    }
    with use_tracer(tracer):
        final_state: GraphState = await graph.ainvoke(initial)
    return await _finalize(final_state, tracer, market)


async def resume_analysis(run_id: str, tracer: Tracer) -> FinalReport:
    """Resume a previously-interrupted run from its last checkpoint.

    Reloads the saved GraphState, marks the stage *after* the last completed
    node as the resume point, and continues the DAG. Stages before that point
    are skipped (their outputs are already in the restored state).
    """
    store = get_store()
    await store.init()
    ckpt = await store.latest_checkpoint(run_id)
    if not ckpt:
        raise RuntimeError(f"No checkpoint found for run {run_id!r}; cannot resume.")

    state: GraphState = ckpt["state"]
    last_node = ckpt["node"]
    # Resume at the node following the last completed one (or re-run qc itself).
    idx = STAGE_ORDER.index(last_node)
    resume_from = STAGE_ORDER[min(idx + 1, len(STAGE_ORDER) - 1)]
    state["resume_from"] = resume_from
    state["run_id"] = run_id

    market = get_market(state.get("market_code", "us"))
    graph = build_graph(market)
    with use_tracer(tracer):
        final_state: GraphState = await graph.ainvoke(state)
    return await _finalize(final_state, tracer, market)


async def _finalize(final_state: GraphState, tracer: Tracer, market: MarketProfile) -> FinalReport:
    settings = get_settings()
    report = FinalReport.model_validate(final_state["report"])
    report.run_id = tracer.run_id

    qc_history = final_state.get("qc_history", []) or []
    rework_count = sum(1 for q in qc_history if q.get("decision") == "rework")
    completeness_items: List[CompetitorKnowledge] = list(report.competitors)
    if report.target_product is not None:
        completeness_items.append(report.target_product)

    completeness = _schema_completeness(completeness_items)
    avg_sources = (sum(c.source_count() for c in completeness_items) / len(completeness_items)
                   if completeness_items else 0.0)
    avg_conf = (sum(c.avg_confidence() for c in completeness_items) / len(completeness_items)
                if completeness_items else 0.0)
    low_conf = sum(len(c.low_confidence_claims(settings.min_confidence)) for c in completeness_items)
    conflicts = sum(len(c.conflicts) for c in completeness_items)

    report.metrics = ReportMetrics(
        elapsed_seconds=tracer.elapsed_seconds(),
        total_tokens=tracer.total_tokens(),
        total_llm_calls=tracer.total_llm_calls(),
        schema_completeness=completeness,
        avg_sources_per_competitor=round(avg_sources, 2),
        qc_iterations=len(qc_history),
        rework_count=rework_count,
        avg_confidence=round(avg_conf, 3),
        low_confidence_claims=low_conf,
        conflict_count=conflicts,
        manual_correction_rate=0.0,
        corrected_fields=0,
    )

    store = get_store()
    await store.init()
    await store.save_report(report)
    await store.save_trace_events(tracer.events)
    await _save_knowledge_snapshots(report, store)
    return report


async def _save_knowledge_snapshots(report: FinalReport, store) -> None:
    """Persist one snapshot per competitor for cross-run evolution/diff."""
    captured_at = report.generated_at.isoformat()
    items: List[CompetitorKnowledge] = list(report.competitors)
    if report.target_product is not None:
        items.append(report.target_product)
    for c in items:
        try:
            await store.save_knowledge_snapshot(
                entity_key=normalize_entity_key(c.name, report.market),
                market=report.market, name=c.name, run_id=report.run_id,
                report_id=report.id, captured_at=captured_at,
                payload_json=c.model_dump_json(),
            )
        except Exception as exc:  # pragma: no cover - snapshots are best-effort
            log.warning(f"knowledge snapshot failed for {c.name!r}: {exc!r}")


def _schema_completeness(competitors: List[CompetitorKnowledge]) -> float:
    """Fraction of the key fields populated across all competitors."""
    if not competitors:
        return 0.0
    expected_per = [
        ("homepage", lambda c: bool(c.homepage)),
        ("short_description", lambda c: bool(c.short_description)),
        ("market_position", lambda c: bool(c.market_position)),
        ("function_tree.nodes", lambda c: bool(c.function_tree.nodes)),
        ("pricing.tiers", lambda c: bool(c.pricing.tiers)),
        ("user_profile.segments", lambda c: bool(c.user_profile.segments)),
        ("swot", lambda c: c.swot is not None),
        ("sources", lambda c: len(c.sources) >= 1),
    ]
    total = len(expected_per) * len(competitors)
    hit = sum(1 for c in competitors for _, ck in expected_per if ck(c))
    return round(hit / total, 3)
