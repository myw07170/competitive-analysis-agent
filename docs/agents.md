# Agents and Message Protocol

This document specifies the role, inputs, outputs, and message protocol of each of the four agents.

## 1. Agent roster

| Agent | File | Role | Reads from | Writes to |
| --- | --- | --- | --- | --- |
| Collector | [`backend/app/agents/collector.py`](../backend/app/agents/collector.py) | Identify competitors and gather structured knowledge per competitor | User request, web search, robots-compliant fetcher, LLM | `GraphState.competitor_names`, `GraphState.competitors` |
| Analyst | [`backend/app/agents/analyst.py`](../backend/app/agents/analyst.py) | Produce SWOT for each competitor | `GraphState.competitors` | `competitor.swot` |
| Writer | [`backend/app/agents/writer.py`](../backend/app/agents/writer.py) | Synthesize the final report | `GraphState.competitors` (with SWOT) | `GraphState.report` |
| Quality control | [`backend/app/agents/qc.py`](../backend/app/agents/qc.py) | Critique structure / coverage / hallucinations | `GraphState.competitors` | `GraphState.qc_history`, `GraphState.last_qc` |

These responsibilities are **non-overlapping**:

* Only the Collector talks to external sources.
* Only the Analyst writes SWOT.
* Only the Writer produces the final report's prose.
* Only the QC agent makes the "rework or approve" decision.

## 2. Message protocol

Inter-agent communication is mediated by `GraphState` — never direct imports — but every payload is typed. Specifically:

```python
class AgentMessage(BaseModel):
    id: str
    sender: AgentRole
    receiver: AgentRole
    intent: str              # function name being invoked
    payload: Dict[str, Any]  # validated against the receiver's schema
    correlation_id: str | None
    created_at: datetime
```

For the QC ↔ Collector feedback loop, the QC payload is a `QCReport` containing a list of `QCFinding`s. Each finding carries `target_agent`, `target_path` (JSONPath-ish), `severity`, `issue`, and `suggested_fix`. The orchestrator translates the report into a `rework_notes` string that the Collector receives as part of its next prompt.

Schemas live in [`backend/app/schema/messages.py`](../backend/app/schema/messages.py).

## 3. Collector agent

### Inputs
* `product: str` — the target product
* `market: MarketProfile` — drives language, currency, source allowlist, search queries
* `iteration: int` — increments on each rework
* `rework_notes: str | None` — concatenated QC findings from the previous QC pass

### Steps
1. **Identify competitors** (`intent="collector.identify_competitors"`) — top-3 list.
2. **Gather competitor** (`intent="collector.gather_competitor"` or `"collector.rework"`) — for each competitor:
   1. Run market-tuned search queries via the configured backend.
   2. Fetch the top 2 hits with the robots-compliant fetcher.
   3. Inject the resulting evidence block into the LLM prompt.
   4. Receive a JSON `CompetitorKnowledge`. Validate. Raise on failure.

### Outputs
`List[CompetitorKnowledge]` — schema-conformant, with every fact source-tagged.

### Self-validation safeguards
* Pydantic strict validation rejects partially-formed competitor objects, preventing downstream crashes.
* When mock mode is on, the rework intent (`collector.rework`) returns a *richer* mock payload (extra pricing sources) so the loop visibly improves the output.

## 4. Analyst agent

### Inputs
* `product: str`
* `competitor: CompetitorKnowledge`

### Steps
1. Serialize the competitor to JSON, truncate to 6 KB, include in prompt.
2. Ask for `SWOTAnalysis` — 2–5 entries per bucket, each backed by `SourceRef`s.
3. Validate via Pydantic.

### Outputs
`SWOTAnalysis` attached to `competitor.swot`.

### Self-validation safeguards
* The system prompt forbids new facts; only sources already in the competitor blob may be cited.
* If the analyst must infer, it must mark the source with `kind="llm_prior"` and `confidence<=0.6`.

## 5. Writer agent

### Inputs
* `product: str`
* `report_id: str`
* `competitors: List[CompetitorKnowledge]` (with SWOT attached)

### Steps
1. Build a locale-aware prompt with the localized section headings.
2. Truncate the competitor JSON to 12 KB before injection.
3. Ask for the report JSON (`title`, `executive_summary_md`, `sections`).
4. Flatten all sources across the competitor blobs into `FinalReport.all_sources`.

### Outputs
`FinalReport` — the canonical artifact returned to the frontend.

## 6. QC agent

The QC agent combines **deterministic** checks (Python) with an **LLM critique** pass, then merges them.

### Deterministic checks (Python)
* Source count per competitor ≥ `MIN_SOURCES_PER_COMPETITOR`.
* Function tree is non-empty.
* Each pricing tier has at least one source.
* No placeholder/local-host URLs in sources.
* User profile has at least one segment.

### LLM critique
* Same checks framed as soft critique.
* Asked to detect language mismatches, prose inconsistencies, and obvious schema-shape errors not caught above.

### Output
`QCReport` with one of three decisions:
* `approve` — no findings; or only `info`-level.
* `approve_with_notes` — minor findings only; ship the report.
* `rework` — at least one blocker, or > 1 major. Routes back to `collect`.

### Loop bound
The orchestrator caps iterations at `MAX_QC_ITERATIONS` (default 2). After that, the run finishes regardless of QC's verdict — the report ships with the final QC notes attached.

## 7. Prompts

System prompts are externalized for auditability:

* [`backend/app/prompts/collector.py`](../backend/app/prompts/collector.py)
* [`backend/app/prompts/analyst.py`](../backend/app/prompts/analyst.py)
* [`backend/app/prompts/writer.py`](../backend/app/prompts/writer.py)
* [`backend/app/prompts/qc.py`](../backend/app/prompts/qc.py)

Each prompt:
* Begins with the agent's role definition (boundary enforcement).
* Lists explicit hard rules (no placeholder URLs, no fabricated facts, etc).
* Declares the output JSON shape inline so the model has the schema in the same turn.
* Pins the **response language** via `{language}` — driven by the active `MarketProfile`.
