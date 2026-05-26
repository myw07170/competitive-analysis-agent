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
5. **Quality-control** the output — the QC agent can return the work to upstream agents for **real** rework, not a pseudo-loop.

Every conclusion is **source-traceable** (URL / doc / interview ID), and every agent decision is **observable** via structured logs and traces.

---

## 2. Highlights against the scoring rubric

| Scoring dimension | How this project addresses it |
| --- | --- |
| **Multi-agent collaboration & credibility (35%)** | Four specialized agents with non-overlapping responsibilities; LangGraph DAG with visualization; structured `AgentMessage` schema with `function_calling`-style payloads; real feedback loop where QC rework changes downstream outputs; strict Pydantic schema validation; every fact carries a `SourceRef`. |
| **Technical depth & engineering (25%)** | End-to-end stack (Collector → Orchestration → Knowledge Store → API → Frontend); per-agent trace records with prompt/input/output/tokens; context fragmentation, self-consistency checks, citation enforcement; retry/timeout/fallback wrappers; mock mode for resilient demos. |
| **Business value & UX (20%)** | Real workflow shaping (input → DAG progress → report → trace → manual fix → replay); quantifiable metrics (time saved, source coverage, schema completeness, manual-correction rate) tracked in `metrics`; market-pluggable architecture (CN / US today, extensible to any market). |
| **Code quality & docs (10%)** | Modular layout, typed Python, fully-documented agent protocol, architecture diagram, deployment guide, extension guide, conventional-commit-friendly. |
| **Compliance & materials (10%)** | `robots.txt` guard on every fetch, ToS-respecting collectors, PII redaction on interview/questionnaire data, declared use of LLMs (Volcengine Ark) and search providers, full submission bundle (proposal, video script, repo). |

---

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
- Questionnaire and interview data are **synthesized** by the LLM and clearly marked as synthetic; if a user imports real interview data, the system runs a PII redaction pass before storage.
- The system uses Volcengine Ark as the sole LLM provider. Search providers are configurable and respect each provider's ToS.

See [`docs/compliance.md`](docs/compliance.md) for full details.

---

## 9. License

MIT — see [`LICENSE`](LICENSE).
