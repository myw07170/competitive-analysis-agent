# Project Structure

A reviewer's map of the repo.

```
competitive-analysis-agent/
│
├── README.md                       # Quickstart + scoring rubric mapping
├── LICENSE                         # MIT
├── AI_USAGE.md                     # Declared AI tool usage
├── .gitignore
│
├── docs/
│   ├── architecture.md             # System architecture + DAG diagrams
│   ├── agents.md                   # Per-agent contract + message protocol
│   ├── schema.md                   # Competitor knowledge schema
│   ├── deployment.md               # Local dev + production deployment
│   ├── extension.md                # Add a market / agent / data source
│   ├── compliance.md               # robots.txt, ToS, PII, LLM usage
│   ├── demo-script.md              # 3-minute video walkthrough script
│   └── project-structure.md        # ← you are here
│
├── backend/
│   ├── main.py                     # FastAPI app factory + uvicorn entry
│   ├── requirements.txt
│   ├── pytest.ini
│   ├── .env.example
│   │
│   ├── app/
│   │   ├── config.py               # Pydantic Settings (env-driven)
│   │   ├── consistency.py          # Conflict detection + self-consistency voting
│   │   ├── knowledge.py            # Cross-run competitor diff
│   │   ├── meta.py                 # Agent self-evaluation → schema suggestions
│   │   ├── learning.py             # Corrections → active-learning prompt guidance
│   │   ├── report_html.py          # Standalone self-contained HTML export
│   │   │
│   │   ├── api/
│   │   │   ├── analysis.py         # /api/analysis/{start,stream,dag,markets,status,resume}
│   │   │   ├── reports.py          # /api/reports/{...} incl. PATCH (human edit)
│   │   │   ├── traces.py           # /api/traces/{run_id}
│   │   │   ├── knowledge.py        # /api/knowledge/{entities,history,diff}
│   │   │   └── meta.py             # /api/meta/{suggestions,corrections}
│   │   │
│   │   ├── agents/
│   │   │   ├── base.py             # LLM call + JSON parse/repair + tracing
│   │   │   ├── collector.py        # Identify (+self-consistency) + gather (web evidence + guidance)
│   │   │   ├── analyst.py          # SWOT analysis (rework-aware)
│   │   │   ├── writer.py           # Final report synthesis (rework-aware)
│   │   │   └── qc.py               # Deterministic + LLM critique → role-routed rework
│   │   │
│   │   ├── orchestration/
│   │   │   ├── graph.py            # LangGraph DAG: role-targeted rework, concurrency, checkpoints
│   │   │   └── state.py            # GraphState + static DAG metadata for FE
│   │   │
│   │   ├── schema/
│   │   │   ├── competitor.py       # Three-pillar schema + SourceRef + ConflictFlag + confidence
│   │   │   ├── messages.py         # AgentMessage / QCReport / QCFinding
│   │   │   └── report.py           # FinalReport + ReportMetrics + Correction + SchemaSuggestion + KnowledgeDiff
│   │   │
│   │   ├── llm/
│   │   │   ├── volcengine.py       # Ark async client + retries
│   │   │   └── mocks.py            # Built-in canned responses for demo mode
│   │   │
│   │   ├── collectors/
│   │   │   ├── search.py           # Pluggable Tavily / Serper / Bing
│   │   │   ├── web.py              # robots-compliant fetcher + rate limit
│   │   │   └── robots.py           # robots.txt cache
│   │   │
│   │   ├── prompts/
│   │   │   ├── collector.py        # System + user prompt templates
│   │   │   ├── analyst.py
│   │   │   ├── writer.py
│   │   │   └── qc.py
│   │   │
│   │   ├── market/
│   │   │   ├── base.py             # MarketProfile dataclass
│   │   │   ├── cn.py               # 🇨🇳 ChinaMarket
│   │   │   ├── us.py               # 🇺🇸 USMarket
│   │   │   └── __init__.py         # Registry + get_market(code)
│   │   │
│   │   ├── i18n/
│   │   │   └── locales.py          # Server-side label strings (zh-CN / en-US)
│   │   │
│   │   ├── observability/
│   │   │   ├── logger.py           # Loguru sink
│   │   │   └── tracer.py           # Per-run TraceEvent recorder + SSE queue
│   │   │
│   │   ├── storage/
│   │   │   └── store.py            # SQLite: reports, traces, knowledge snapshots,
│   │   │                           #   corrections, run registry, checkpoints
│   │   │
│   │   └── scripts/
│   │       └── demo.py             # One-shot CLI: produces a full report
│   │
│   └── tests/
│       ├── conftest.py             # Mock mode + isolated data dir
│       ├── test_schema.py
│       ├── test_qc.py              # Deterministic checks incl. role routing
│       ├── test_consistency.py     # Conflict detection + majority vote
│       ├── test_json_repair.py     # JSON recovery pipeline
│       ├── test_knowledge.py       # Cross-run diff
│       ├── test_routing.py         # Role-targeted rework routing
│       ├── test_learning.py        # Active-learning guidance
│       ├── test_robots.py          # Compliance helpers
│       ├── test_checkpoint.py      # Checkpoint + resume
│       ├── test_api.py             # End-to-end ASGI (start→edit→knowledge→meta)
│       └── test_orchestration.py   # Full DAG, mock mode, including rework loop
│
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── tailwind.config.js
│   ├── postcss.config.js
│   ├── index.html
│   │
│   └── src/
│       ├── main.tsx                # Entry + router
│       ├── App.tsx                 # Shell + nav + health pill
│       ├── index.css               # Tailwind + DAG node styles
│       │
│       ├── pages/
│       │   ├── Home.tsx            # Form + DAG + live trace list + resume button
│       │   ├── Report.tsx          # Tabs: report / comparison / competitors /
│       │   │                       #   evolution / trace / sources; inline edit + conflicts
│       │   └── History.tsx         # Past report list + meta self-eval panel
│       │
│       ├── components/
│       │   ├── AnalysisForm.tsx    # Product + market-chip selector
│       │   ├── AgentFlow.tsx       # Agent-flow + decision-trace replay (by rework round)
│       │   ├── ComparisonView.tsx  # Charts + comparison tables
│       │   ├── TraceList.tsx       # Expandable per-event drill-down
│       │   └── SourceBadge.tsx     # Inline citation chip
│       │
│       ├── api/
│       │   └── client.ts           # REST + SSE client
│       │
│       └── i18n/
│           ├── index.ts            # marketToLocale + makeT
│           ├── zh.ts               # 🇨🇳 zh-CN bundle
│           └── en.ts               # 🇺🇸 en-US bundle
│
├── .github/
│   └── workflows/
│       └── ci.yml                  # Backend pytest + frontend typecheck/build
│
└── scripts/
    ├── start-backend.ps1           # venv setup + python main.py
    ├── start-frontend.ps1          # pnpm/npm install + dev
    └── run-demo.ps1                # CLI demo wrapper
```

## File-count summary

| Area | Files |
| --- | --- |
| Documentation | 8 |
| Backend Python | ~40 |
| Frontend TS/TSX | ~13 |
| Configuration | 7 |
| Scripts | 3 |
| Tests | 11 |

## Reading order for reviewers

If you have 20 minutes, read in this order:

1. [`README.md`](../README.md) — what + why + how to run.
2. [`docs/architecture.md`](architecture.md) — the DAG and where each rubric criterion is satisfied.
3. [`backend/app/schema/competitor.py`](../backend/app/schema/competitor.py) — the schema is the contract.
4. [`backend/app/orchestration/graph.py`](../backend/app/orchestration/graph.py) — the DAG and the feedback loop.
5. [`backend/app/agents/qc.py`](../backend/app/agents/qc.py) — the deterministic + LLM hybrid critique.
6. [`docs/extension.md`](extension.md) — how the system stays open-ended.
