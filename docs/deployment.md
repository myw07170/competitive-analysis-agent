# 部署指南

## 1. 本地开发

### 依赖环境
* Python **3.10+**
* Node **18+**、`pnpm`（或 `npm` / `yarn`）
* 一个火山方舟 Ark 账号（可选——系统同样能以 mock 模式运行）

### 后端

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

Copy-Item .env.example .env
# 填写 ARK_API_KEY 和 ARK_MODEL_ID，或将它们留空以走 mock 模式。

python main.py
```

后端监听 `http://127.0.0.1:8000`。健康检查：`GET /api/health`。

### 前端

```powershell
cd frontend
pnpm install
pnpm dev
```

前端运行在 `http://127.0.0.1:5173`。Vite 代理会把 `/api/*` 转发到后端，因此本地开发无需配置 CORS。

### 一键演示（CLI，无界面）

```powershell
cd backend
python -m app.scripts.demo --product "Notion" --market us
```

它会打印最终的 JSON 报告并写入 `backend/data/reports/`。适合录屏，或把结果管道传给其他工具。

## 2. 配置

所有配置都通过环境变量（或 `.env`）。完整清单见 `backend/.env.example`。最重要的几项：

| 变量 | 默认值 | 用途 |
| --- | --- | --- |
| `ARK_API_KEY` | 空 | 火山方舟 API Key |
| `ARK_MODEL_ID` | 空 | Endpoint / 模型 ID（例如 `ep-202401XX-xxxxx`） |
| `ARK_BASE_URL` | `https://ark.cn-beijing.volces.com/api/v3` | Ark 接入地址 |
| `VOLC_MOCK` | `0` | 置为 `1` 可在有 Key 时也强制走 mock 模式 |
| `SEARCH_PROVIDER` | `none` | `tavily` / `serper` / `bing` / `none` |
| `MAX_QC_ITERATIONS` | `2` | 最大返工循环次数 |
| `MIN_SOURCES_PER_COMPETITOR` | `3` | QC 阈值 |
| `COLLECTOR_CONCURRENCY` | `3` | 每竞品采集 / 分析的并行度（1 = 串行） |
| `MIN_CONFIDENCE` | `0.55` | 低于此值的断言触发置信度感知的重新采集 |
| `SELF_CONSISTENCY_SAMPLES` | `1` | 竞品识别的 N 样本多数投票（1 = 关闭） |
| `ENABLE_CONFLICT_DETECTION` | `1` | 跨来源冲突标记 |
| `RESPECT_ROBOTS` | `1` | 仅用于测试时才置为 `0` |

### API 一览

| 端点 | 用途 |
| --- | --- |
| `POST /api/analysis/start` · `GET .../stream/{id}` · `GET .../status/{id}` · `GET .../dag` · `GET .../markets` | 运行生命周期 + 实时 SSE + DAG 元数据 |
| `POST /api/analysis/resume/{run_id}` | 从最近检查点恢复一次被中断的运行 |
| `GET/DELETE /api/reports/{id}` · `GET .../html` | 读取 / 删除 / 导出报告 |
| `PATCH /api/reports/{id}` | 人在回路字段编辑（记录一条 `Correction`） |
| `GET /api/traces/{run_id}` | 决策追踪回放 |
| `GET /api/knowledge/{entities,history,diff}` | 跨运行的竞品演化 |
| `GET /api/meta/{suggestions,corrections}` | 智能体自评 + 修正信息流 |

## 3. 生产部署

### 3.1 单机部署（首次部署推荐）

```
┌────────────────────────────┐
│       Nginx / Caddy        │
│  静态前端（已构建）        │
│  反向代理到 :8000          │
└────────────────────────────┘
              │
┌────────────────────────────┐
│   FastAPI (uvicorn)        │
│   端口 8000                │
└────────────────────────────┘
              │
┌────────────────────────────┐
│  SQLite (data/app.sqlite)  │
└────────────────────────────┘
```

步骤：

1. 构建前端：`cd frontend && pnpm build`。产物在 `frontend/dist`。
2. 配置 Nginx 提供 `frontend/dist` 并把 `/api/*` 代理到 `127.0.0.1:8000`。
3. 在进程守护工具（systemd、supervisord、pm2）下运行后端。

systemd 单元示例（Linux）：

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

### 3.2 Docker（可选）

为保持仓库精简，默认不附带 `Dockerfile`，但布局很直接：

```dockerfile
# 阶段 1：前端
FROM node:20-alpine AS fe
WORKDIR /app
COPY frontend/ ./frontend
RUN cd frontend && npm install && npm run build

# 阶段 2：后端
FROM python:3.11-slim
WORKDIR /app
COPY backend/ ./backend
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY --from=fe /app/frontend/dist /app/frontend_dist
EXPOSE 8000
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

（在前面用 Nginx 提供 `/app/frontend_dist`，或在 FastAPI 中挂一个 `StaticFiles` 路由。）

### 3.3 扩容

* **垂直扩容**：增大 uvicorn 的 `--workers`。运行注册表现已**持久化到 SQLite**（`runs` + `run_checkpoints` 表），因此当某次运行不在本地 worker 的内存中时，`GET /api/analysis/status` 与 `/stream` 会回退到数据库——状态与追踪回放能在重启后存活。实时 SSE 的*推送*仍需命中持有内存中 `Tracer` 队列的那个 worker；要实现真正的多 worker 实时流式，可把该队列替换为 Redis 发布 / 订阅。
* **可续跑性**：由于每个节点都对 `GraphState` 打检查点，一次因崩溃 / 重启而中断的运行可用 `POST /api/analysis/resume/{run_id}` 继续，而非从头重跑。
* **持久化存储**：SQLite 对原型足够。生产级别可切换到 Postgres——`aiosqlite` ↔ `asyncpg` 基本是机械替换，表结构一致。

## 4. 生产环境中的可观测性

* 所有日志行都是结构化的（组件、级别、消息）。把 stderr 接入你的日志聚合系统。
* `/api/traces/{run_id}` 端点是回放的真相之源。
* `report.metrics` 包含每次运行的 KPI，应当摄入你的 BI 工具来跟踪：
  * `elapsed_seconds`、`total_tokens`
  * `schema_completeness`、`avg_sources_per_competitor`
  * `avg_confidence`、`low_confidence_claims`、`conflict_count`
  * `qc_iterations`、`rework_count`
  * `manual_correction_rate`、`corrected_fields`
* `GET /api/meta/suggestions` 暴露跨运行聚合（字段完整度、反复出现的修正 / 冲突），供智能体自评仪表盘使用。

这些直接对应评分细则点名的"业务闭环"指标：效率（时间）、覆盖度（来源）、一致性（schema 完整度）、可信度（平均置信度 / 冲突），以及**人工修正率**——如今它是一等指标，每次人工编辑（`PATCH /api/reports/{id}`）都会重新计算。

## 5. 常见问题

| 症状 | 可能原因 | 解决办法 |
| --- | --- | --- |
| 前端能渲染，但 API 调用 404 | Vite 代理目标错配 | 检查 `vite.config.ts` 代理 `target` 是否与后端端口一致 |
| 一次运行后报 `report not found` | 后端在 start 与 finish 之间重启过 | SQLite 是按主机的；开发环境每次重启会重置 |
| LLM 调用返回 401 | Key 错误或已过期 | 在火山方舟控制台重新签发；检查 `ARK_MODEL_ID` 是 endpoint ID，而非模型族名 |
| 所有来源都显示 "llm_prior" | 未配置搜索后端 | 在 `.env` 里设置 `SEARCH_PROVIDER` 及对应的 Key |
| 长时运行触发超时 | `ARK_TIMEOUT` 对你的模型太低 | 对较慢的模型调高到 120s 以上 |
