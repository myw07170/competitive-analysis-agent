"""智能体间共享的 Pydantic schema。

这些 schema 是智能体之间的契约。每个智能体的输入 / 输出都对照它们校验，
正是这一点让"结构化消息传递（类函数调用风格）而非纯自然语言对话"得以强制执行。
"""
from .competitor import (
    Cited,
    CompetitorKnowledge,
    ConflictFlag,
    FunctionNode,
    FunctionTree,
    PricingModel,
    PricingTier,
    SourceRef,
    SWOTAnalysis,
    UserProfile,
    UserSegment,
)
from .messages import (
    AgentMessage,
    AgentRole,
    QCFinding,
    QCReport,
    Severity,
)
from .report import (
    ComparisonCell,
    ComparisonMatrix,
    ComparisonRow,
    Correction,
    FinalReport,
    KnowledgeChange,
    KnowledgeDiff,
    ReportMetrics,
    ReportSection,
    SchemaSuggestion,
)

__all__ = [
    "Cited",
    "CompetitorKnowledge",
    "ConflictFlag",
    "FunctionNode",
    "FunctionTree",
    "PricingModel",
    "PricingTier",
    "SourceRef",
    "SWOTAnalysis",
    "UserProfile",
    "UserSegment",
    "AgentMessage",
    "AgentRole",
    "QCFinding",
    "QCReport",
    "Severity",
    "ComparisonCell",
    "ComparisonMatrix",
    "ComparisonRow",
    "Correction",
    "FinalReport",
    "KnowledgeChange",
    "KnowledgeDiff",
    "ReportMetrics",
    "ReportSection",
    "SchemaSuggestion",
]
