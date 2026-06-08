# 🎯 AI-Driven Competitive Product Analysis Agent System

> A multi-agent collaboration system that automates the end-to-end competitive analysis workflow — from public information collection to structured competitor reports — with cross-agent review and feedback loops.

[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org)
[![LangGraph](https://img.shields.io/badge/orchestration-LangGraph-orange.svg)](https://langchain-ai.github.io/langgraph/)
[![React](https://img.shields.io/badge/frontend-React%2018-61dafb.svg)](https://react.dev)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

---

## 1. What it does

Given a product name and a target market (🇨🇳 China / 🇺🇸 US), the system spins up a "digital research team" of specialized agents that:

1. **Collect** public competitor information (web search, robots.txt-compliant crawling, questionnaire-style synthesis, simulated user interviews).
2. **Structure** the information against a strict competitor knowledge **Schema** (function tree, pricing model, user profile).
3. **Analyze** competitors (SWOT, positioning, differentiation).
4. **Write** a polished, traceable report.
5. **Quality-control** the output — the QC agent reviews both the collected knowledge and the final report, then returns work to the **specific** upstream agent that owns each defect (collector / analyst / writer) for **real, targeted** rework — not a pseudo-loop.

Every conclusion is **source-traceable** (URL / doc / interview ID) with a confidence score, and every agent decision is **observable** via structured logs and traces. A reviewer can **edit any field in place** (human-in-the-loop), and those edits feed an **active-learning loop** that steers future runs.

---

## 2. Highlights against the scoring rubric

| Scoring dimension | How this project addresses it |
| --- | --- |
| **Multi-agent collaboration & credibility (35%)** | Four specialized agents with non-overlapping responsibilities; LangGraph DAG with visualization; **structured inter-agent protocol** — every hand-off is a validated Pydantic object (`CompetitorKnowledge`, `QCReport`), and QC rework is dispatched as a typed `AgentMessage(intent="request_rework")` recorded in the trace; **real, role-targeted feedback loop** — QC reviews the collected knowledge *and the final report*, then routes rework to the agent that owns the defect (collector / analyst / writer), re-collecting only the flagged competitors; strict schema validation; every fact carries a `SourceRef` with a confidence score. |
| **Technical depth & engineering (25%)** | End-to-end stack (Collector → Orchestration → Knowledge Store → API → Frontend); per-agent trace records with prompt/input/output/tokens; **confidence-aware orchestration**, **cross-source conflict detection**, self-consistency voting, citation enforcement; concurrent per-competitor collection; **DAG checkpoint + resume**; externalized run registry; retry/timeout/fallback wrappers; mock mode for resilient demos. |
| **Business value & UX (20%)** | Real workflow shaping (input → DAG progress → report → trace → **human-in-the-loop edit** → replay); quantifiable metrics (time, source coverage, schema completeness, avg confidence, conflicts, **manual-correction rate**) tracked in `metrics`; **cross-run knowledge evolution** (diff a competitor across runs); **agent self-evaluation** that proposes schema changes; market-pluggable architecture (CN / US today, extensible to any market). |
| **Code quality & docs (10%)** | Modular layout, typed Python, fully-documented agent protocol, architecture diagram, deployment guide, extension guide; backend `pytest` suite + frontend typecheck/build run in **CI** (`.github/workflows/ci.yml`). |
| **Compliance & materials (10%)** | `robots.txt` guard on every fetch, ToS-respecting collectors, synthetic-only interview/questionnaire data clearly labeled (real-data import + mandatory PII-redaction pass is **specified as planned v1.1**, see [`docs/compliance.md`](docs/compliance.md) §4), declared use of LLMs (Volcengine Ark) and search providers, full submission bundle (proposal, video script, repo). |

---

## 2.1 Capabilities (v1.1)

Beyond the baseline pipeline, the system implements:

- **Role-targeted feedback loop** — `qc` routes rework back to `collect`, `analyze`, **or** `write` depending on which agent owns the blocking finding ([`orchestration/graph.py:_route_after_qc`](backend/app/orchestration/graph.py)). Only the flagged competitors are re-collected ("targeted rework"), and each agent receives the slice of QC findings addressed to it, carried as a typed `AgentMessage`.
- **Confidence-aware orchestration** — every claim aggregates the confidence of its sources; weak-evidence claims become re-collection candidates. Surfaced as the `avg_confidence` / `low_confidence_claims` metrics.
- **Self-consistency + cross-source conflict detection** — competitor identification can be majority-voted across N samples; pricing/currency/capability contradictions are flagged as `ConflictFlag`s and rendered as "⚠ source conflict" badges ([`consistency.py`](backend/app/consistency.py)).
- **Human-in-the-loop editing** — `PATCH /api/reports/{id}` applies field edits, records a `Correction` audit trail, and recomputes the **manual-correction-rate** KPI.
- **Active learning** — recent corrections are distilled into "lessons learned" injected into the Collector/Writer prompts ([`learning.py`](backend/app/learning.py)).
- **Cross-run knowledge evolution** — each run snapshots every competitor by a normalized entity key; `GET /api/knowledge/diff` shows what changed since last time ([`knowledge.py`](backend/app/knowledge.py)).
- **Agent self-evaluation / dynamic schema** — `GET /api/meta/suggestions` aggregates field completeness + recurring corrections/conflicts into schema-evolution suggestions ([`meta.py`](backend/app/meta.py)).
- **DAG checkpoint + resume** — every node checkpoints `GraphState`; an interrupted run resumes from the last completed stage via `POST /api/analysis/resume/{run_id}`.
- **Concurrency + durability** — per-competitor collection/analysis run concurrently (bounded semaphore); the run registry is persisted so status/trace survive a restart.

## 3. Architecture (at a glance)

```
┌────────────────────────────────────────────────────────────────────┐
│                         React + Vite Frontend                       │
│   Analysis form │ DAG Flow │ Report View │ Trace Viewer │ i18n      │
└──────────────────────────────┬─────────────────────────────────────┘
                               │  REST / SSE
┌──────────────────────────────▼─────────────────────────────────────┐
│                           FastAPI Backend                           │
│  /api/analysis  /api/reports  /api/traces  /api/stream             │
└──────────────────────────────┬─────────────────────────────────────┘
                               │
              ┌────────────────▼────────────────┐
              │   LangGraph Orchestrator (DAG)  │
              └────────────────┬────────────────┘
                               │
   ┌──────────┬───────────┬────┴────┬────────────┐
   ▼          ▼           ▼         ▼            ▼
 Collector  Analyst    Writer    QC Agent    (Re-route)
   │          │           │         │
   ▼          ▼           ▼         ▼
 ┌─────────────────────────────────────────────┐
 │  Knowledge Store (SQLite) │ Trace Store     │
 └─────────────────────────────────────────────┘
                               │
   ┌───────────────────────────┴───────────────────────────┐
   ▼                                                       ▼
 Volcengine Ark LLM                              Pluggable Web Search
 (Doubao / custom model)                         (Tavily / Bing / Serper)
```

Full diagram, sequence flows, and state machine details: see [`docs/architecture.md`](docs/architecture.md).

---

## 4. Quick start

### 4.1 Prerequisites

- Python **3.10+**
- Node **18+** and **pnpm** (or npm / yarn)
- A **Volcengine Ark** API key + a model endpoint ID (e.g. Doubao). You can also start in **mock mode** without a key.

### 4.2 Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Copy and fill in env
Copy-Item .env.example .env
notepad .env       # set ARK_API_KEY and ARK_MODEL_ID, or leave VOLC_MOCK=1

python main.py     # starts FastAPI on http://127.0.0.1:8000
```

### 4.3 Frontend

```powershell
cd frontend
pnpm install
pnpm dev           # starts Vite on http://127.0.0.1:5173
```

Open `http://127.0.0.1:5173`, choose **🇨🇳 Chinese market** or **🇺🇸 US market**, enter a product (e.g. "Notion" or "飞书"), and watch the DAG light up.

### 4.4 One-shot demo (no UI)

```powershell
cd backend
python -m app.scripts.demo --product "Notion" --market us
```

---

## 5. Repository layout

```
competitive-analysis-agent/
├── README.md                       # ← you are here
├── docs/                           # Architecture, agents, schema, deployment, extension
├── backend/                        # FastAPI + LangGraph agent system
│   ├── main.py
│   ├── requirements.txt
│   ├── .env.example
│   └── app/
│       ├── api/                    # REST endpoints + SSE
│       ├── agents/                 # Collector / Analyst / Writer / QC
│       ├── orchestration/          # LangGraph DAG + state machine
│       ├── schema/                 # Pydantic schemas (competitor / messages / report)
│       ├── llm/                    # Volcengine Ark client
│       ├── collectors/             # Web search + robots.txt-compliant crawler
│       ├── market/                 # Market profiles (CN / US, pluggable)
│       ├── i18n/                   # Server-side locale strings
│       ├── observability/          # Structured logger + trace store
│       ├── storage/                # SQLite knowledge store
│       └── prompts/                # System prompts per agent, per locale
├── frontend/                       # React 18 + Vite + TS + Tailwind
│   └── src/
│       ├── pages/
│       ├── components/             # DAGFlow, ReportView, TraceViewer, SourceBadge
│       ├── api/
│       └── i18n/                   # zh / en bundles
└── scripts/                        # Convenience launchers
```

---

## 6. Extending to a new market (e.g. EU, JP, SEA)

The market layer is a clean plug-in point. To add a new market:

1. Create `backend/app/market/<code>.py` implementing `MarketProfile` (search backend, search seeds, locale, compliance overrides).
2. Add a locale bundle in `backend/app/i18n/locales.py` and `frontend/src/i18n/<code>.ts`.
3. Register the new market in `backend/app/market/__init__.py` and `frontend/src/api/client.ts`.
4. (Optional) Add domain-specific source allowlists.

The agents, schema, orchestrator, and UI components are all market-agnostic — they read from the active `MarketProfile`. See [`docs/extension.md`](docs/extension.md) for a worked example.

---

## 7. Documentation

- [`docs/architecture.md`](docs/architecture.md) — System architecture, DAG, sequence diagrams
- [`docs/agents.md`](docs/agents.md) — Agent role specifications and message protocol
- [`docs/schema.md`](docs/schema.md) — Competitor knowledge schema (function tree, pricing, user profile)
- [`docs/deployment.md`](docs/deployment.md) — Local dev + production deployment
- [`docs/extension.md`](docs/extension.md) — How to add markets, agents, data sources
- [`docs/compliance.md`](docs/compliance.md) — Robots.txt, ToS, PII handling

---

## 8. Compliance notes

- **robots.txt** is fetched and respected for every external URL.
- The collector identifies as `CompetitiveAnalysisAgent/1.0` with a contact URL in the User-Agent.
- Questionnaire and interview data are **synthesized** by the LLM and clearly marked as synthetic (`kind="interview" / "questionnaire"`, low confidence). There is **no real-PII ingestion path today**. A real-data import gated behind a mandatory PII-redaction pass is **specified as a planned v1.1 capability** — see [`docs/compliance.md`](docs/compliance.md) §4. The codebase does not yet ship that redaction code, and the docs no longer claim it does.
- The system uses Volcengine Ark as the sole LLM provider. Search providers are configurable and respect each provider's ToS.

See [`docs/compliance.md`](docs/compliance.md) for full details.

---

## 9. License

MIT — see [`LICENSE`](LICENSE).
