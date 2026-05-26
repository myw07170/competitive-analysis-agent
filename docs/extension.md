# Extension Guide

This document shows exactly what changes when you extend the system. Three common extensions are worked out in detail:

1. Adding a new market (e.g. Japan)
2. Adding a new agent role (e.g. a fact-checker)
3. Adding a new schema field (e.g. a "go-to-market motion" pillar)

## 1. Adding a new market

The market layer is the cleanest extension point. Three small files, no changes to the agents or orchestrator.

### Step 1 — Add a `MarketProfile`

Create `backend/app/market/jp.py`:

```python
from dataclasses import dataclass, field
from typing import List
from .base import MarketProfile


def _default_seeds() -> List[str]:
    return [
        "{product} 競合",
        "{product} 比較",
        "{product} 価格",
        "{product} レビュー",
        "{product} 機能",
    ]


@dataclass
class JapanMarket(MarketProfile):
    code: str = "jp"
    display_name: str = "Japan"
    locale: str = "ja-JP"
    language: str = "ja"
    currency: str = "JPY"
    flag: str = "🇯🇵"
    search_seeds: List[str] = field(default_factory=_default_seeds)
    preferred_search_provider: str = "bing"
    allowed_source_domains: List[str] = field(default_factory=lambda: [
        "note.com", "qiita.com", "itreview.jp", "boxil.jp",
    ])
```

### Step 2 — Register it

In `backend/app/market/__init__.py`:

```python
from .jp import JapanMarket

REGISTRY: Dict[str, MarketProfile] = {
    "cn": ChinaMarket(),
    "us": USMarket(),
    "jp": JapanMarket(),     # ← add
}
```

### Step 3 — Add a server-side locale bundle

In `backend/app/i18n/locales.py`, add a `"ja-JP"` block mirroring the keys in `"zh-CN"` / `"en-US"`. Keep the keys identical — section labels and prompt strings will pick up the new locale automatically.

### Step 4 — Add a frontend locale bundle

Create `frontend/src/i18n/ja.ts` mirroring `zh.ts` / `en.ts`. Register it in `frontend/src/i18n/index.ts`:

```ts
import { ja } from "./ja";

const BUNDLES: Record<Locale, Record<string, string>> = {
  "zh-CN": zh, "en-US": en, "ja-JP": ja,   // ← add
};

export function marketToLocale(market: string): Locale {
  if (market === "cn") return "zh-CN";
  if (market === "us") return "en-US";
  if (market === "jp") return "ja-JP";     // ← add
  return "en-US";
}
```

Also extend the `Locale` type union to include `"ja-JP"`.

### Step 5 — Update the language-name map (optional)

In `backend/app/agents/base.py`, add the Japanese display name so the system prompt phrases the language constraint nicely:

```python
return {"zh": "Simplified Chinese (简体中文)", "en": "English",
        "ja": "Japanese (日本語)"}.get(self.market.language, self.market.language)
```

### That's it

The DAG, the agents, the schema, the frontend components — none of these touch the market code. They read from the active `MarketProfile`. The `/api/analysis/markets` endpoint will now list Japan and the form will render the new chip with its flag.

## 2. Adding a new agent role

Suppose you want a **Fact-Checker** agent that runs between Writer and QC, picking out claims from the report draft and cross-checking them against sources.

### Step 1 — Implement the agent

Create `backend/app/agents/fact_checker.py`:

```python
from .base import BaseAgent

class FactCheckerAgent(BaseAgent):
    role = "fact_checker"

    async def check(self, *, report: FinalReport) -> List[FactCheckIssue]:
        ...
```

Add to `backend/app/agents/__init__.py`.

### Step 2 — Add a DAG node

In `backend/app/orchestration/state.py`:

```python
DagNode("fact_check", "事实核查", "Fact check", "fact_checker",
        "校验报告中的事实是否与来源一致。", "Verify each claim against its source."),
```

And an edge: `DagEdge("write", "fact_check")`, then `DagEdge("fact_check", "qc")`. Remove the old `("write", "qc")` edge.

### Step 3 — Wire it into the graph

In `backend/app/orchestration/graph.py`, inside `_make_nodes`:

```python
fact_checker = FactCheckerAgent(market)

async def n_fact_check(state: GraphState) -> GraphState:
    report = FinalReport.model_validate(state["report"])
    issues = await fact_checker.check(report=report)
    return {**state, "fact_check_issues": [i.model_dump() for i in issues]}
```

And in `build_graph`:

```python
g.add_node("fact_check", n_fact_check)
g.add_edge("write", "fact_check")
g.add_edge("fact_check", "qc")
```

### Step 4 — Frontend changes

None required for the DAG — it reads its definition from `/api/analysis/dag`, which now includes the new node. The `TraceList` already groups by `agent`, so the new agent's events will appear with their own pill color (add a row in `AGENT_COLOR` in `TraceList.tsx` if you want a custom color).

## 3. Adding a new schema field

The schema is intentionally permissive — adding **optional** fields is non-breaking.

Example: add a `gtm_motion` field describing each competitor's go-to-market motion (`"plg"`, `"sales_led"`, `"hybrid"`).

### Step 1 — Add to the schema

In `backend/app/schema/competitor.py`:

```python
class GTMMotion(BaseModel):
    primary: Optional[Literal["plg", "sales_led", "hybrid"]] = None
    notes: str = ""
    sources: List[SourceRef] = Field(default_factory=list)

class CompetitorKnowledge(BaseModel):
    ...
    gtm_motion: Optional[GTMMotion] = None
```

### Step 2 — Bump schema version

Set `schema_version: str = "1.1.0"`.

### Step 3 — Update Collector prompt

In `backend/app/prompts/collector.py`, add a bullet to the schema-reminder list. The model will start producing the new field automatically.

### Step 4 — Update QC checks (optional)

If you want QC to enforce non-null `gtm_motion`, add a deterministic check in `backend/app/agents/qc.py`. Otherwise the field stays advisory.

### Step 5 — Update frontend rendering (optional)

Add a card in `frontend/src/pages/Report.tsx` under the competitors tab. The renderer already handles missing fields gracefully.

### Backwards compatibility

Older reports (schema 1.0.0) don't have the new field. Because it's `Optional`, Pydantic loads them without complaint. No migration script is needed for additive changes.

## 4. Adding a new data source

Suppose you want to add a "G2 reviews" connector that the Collector calls in addition to general web search.

### Step 1 — Add the connector

Create `backend/app/collectors/g2.py` with an `async def fetch_g2(product: str) -> List[Cited]` function.

### Step 2 — Plumb into the Collector

In `backend/app/agents/collector.py`, modify `_build_evidence` to call `fetch_g2(competitor_name)` when the active market's `allowed_source_domains` includes `"g2.com"`.

### Step 3 — Done

No schema change — the resulting facts use the existing `SourceRef` with `kind="web"` and the actual G2 URL.

---

The whole point of the layout is that **agents are stateless workers**, **markets are configuration**, and **schemas are the contract**. Adding capabilities means touching the right axis — almost never the orchestrator.
