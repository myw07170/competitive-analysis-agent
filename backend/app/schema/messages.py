"""结构化的智能体间消息协议。

所有智能体间通信都使用这些带类型的信封 —— 绝不用裸自然语言。
这正是评分细则中"类函数调用风格"的约束。
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
    BLOCKER = "blocker"      # 必须返工
    MAJOR = "major"           # 应当返工
    MINOR = "minor"           # 可改可不改，不会触发返工
    INFO = "info"


class AgentMessage(BaseModel):
    """智能体间一条消息的信封。"""

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
    """QC 智能体提出的一个问题。"""

    id: str = Field(default_factory=lambda: f"qcf_{uuid4().hex[:8]}")
    target_agent: AgentRole
    target_path: str = Field(
        description="JSONPath-ish pointer to the offending field, e.g. 'competitors[0].pricing.tiers'",
    )
    severity: Severity
    issue: str
    suggested_fix: str = ""


class QCReport(BaseModel):
    """QC 智能体一次迭代的输出。"""

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
