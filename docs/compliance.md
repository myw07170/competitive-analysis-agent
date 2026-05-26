# Compliance Notes

This document covers the project's posture on robots.txt, ToS, data privacy, LLM usage, and the rubric's compliance scoring item.

## 1. Web crawling

### robots.txt enforcement

* Implemented in [`backend/app/collectors/robots.py`](../backend/app/collectors/robots.py).
* The crawler uses Python's stdlib `urllib.robotparser` with an async cache.
* On every fetch, `can_fetch(url)` is called with our `USER_AGENT` (default `"CompetitiveAnalysisAgent/1.0 (+https://example.com/contact)"`).
* If the host disallows our UA on a path, the crawler returns a `FetchedPage(blocked_by_robots=True)` — never the page content.
* `RESPECT_ROBOTS` defaults to `1`. Set to `0` *only* in controlled test environments.

### Rate limiting

* Per-host rate limit defaults to `1 request / second / host` via `CRAWL_RATE_LIMIT_PER_HOST`.
* Implemented as an asyncio lock per host plus monotonic-clock pacing in [`backend/app/collectors/web.py`](../backend/app/collectors/web.py).

### User-Agent

* The `USER_AGENT` env var sets the string sent on every fetch and every robots.txt request.
* The default contains a contact URL placeholder. **Replace this placeholder with a real contact URL before any production deployment.**

### Domain allowlists

Each market profile carries an `allowed_source_domains` list. Future versions can hard-restrict the collector to that list. Today the list is informational and used by the search query tuner.

## 2. Search-provider ToS

The pluggable search backend (`SEARCH_PROVIDER`) supports Tavily, Serper, and Bing. Each is called via its official API, with the API key supplied by the operator. **No scraping of search engine result pages is done** — only sanctioned APIs.

## 3. LLM usage

### Provider

Volcengine Ark (Huoshan Engine / 火山方舟). The operator supplies:

* `ARK_API_KEY` — issued from the Volcengine console.
* `ARK_MODEL_ID` — the endpoint ID for the chosen model (e.g. Doubao or a custom-deployed model).
* `ARK_BASE_URL` — defaults to `https://ark.cn-beijing.volces.com/api/v3`, override if your deployment uses a different region.

### Mock mode

When no key is configured (or `VOLC_MOCK=1`), the LLM client returns built-in canned outputs. **The mock outputs are clearly labeled** in the UI (a yellow "mock mode" banner) and in the trace records (`extras.mocked = true`). This prevents demo artifacts from being mistaken for real model output.

### Data sent to the LLM

* Agent prompts (system + user).
* Snippets fetched from public web pages (subject to robots).
* User input (product name + market + optional extra competitors).

The system does NOT send:
* User identity / authentication tokens (there is no per-user account today).
* Anything outside the agent prompts.

If you import private documents in a future version, they MUST flow through a PII-redaction pass first (see §4).

## 4. PII handling

### Synthesized interviews and questionnaires

The Collector agent can produce "synthesized" interview snippets and questionnaire summaries. These are tagged with `kind="interview"` or `kind="questionnaire"` and a low confidence (≤ 0.6). The system prompt instructs the model to make these clearly fictional ("Synthetic interview #1", etc.) — they should never be presented as real user statements.

### Importing real interview / questionnaire data (v1.1, planned)

The schema already supports `kind="interview"` and `kind="questionnaire"` for real data. When the import endpoint is added in v1.1, it MUST:

1. Strip standard PII (email, phone, government IDs) via a regex + named-entity pass.
2. Replace personal names with role labels (`"Persona A"`, `"PM at midmarket fintech"`).
3. Hash the source row ID — never store the raw identifier.
4. Surface a confirmation dialog to the operator before the data hits the store.

### Data retention

* The SQLite store keeps reports and traces indefinitely by default. Operators should add a retention job (cron + `DELETE FROM ... WHERE generated_at < ?`) appropriate to their jurisdiction.
* Traces include the full prompts and responses, which may contain quoted excerpts from public pages. Treat the store as containing third-party content and apply your normal IP / retention policy.

## 5. Compliance with the challenge competition's "Tool and Resource Usage Guidelines"

* All third-party libraries are open source (MIT / BSD / Apache 2.0). See [`backend/requirements.txt`](../backend/requirements.txt) and [`frontend/package.json`](../frontend/package.json).
* The sole closed-source dependency is the Volcengine Ark API, which is the LLM provider mandated by the challenge.
* No proprietary datasets are bundled; mock data is synthesized by the project's authors and is clearly fictional.
* AI programming assistance (TRAE / Claude / similar) was used during development; the use is acknowledged in the repository and the commit log.

## 6. Submission bundle

The complete submission set includes:

* **Proposal document** — `docs/architecture.md`, `docs/agents.md`, `docs/schema.md`.
* **Code repository** — this directory.
* **Demonstration video script** — `docs/demo-script.md`.
* **README and run instructions** — top-level `README.md` and `docs/deployment.md`.
* **Compliance statement** — this file.

## 7. Operator checklist

Before pointing this system at production traffic:

- [ ] Replace the placeholder contact URL in `USER_AGENT` with a real one.
- [ ] Set `ARK_API_KEY`, `ARK_MODEL_ID`, and choose a region in `ARK_BASE_URL`.
- [ ] Choose a search provider and set its key.
- [ ] Decide whether to keep `RESPECT_ROBOTS=1` (yes) and `CRAWL_RATE_LIMIT_PER_HOST` (≥ 1.0).
- [ ] Add a retention job on the SQLite store.
- [ ] Lock down the `/api/analysis/start` endpoint behind authentication if exposed publicly.
- [ ] Consider whether `CORSMiddleware` should be restricted from `"*"` to your frontend origin only.
