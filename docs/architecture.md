# Architecture

## 1. Goals

1. **Reproducibility** — given the same product + market, the system should walk the same DAG. Randomness lives only in LLM sampling; the *structure* of agent collaboration is deterministic.
2. **Traceability** — every conclusion in the final report can be traced (a) to the agent that wrote it and (b) to the source(s) that support it.
3. **Extensibility** — new markets, new data sources, and new agents can be added without touching the orchestrator or the schema.

## 2. High-level architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                          React + Vite Frontend                            │
│   AnalysisForm    DAGFlow (reactflow)    ReportView    TraceList         │
│   i18n (zh-CN | en-US, extensible)                                       │
└──────────────────────────────┬───────────────────────────────────────────┘
                               │ REST + Server-Sent Events
┌──────────────────────────────▼───────────────────────────────────────────┐
│                            FastAPI Backend                                │
│   /api/analysis/{start,stream,status,dag,markets}                        │
│   /api/reports/{...}     /api/traces/{run_id}     /api/health            │
└──────────────────────────────┬───────────────────────────────────────────┘
                               │
              ┌────────────────▼─────────────────┐
              │  LangGraph Orchestrator (DAG)    │
              │  identify → collect → analyze →  │
              │            write → qc → done/↺   │
              └────────────────┬─────────────────┘
                               │
   ┌──────────┬───────────┬────┴────┬────────────┐
   ▼          ▼           ▼         ▼            ▼
 Collector  Analyst    Writer    QC Agent    (Conditional re-route)
   │          │           │         │
   ▼          ▼           ▼         ▼
 ┌─────────────────────────────────────────────┐
 │ SQLite (reports + traces)                    │
 └─────────────────────────────────────────────┘
                               │
   ┌───────────────────────────┴───────────────────────────┐
   ▼                                                       ▼
 Volcengine Ark LLM                              Web search backend
 (Doubao / custom endpoint)                      (Tavily / Bing / Serper)
                                                 + robots.txt enforced fetcher
```

## 3. DAG state machine

```
                                 ┌──────────────┐
                                 │   identify   │   (collector)
                                 └──────┬───────┘
                                        ▼
            ┌──────────────────▶┌──────────────┐
            │ rework→collector   │   collect    │
            │                    └──────┬───────┘
            │                           ▼
            │ rework→analyst    ┌──────────────┐
            ├──────────────────▶│   analyze    │   (analyst)
            │                    └──────┬───────┘
            │                           ▼
            │ rework→writer     ┌──────────────┐
            ├──────────────────▶│    write     │   (writer)
            │                    └──────┬───────┘
            │                           ▼
            │                    ┌──────────────┐
            │   role-targeted    │      qc      │   (qc — reviews knowledge
            └────────────────────┤  decision?   │        AND the final report)
                                 └──────┬───────┘
                                        │ approve / approve_with_notes
                                        ▼
                                 ┌──────────────┐
                                 │    done      │
                                 └──────────────┘
```

* Loop bound: `MAX_QC_ITERATIONS` (default `2`). After that, the run finishes with whatever QC reports.
* **Role-targeted routing** ([`_route_after_qc`](../backend/app/orchestration/graph.py)): QC produces findings tagged with `target_agent` (collector / analyst / writer). The run re-enters at the *earliest stage that owns a blocking/major finding* — a missing SWOT re-runs `analyze`, a broken citation re-runs `write`, low source coverage re-runs `collect`. It does **not** blindly restart from `collect`.
* **Targeted rework**: on a collector rework, only the competitors QC flagged are re-collected (the rest are carried over), and each competitor's `gather` call receives only the findings whose `target_path` points at it. The QC→agent hand-off is a typed `AgentMessage(intent="request_rework")`, recorded in the trace.
* **Confidence-aware**: claims supported only by low-confidence sources (below `MIN_CONFIDENCE`) are themselves flagged, so the loop pursues stronger evidence, not just missing fields.
* The mock backend returns a visibly richer payload on the rework pass, so the loop *measurably* improves (more sources, fewer schema gaps) in a key-less demo; in live mode the deterministic checks (source count, empty fields, conflicts, low confidence) give the loop objective improvement criteria.

## 4. Data flow

```
   User input
       │
       ▼
   AnalysisRequest{ product, market, extra_competitors }
       │
       ▼  (orchestrator)
   GraphState
   ├── competitor_names: ["Notion", "Coda", "ClickUp"]
   ├── competitors: [CompetitorKnowledge × N]
   ├── qc_history: [QCReport × iterations]
   ├── last_qc: QCReport
   └── report: FinalReport
       │
       ▼
   FinalReport (Pydantic)
       │
       ▼
   SQLite + Frontend
```

The orchestrator never mutates a schema instance in place — every node produces a new typed value and the state-graph layer merges it back in. This is what makes the trace a faithful replay tool.

## 5. Sequence diagram: one full run

```
User           Frontend       FastAPI           Orchestrator     Collector  Analyst  Writer   QC     LLM/Search
 │   submit       │              │                    │              │         │        │     │         │
 │ ─────────────▶ │  POST /start │                    │              │         │        │     │         │
 │                │ ────────────▶│ build_graph()      │              │         │        │     │         │
 │                │              │ ainvoke ──────────▶│              │         │        │     │         │
 │                │              │                    │ identify ───▶│         │        │     │         │
 │                │              │                    │              │ ◀──────────────────────────────▶│
 │                │              │                    │ collect ────▶│         │        │     │         │
 │                │              │                    │              │ ─search + robots ▶│             │
 │                │              │                    │ analyze ────────────▶ │         │     │         │
 │                │              │                    │ write ────────────────────────▶ │     │         │
 │                │              │                    │ qc ────────────────────────────────▶ │         │
 │                │              │                    │ ◀─ decision: rework ──────────────── │         │
 │                │              │                    │ collect (with rework notes) ──▶│             │
 │                │              │                    │ analyze / write / qc again                    │
 │                │              │                    │ ◀─ decision: approve ──────────────────────── │
 │                │ ◀─ SSE: trace events as they fire ┤                                              │
 │                │ ◀─ SSE: done(report_id)            │                                             │
```

## 6. Where each scoring criterion is satisfied

| Criterion (from rubric) | File / module | How |
| --- | --- | --- |
| Clear role division | [`backend/app/agents/`](../backend/app/agents/) | Four agent files; `BaseAgent` is the only shared logic. |
| Visual DAG | [`backend/app/orchestration/state.py`](../backend/app/orchestration/state.py) + [`frontend/src/components/DAGFlow.tsx`](../frontend/src/components/DAGFlow.tsx) | Static DAG metadata served from `/api/analysis/dag`, rendered via ReactFlow. |
| Structured (function-calling-style) messaging | [`backend/app/schema/messages.py`](../backend/app/schema/messages.py) + Pydantic validation on every boundary; `AgentMessage` now carries QC→agent rework requests ([`graph.py:_emit_rework_messages`](../backend/app/orchestration/graph.py)) | Inter-agent payloads are typed objects, never raw text; rework is dispatched as a typed `AgentMessage(intent="request_rework")` recorded in the trace. |
| Real, role-targeted feedback loop | [`backend/app/orchestration/graph.py:_route_after_qc`](../backend/app/orchestration/graph.py); QC reviews knowledge **and** the report ([`agents/qc.py`](../backend/app/agents/qc.py)) | QC findings route to the collector, analyst, **or** writer; only flagged competitors are re-collected, each with its own findings slice. The mock backend returns visibly richer data on the rework pass. |
| Schema conformance | [`backend/app/schema/competitor.py`](../backend/app/schema/competitor.py) | Pydantic `CompetitorKnowledge.model_validate` is called on every agent output. |
| Source traceability | `SourceRef` is a required field on every fact-bearing schema node. Frontend renders `SourceBadge`. | Every Cited / SourceRef has a kind, optional URL, snippet, confidence. |
| Observability | [`backend/app/observability/tracer.py`](../backend/app/observability/tracer.py) + `/api/traces/{run_id}` | One trace event per agent call captures prompt/input/output/tokens/duration. |
| Compliance | [`backend/app/collectors/robots.py`](../backend/app/collectors/robots.py), [`docs/compliance.md`](compliance.md) | robots.txt enforcement, per-host rate limiting, configurable User-Agent. |

## 7. Performance and resilience

* **Retries**: LLM calls use exponential backoff (tenacity). Timeouts and 5xx are retried; client errors are not.
* **Mock fallback**: when no API key is set, the system silently switches to mocks — useful for demos and for offline development.
* **Hallucination suppression**: a layered strategy — (1) deterministic QC checks catch placeholder URLs (`example.com`, `localhost`), low source counts, and missing fields; (2) **citation enforcement** verifies every `[^src_xxx]` in the report resolves to a real source; (3) **confidence aggregation** flags claims backed only by weak sources; (4) **cross-source conflict detection** surfaces contradictions; (5) optional **self-consistency voting** (`SELF_CONSISTENCY_SAMPLES > 1`) majority-votes competitor identification across samples.
* **Concurrency**: per-competitor collection and analysis run concurrently under a bounded semaphore (`COLLECTOR_CONCURRENCY`, default 3).
* **Context fragmentation**: the writer prompt truncates the per-competitor JSON to 12 KB; the analyst to 6 KB. Long contexts are chunked rather than dropped.
* **Resume**: every node checkpoints `GraphState`; an interrupted run resumes from the last completed stage rather than restarting.

## 8. Implemented advanced capabilities (v1.1)

| Capability | Where | Notes |
| --- | --- | --- |
| Role-targeted feedback loop | [`orchestration/graph.py`](../backend/app/orchestration/graph.py) `_route_after_qc` | Rework routes to collector / analyst / writer. |
| Targeted rework + structured `AgentMessage` | `graph.py` `n_collect`, `_emit_rework_messages` | Only flagged competitors re-collected; typed message traced. |
| Confidence-aware orchestration | `competitor.py` `low_confidence_claims`, `qc.py` | Weak-evidence claims become re-collection candidates. |
| Self-consistency voting | [`consistency.py`](../backend/app/consistency.py) `majority_vote`, `collector.py` | N-sample majority vote on competitor identification (`SELF_CONSISTENCY_SAMPLES`). |
| Cross-source conflict detection | [`consistency.py`](../backend/app/consistency.py) `detect_conflicts` | `ConflictFlag`s → QC findings + "⚠ conflict" UI badges. |
| Human-in-the-loop editing | [`api/reports.py`](../backend/app/api/reports.py) `PATCH` | Records `Correction`, updates `manual_correction_rate`. |
| Active learning | [`learning.py`](../backend/app/learning.py) | Corrections → "lessons learned" injected into prompts. |
| Cross-run knowledge evolution | [`knowledge.py`](../backend/app/knowledge.py), [`api/knowledge.py`](../backend/app/api/knowledge.py) | Entity-keyed snapshots; structural diff endpoint. |
| Agent self-evaluation / schema suggestions | [`meta.py`](../backend/app/meta.py), [`api/meta.py`](../backend/app/api/meta.py) | Field completeness + recurring corrections → suggestions. |
| DAG checkpoint + resume | `graph.py` `_wrap_checkpointed`, `resume_analysis` | Per-node `GraphState` snapshot; `POST /api/analysis/resume/{run_id}`. |
| Concurrency | `graph.py` `_bounded_gather` | Per-competitor collect/analyze run concurrently (`COLLECTOR_CONCURRENCY`). |
| Durable run registry | [`api/analysis.py`](../backend/app/api/analysis.py), `storage/store.py` | Status + trace survive restart; `/status` & `/stream` fall back to SQLite. |

## 9. Future extensions

* **More markets** — see [`extension.md`](extension.md).
* **More agents** — add `app/agents/<role>.py`, register a new DAG node + edge in `app/orchestration/state.py` and `app/orchestration/graph.py`. The frontend picks up new nodes automatically from `/api/analysis/dag`.
* **Embedding-based entity resolution** — the cross-run knowledge store currently uses a normalized-name key; an embedding index would catch rebrands / aliases.
* **Auto-applied schema evolution** — `MetaEvaluator` proposes changes today; a future version could apply accepted suggestions and bump `schema_version` automatically.
