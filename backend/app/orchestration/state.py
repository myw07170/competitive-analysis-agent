"""关于 DAG 的静态元数据 —— 供前端渲染。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

from pydantic import BaseModel, Field


class AnalysisRequest(BaseModel):
    product: str = Field(min_length=1, max_length=200)
    market: str = Field(description="cn | us | <future market code>")
    extra_competitors: List[str] = Field(
        default_factory=list,
        description="Optional user-supplied competitor names to include.",
    )


@dataclass(frozen=True)
class DagNode:
    id: str
    label_zh: str
    label_en: str
    agent: str
    description_zh: str
    description_en: str


@dataclass(frozen=True)
class DagEdge:
    src: str
    dst: str
    condition: str = ""   # 人类可读的条件标签（例如 "rework"）


def dag_definition() -> dict:
    """前端 ``DAGFlow`` 组件使用的静态 DAG 布局。

    条件边（QC → 返工 / 通过）被表示为独立的边；由运行时决定哪一条触发。
    """
    nodes: List[DagNode] = [
        DagNode("identify", "识别竞品", "Identify competitors", "collector",
                "列出目标市场中的直接竞品。", "List direct competitors in the target market."),
        DagNode("collect", "收集信息", "Collect knowledge", "collector",
                "对每个竞品收集结构化数据。", "Gather structured data per competitor."),
        DagNode("analyze", "SWOT 分析", "SWOT analysis", "analyst",
                "对每个竞品做 SWOT。", "Run SWOT per competitor."),
        DagNode("write", "撰写报告", "Write report", "writer",
                "整合所有材料,生成最终报告。", "Synthesize the final report."),
        DagNode("qc", "质量控制", "Quality control", "qc",
                "审查输出,必要时退回重做。", "Critique and route to rework if needed."),
        DagNode("done", "完成", "Done", "orchestrator",
                "报告就绪并持久化。", "Report ready and persisted."),
    ]
    edges: List[DagEdge] = [
        DagEdge("identify", "collect"),
        DagEdge("collect", "analyze"),
        DagEdge("analyze", "write"),
        DagEdge("write", "qc"),
        # 按角色定向的返工：QC 从拥有该缺陷的那个阶段重新进入。
        DagEdge("qc", "collect", "rework→collector"),
        DagEdge("qc", "analyze", "rework→analyst"),
        DagEdge("qc", "write", "rework→writer"),
        DagEdge("qc", "done", "approve"),
    ]
    return {
        "nodes": [n.__dict__ for n in nodes],
        "edges": [e.__dict__ for e in edges],
    }
