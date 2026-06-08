"""竞品分析流水线的 LangGraph DAG。

状态机
======

    [identify] → [collect] → [analyze] → [write] → [qc]
                    ▲            ▲          ▲        │
                    └────────────┴──────────┴── 返工（路由到真正
                                                 对缺陷负责的智能体）
                                                          │
                                                          └─── 通过 → END

是什么让这个循环是*真实的*（而非伪装的）：

* QC 同时审查采集到的知识与最终报告，并产出按角色路由的结论
  （采集器 / 分析师 / 撰写器）。
* ``_route_after_qc`` 把运行退回到**拥有阻塞 / 重大问题的最早阶段** ——
  因此分析师的缺陷从 ``analyze`` 重跑，撰写器的缺陷从 ``write`` 重跑，
  而非盲目地从 ``collect`` 重跑。
* 返工是**定向的**：只重新采集被标记的竞品，且每个智能体只收到发给它的那部分
  结论，以带类型的 :class:`AgentMessage` 承载（记入追踪），而非一团自然语言。
* 采集 / 分析**并发**执行（受信号量约束）。
* 每个节点都对状态打检查点，使失败的运行可以续跑。
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

# 线性阶段顺序（不含终态 "done"）。用于续跑跳过，
# 以及在返工时选择重新进入的最早阶段。
STAGE_ORDER = ["identify", "collect", "analyze", "write", "qc"]
_AGENT_TO_STAGE = {
    AgentRole.COLLECTOR.value: "collect",
    AgentRole.ANALYST.value: "analyze",
    AgentRole.WRITER.value: "write",
}


# ---------------------------------------------------------------------------
# 状态
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
# 返工备注辅助函数（结构化 → 按智能体 / 按竞品切片）
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
    """针对某个竞品标签（'competitors[2]' 或 'target_product'）的备注。"""
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
    """带有采集器结论的标签（'competitors[i]' / 'target_product'）。"""
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
# 节点实现
# ---------------------------------------------------------------------------
def _make_nodes(market: MarketProfile):
    collector = CollectorAgent(market)
    analyst = AnalystAgent(market)
    writer = WriterAgent(market)
    qc = QCAgent(market)
    settings = get_settings()
    concurrency = settings.collector_concurrency

    async def _bounded_gather(factories: List[Callable[[], Awaitable[Any]]]) -> List[Any]:
        """并发运行协程工厂，受配置的上限约束。"""
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

        # 定向返工：在迭代 > 0 时只重新采集 QC 实际标记的竞品；
        # 其余一律原样沿用。
        flagged = _flagged_collector_labels(last_qc) if iteration > 0 else None

        # --- 自身 / 目标产品 ---
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

        # --- 竞品（并发） ---
        def _needs(i: int, name: str) -> bool:
            if flagged is None:
                return True
            label = f"competitors[{i}]"
            # 把当前索引映射回 QC 使用的标签（上一轮的顺序）。
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

        # 发出结构化、带类型的返工请求（智能体间协议），
        # 并各记一条追踪事件，使交接可观测。
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
    """为每个接收智能体构建一条带类型的 AgentMessage 并记入追踪。"""
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
# 条件路由（按角色定向）
# ---------------------------------------------------------------------------
def _route_after_qc(state: GraphState) -> str:
    last = state.get("last_qc") or {}
    decision = last.get("decision", "approve")
    settings = get_settings()
    if decision != "rework" or state.get("iteration", 0) > settings.max_qc_iterations:
        log.info(f"QC decision={decision} — finishing")
        return "done"

    # 从拥有阻塞 / 重大问题的最早阶段重新进入。
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
# 检查点包装器（续跑支持）
# ---------------------------------------------------------------------------
def _wrap_checkpointed(name: str, fn, seq: Dict[str, int]):
    async def _node(state: GraphState) -> GraphState:
        resume_from = state.get("resume_from")
        if resume_from and STAGE_ORDER.index(name) < STAGE_ORDER.index(resume_from):
            return state  # 在被中断的运行中已完成 —— 跳过
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
    except Exception as exc:  # pragma: no cover - 检查点绝不能中断一次运行
        log.warning(f"checkpoint save failed (node={node}): {exc!r}")


# ---------------------------------------------------------------------------
# 公共 API
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
    """运行完整 DAG 并返回已持久化的最终报告。"""
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
    """从最近的检查点恢复一次此前被中断的运行。

    重新加载已保存的 GraphState，把最后一个完成节点*之后*的阶段标记为恢复点，
    然后继续 DAG。该点之前的阶段会被跳过（它们的输出已在恢复的状态中）。
    """
    store = get_store()
    await store.init()
    ckpt = await store.latest_checkpoint(run_id)
    if not ckpt:
        raise RuntimeError(f"No checkpoint found for run {run_id!r}; cannot resume.")

    state: GraphState = ckpt["state"]
    last_node = ckpt["node"]
    # 从最后一个完成节点的下一个节点恢复（或重跑 qc 本身）。
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
    """为跨运行演化 / diff，给每个竞品持久化一个快照。"""
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
        except Exception as exc:  # pragma: no cover - 快照尽力而为
            log.warning(f"knowledge snapshot failed for {c.name!r}: {exc!r}")


def _schema_completeness(competitors: List[CompetitorKnowledge]) -> float:
    """所有竞品中关键字段已填充的比例。"""
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
