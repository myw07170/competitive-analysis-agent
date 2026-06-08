"""Agent self-evaluation & dynamic schema evolution (Innovation-4).

The :class:`MetaEvaluator` looks across *all* historical reports — not a single
run — and asks: which schema fields are consistently empty? which fields do
humans keep correcting? where do sources keep disagreeing? From those aggregate
signals it emits :class:`SchemaSuggestion` records proposing concrete changes
(deprecate a dead field, tighten a prompt, split an overloaded field).

It does not mutate the schema automatically — the suggestions are surfaced in
the UI for a human to accept — but ``schema_version`` is already persisted with
every report, so accepted changes can roll forward without invalidating history.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Callable, Dict, List

from .schema.competitor import CompetitorKnowledge
from .schema.report import SchemaSuggestion
from .storage import get_store

# Field -> predicate "is this field populated for this competitor?"
_FIELDS: Dict[str, Callable[[CompetitorKnowledge], bool]] = {
    "homepage": lambda c: bool(c.homepage),
    "short_description": lambda c: bool(c.short_description),
    "market_position": lambda c: bool(c.market_position),
    "function_tree.nodes": lambda c: bool(c.function_tree.nodes),
    "pricing.tiers": lambda c: bool(c.pricing.tiers),
    "pricing.addons": lambda c: bool(c.pricing.addons),
    "user_profile.segments": lambda c: bool(c.user_profile.segments),
    "user_profile.nps_or_rating": lambda c: bool(c.user_profile.nps_or_rating),
    "user_profile.estimated_user_base": lambda c: bool(c.user_profile.estimated_user_base),
    "swot": lambda c: c.swot is not None,
}

_LOW = 0.2     # below this completeness → candidate for deprecate/make_optional
_DEAD = 0.05   # essentially never populated → deprecate
_CORRECTION_HOT = 3   # a path corrected at least this many times → tighten prompt


class MetaEvaluator:
    async def evaluate(self, *, limit: int = 200) -> Dict[str, Any]:
        store = get_store()
        await store.init()
        reports = await store.get_recent_reports(limit=limit)
        corrections = await store.list_corrections(limit=500)

        competitors: List[CompetitorKnowledge] = []
        for r in reports:
            competitors.extend(r.competitors)
            if r.target_product is not None:
                competitors.append(r.target_product)

        n = len(competitors)
        completeness: Dict[str, float] = {}
        if n:
            for field, pred in _FIELDS.items():
                hits = sum(1 for c in competitors if pred(c))
                completeness[field] = round(hits / n, 3)

        # Correction hot-spots: normalize the indexed path (drop array indices).
        def _norm(path: str) -> str:
            import re
            return re.sub(r"\[[^\]]*\]", "[]", path or "")

        corr_counter: Counter = Counter(_norm(c.target_path) for c in corrections)
        # Conflict hot-spots across all competitors.
        conflict_counter: Counter = Counter()
        for c in competitors:
            for cf in c.conflicts:
                conflict_counter[_norm(cf.field)] += 1

        suggestions: List[SchemaSuggestion] = []

        # 1) Dead / sparse fields → deprecate or make optional.
        for field, frac in completeness.items():
            if n < 3:
                continue  # not enough data to judge
            if frac <= _DEAD:
                suggestions.append(SchemaSuggestion(
                    field=field, action="deprecate",
                    rationale=f"Populated in only {frac:.0%} of {n} competitors — effectively dead.",
                    evidence={"completeness": frac, "n": n}, confidence=0.7,
                ))
            elif frac <= _LOW:
                suggestions.append(SchemaSuggestion(
                    field=field, action="make_optional",
                    rationale=f"Populated in only {frac:.0%} of {n} competitors — rarely available.",
                    evidence={"completeness": frac, "n": n}, confidence=0.55,
                ))

        # 2) Frequently-corrected paths → tighten the producing prompt.
        for path, count in corr_counter.most_common(8):
            if count >= _CORRECTION_HOT:
                suggestions.append(SchemaSuggestion(
                    field=path, action="tighten_prompt",
                    rationale=f"Humans corrected this field {count} times — the prompt under-specifies it.",
                    evidence={"corrections": float(count)}, confidence=0.6,
                ))

        # 3) Frequent source conflicts → add an explicit reconciliation field / prompt.
        for path, count in conflict_counter.most_common(5):
            if count >= 2:
                suggestions.append(SchemaSuggestion(
                    field=path, action="tighten_prompt",
                    rationale=f"Sources disagreed on this field {count} times — require a primary source.",
                    evidence={"conflicts": float(count)}, confidence=0.55,
                ))

        return {
            "n_reports": len(reports),
            "n_competitors": n,
            "field_completeness": completeness,
            "top_correction_paths": [{"path": p, "count": c} for p, c in corr_counter.most_common(8)],
            "top_conflict_paths": [{"path": p, "count": c} for p, c in conflict_counter.most_common(5)],
            "suggestions": [s.model_dump(mode="json") for s in suggestions],
        }
