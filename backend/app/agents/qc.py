"""质量控制智能体。

把确定性的 schema / 结构检查与一次 LLM 批评结合起来。确定性检查廉价、可复现，
而且——关键在于——*会路由到正确的上游智能体*：

* 采集器结论   → 缺失字段、来源过少、占位 URL、
  低置信度断言（置信度感知）、跨来源冲突。
* 分析师结论   → 缺失 / 为空 / 无来源的 SWOT。
* 撰写器结论   → 空执行摘要、断链引用、叙述中未覆盖的竞品。

QC 不仅审查采集到的知识，也审查*最终报告*，因此反馈闭环可以把工作退回给
采集器、分析师或撰写器 —— 取决于究竟是谁对该缺陷负责。
"""
from __future__ import annotations

import json
import re
from typing import List, Optional, Tuple
from urllib.parse import urlsplit

from ..config import get_settings
from ..prompts import QC_SYSTEM, QC_USER
from ..schema import (
    AgentRole,
    CompetitorKnowledge,
    FinalReport,
    QCFinding,
    QCReport,
    Severity,
)
from .base import BaseAgent


_PLACEHOLDER_HOSTS = {"example.com", "example.cn", "example.org", "test.com"}
_CITE_RE = re.compile(r"\[\^(src_[A-Za-z0-9_]+)\]")


class QCAgent(BaseAgent):
    role = "qc"

    async def review(
        self,
        *,
        iteration: int,
        competitors: List[CompetitorKnowledge],
        report: Optional[FinalReport] = None,
        target_product: Optional[CompetitorKnowledge] = None,
    ) -> QCReport:
        settings = get_settings()

        # 带标签的条目：竞品保留其带索引的路径；用户自己的产品
        # 在 'target_product' 前缀下检查。
        labelled: List[Tuple[str, CompetitorKnowledge]] = [
            (f"competitors[{i}]", c) for i, c in enumerate(competitors)
        ]
        if target_product is not None:
            labelled.append(("target_product", target_product))

        # 1) 确定性检查 —— 廉价、可复现、按角色路由。
        deterministic: List[QCFinding] = []
        deterministic += self._collector_checks(
            labelled, settings.min_sources_per_competitor, settings.min_confidence
        )
        deterministic += self._analyst_checks(labelled)
        if report is not None:
            deterministic += self._writer_checks(report)

        # 2) 请 LLM 给出更细微的批评。
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
        try:
            llm_report = QCReport.model_validate(raw)
        except Exception:
            llm_report = QCReport(iteration=iteration, decision="approve",
                                  findings=[], summary="LLM critique skipped (parse failure).")

        merged = QCReport(
            iteration=iteration,
            decision=llm_report.decision,
            summary=llm_report.summary,
            findings=deterministic + llm_report.findings,
        )
        # 若存在确定性的阻塞 / 重大问题，则覆盖该决策。
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
    # 采集器负责的检查
    # ------------------------------------------------------------------
    def _collector_checks(
        self,
        items: List[Tuple[str, CompetitorKnowledge]],
        min_sources: int,
        min_confidence: float,
    ) -> List[QCFinding]:
        findings: List[QCFinding] = []
        for base_path, c in items:
            n = c.source_count()
            if n < min_sources:
                findings.append(QCFinding(
                    target_agent=AgentRole.COLLECTOR,
                    target_path=f"{base_path}.sources",
                    severity=Severity.MAJOR,
                    issue=f"Only {n} distinct sources for {c.name}; minimum is {min_sources}.",
                    suggested_fix=f"Re-collect with at least {min_sources} independent sources.",
                ))

            if not c.function_tree.nodes:
                findings.append(QCFinding(
                    target_agent=AgentRole.COLLECTOR,
                    target_path=f"{base_path}.function_tree.nodes",
                    severity=Severity.BLOCKER,
                    issue="Function tree is empty.",
                    suggested_fix="Populate at least 3 top-level function nodes with sources.",
                ))

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

            for r in c.sources:
                if r.url and _looks_placeholder(r.url):
                    findings.append(QCFinding(
                        target_agent=AgentRole.COLLECTOR,
                        target_path=f"{base_path}.sources[{r.id}]",
                        severity=Severity.MINOR,
                        issue=f"Source URL looks like a placeholder: {r.url}",
                        suggested_fix="Replace with a real citation or mark kind='llm_prior'.",
                    ))

            if not c.user_profile.segments:
                findings.append(QCFinding(
                    target_agent=AgentRole.COLLECTOR,
                    target_path=f"{base_path}.user_profile.segments",
                    severity=Severity.MAJOR,
                    issue="No user segments identified.",
                    suggested_fix="Define at least one user segment with use cases and pain points.",
                ))

            # 置信度感知的编排：证据薄弱的断言会被重新采集。
            for path in c.low_confidence_claims(min_confidence):
                findings.append(QCFinding(
                    target_agent=AgentRole.COLLECTOR,
                    target_path=f"{base_path}.{path}",
                    severity=Severity.MINOR,
                    issue=f"Claim is supported only by low-confidence sources (< {min_confidence}).",
                    suggested_fix="Find a stronger primary source or lower the claim's specificity.",
                ))

            # 跨来源冲突（创新点 2）：暴露分歧。
            for cf in c.conflicts:
                sev = Severity.MAJOR if cf.severity == "major" else (
                    Severity.MINOR if cf.severity == "minor" else Severity.INFO)
                findings.append(QCFinding(
                    target_agent=AgentRole.COLLECTOR,
                    target_path=f"{base_path}.{cf.field}",
                    severity=sev,
                    issue=f"Source conflict ({cf.kind}): {cf.detail} values={cf.values}",
                    suggested_fix="Reconcile against a single authoritative source.",
                ))
        return findings

    # ------------------------------------------------------------------
    # 分析师负责的检查
    # ------------------------------------------------------------------
    def _analyst_checks(
        self, items: List[Tuple[str, CompetitorKnowledge]]
    ) -> List[QCFinding]:
        findings: List[QCFinding] = []
        for base_path, c in items:
            if c.swot is None:
                findings.append(QCFinding(
                    target_agent=AgentRole.ANALYST,
                    target_path=f"{base_path}.swot",
                    severity=Severity.MAJOR,
                    issue=f"SWOT analysis missing for {c.name}.",
                    suggested_fix="Produce a 4-quadrant SWOT, each item bound to a source.",
                ))
                continue
            for label, bucket in (("strengths", c.swot.strengths),
                                  ("weaknesses", c.swot.weaknesses),
                                  ("opportunities", c.swot.opportunities),
                                  ("threats", c.swot.threats)):
                if not bucket:
                    findings.append(QCFinding(
                        target_agent=AgentRole.ANALYST,
                        target_path=f"{base_path}.swot.{label}",
                        severity=Severity.MINOR,
                        issue=f"SWOT '{label}' is empty for {c.name}.",
                        suggested_fix=f"Add 2–3 {label} with supporting sources.",
                    ))
                else:
                    unsourced = sum(1 for it in bucket if not it.sources)
                    if unsourced:
                        findings.append(QCFinding(
                            target_agent=AgentRole.ANALYST,
                            target_path=f"{base_path}.swot.{label}",
                            severity=Severity.MINOR,
                            issue=f"{unsourced} '{label}' item(s) for {c.name} cite no source.",
                            suggested_fix="Bind each SWOT item to at least one source (kind='llm_prior' if inferred).",
                        ))
        return findings

    # ------------------------------------------------------------------
    # 撰写器负责的检查（报告级）
    # ------------------------------------------------------------------
    def _writer_checks(self, report: FinalReport) -> List[QCFinding]:
        findings: List[QCFinding] = []

        if not (report.executive_summary_md or "").strip():
            findings.append(QCFinding(
                target_agent=AgentRole.WRITER,
                target_path="report.executive_summary_md",
                severity=Severity.MAJOR,
                issue="Executive summary is empty.",
                suggested_fix="Write a tight executive summary covering all competitors.",
            ))

        # 引用完整性：正文中的每个 [^src_xxx] 都必须能解析。
        known_ids = {s.id for s in report.all_sources}
        for c in report.competitors:
            known_ids.update(s.id for s in c.all_source_refs())
        if report.target_product:
            known_ids.update(s.id for s in report.target_product.all_source_refs())

        broken: set[str] = set()
        bodies = [report.executive_summary_md or ""] + [s.body_md or "" for s in report.sections]
        for body in bodies:
            for m in _CITE_RE.findall(body):
                if m not in known_ids:
                    broken.add(m)
        if broken:
            findings.append(QCFinding(
                target_agent=AgentRole.WRITER,
                target_path="report.sections[*].body_md",
                severity=Severity.MAJOR,
                issue=f"{len(broken)} citation marker(s) reference unknown source IDs: {sorted(broken)[:5]}",
                suggested_fix="Only cite [^src_xxx] IDs that exist in the competitor data.",
            ))

        # 覆盖度：每个竞品都应在叙述中被提及。
        joined = " ".join(bodies)
        missing = [c.name for c in report.competitors if c.name and c.name not in joined]
        if missing and len(report.competitors) > 1:
            findings.append(QCFinding(
                target_agent=AgentRole.WRITER,
                target_path="report.sections",
                severity=Severity.MINOR,
                issue=f"Competitors not covered in the narrative: {missing}.",
                suggested_fix="Ensure every competitor appears in each comparison section.",
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
