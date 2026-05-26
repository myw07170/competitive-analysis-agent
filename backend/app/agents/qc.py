"""Quality Control Agent.

Combines deterministic schema/structure checks with an LLM-based critique pass.
The deterministic checks catch the obvious failures (missing field, < min
sources, hallucinated URLs) so the LLM can focus on subtler issues.
"""
from __future__ import annotations

import json
import re
from typing import List
from urllib.parse import urlsplit

from ..config import get_settings
from ..prompts import QC_SYSTEM, QC_USER
from ..schema import (
    AgentRole,
    CompetitorKnowledge,
    QCFinding,
    QCReport,
    Severity,
)
from .base import BaseAgent


_PLACEHOLDER_HOSTS = {"example.com", "example.cn", "example.org", "test.com"}


class QCAgent(BaseAgent):
    role = "qc"

    async def review(
        self,
        *,
        iteration: int,
        competitors: List[CompetitorKnowledge],
    ) -> QCReport:
        settings = get_settings()

        # 1) Deterministic checks first — these are cheap, reproducible.
        deterministic = self._deterministic_checks(competitors, settings.min_sources_per_competitor)

        # 2) Ask the LLM for subtler critique.
        sys_prompt = QC_SYSTEM.format(
            language=self.language_name,
            min_sources=settings.min_sources_per_competitor,
        )
        user_prompt = QC_USER.format(
            iteration=iteration,
            locale=self.market.locale,
            min_sources=settings.min_sources_per_competitor,
            competitors_json=json.dumps(
                [c.model_dump(mode="json") for c in competitors],
                ensure_ascii=False, indent=2,
            )[:10000],
        )
        raw = await self._call(
            intent="qc.review",
            system=sys_prompt,
            user=user_prompt,
            max_tokens=1500,
            decision_label=f"qc.review(it={iteration})",
        )
        # Merge LLM findings with deterministic ones.
        try:
            llm_report = QCReport.model_validate(raw)
        except Exception:
            # If LLM output couldn't be parsed as a QCReport, fall back to
            # deterministic-only verdict — still a valid QC pass.
            llm_report = QCReport(iteration=iteration, decision="approve",
                                  findings=[], summary="LLM critique skipped (parse failure).")

        merged = QCReport(
            iteration=iteration,
            decision=llm_report.decision,
            summary=llm_report.summary,
            findings=deterministic + llm_report.findings,
        )
        # If deterministic blockers/majors exist, override the decision.
        blocker_or_major = [
            f for f in merged.findings
            if f.severity in (Severity.BLOCKER, Severity.MAJOR)
        ]
        if blocker_or_major and iteration < settings.max_qc_iterations:
            merged.decision = "rework"
        elif merged.findings and merged.decision == "approve":
            merged.decision = "approve_with_notes"
        return merged

    # ------------------------------------------------------------------
    # Deterministic checks
    # ------------------------------------------------------------------
    def _deterministic_checks(
        self,
        competitors: List[CompetitorKnowledge],
        min_sources: int,
    ) -> List[QCFinding]:
        findings: List[QCFinding] = []
        for i, c in enumerate(competitors):
            base_path = f"competitors[{i}]"

            # Source count
            n = c.source_count()
            if n < min_sources:
                findings.append(QCFinding(
                    target_agent=AgentRole.COLLECTOR,
                    target_path=f"{base_path}.sources",
                    severity=Severity.MAJOR,
                    issue=f"Only {n} distinct sources for {c.name}; minimum is {min_sources}.",
                    suggested_fix=f"Re-collect with at least {min_sources} independent sources.",
                ))

            # Function tree non-empty
            if not c.function_tree.nodes:
                findings.append(QCFinding(
                    target_agent=AgentRole.COLLECTOR,
                    target_path=f"{base_path}.function_tree.nodes",
                    severity=Severity.BLOCKER,
                    issue="Function tree is empty.",
                    suggested_fix="Populate at least 3 top-level function nodes with sources.",
                ))

            # Pricing tiers
            if not c.pricing.tiers:
                findings.append(QCFinding(
                    target_agent=AgentRole.COLLECTOR,
                    target_path=f"{base_path}.pricing.tiers",
                    severity=Severity.MAJOR,
                    issue="No pricing tiers recorded.",
                    suggested_fix="Add at least one pricing tier (free or paid) with a source.",
                ))
            for j, tier in enumerate(c.pricing.tiers):
                if not tier.sources:
                    findings.append(QCFinding(
                        target_agent=AgentRole.COLLECTOR,
                        target_path=f"{base_path}.pricing.tiers[{j}].sources",
                        severity=Severity.MAJOR,
                        issue=f"Pricing tier {tier.name!r} has no source.",
                        suggested_fix="Add an explicit pricing-page citation.",
                    ))

            # Hallucinated URLs
            for r in c.sources:
                if r.url and _looks_placeholder(r.url):
                    findings.append(QCFinding(
                        target_agent=AgentRole.COLLECTOR,
                        target_path=f"{base_path}.sources[{r.id}]",
                        severity=Severity.MINOR,
                        issue=f"Source URL looks like a placeholder: {r.url}",
                        suggested_fix="Replace with a real citation or mark kind='llm_prior'.",
                    ))

            # User-profile segments
            if not c.user_profile.segments:
                findings.append(QCFinding(
                    target_agent=AgentRole.COLLECTOR,
                    target_path=f"{base_path}.user_profile.segments",
                    severity=Severity.MAJOR,
                    issue="No user segments identified.",
                    suggested_fix="Define at least one user segment with use cases and pain points.",
                ))

        return findings


def _looks_placeholder(url: str) -> bool:
    try:
        host = urlsplit(url).netloc.lower()
    except Exception:
        return True
    if any(host.endswith("." + p) or host == p for p in _PLACEHOLDER_HOSTS):
        return True
    if re.search(r"\b(localhost|127\.0\.0\.1)\b", host):
        return True
    return False
