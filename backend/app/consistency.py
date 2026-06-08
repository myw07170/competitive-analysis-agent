"""Deterministic self-consistency & cross-source conflict detection.

Two responsibilities, both deliberately deterministic (no extra LLM calls) so
they are cheap, reproducible, and demonstrable:

1. ``detect_conflicts`` — inspect one ``CompetitorKnowledge`` for *internal*
   contradictions and cross-source disagreements (e.g. two pricing tiers with
   the same name but different prices, ``has_free_tier=True`` with no $0 tier,
   currency drift). Each becomes a :class:`ConflictFlag` rendered in the UI as a
   "⚠ source conflict" badge instead of silently trusting one value.

2. ``majority_vote`` — reconcile *N* independent samples of a list-valued answer
   (used for self-consistency on competitor identification). With a single
   sample it is a no-op; with several it keeps items that recur in a majority of
   samples, ordered by frequency.

These power the "self-consistency check + citation enforcement" hallucination
strategy and the confidence-aware orchestration.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Dict, List, Sequence

from .schema import CompetitorKnowledge, ConflictFlag


# ---------------------------------------------------------------------------
# Conflict detection
# ---------------------------------------------------------------------------
def detect_conflicts(c: CompetitorKnowledge) -> List[ConflictFlag]:
    """Return all detected conflicts/inconsistencies for one competitor."""
    flags: List[ConflictFlag] = []

    # 1) Same-named pricing tiers that disagree on monthly price.
    by_name: Dict[str, List] = defaultdict(list)
    for tier in c.pricing.tiers:
        by_name[(tier.name or "").strip().lower()].append(tier)
    for name, tiers in by_name.items():
        prices = {t.monthly_price for t in tiers if t.monthly_price is not None}
        if len(prices) > 1:
            flags.append(ConflictFlag(
                field=f"pricing.tiers[{name}].monthly_price",
                kind="value_mismatch",
                detail=f"Tier '{name}' is listed with conflicting monthly prices.",
                values=[str(p) for p in sorted(prices)],
                source_ids=[s.id for t in tiers for s in t.sources],
                severity="major",
            ))

    # 2) Claims a free tier but no tier is actually priced at 0.
    if c.pricing.has_free_tier:
        has_zero = any(
            (t.monthly_price == 0) or ("free" in (t.name or "").lower())
            or ("免费" in (t.name or ""))
            for t in c.pricing.tiers
        )
        if c.pricing.tiers and not has_zero:
            flags.append(ConflictFlag(
                field="pricing.has_free_tier",
                kind="unsupported",
                detail="has_free_tier is true but no tier is priced at 0 / named 'Free'.",
                values=["has_free_tier=true", "no $0 tier"],
                source_ids=[s.id for s in c.pricing.sources],
                severity="minor",
            ))

    # 3) Currency drift across paid tiers (e.g. mixing USD and CNY in one market).
    currencies = {t.currency for t in c.pricing.tiers if t.monthly_price not in (None, 0)}
    if len(currencies) > 1:
        flags.append(ConflictFlag(
            field="pricing.tiers[*].currency",
            kind="value_mismatch",
            detail="Paid tiers mix multiple currencies.",
            values=sorted(currencies),
            severity="minor",
        ))

    # 4) Duplicate top-level capabilities (a tell-tale of merged hallucinations).
    top_names = [(n.name or "").strip().lower() for n in c.function_tree.nodes if n.name]
    dups = [n for n, k in Counter(top_names).items() if k > 1]
    for d in dups:
        flags.append(ConflictFlag(
            field=f"function_tree.nodes[{d}]",
            kind="duplicate",
            detail=f"Capability '{d}' appears more than once at the top level.",
            values=[d],
            severity="info",
        ))

    return flags


def annotate_conflicts(c: CompetitorKnowledge) -> CompetitorKnowledge:
    """Attach detected conflicts to the competitor in place and return it."""
    c.conflicts = detect_conflicts(c)
    return c


# ---------------------------------------------------------------------------
# Self-consistency voting
# ---------------------------------------------------------------------------
def majority_vote(samples: Sequence[Sequence[str]], *, keep: int) -> List[str]:
    """Keep items that recur across independent samples, ordered by frequency.

    ``samples`` is a list of answers (each a list of names). An item is retained
    if it appears in at least ``ceil(n/2)`` samples (a strict majority when n is
    odd). Ties broken by first-seen order. With a single sample, returns it
    unchanged (truncated to ``keep``).
    """
    samples = [list(s) for s in samples if s]
    if not samples:
        return []
    if len(samples) == 1:
        return samples[0][:keep]

    n = len(samples)
    threshold = (n + 1) // 2  # strict majority
    counts: Counter = Counter()
    first_seen: Dict[str, int] = {}
    order = 0
    for s in samples:
        seen_in_sample = set()
        for name in s:
            key = name.strip()
            if not key or key.lower() in seen_in_sample:
                continue
            seen_in_sample.add(key.lower())
            counts[key] += 1
            if key not in first_seen:
                first_seen[key] = order
                order += 1

    winners = [name for name, ct in counts.items() if ct >= threshold]
    # Fall back to the most-frequent items if the majority filter is too strict
    # (e.g. every sample returned a different set).
    if not winners:
        winners = [name for name, _ in counts.most_common(keep)]
    winners.sort(key=lambda x: (-counts[x], first_seen.get(x, 1_000_000)))
    return winners[:keep]
