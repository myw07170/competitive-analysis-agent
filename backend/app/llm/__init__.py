"""LLM 提供方抽象（当前：火山方舟 Ark）。"""
from .volcengine import LLMClient, LLMResponse, get_llm_client

__all__ = ["LLMClient", "LLMResponse", "get_llm_client"]
