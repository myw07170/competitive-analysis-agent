"""Pydantic schemas shared across agents.

These schemas are the contract between agents. Every agent input / output
is validated against them, which is what makes "structured message passing
(function-calling style) instead of pure natural-language dialogue" enforceable.
"""
from .competitor import (
    CompetitorKnowledge,
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
from .report import FinalReport, ReportSection

__all__ = [
    "CompetitorKnowledge",
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
    "FinalReport",
    "ReportSection",
]
