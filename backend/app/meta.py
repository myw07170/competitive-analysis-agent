"""智能体自评与动态 schema 演进（创新点 4）。

:class:`MetaEvaluator` 横跨*所有*历史报告——而非单次运行——并发问：哪些 schema 字段
始终为空？哪些字段被人类反复修正？来源在哪里反复分歧？从这些聚合信号中，它产出
:class:`SchemaSuggestion` 记录，提出具体的变更建议（弃用一个无用字段、收紧一个 prompt、
拆分一个承载过多的字段）。

它不会自动修改 schema——这些建议会在 UI 中呈现供人类采纳——但 ``schema_version`` 已随
每份报告持久化，因此被采纳的变更可以向前滚动而不使历史失效。
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Callable, Dict, List

from .schema.competitor import CompetitorKnowledge
from .schema.report import SchemaSuggestion
from .storage import get_store

# 字段 -> 谓词"该竞品的这个字段是否已填充？"
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

_LOW = 0.2     # 完整度低于此值 → 弃用 / 改为可选的候选项
_DEAD = 0.05   # 基本从不填充 → 弃用
_CORRECTION_HOT = 3   # 一个路径被修正至少这么多次 → 收紧 prompt


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

        # 修正热点：归一化带索引的路径（去掉数组下标）。
        def _norm(path: str) -> str:
            import re
            return re.sub(r"\[[^\]]*\]", "[]", path or "")

        corr_counter: Counter = Counter(_norm(c.target_path) for c in corrections)
        # 横跨所有竞品的冲突热点。
        conflict_counter: Counter = Counter()
        for c in competitors:
            for cf in c.conflicts:
                conflict_counter[_norm(cf.field)] += 1

        suggestions: List[SchemaSuggestion] = []

        # 1) 无用 / 稀疏字段 → 弃用或改为可选。
        for field, frac in completeness.items():
            if n < 3:
                continue  # 数据不足以判断
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

        # 2) 频繁被修正的路径 → 收紧产出它的 prompt。
        for path, count in corr_counter.most_common(8):
            if count >= _CORRECTION_HOT:
                suggestions.append(SchemaSuggestion(
                    field=path, action="tighten_prompt",
                    rationale=f"Humans corrected this field {count} times — the prompt under-specifies it.",
                    evidence={"corrections": float(count)}, confidence=0.6,
                ))

        # 3) 频繁的来源冲突 → 增加一个显式的协调字段 / prompt。
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
