"""智能体实现。

四个智能体共享一个小型基类，由它处理 LLM 调用 + 追踪。
智能体通过编排层的 ``GraphState`` 通信 —— 绝不通过相互 import。
"""
from .analyst import AnalystAgent
from .base import BaseAgent
from .collector import CollectorAgent
from .qc import QCAgent
from .writer import WriterAgent

__all__ = ["BaseAgent", "CollectorAgent", "AnalystAgent", "WriterAgent", "QCAgent"]
