"""Cross-run competitor knowledge evolution (Innovation-3).

Each run stores a snapshot of every competitor keyed by a normalized entity key
(see ``app.storage.store.normalize_entity_key``). ``compute_diff`` lines up the
two most recent snapshots and produces a field-level :class:`KnowledgeDiff` —
"what changed since we last looked at this competitor": new/removed capabilities,
pricing moves, segment shifts, positioning changes.

This is deliberately a deterministic structural diff (no embeddings) so it is
explainable and cheap; entity resolution is the normalized-key step upstream.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .schema.competitor import CompetitorKnowledge
from .schema.report import KnowledgeChange, KnowledgeDiff


def _top_capabilities(c: CompetitorKnowledge) -> Dict[str, str]:
    return {(n.name or "").strip(): (n.maturity or "") for n in c.function_tree.nodes if n.name}


def _tiers(c: CompetitorKnowledge) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for t in c.pricing.tiers:
        key = (t.name or "").strip()
        if not key:
            continue
        if t.monthly_price is not None:
            out[key] = f"{t.monthly_price:g} {t.currency}/mo"
        else:
            out[key] = "custom"
    return out


def _segments(c: CompetitorKnowledge) -> Dict[str, str]:
    return {(s.name or "").strip(): (s.company_size or "") for s in c.user_profile.segments if s.name}


def _diff_maps(prefix: str, before: Dict[str, str], after: Dict[str, str]) -> List[KnowledgeChange]:
    changes: List[KnowledgeChange] = []
    for k, v in after.items():
        if k not in before:
            changes.append(KnowledgeChange(path=f"{prefix}.{k}", change="added", after=v or k))
        elif before[k] != v:
            changes.append(KnowledgeChange(path=f"{prefix}.{k}", change="changed",
                                           before=before[k], after=v))
    for k, v in before.items():
        if k not in after:
            changes.append(KnowledgeChange(path=f"{prefix}.{k}", change="removed", before=v or k))
    return changes


def _diff_scalar(path: str, before: Optional[str], after: Optional[str]) -> List[KnowledgeChange]:
    b = (before or "").strip()
    a = (after or "").strip()
    if b != a and (b or a):
        return [KnowledgeChange(path=path, change="changed", before=b or None, after=a or None)]
    return []


def compute_diff(
    *, entity_key: str, name: str, market: str,
    latest: Dict[str, Any], previous: Optional[Dict[str, Any]],
) -> KnowledgeDiff:
    """Build a KnowledgeDiff from two snapshot rows (each ``{run_id, captured_at, payload}``)."""
    cur = CompetitorKnowledge.model_validate(latest["payload"])
    diff = KnowledgeDiff(
        entity_key=entity_key, name=name, market=market,
        to_run_id=latest.get("run_id", ""), to_captured_at=latest.get("captured_at"),
    )
    if previous is None:
        diff.summary = "first_snapshot"
        return diff

    prev = CompetitorKnowledge.model_validate(previous["payload"])
    diff.from_run_id = previous.get("run_id", "")
    diff.from_captured_at = previous.get("captured_at")

    changes: List[KnowledgeChange] = []
    changes += _diff_maps("function", _top_capabilities(prev), _top_capabilities(cur))
    changes += _diff_maps("pricing", _tiers(prev), _tiers(cur))
    changes += _diff_maps("segment", _segments(prev), _segments(cur))
    changes += _diff_scalar("market_position", prev.market_position, cur.market_position)
    changes += _diff_scalar("user_profile.nps_or_rating",
                            prev.user_profile.nps_or_rating, cur.user_profile.nps_or_rating)

    diff.changes = changes
    added = sum(1 for c in changes if c.change == "added")
    removed = sum(1 for c in changes if c.change == "removed")
    changed = sum(1 for c in changes if c.change == "changed")
    diff.summary = (
        "no_change" if not changes
        else f"{added} added · {removed} removed · {changed} changed"
    )
    return diff
