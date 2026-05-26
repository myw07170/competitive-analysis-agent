"""Structured agent-to-agent message protocol.

All inter-agent communication uses these typed envelopes — never raw natural
language. This is the "function-calling style" constraint from the scoring rubric.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class AgentRole(str, Enum):
    COLLECTOR = "collector"
    ANALYST = "analyst"
    WRITER = "writer"
    QC = "qc"
    ORCHESTRATOR = "orchestrator"


class Severity(str, Enum):
    BLOCKER = "blocker"      # must rework
    MAJOR = "major"           # should rework
    MINOR = "minor"           # nice-to-fix, will not trigger rework
    INFO = "info"


class AgentMessage(BaseModel):
    """Envelope for one message between agents."""

    id: str = Field(default_factory=lambda: f"msg_{uuid4().hex[:10]}")
    sender: AgentRole
    receiver: AgentRole
    intent: str = Field(
        description="The 'function name' being invoked, e.g. 'request_rework', 'submit_knowledge'",
    )
    payload: Dict[str, Any] = Field(default_factory=dict)
    correlation_id: Optional[str] = Field(
        default=None,
        description="Links a response back to the request that triggered it.",
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class QCFinding(BaseModel):
    """One issue raised by the QC agent."""

    id: str = Field(default_factory=lambda: f"qcf_{uuid4().hex[:8]}")
    target_agent: AgentRole
    target_path: str = Field(
        description="JSONPath-ish pointer to the offending field, e.g. 'competitors[0].pricing.tiers'",
    )
    severity: Severity
    issue: str
    suggested_fix: str = ""


class QCReport(BaseModel):
    """Output of the QC agent for one iteration."""

    iteration: int
    findings: List[QCFinding] = Field(default_factory=list)
    decision: Literal["approve", "rework", "approve_with_notes"]
    summary: str = ""

    @property
    def blockers(self) -> List[QCFinding]:
        return [f for f in self.findings if f.severity == Severity.BLOCKER]

    @property
    def needs_rework(self) -> bool:
        return self.decision == "rework"
