"""Pydantic schemas shared across agents.

These schemas are the contract between agents. Every agent input / output
is validated against them, which is what makes "structured message passing
(function-calling style) instead of pure natural-language dialogue" enforceable.
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
