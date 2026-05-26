"""Analyst Agent — produces SWOT for one competitor at a time."""
from __future__ import annotations

import json

from ..prompts import ANALYST_SYSTEM, SWOT_USER
from ..schema import CompetitorKnowledge, SWOTAnalysis
from .base import BaseAgent


class AnalystAgent(BaseAgent):
    role = "analyst"

    async def analyze(self, *, product: str, competitor: CompetitorKnowledge) -> SWOTAnalysis:
        sys_prompt = ANALYST_SYSTEM.format(language=self.language_name)
        user_prompt = SWOT_USER.format(
            product=product,
            market_display=self.market.display_name,
            competitor_json=json.dumps(competitor.model_dump(mode="json"),
                                       ensure_ascii=False, indent=2)[:6000],
        )
        raw = await self._call(
            intent="analyst.swot",
            system=sys_prompt,
            user=user_prompt,
            max_tokens=2048,
            decision_label=f"swot({competitor.name})",
        )
        return SWOTAnalysis.model_validate(raw)
