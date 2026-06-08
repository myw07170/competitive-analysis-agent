"""跨运行的竞品知识演化（创新点 3）。

每次运行都会按归一化的实体键（见 ``app.storage.store.normalize_entity_key``）
存储每个竞品的快照。``compute_diff`` 对齐最近的两个快照，产出一个字段级的
:class:`KnowledgeDiff` —— "自上次查看该竞品以来发生了什么变化"：新增 / 移除的能力、
定价变动、细分迁移、定位改变。

这刻意是一个确定性的结构化 diff（不用嵌入），因此可解释且廉价；实体消歧由上游的
归一化键这一步完成。
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
    """从两条快照记录（每条 ``{run_id, captured_at, payload}``）构建一个 KnowledgeDiff。"""
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
