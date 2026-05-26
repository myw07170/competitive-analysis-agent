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
                                 ┌──────────────┐
            ┌──────────────────▶│   collect    │◀── rework (with QC notes)
            │                    └──────┬───────┘
            │                           ▼
            │                    ┌──────────────┐
            │                    │   analyze    │   (analyst)
            │                    └──────┬───────┘
            │                           ▼
            │                    ┌──────────────┐
            │                    │    write     │   (writer)
            │                    └──────┬───────┘
            │                           ▼
            │                    ┌──────────────┐
            │     rework         │      qc      │   (qc)
            └────────────────────┤  decision?   │
                                 └──────┬───────┘
                                        │ approve / approve_with_notes
                                        ▼
                                 ┌──────────────┐
                                 │    done      │
                                 └──────────────┘
```

* Loop bound: `MAX_QC_ITERATIONS` (default `2`). After that, the run finishes with whatever QC reports.
* The QC agent injects its findings into the next `collect` call as **rework notes**, so the second pass *measurably* improves on the first (more sources, fewer schema gaps).

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
| Function-calling-style messaging | [`backend/app/schema/messages.py`](../backend/app/schema/messages.py) and Pydantic validation on every agent boundary | Inter-agent payloads are typed; raw text never crosses agent boundaries unparsed. |
| Real feedback loop | [`backend/app/orchestration/graph.py:_route_after_qc`](../backend/app/orchestration/graph.py) and the `rework_notes` parameter on `CollectorAgent.gather_competitor` | QC findings are passed back into the next collect call. The mock backend even returns visibly different data on the second pass. |
| Schema conformance | [`backend/app/schema/competitor.py`](../backend/app/schema/competitor.py) | Pydantic `CompetitorKnowledge.model_validate` is called on every agent output. |
| Source traceability | `SourceRef` is a required field on every fact-bearing schema node. Frontend renders `SourceBadge`. | Every Cited / SourceRef has a kind, optional URL, snippet, confidence. |
| Observability | [`backend/app/observability/tracer.py`](../backend/app/observability/tracer.py) + `/api/traces/{run_id}` | One trace event per agent call captures prompt/input/output/tokens/duration. |
| Compliance | [`backend/app/collectors/robots.py`](../backend/app/collectors/robots.py), [`docs/compliance.md`](compliance.md) | robots.txt enforcement, per-host rate limiting, configurable User-Agent. |

## 7. Performance and resilience

* **Retries**: LLM calls use exponential backoff (tenacity). Timeouts and 5xx are retried; client errors are not.
* **Mock fallback**: when no API key is set, the system silently switches to mocks — useful for demos and for offline development.
* **Hallucination suppression**: deterministic checks in QC catch placeholder URLs (`example.com`, `localhost`), low source counts, and missing fields, *before* the LLM is asked to opine.
* **Context fragmentation**: the writer prompt truncates the per-competitor JSON to 12 KB; the analyst to 6 KB. Long contexts are chunked rather than dropped.

## 8. Future extensions

* **More markets** — see [`extension.md`](extension.md).
* **More agents** — add `app/agents/<role>.py`, register a new DAG node + edge in `app/orchestration/state.py` and `app/orchestration/graph.py`. The frontend picks up new nodes automatically from `/api/analysis/dag`.
* **Dynamic schema evolution** — `CompetitorKnowledge.schema_version` is persisted with every report. Future versions can add fields without invalidating old reports.
* **Adaptive task splitting** — the orchestrator already loops over competitors sequentially; swapping in `asyncio.gather` is a one-line change once Ark rate limits are known.
