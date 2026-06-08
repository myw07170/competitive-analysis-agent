"""火山方舟 Ark LLM 客户端。

Ark 暴露一个 OpenAI 兼容的 REST API。我们对它封装了：

* 基于 tenacity 的重试（指数退避，仅幂等情况）
* 每次调用的 token 计量（汇总进追踪）
* 一个按 ``intent`` 索引返回预设结构化输出的 mock 模式
  —— 因此即便没有 Key，完整的 DAG / 追踪 / 报告界面也可演示。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Dict, List, Optional

import httpx
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from ..config import Settings, get_settings
from ..observability.logger import get_logger
from . import mocks as _mocks  # noqa: F401  （在下方注册）

log = get_logger("llm.ark")


@dataclass
class LLMResponse:
    content: str
    raw: Dict[str, Any] = field(default_factory=dict)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    model: str = ""
    mocked: bool = False


class LLMError(RuntimeError):
    pass


class LLMClient:
    """对 Ark /chat/completions 端点的轻量异步封装。"""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()

    # ---- 公共 API ----
    async def chat_json(
        self,
        *,
        system: str,
        user: str,
        intent: str,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        extra_messages: Optional[List[Dict[str, str]]] = None,
    ) -> LLMResponse:
        """调用模型并期望返回一个 JSON 对象。

        ``intent`` 纯属诊断用途 —— 供 mock 后端和追踪标签使用。
        它不影响真实的 API 调用。
        """
        if self.settings.use_mock_llm:
            payload = _mocks.respond(intent, system=system, user=user)
            return LLMResponse(
                content=json.dumps(payload, ensure_ascii=False),
                raw={"mock": True, "intent": intent},
                prompt_tokens=len(user) // 4,
                completion_tokens=len(json.dumps(payload)) // 4,
                total_tokens=(len(user) + len(json.dumps(payload))) // 4,
                model="mock",
                mocked=True,
            )

        messages: List[Dict[str, str]] = [{"role": "system", "content": system}]
        if extra_messages:
            messages.extend(extra_messages)
        messages.append({"role": "user", "content": user})

        body: Dict[str, Any] = {
            "model": self.settings.ark_model_id,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if self.settings.ark_use_json_mode:
            body["response_format"] = {"type": "json_object"}
        headers = {
            "Authorization": f"Bearer {self.settings.ark_api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self.settings.ark_base_url.rstrip('/')}/chat/completions"

        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(self.settings.ark_max_retries + 1),
            wait=wait_exponential(multiplier=0.5, min=0.5, max=4.0),
            retry=retry_if_exception_type((httpx.TimeoutException, httpx.HTTPStatusError)),
            reraise=True,
        ):
            with attempt:
                async with httpx.AsyncClient(timeout=self.settings.ark_timeout) as client:
                    resp = await client.post(url, headers=headers, json=body)
                    if resp.status_code >= 500:
                        raise httpx.HTTPStatusError(
                            f"Ark server error {resp.status_code}: {resp.text[:200]}",
                            request=resp.request,
                            response=resp,
                        )
                    if resp.status_code >= 400:
                        raise LLMError(
                            f"Ark client error {resp.status_code}: {resp.text[:500]}"
                        )
                    data = resp.json()
                    choice = data["choices"][0]["message"]["content"]
                    usage = data.get("usage", {}) or {}
                    return LLMResponse(
                        content=choice,
                        raw=data,
                        prompt_tokens=int(usage.get("prompt_tokens", 0)),
                        completion_tokens=int(usage.get("completion_tokens", 0)),
                        total_tokens=int(usage.get("total_tokens", 0)),
                        model=self.settings.ark_model_id,
                        mocked=False,
                    )

        # 不可达 —— AsyncRetrying 在重试耗尽时会重新抛出异常。
        raise LLMError("LLM call exhausted retries")


@lru_cache(maxsize=1)
def get_llm_client() -> LLMClient:
    return LLMClient()
