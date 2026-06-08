"""分析师智能体 —— 一次为一个竞品产出 SWOT。"""
from __future__ import annotations

import json
from typing import Optional

from ..prompts import ANALYST_SYSTEM, SWOT_USER
from ..schema import CompetitorKnowledge, SWOTAnalysis
from .base import BaseAgent


class AnalystAgent(BaseAgent):
    role = "analyst"

    async def analyze(
        self,
        *,
        product: str,
        competitor: CompetitorKnowledge,
        rework_notes: Optional[str] = None,
    ) -> SWOTAnalysis:
        sys_prompt = ANALYST_SYSTEM.format(language=self.language_name)
        rework_block = (
            f"\n[Previous QC findings to address in this rework iteration]:\n{rework_notes}\n"
            if rework_notes else ""
        )
        user_prompt = SWOT_USER.format(
            product=product,
            market_display=self.market.display_name,
            competitor_json=json.dumps(competitor.model_dump(mode="json"),
                                       ensure_ascii=False, indent=2)[:6000],
        ) + rework_block
        raw = await self._call(
            intent="analyst.swot",
            system=sys_prompt,
            user=user_prompt,
            max_tokens=2048,
            decision_label=f"swot({competitor.name})",
        )
        return SWOTAnalysis.model_validate(raw)
