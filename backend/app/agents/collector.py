"""Collector Agent.

Two-step:
1. ``identify_competitors`` — get the top-3 list (with optional self-consistency
   voting across N samples).
2. ``gather_competitor``    — for each, produce a CompetitorKnowledge, grounded
   in web evidence when a search backend is configured, and steered by any QC
   rework notes plus accumulated human-correction guidance (active learning).
"""
from __future__ import annotations

from typing import Dict, List, Optional

from ..collectors import search
from ..collectors.web import fetch_page
from ..config import get_settings
from ..consistency import majority_vote
from ..learning import recent_guidance
from ..prompts import (
    COLLECTOR_SYSTEM,
    GATHER_COMPETITOR_USER,
    IDENTIFY_COMPETITORS_USER,
)
from ..schema import CompetitorKnowledge
from .base import BaseAgent


class CollectorAgent(BaseAgent):
    role = "collector"

    async def identify_competitors(self, product: str) -> List[Dict]:
        sys_prompt = COLLECTOR_SYSTEM.format(language=self.language_name)
        user_prompt = IDENTIFY_COMPETITORS_USER.format(
            product=product,
            market_display=self.market.display_name,
            market_code=self.market.code,
        )
        samples_n = get_settings().self_consistency_samples

        async def _one(temperature: float) -> List[Dict]:
            out = await self._call(
                intent="collector.identify_competitors",
                system=sys_prompt,
                user=user_prompt,
                temperature=temperature,
                decision_label=f"identify_competitors({product})",
            )
            return out.get("competitors", []) or []

        if samples_n <= 1:
            return await _one(temperature=0.2)

        # Self-consistency: draw N samples at higher temperature, keep the
        # competitors a majority of samples agree on (more robust to one-off
        # hallucinations than a single greedy answer).
        all_names: List[List[str]] = []
        raw_by_name: Dict[str, Dict] = {}
        for i in range(samples_n):
            comps = await _one(temperature=0.5 if i else 0.2)
            names = [c["name"] for c in comps if c.get("name")]
            all_names.append(names)
            for c in comps:
                if c.get("name") and c["name"] not in raw_by_name:
                    raw_by_name[c["name"]] = c
        voted = majority_vote(all_names, keep=4)
        self.log.info(f"self-consistency vote ({samples_n} samples) -> {voted}")
        return [raw_by_name.get(n, {"name": n}) for n in voted]

    async def gather_competitor(
        self,
        *,
        product: str,
        competitor_name: str,
        iteration: int = 0,
        rework_notes: Optional[str] = None,
    ) -> CompetitorKnowledge:
        evidence_block = await self._build_evidence(product, competitor_name)
        rework_block = (
            f"\n[Previous QC findings to address in this rework iteration]:\n{rework_notes}\n"
            if rework_notes else ""
        )
        # Active learning: fold in lessons learned from past human corrections.
        guidance = await recent_guidance(self.market.code)
        sys_prompt = COLLECTOR_SYSTEM.format(language=self.language_name) + guidance
        user_prompt = GATHER_COMPETITOR_USER.format(
            product=product,
            market_display=self.market.display_name,
            market_code=self.market.code,
            competitor_name=competitor_name,
            iteration=iteration,
            evidence_block=evidence_block,
            rework_block=rework_block,
            min_sources=get_settings().min_sources_per_competitor,
        )
        intent = "collector.gather_competitor" if iteration == 0 else "collector.rework"
        raw = await self._call(
            intent=intent,
            system=sys_prompt,
            user=user_prompt,
            max_tokens=8192,
            decision_label=f"gather({competitor_name}, it={iteration})",
        )
        # Pydantic validation — fail loud rather than ship broken data downstream.
        return CompetitorKnowledge.model_validate(raw)

    async def _build_evidence(self, product: str, competitor_name: str) -> str:
        """Search + optional page-fetch, return a markdown evidence block.

        Falls back to an empty string when no search backend is configured —
        the LLM then falls back to its prior knowledge.
        """
        settings = get_settings()
        if settings.search_provider == "none":
            return "[No live web search backend configured; using model prior knowledge.]"

        queries = self.market.search_queries(competitor_name)[:3]
        all_hits: List = []
        for q in queries:
            hits = await search.search(q, limit=3,
                                       provider_override=self.market.preferred_search_provider
                                       if settings.search_provider == "none" else None)
            all_hits.extend(hits)
            if len(all_hits) >= 8:
                break

        if not all_hits:
            return "[Search returned no hits.]"

        # Light page fetch on the top 2 hits to enrich snippets.
        enriched: List[str] = []
        for h in all_hits[:2]:
            page = await fetch_page(h.url, max_chars=1500)
            if page and page.text and not page.blocked_by_robots:
                enriched.append(f"### {h.title}\nURL: {page.url}\n\n{page.text[:1200]}")
            else:
                enriched.append(f"### {h.title}\nURL: {h.url}\n\n{h.snippet}")
        for h in all_hits[2:]:
            enriched.append(f"### {h.title}\nURL: {h.url}\n\n{h.snippet}")

        return "Evidence collected from web search:\n\n" + "\n\n".join(enriched)
