"""确定性的自一致性与跨来源冲突检测。

两项职责，均刻意保持确定性（不额外调用 LLM），因此廉价、可复现、可演示：

1. ``detect_conflicts`` —— 检查一个 ``CompetitorKnowledge`` 的*内部*矛盾与跨来源
   分歧（例如两个同名但价格不同的定价档位、``has_free_tier=True`` 却没有 $0 档位、
   币种漂移）。每一处都会成为一个 :class:`ConflictFlag`，在 UI 中渲染为
   "⚠ 来源冲突"徽标，而非默默信任某一个值。

2. ``majority_vote`` —— 协调一个列表型答案的 *N* 个独立样本（用于竞品识别的
   自一致性）。只有一个样本时它是空操作；有多个时，它保留在多数样本中复现的项，
   并按频率排序。

它们支撑了"自一致性检查 + 引用强制校验"的抗幻觉策略以及置信度感知的编排。
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Dict, List, Sequence

from .schema import CompetitorKnowledge, ConflictFlag


# ---------------------------------------------------------------------------
# 冲突检测
# ---------------------------------------------------------------------------
def detect_conflicts(c: CompetitorKnowledge) -> List[ConflictFlag]:
    """返回针对单个竞品检测到的所有冲突 / 不一致。"""
    flags: List[ConflictFlag] = []

    # 1) 同名但月度价格不一致的定价档位。
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

    # 2) 声称有免费档位，但实际没有任何档位定价为 0。
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

    # 3) 付费档位间的币种漂移（例如在同一市场混用 USD 和 CNY）。
    currencies = {t.currency for t in c.pricing.tiers if t.monthly_price not in (None, 0)}
    if len(currencies) > 1:
        flags.append(ConflictFlag(
            field="pricing.tiers[*].currency",
            kind="value_mismatch",
            detail="Paid tiers mix multiple currencies.",
            values=sorted(currencies),
            severity="minor",
        ))

    # 4) 重复的顶层能力（合并幻觉的典型迹象）。
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
    """就地把检测到的冲突挂到竞品上并返回它。"""
    c.conflicts = detect_conflicts(c)
    return c


# ---------------------------------------------------------------------------
# 自一致性投票
# ---------------------------------------------------------------------------
def majority_vote(samples: Sequence[Sequence[str]], *, keep: int) -> List[str]:
    """保留在多个独立样本间复现的项，并按频率排序。

    ``samples`` 是一组答案（每个都是一个名称列表）。若某项至少出现在
    ``ceil(n/2)`` 个样本中（n 为奇数时即严格多数），则予以保留。平局按首次出现
    顺序决定。只有单个样本时，原样返回（截断到 ``keep``）。
    """
    samples = [list(s) for s in samples if s]
    if not samples:
        return []
    if len(samples) == 1:
        return samples[0][:keep]

    n = len(samples)
    threshold = (n + 1) // 2  # 严格多数
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
    # 若多数过滤过于严格（例如每个样本都返回了不同的集合），
    # 则回退到出现频率最高的那些项。
    if not winners:
        winners = [name for name, _ in counts.most_common(keep)]
    winners.sort(key=lambda x: (-counts[x], first_seen.get(x, 1_000_000)))
    return winners[:keep]
