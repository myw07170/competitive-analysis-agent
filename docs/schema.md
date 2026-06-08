# Competitor Knowledge Schema

The canonical schema is defined in [`backend/app/schema/competitor.py`](../backend/app/schema/competitor.py). Every agent input and output is validated against it.

## 1. `CompetitorKnowledge`

```python
class CompetitorKnowledge(BaseModel):
    name: str
    aliases: List[str]
    homepage: Optional[str]
    short_description: str
    market_position: Optional[str]

    function_tree: FunctionTree            # Pillar 1
    pricing: PricingModel                  # Pillar 2
    user_profile: UserProfile              # Pillar 3
    swot: Optional[SWOTAnalysis]           # Added by Analyst

    sources: List[SourceRef]               # Top-level provenance
    conflicts: List[ConflictFlag]          # Cross-source disagreements (see §9)
    schema_version: str = "1.1.0"
```

Confidence helpers:
* `avg_confidence()` — mean confidence across every `SourceRef` on the competitor (drives the `avg_confidence` metric).
* `low_confidence_claims(threshold)` — dotted paths of structured claims whose best source is below `threshold` (drives confidence-aware rework).

## 2. Pillar 1 — `FunctionTree`

Hierarchical capability map.

```python
class FunctionNode:
    name: str
    description: str
    category: Optional[str]
    maturity: Optional[Literal["ga", "beta", "preview", "rumored"]]
    sources: List[SourceRef]
    children: List[FunctionNode]   # recursive

class FunctionTree:
    root_name: str
    nodes: List[FunctionNode]
```

Design notes:
* Self-referential — allows arbitrary depth without schema changes.
* Every node carries its own `sources` so a leaf can be traced independently.

## 3. Pillar 2 — `PricingModel`

```python
class PricingTier:
    name: str
    monthly_price: Optional[float]
    annual_price: Optional[float]
    currency: str               # "USD", "CNY", ...
    seat_based: bool
    included_features: List[str]
    limits: dict                # {"storage_gb": 100, "seats": 10}
    sources: List[SourceRef]

class PricingModel:
    summary: str
    tiers: List[PricingTier]
    addons: List[PricingTier]
    has_free_tier: bool
    has_enterprise: bool
    notes: str
    sources: List[SourceRef]
```

Design notes:
* `monthly_price` and `annual_price` are both optional — some tiers are quote-only.
* `currency` is required (per the rubric on consistency).
* `limits` is a free dict so different verticals can express their constraints idiomatically.

## 4. Pillar 3 — `UserProfile`

```python
class UserSegment:
    name: str
    description: str
    company_size: Optional[Literal["smb", "mid_market", "enterprise", "individual", "mixed"]]
    industries: List[str]
    geographies: List[str]
    use_cases: List[str]
    pain_points: List[str]
    representative_quotes: List[Cited]
    sources: List[SourceRef]

class UserProfile:
    primary_segment: Optional[str]
    segments: List[UserSegment]
    estimated_user_base: Optional[str]
    nps_or_rating: Optional[str]
    sources: List[SourceRef]
```

`representative_quotes` are `Cited` values — each quote is bound to its source(s). This is what enables the UI to render a click-through from a quote back to the interview record that produced it.

## 5. `SourceRef` — the traceability primitive

```python
class SourceRef:
    id: str = "src_xxx"
    kind: Literal["web", "doc", "interview", "questionnaire", "llm_prior"]
    title: str
    url: Optional[str]
    snippet: str           # verbatim excerpt
    retrieved_at: datetime
    confidence: float      # 0..1
```

Rules:
* Every fact in a `CompetitorKnowledge` instance MUST be attached to at least one `SourceRef`.
* When the LLM infers a fact without external evidence, the source must declare `kind="llm_prior"` and `confidence <= 0.6`.
* `confidence >= 0.9` is reserved for verbatim citations from an actually-fetched page.

## 6. Cited<T>

```python
class Cited:
    value: str
    sources: List[SourceRef]
```

Used inside SWOT entries and representative quotes — anywhere a single fact needs its own provenance distinct from a parent's.

## 7. Versioning

`CompetitorKnowledge.schema_version` is persisted with every saved report. Current version is **`1.1.0`** (added `conflicts`, confidence helpers, and the report-level credibility/correction metrics). Future schema bumps:

| Bump type | Example | What happens |
| --- | --- | --- |
| Patch | "1.1.0" → "1.1.1" | Add an optional field. Old reports remain valid. |
| Minor | "1.1.0" → "1.2.0" | Add a field with a default. Old reports auto-migrate (Pydantic defaults). |
| Major | "1.1.0" → "2.0.0" | Breaking. Bundled with a one-shot migration script in `backend/app/scripts/`. |

The [`MetaEvaluator`](../backend/app/meta.py) proposes data-driven `SchemaSuggestion`s (deprecate / make-optional / tighten-prompt) from historical field completeness — the input to deciding the next bump.

## 8. Why "function tree + pricing + user profile"?

These three pillars match how product managers actually structure competitive analysis in practice:

* **Function tree** answers *"what can it do?"* — comparable across markets.
* **Pricing model** answers *"who can afford it?"* — drives positioning.
* **User profile** answers *"who already uses it?"* — drives go-to-market strategy.

SWOT, recommendations, and market overview are *derived* from these — see the Writer agent's prompt.

## 9. Credibility & feedback models (v1.1)

Defined in [`schema/competitor.py`](../backend/app/schema/competitor.py) and [`schema/report.py`](../backend/app/schema/report.py).

```python
class ConflictFlag:               # cross-source disagreement (Innovation-2)
    field: str                    # e.g. "pricing.tiers[Pro].monthly_price"
    kind: str                     # value_mismatch | duplicate | unsupported | range
    detail: str
    values: List[str]             # the disagreeing values
    source_ids: List[str]
    severity: str                 # major | minor | info

class Correction:                 # human-in-the-loop edit (Innovation-5)
    id: str
    report_id: str
    market: str
    target_path: str              # dotted path that was edited
    before: str
    after: str
    note: str
    author: str
    created_at: datetime

class SchemaSuggestion:           # agent self-evaluation (Innovation-4)
    field: str
    action: str                   # deprecate | make_optional | tighten_prompt | add_field | split_field
    rationale: str
    evidence: Dict[str, float]
    confidence: float

class KnowledgeDiff:              # cross-run evolution (Innovation-3)
    entity_key: str
    name: str
    market: str
    changes: List[KnowledgeChange]  # path / change(added|removed|changed) / before / after
    summary: str
```

### `ReportMetrics` (extended)

Beyond the original time/token/completeness fields, v1.1 adds:

| Field | Meaning |
| --- | --- |
| `avg_confidence` | Mean source confidence across everything shipped. |
| `low_confidence_claims` | Count of claims below `MIN_CONFIDENCE`. |
| `conflict_count` | Cross-source disagreements detected. |
| `manual_correction_rate` | Fraction of structured claims a human edited — the KPI the team drives down. |
| `corrected_fields` | Absolute count of human edits applied. |
