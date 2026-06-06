"""LangGraph DAG for the competitive-analysis pipeline.

State machine
=============

    [identify] → [collect] → [analyze] → [write] → [qc]
                    ▲                                │
                    └───── rework (if QC requires) ──┘
                                                     │
                                                     └─── approve → END

The state holds the current iteration counter and the latest QC report so
that ``collect`` can use the previous findings as "rework notes" — that is
what makes the loop real, not pseudo.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict
from uuid import uuid4

from langgraph.graph import END, StateGraph

from ..agents import AnalystAgent, CollectorAgent, QCAgent, WriterAgent
from ..config import get_settings
from ..market import MarketProfile, get_market
from ..observability.logger import get_logger
from ..observability.tracer import Tracer, use_tracer
from ..schema import (
    CompetitorKnowledge,
    FinalReport,
    QCReport,
    SWOTAnalysis,
)
from ..schema.report import ReportMetrics
from ..storage import get_store
from .state import AnalysisRequest

log = get_logger("orchestration")


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
    qc_history: List[Dict[str, Any]]
    last_qc: Optional[Dict[str, Any]]
    report: Optional[Dict[str, Any]]
    run_id: str


# ---------------------------------------------------------------------------
# Node implementations
# ---------------------------------------------------------------------------
def _make_nodes(market: MarketProfile):
    collector = CollectorAgent(market)
    analyst = AnalystAgent(market)
    writer = WriterAgent(market)
    qc = QCAgent(market)

    async def n_identify(state: GraphState) -> GraphState:
        product = state["request"]["product"]
        extra: List[str] = state["request"].get("extra_competitors") or []
        comps = await collector.identify_competitors(product)
        names: List[str] = [c["name"] for c in comps if "name" in c]
        # Merge in any user-supplied competitors (dedup, preserve order)
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
        rework_notes = _rework_notes(last_qc)

        # First, gather knowledge about the user's own product so it can be
        # included in the comparison alongside competitors. We treat this as
        # a regular collector call (same schema, same evidence pipeline) and
        # surface it through ``state["target_product"]``.
        target_product = state.get("target_product")
        if target_product is None or iteration > 0:
            try:
                self_ck = await collector.gather_competitor(
                    product=product,
                    competitor_name=product,
                    iteration=iteration,
                    rework_notes=rework_notes,
                )
                target_product = self_ck.model_dump(mode="json")
            except Exception as exc:
                log.warning(f"collector failed for self={product!r} (it={iteration}): {exc!r}")

        # On rework iterations, keep the previous-iteration competitors so we
        # never lose ground when a single fresh response is malformed.
        previous_by_name: Dict[str, Dict[str, Any]] = {
            c.get("name"): c for c in state.get("competitors", []) if c.get("name")
        }

        fresh: List[Dict[str, Any]] = []
        skipped: List[Dict[str, str]] = list(state.get("skipped_competitors", []))
        for name in state.get("competitor_names", []):
            try:
                ck = await collector.gather_competitor(
                    product=product,
                    competitor_name=name,
                    iteration=iteration,
                    rework_notes=rework_notes,
                )
                fresh.append(ck.model_dump(mode="json"))
            except Exception as exc:
                log.warning(f"collector failed for {name!r} (it={iteration}): {exc!r}")
                skipped.append({"name": name, "error": str(exc)[:300], "iteration": iteration})

        # Merge: prefer fresh; fall back to previous when fresh is missing.
        merged_by_name: Dict[str, Dict[str, Any]] = dict(previous_by_name)
        for c in fresh:
            if c.get("name"):
                merged_by_name[c["name"]] = c

        merged = [merged_by_name[n] for n in state.get("competitor_names", [])
                  if n in merged_by_name]

        if not merged:
            raise RuntimeError(
                f"Collector produced 0 valid competitors out of "
                f"{len(state.get('competitor_names', []))}. Skipped: {skipped}"
            )

        if iteration > 0:
            log.info(
                f"rework merge: {len(fresh)} fresh, "
                f"{len(merged) - len(fresh)} carried over from previous iteration"
            )

        return {
            **state,
            "competitors": merged,
            "skipped_competitors": skipped,
            "target_product": target_product,
        }

    async def n_analyze(state: GraphState) -> GraphState:
        product = state["request"]["product"]
        out: List[Dict[str, Any]] = []
        for c in state.get("competitors", []):
            ck = CompetitorKnowledge.model_validate(c)
            try:
                swot = await analyst.analyze(product=product, competitor=ck)
                ck.swot = swot
            except Exception as exc:
                # SWOT failure is non-fatal — ship the competitor without it.
                log.warning(f"analyst failed for {ck.name!r}: {exc!r}; continuing without SWOT")
            out.append(ck.model_dump(mode="json"))

        # Also produce a SWOT for the user's own product so the comparison
        # shows symmetric coverage.
        target_product = state.get("target_product")
        if target_product:
            try:
                tck = CompetitorKnowledge.model_validate(target_product)
                tck.swot = await analyst.analyze(product=product, competitor=tck)
                target_product = tck.model_dump(mode="json")
            except Exception as exc:
                log.warning(f"analyst failed for self={product!r}: {exc!r}; continuing without SWOT")

        return {**state, "competitors": out, "target_product": target_product}

    async def n_write(state: GraphState) -> GraphState:
        product = state["request"]["product"]
        comps = [CompetitorKnowledge.model_validate(c) for c in state.get("competitors", [])]
        tp_raw = state.get("target_product")
        target_product = (
            CompetitorKnowledge.model_validate(tp_raw) if tp_raw else None
        )
        report: FinalReport = await writer.write(
            product=product,
            report_id=f"rpt_{uuid4().hex[:10]}",
            competitors=comps,
            target_product=target_product,
        )
        return {**state, "report": report.model_dump(mode="json")}

    async def n_qc(state: GraphState) -> GraphState:
        iteration = state.get("iteration", 0)
        comps = [CompetitorKnowledge.model_validate(c) for c in state.get("competitors", [])]
        qc_report: QCReport = await qc.review(iteration=iteration, competitors=comps)
        history = list(state.get("qc_history", []))
        history.append(qc_report.model_dump(mode="json"))
        return {
            **state,
            "qc_history": history,
            "last_qc": qc_report.model_dump(mode="json"),
            "iteration": iteration + (1 if qc_report.needs_rework else 0),
        }

    return n_identify, n_collect, n_analyze, n_write, n_qc


def _rework_notes(qc_dict: Dict[str, Any]) -> Optional[str]:
    if not qc_dict:
        return None
    findings = qc_dict.get("findings", [])
    if not findings:
        return None
    lines = [f"- [{f['severity']}] {f['target_path']}: {f['issue']} | fix: {f.get('suggested_fix','')}"
             for f in findings]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Conditional routing
# ---------------------------------------------------------------------------
def _route_after_qc(state: GraphState) -> str:
    last = state.get("last_qc") or {}
    decision = last.get("decision", "approve")
    settings = get_settings()
    if decision == "rework" and state.get("iteration", 0) <= settings.max_qc_iterations:
        log.info(f"QC requested rework — iteration={state.get('iteration')}")
        return "collect"
    log.info(f"QC decision={decision} — finishing")
    return "done"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def build_graph(market: MarketProfile):
    n_identify, n_collect, n_analyze, n_write, n_qc = _make_nodes(market)

    g = StateGraph(GraphState)
    g.add_node("identify", n_identify)
    g.add_node("collect", n_collect)
    g.add_node("analyze", n_analyze)
    g.add_node("write", n_write)
    g.add_node("qc", n_qc)

    g.set_entry_point("identify")
    g.add_edge("identify", "collect")
    g.add_edge("collect", "analyze")
    g.add_edge("analyze", "write")
    g.add_edge("write", "qc")
    g.add_conditional_edges("qc", _route_after_qc, {"collect": "collect", "done": END})

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
        "last_qc": None,
        "report": None,
        "run_id": tracer.run_id,
    }

    with use_tracer(tracer):
        final_state: GraphState = await graph.ainvoke(initial)

    report = FinalReport.model_validate(final_state["report"])
    # Link the report to the trace that produced it so the "decision trace"
    # panel can be reconstructed later (e.g. when opened from history), not
    # only in the brief window where the live ?run= query param is present.
    report.run_id = tracer.run_id

    # Compute metrics now that the run is done.
    qc_history = final_state.get("qc_history", []) or []
    rework_count = sum(1 for q in qc_history if q.get("decision") == "rework")
    # Include the target product in completeness/avg-source metrics so the
    # numbers reflect everything actually shipped in the report.
    completeness_items = list(report.competitors)
    if report.target_product is not None:
        completeness_items.append(report.target_product)
    completeness = _schema_completeness(completeness_items)
    avg_sources = (sum(c.source_count() for c in completeness_items) / len(completeness_items)
                   if completeness_items else 0.0)

    report.metrics = ReportMetrics(
        elapsed_seconds=tracer.elapsed_seconds(),
        total_tokens=tracer.total_tokens(),
        total_llm_calls=tracer.total_llm_calls(),
        schema_completeness=completeness,
        avg_sources_per_competitor=round(avg_sources, 2),
        qc_iterations=len(qc_history),
        rework_count=rework_count,
    )

    # Persist
    store = get_store()
    await store.init()
    await store.save_report(report)
    await store.save_trace_events(tracer.events)

    return report


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
