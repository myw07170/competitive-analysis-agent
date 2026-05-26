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
│   │   │
│   │   ├── api/
│   │   │   ├── analysis.py         # /api/analysis/{start,stream,dag,markets,status}
│   │   │   ├── reports.py          # /api/reports/{...}
│   │   │   └── traces.py           # /api/traces/{run_id}
│   │   │
│   │   ├── agents/
│   │   │   ├── base.py             # LLM call + JSON parse + tracing
│   │   │   ├── collector.py        # Identify + gather (with web evidence)
│   │   │   ├── analyst.py          # SWOT analysis
│   │   │   ├── writer.py           # Final report synthesis
│   │   │   └── qc.py               # Deterministic + LLM critique → rework decision
│   │   │
│   │   ├── orchestration/
│   │   │   ├── graph.py            # LangGraph DAG with conditional edges
│   │   │   └── state.py            # GraphState + static DAG metadata for FE
│   │   │
│   │   ├── schema/
│   │   │   ├── competitor.py       # Three-pillar schema + SourceRef
│   │   │   ├── messages.py         # AgentMessage / QCReport / QCFinding
│   │   │   └── report.py           # FinalReport + ReportMetrics
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
│   │   │   └── store.py            # SQLite (reports + traces)
│   │   │
│   │   └── scripts/
│   │       └── demo.py             # One-shot CLI: produces a full report
│   │
│   └── tests/
│       ├── test_schema.py
│       ├── test_qc.py
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
│       │   ├── Home.tsx            # Form + DAG + live trace list
│       │   ├── Report.tsx          # Tabs: report / competitors / trace / sources
│       │   └── History.tsx         # Past report list
│       │
│       ├── components/
│       │   ├── AnalysisForm.tsx    # Product + market-chip selector
│       │   ├── DAGFlow.tsx         # ReactFlow visualization w/ status colors
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
└── scripts/
    ├── start-backend.ps1           # venv setup + python main.py
    ├── start-frontend.ps1          # pnpm/npm install + dev
    └── run-demo.ps1                # CLI demo wrapper
```

## File-count summary

| Area | Files |
| --- | --- |
| Documentation | 8 |
| Backend Python | ~30 |
| Frontend TS/TSX | ~12 |
| Configuration | 6 |
| Scripts | 3 |
| Tests | 3 |

## Reading order for reviewers

If you have 20 minutes, read in this order:

1. [`README.md`](../README.md) — what + why + how to run.
2. [`docs/architecture.md`](architecture.md) — the DAG and where each rubric criterion is satisfied.
3. [`backend/app/schema/competitor.py`](../backend/app/schema/competitor.py) — the schema is the contract.
4. [`backend/app/orchestration/graph.py`](../backend/app/orchestration/graph.py) — the DAG and the feedback loop.
5. [`backend/app/agents/qc.py`](../backend/app/agents/qc.py) — the deterministic + LLM hybrid critique.
6. [`docs/extension.md`](extension.md) — how the system stays open-ended.
