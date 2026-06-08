"""撰写器智能体 —— 把分析后的竞品知识转化为最终报告。"""
from __future__ import annotations

import json
import re
from collections import Counter
from typing import Dict, List, Optional

from ..i18n import get_locale
from ..prompts import WRITER_SYSTEM, WRITER_USER
from ..schema import (
    ComparisonCell,
    ComparisonMatrix,
    ComparisonRow,
    CompetitorKnowledge,
    FinalReport,
    FunctionNode,
    ReportSection,
    SourceRef,
)
from .base import BaseAgent


class WriterAgent(BaseAgent):
    role = "writer"

    async def write(
        self,
        *,
        product: str,
        report_id: str,
        competitors: List[CompetitorKnowledge],
        target_product: Optional[CompetitorKnowledge] = None,
        rework_notes: Optional[str] = None,
    ) -> FinalReport:
        loc = get_locale(self.market.locale)
        sys_prompt = WRITER_SYSTEM.format(language=self.language_name)
        competitor_names = ", ".join(c.name for c in competitors) or "—"
        competitor_names_pipe = " | ".join(c.name for c in competitors) or "—"
        rework_block = (
            f"\n[Previous QC findings to address in this rework iteration]:\n{rework_notes}\n"
            if rework_notes else ""
        )
        user_prompt = WRITER_USER.format(
            product=product,
            market_display=self.market.display_name,
            locale=self.market.locale,
            label_summary=loc["section.executive_summary"],
            label_market=loc["section.market_overview"],
            label_function=loc["section.function_comparison"],
            label_pricing=loc["section.pricing_comparison"],
            label_user=loc["section.user_comparison"],
            label_swot=loc["section.swot"],
            label_reco=loc["section.recommendations"],
            competitor_names=competitor_names,
            competitor_names_pipe=competitor_names_pipe,
            competitors_json=json.dumps(
                [c.model_dump(mode="json") for c in competitors],
                ensure_ascii=False, indent=2,
            )[:12000],
        ) + rework_block
        raw = await self._call(
            intent="writer.report",
            system=sys_prompt,
            user=user_prompt,
            max_tokens=4096,
            decision_label=f"write_report({product})",
        )

        # 采集到的来源是标准的、可按 ID 寻址的集合。先建立一个查找表，
        # 这样每个章节的 "sources" —— 撰写器 LLM 倾向于把它写成裸的
        # [^src_xxx] ID 字符串而非完整的 SourceRef 字典 —— 才能被解析回真实记录，
        # 而不是导致校验失败。
        all_sources = _collect_sources(
            (competitors + [target_product]) if target_product else competitors
        )
        known_by_id = {s.id: s for s in all_sources}

        sections = [
            _section_from_raw(s, known_by_id) for s in raw.get("sections", [])
        ]
        # 保证多竞品覆盖：若撰写器的叙述提及的竞品不足一半，
        # 则追加一个确定性的对比附录，使用户仍能看到全部竞品。
        sections = _ensure_multi_competitor_coverage(
            sections, competitors, loc, target_product=target_product,
        )
        comparison = _build_comparison_matrix(competitors, target_product=target_product)

        return FinalReport(
            id=report_id,
            product=product,
            market=self.market.code,
            locale=self.market.locale,
            title=raw.get("title", loc["report.title"]),
            executive_summary_md=raw.get("executive_summary_md", ""),
            sections=sections,
            competitors=competitors,
            target_product=target_product,
            comparison=comparison,
            all_sources=all_sources,
        )


def _coerce_source_refs(
    value, known_by_id: Dict[str, SourceRef]
) -> List[SourceRef]:
    """把一个章节的 ``sources`` 字段归一化为真正的 ``SourceRef`` 对象。

    撰写器 LLM 通过 ``[^src_xxx]`` ID 引用事实，因此它常把章节的 ``sources``
    写成一列裸 ID 字符串（或 ``{"id": "src_xxx"}`` 残桩）而非完整的 SourceRef 字典
    —— 这会导致 ``List[SourceRef]`` 校验失败。把每一项对照采集到的来源解析，
    并回退到一个最小化的 ref，使引用绝不会被默默丢弃。
    """
    out: List[SourceRef] = []
    seen: set[str] = set()

    def _push(ref: SourceRef) -> None:
        if ref.id not in seen:
            seen.add(ref.id)
            out.append(ref)

    for item in value or []:
        if isinstance(item, SourceRef):
            _push(item)
        elif isinstance(item, str):
            _push(known_by_id.get(item) or SourceRef(id=item))
        elif isinstance(item, dict):
            sid = item.get("id")
            # 一个裸的 {"id": ...} 残桩 → 优先使用完整的已知记录。
            if sid and len(item) == 1 and sid in known_by_id:
                _push(known_by_id[sid])
                continue
            try:
                _push(SourceRef.model_validate(item))
            except Exception:
                if sid:
                    _push(known_by_id.get(sid) or SourceRef(id=sid))
    return out


def _section_from_raw(s, known_by_id: Dict[str, SourceRef]) -> ReportSection:
    """校验一个原始章节，容忍 LLM 的来源 ID 简写形式。"""
    if isinstance(s, dict):
        data = dict(s)
        data["sources"] = _coerce_source_refs(data.get("sources"), known_by_id)
        return ReportSection.model_validate(data)
    return ReportSection.model_validate(s)


def _collect_sources(competitors: List[CompetitorKnowledge]) -> List[SourceRef]:
    seen: dict[str, SourceRef] = {}

    def _add(refs: List[SourceRef]) -> None:
        for r in refs:
            if r.id not in seen:
                seen[r.id] = r

    for c in competitors:
        _add(c.sources)
        _add(c.pricing.sources)
        _add(c.user_profile.sources)
        for t in c.pricing.tiers + c.pricing.addons:
            _add(t.sources)
        for seg in c.user_profile.segments:
            _add(seg.sources)

        def _walk(node) -> None:
            _add(node.sources)
            for child in node.children:
                _walk(child)

        for n in c.function_tree.nodes:
            _walk(n)
        if c.swot:
            for bucket in (c.swot.strengths, c.swot.weaknesses,
                           c.swot.opportunities, c.swot.threats):
                for item in bucket:
                    _add(item.sources)
    return list(seen.values())


# ---------------------------------------------------------------------------
# 多竞品覆盖辅助函数
# ---------------------------------------------------------------------------
def _ensure_multi_competitor_coverage(
    sections: List[ReportSection],
    competitors: List[CompetitorKnowledge],
    loc: Dict[str, str],
    target_product: Optional[CompetitorKnowledge] = None,
) -> List[ReportSection]:
    """若撰写器的正文对竞品覆盖不足，则追加一个确定性的多竞品附录，
    使用户始终能看到每一个竞品。

    当提供了 ``target_product`` 时，它会作为第一列纳入，使该快照把用户自己的
    产品与竞品并排呈现。
    """
    if len(competitors) <= 1 or not sections:
        return sections

    all_items: List[CompetitorKnowledge] = (
        ([target_product] + competitors) if target_product else competitors
    )
    names = [c.name for c in all_items]
    joined_body = " \n".join(s.body_md or "" for s in sections)
    mentions = sum(1 for n in names if n and n in joined_body)
    # 若至少引用了 60% 的竞品，则信任撰写器的输出。
    if mentions >= max(2, int(len(names) * 0.6)):
        return sections

    heading_overview = loc.get("section.market_overview", "Comparison overview")
    body_lines: List[str] = []
    body_lines.append(f"| {loc.get('label.product', 'Aspect')} | " + " | ".join(names) + " |")
    body_lines.append("|" + "|".join(["---"] * (len(names) + 1)) + "|")

    def _row(label: str, getter) -> str:
        cells = [str(getter(c) or "—") for c in all_items]
        return f"| **{label}** | " + " | ".join(cells) + " |"

    body_lines.append(_row("Market position", lambda c: c.market_position))
    body_lines.append(_row("Function leaves", lambda c: c.function_tree.leaf_count()))
    body_lines.append(_row(
        "Cheapest tier",
        lambda c: _cheapest_tier_label(c),
    ))
    body_lines.append(_row("Primary segment", lambda c: c.user_profile.primary_segment))

    appendix = ReportSection(
        heading=f"{heading_overview} — Multi-competitor snapshot",
        body_md="\n".join(body_lines),
        sources=[],
    )
    return sections + [appendix]


def _cheapest_tier_label(c: CompetitorKnowledge) -> str:
    tiers = [t for t in c.pricing.tiers if t.monthly_price is not None]
    if not tiers:
        return c.pricing.summary[:40] if c.pricing.summary else "—"
    cheapest = min(tiers, key=lambda t: t.monthly_price)  # type: ignore[arg-type]
    return f"{cheapest.name}: {cheapest.monthly_price} {cheapest.currency}/mo"


# ---------------------------------------------------------------------------
# 结构化对比矩阵（确定性 —— 独立于 LLM 的 markdown）
# ---------------------------------------------------------------------------
def _build_comparison_matrix(
    competitors: List[CompetitorKnowledge],
    target_product: Optional[CompetitorKnowledge] = None,
) -> ComparisonMatrix:
    """构建结构化对比。

    当提供了 ``target_product`` 时，它会作为第一列前置，使每张图表 / 表格都
    包含用户自己的产品与竞品并列。
    """
    all_items: List[CompetitorKnowledge] = (
        ([target_product] + competitors) if target_product else competitors
    )
    names = [c.name for c in all_items]

    feature_rows = _build_feature_rows(all_items)
    pricing_rows = _build_pricing_rows(all_items)
    user_rows = _build_user_rows(all_items)

    keywords: Dict[str, List[str]] = {}
    function_coverage: Dict[str, int] = {}
    source_counts: Dict[str, int] = {}
    pricing_floor: Dict[str, Optional[float]] = {}

    for c in all_items:
        keywords[c.name] = _extract_keywords(c)
        function_coverage[c.name] = c.function_tree.leaf_count()
        source_counts[c.name] = c.source_count()
        prices = [t.monthly_price for t in c.pricing.tiers
                  if isinstance(t.monthly_price, (int, float))]
        pricing_floor[c.name] = float(min(prices)) if prices else None

    return ComparisonMatrix(
        competitors=names,
        self_name=target_product.name if target_product else None,
        feature_rows=feature_rows,
        pricing_rows=pricing_rows,
        user_rows=user_rows,
        keywords=keywords,
        function_coverage=function_coverage,
        source_counts=source_counts,
        pricing_floor=pricing_floor,
    )


def _walk_leaves(node: FunctionNode, out: List[FunctionNode]) -> None:
    if not node.children:
        out.append(node)
        return
    for ch in node.children:
        _walk_leaves(ch, out)


def _build_feature_rows(competitors: List[CompetitorKnowledge]) -> List[ComparisonRow]:
    """汇总所有竞品中最主要的功能，并检查每个竞品是否具备各项功能。"""
    feature_per_competitor: Dict[str, set[str]] = {}
    counter: Counter[str] = Counter()
    for c in competitors:
        leaves: List[FunctionNode] = []
        for n in c.function_tree.nodes:
            _walk_leaves(n, leaves)
        names_norm = set()
        for leaf in leaves:
            label = (leaf.name or "").strip()
            if not label:
                continue
            names_norm.add(label.lower())
            counter[label.lower()] += 1
        feature_per_competitor[c.name] = names_norm

    # 取最共有 / 最常被提及的约 10 个功能。
    top = [f for f, _ in counter.most_common(10)]
    if not top:
        return []

    rows: List[ComparisonRow] = []
    for feature in top:
        cells = []
        for c in competitors:
            has_it = feature in feature_per_competitor.get(c.name, set())
            cells.append(ComparisonCell(
                competitor=c.name,
                value="✓" if has_it else "—",
                detail=feature if has_it else None,
            ))
        rows.append(ComparisonRow(label=feature.title(), category="capability", cells=cells))
    return rows


def _build_pricing_rows(competitors: List[CompetitorKnowledge]) -> List[ComparisonRow]:
    # 按归一化的标准分组把档位归类。
    canonical_order = ["Free", "Starter", "Pro", "Business", "Enterprise"]

    def _bucket(name: str) -> str:
        low = (name or "").lower()
        if any(k in low for k in ("free", "免费", "试用")):
            return "Free"
        if any(k in low for k in ("starter", "basic", "personal", "个人", "入门")):
            return "Starter"
        if any(k in low for k in ("pro", "plus", "team", "标准", "专业")):
            return "Pro"
        if any(k in low for k in ("business", "growth", "企业版", "商业")):
            return "Business"
        if any(k in low for k in ("enterprise", "ent", "旗舰", "定制", "custom", "contact")):
            return "Enterprise"
        return name.strip() or "Other"

    buckets_seen: set[str] = set()
    by_competitor: Dict[str, Dict[str, str]] = {c.name: {} for c in competitors}

    for c in competitors:
        for tier in c.pricing.tiers:
            b = _bucket(tier.name)
            buckets_seen.add(b)
            if isinstance(tier.monthly_price, (int, float)):
                cell = f"{tier.monthly_price:g} {tier.currency}/mo"
            elif tier.monthly_price is None and tier.annual_price is None:
                cell = tier.name or "—"
            else:
                cell = tier.name or "—"
            by_competitor[c.name].setdefault(b, cell)

    # 稳定排序：标准分组在前，其余额外项按字母序。
    ordered = [b for b in canonical_order if b in buckets_seen] + sorted(
        b for b in buckets_seen if b not in canonical_order
    )
    rows: List[ComparisonRow] = []
    for b in ordered:
        cells = []
        for c in competitors:
            cell_val = by_competitor[c.name].get(b, "—")
            cells.append(ComparisonCell(competitor=c.name, value=cell_val))
        rows.append(ComparisonRow(label=b, category="pricing", cells=cells))
    return rows


def _build_user_rows(competitors: List[CompetitorKnowledge]) -> List[ComparisonRow]:
    rows = []

    def _row(label: str, getter) -> ComparisonRow:
        cells = []
        for c in competitors:
            v = getter(c) or "—"
            if isinstance(v, list):
                v = ", ".join(str(x) for x in v[:4]) or "—"
            cells.append(ComparisonCell(competitor=c.name, value=str(v)))
        return ComparisonRow(label=label, category="user", cells=cells)

    rows.append(_row("Primary segment", lambda c: c.user_profile.primary_segment))
    rows.append(_row("Top segments", lambda c: [s.name for s in c.user_profile.segments]))
    rows.append(_row(
        "Geographies",
        lambda c: list({g for s in c.user_profile.segments for g in s.geographies}),
    ))
    rows.append(_row(
        "Pain points",
        lambda c: list({p for s in c.user_profile.segments for p in s.pain_points})[:4],
    ))
    rows.append(_row("Rating", lambda c: c.user_profile.nps_or_rating))
    return rows


_KEYWORD_RE = re.compile(r"[A-Za-z0-9_一-鿿][A-Za-z0-9_一-鿿\- ]{1,28}")


def _extract_keywords(c: CompetitorKnowledge) -> List[str]:
    """为关键词卡片挑选 5~8 个简短、高信息量的短语。"""
    bag: List[str] = []
    if c.market_position:
        bag.append(c.market_position[:40])

    # SWOT 的优势项给出最强的信号。
    if c.swot:
        for item in c.swot.strengths[:3]:
            bag.append(item.value[:40])
        for item in c.swot.opportunities[:1]:
            bag.append(item.value[:40])

    # 顶层功能类别。
    for node in c.function_tree.nodes[:3]:
        bag.append(node.name)

    # 主要细分 / 第一个细分。
    if c.user_profile.primary_segment:
        bag.append(c.user_profile.primary_segment[:30])
    for s in c.user_profile.segments[:1]:
        bag.append(s.name)

    # 去重、去空、上限 8 个。
    out: List[str] = []
    seen: set[str] = set()
    for raw in bag:
        kw = (raw or "").strip().strip(".。!?,;:")
        if not kw or kw.lower() in seen:
            continue
        seen.add(kw.lower())
        out.append(kw)
        if len(out) >= 8:
            break
    return out
