"""智能体系统 prompt，外置以便审计与调优。"""
from .collector import (
    IDENTIFY_COMPETITORS_USER,
    GATHER_COMPETITOR_USER,
    COLLECTOR_SYSTEM,
)
from .analyst import ANALYST_SYSTEM, SWOT_USER
from .writer import WRITER_SYSTEM, WRITER_USER
from .qc import QC_SYSTEM, QC_USER

__all__ = [
    "COLLECTOR_SYSTEM",
    "IDENTIFY_COMPETITORS_USER",
    "GATHER_COMPETITOR_USER",
    "ANALYST_SYSTEM",
    "SWOT_USER",
    "WRITER_SYSTEM",
    "WRITER_USER",
    "QC_SYSTEM",
    "QC_USER",
]
