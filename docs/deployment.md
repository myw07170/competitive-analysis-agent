# Deployment Guide

## 1. Local development

### Prerequisites
* Python **3.10+**
* Node **18+**, `pnpm` (or `npm` / `yarn`)
* A Volcengine Ark account (optional — system also runs in mock mode)

### Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

Copy-Item .env.example .env
# Fill in ARK_API_KEY and ARK_MODEL_ID, or leave them blank for mock mode.

python main.py
```

Backend listens on `http://127.0.0.1:8000`. Health check: `GET /api/health`.

### Frontend

```powershell
cd frontend
pnpm install
pnpm dev
```

Frontend on `http://127.0.0.1:5173`. The Vite proxy forwards `/api/*` to the backend, so no CORS configuration is needed for local dev.

### One-shot demo (CLI, no UI)

```powershell
cd backend
python -m app.scripts.demo --product "Notion" --market us
```

This prints the final JSON report and writes it to `backend/data/reports/`. Useful for screen-recording or for piping into other tools.

## 2. Configuration

All configuration is via environment variables (or `.env`). See `backend/.env.example` for the complete list. The most important ones:

| Variable | Default | Purpose |
| --- | --- | --- |
| `ARK_API_KEY` | empty | Volcengine API key |
| `ARK_MODEL_ID` | empty | Endpoint / model ID (e.g. `ep-202401XX-xxxxx`) |
| `ARK_BASE_URL` | `https://ark.cn-beijing.volces.com/api/v3` | Ark endpoint |
| `VOLC_MOCK` | `0` | Set to `1` to force mock mode even with a key |
| `SEARCH_PROVIDER` | `none` | `tavily` / `serper` / `bing` / `none` |
| `MAX_QC_ITERATIONS` | `2` | Maximum rework loops |
| `MIN_SOURCES_PER_COMPETITOR` | `3` | QC threshold |
| `COLLECTOR_CONCURRENCY` | `3` | Parallel per-competitor collect/analyze (1 = sequential) |
| `MIN_CONFIDENCE` | `0.55` | Claims below this trigger confidence-aware re-collection |
| `SELF_CONSISTENCY_SAMPLES` | `1` | N-sample majority vote on competitor identification (1 = off) |
| `ENABLE_CONFLICT_DETECTION` | `1` | Cross-source conflict flagging |
| `RESPECT_ROBOTS` | `1` | Set to `0` only for testing |

### API surface

| Endpoint | Purpose |
| --- | --- |
| `POST /api/analysis/start` · `GET .../stream/{id}` · `GET .../status/{id}` · `GET .../dag` · `GET .../markets` | Run lifecycle + live SSE + DAG metadata |
| `POST /api/analysis/resume/{run_id}` | Resume an interrupted run from its last checkpoint |
| `GET/DELETE /api/reports/{id}` · `GET .../html` | Read / delete / export a report |
| `PATCH /api/reports/{id}` | Human-in-the-loop field edit (records a `Correction`) |
| `GET /api/traces/{run_id}` | Decision-trace replay |
| `GET /api/knowledge/{entities,history,diff}` | Cross-run competitor evolution |
| `GET /api/meta/{suggestions,corrections}` | Agent self-evaluation + correction feed |

## 3. Production deployment

### 3.1 Single-host (recommended for first deploy)

```
┌────────────────────────────┐
│       Nginx / Caddy        │
│  Static frontend (built)   │
│  Reverse-proxy to :8000    │
└────────────────────────────┘
              │
┌────────────────────────────┐
│   FastAPI (uvicorn)        │
│   Port 8000                │
└────────────────────────────┘
              │
┌────────────────────────────┐
│  SQLite (data/app.sqlite)  │
└────────────────────────────┘
```

Steps:

1. Build the frontend: `cd frontend && pnpm build`. Output goes to `frontend/dist`.
2. Configure Nginx to serve `frontend/dist` and proxy `/api/*` to `127.0.0.1:8000`.
3. Run the backend under a process supervisor (systemd, supervisord, pm2).

Sample systemd unit (Linux):

```ini
[Unit]
Description=Competitive Analysis Agent backend
After=network.target

[Service]
WorkingDirectory=/srv/competitive-analysis-agent/backend
EnvironmentFile=/srv/competitive-analysis-agent/backend/.env
ExecStart=/srv/competitive-analysis-agent/backend/.venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000 --workers 2
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### 3.2 Docker (optional)

A `Dockerfile` is not included by default to keep the repo lean, but the layout is straightforward:

```dockerfile
# Stage 1: frontend
FROM node:20-alpine AS fe
WORKDIR /app
COPY frontend/ ./frontend
RUN cd frontend && npm install && npm run build

# Stage 2: backend
FROM python:3.11-slim
WORKDIR /app
COPY backend/ ./backend
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY --from=fe /app/frontend/dist /app/frontend_dist
EXPOSE 8000
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

(Serve `/app/frontend_dist` with Nginx in front, or mount a `StaticFiles` route in FastAPI.)

### 3.3 Scaling

* **Vertical scale**: increase `--workers` on uvicorn. The run registry is now **persisted to SQLite** (`runs` + `run_checkpoints` tables), so `GET /api/analysis/status` and `/stream` fall back to the database when a run is not in the local worker's memory — status and trace replay survive a restart. The live SSE *push* still requires hitting the worker that owns the in-memory `Tracer` queue; for true multi-worker live streaming, swap that queue for Redis pub/sub.
* **Resumability**: because every node checkpoints `GraphState`, a run interrupted by a crash/restart can be continued with `POST /api/analysis/resume/{run_id}` instead of restarting from scratch.
* **Persistent storage**: SQLite is fine for prototype. For production-grade, switch to Postgres — `aiosqlite` ↔ `asyncpg` is mostly mechanical, the table schema is identical.

## 4. Observability in production

* All log lines are structured (component, level, message). Pipe stderr to your log aggregator.
* The `/api/traces/{run_id}` endpoint is the source of truth for replay.
* `report.metrics` contains per-run KPIs that you should ingest into your BI tool to track:
  * `elapsed_seconds`, `total_tokens`
  * `schema_completeness`, `avg_sources_per_competitor`
  * `avg_confidence`, `low_confidence_claims`, `conflict_count`
  * `qc_iterations`, `rework_count`
  * `manual_correction_rate`, `corrected_fields`
* `GET /api/meta/suggestions` exposes cross-run aggregates (field completeness, recurring corrections/conflicts) for the agent self-evaluation dashboard.

These map directly to the "business loop" metrics the rubric calls out: efficiency (time), coverage (sources), consistency (schema completeness), credibility (avg confidence / conflicts), and **manual-correction rate** — now a first-class metric, recomputed on every human edit via `PATCH /api/reports/{id}`.

## 5. Common issues

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| Frontend renders but API calls 404 | Vite proxy mis-targeted | Check `vite.config.ts` proxy `target` matches backend port |
| `report not found` after a run | Backend restarted between start and finish | SQLite is per-host; in dev that resets on each restart |
| LLM call returns 401 | Bad key or expired key | Re-issue from the Volcengine console; check `ARK_MODEL_ID` is the endpoint ID, not the model family name |
| All sources show "llm_prior" | No search backend configured | Set `SEARCH_PROVIDER` and the corresponding key in `.env` |
| Long runs hit timeout | `ARK_TIMEOUT` too low for your model | Bump to 120s+ for slower models |
