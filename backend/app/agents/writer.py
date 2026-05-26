"""Writer Agent — turns analyzed competitor knowledge into a final report."""
from __future__ import annotations

import json
from typing import List

from ..i18n import get_locale
from ..prompts import WRITER_SYSTEM, WRITER_USER
from ..schema import CompetitorKnowledge, FinalReport, ReportSection, SourceRef
from .base import BaseAgent


class WriterAgent(BaseAgent):
    role = "writer"

    async def write(
        self,
        *,
        product: str,
        report_id: str,
        competitors: List[CompetitorKnowledge],
    ) -> FinalReport:
        loc = get_locale(self.market.locale)
        sys_prompt = WRITER_SYSTEM.format(language=self.language_name)
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
            competitors_json=json.dumps(
                [c.model_dump(mode="json") for c in competitors],
                ensure_ascii=False, indent=2,
            )[:12000],
        )
        raw = await self._call(
            intent="writer.report",
            system=sys_prompt,
            user=user_prompt,
            max_tokens=4096,
            decision_label=f"write_report({product})",
        )

        sections = [ReportSection.model_validate(s) for s in raw.get("sections", [])]
        all_sources = _collect_sources(competitors)

        return FinalReport(
            id=report_id,
            product=product,
            market=self.market.code,
            locale=self.market.locale,
            title=raw.get("title", loc["report.title"]),
            executive_summary_md=raw.get("executive_summary_md", ""),
            sections=sections,
            competitors=competitors,
            all_sources=all_sources,
        )


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
