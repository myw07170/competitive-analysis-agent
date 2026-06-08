"""智能体基类。

为 LLM 客户端封装了：追踪、JSON 解析 + 修复，以及一个由当前激活市场画像
解析得到的 ``language`` 参数。
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Dict, Optional

from ..config import get_settings
from ..llm import LLMResponse, get_llm_client
from ..market import MarketProfile
from ..observability.logger import get_logger
from ..observability.tracer import get_tracer


class BaseAgent:
    role: str = "base"

    def __init__(self, market: MarketProfile) -> None:
        self.market = market
        self.llm = get_llm_client()
        self.log = get_logger(f"agent.{self.role}")

    @property
    def language_name(self) -> str:
        return {"zh": "Simplified Chinese (简体中文)", "en": "English"}.get(
            self.market.language, self.market.language
        )

    async def _call(
        self,
        *,
        intent: str,
        system: str,
        user: str,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        decision_label: str = "",
    ) -> Dict[str, Any]:
        """调用 LLM，记录一条追踪事件，返回解析后的 JSON。"""
        tracer = get_tracer()
        with tracer.span(self.role, intent) as ev:
            ev.prompt_system = system
            ev.prompt_user = user
            ev.decision = decision_label or intent

            resp: LLMResponse = await self.llm.chat_json(
                system=system, user=user, intent=intent,
                temperature=temperature, max_tokens=max_tokens,
            )
            ev.response = resp.content
            ev.prompt_tokens = resp.prompt_tokens
            ev.completion_tokens = resp.completion_tokens
            ev.total_tokens = resp.total_tokens
            ev.model = resp.model
            if resp.mocked:
                ev.extras["mocked"] = True

            parsed = _parse_json_safely(resp.content)
            if parsed is None:
                ev.status = "error"
                ev.extras["parse_error"] = resp.content[:500]
                debug_path = _dump_failed_response(self.role, intent, resp.content)
                preview = (resp.content or "").strip()
                preview = (preview[:400] + "…") if len(preview) > 400 else preview
                self.log.error(
                    f"non-JSON response (intent={intent}, tokens={resp.total_tokens}, "
                    f"finish={resp.raw.get('choices', [{}])[0].get('finish_reason', '?')}, "
                    f"len={len(resp.content)}). Full text saved to {debug_path}."
                )
                raise ValueError(
                    f"Agent {self.role} produced non-JSON for intent {intent!r}. "
                    f"Full response written to {debug_path}. First 300 chars: {preview[:300]!r}"
                )
            return parsed


_FENCE_RE = re.compile(r"```(?:json|JSON)?\s*", re.MULTILINE)
_TRAILING_FENCE_RE = re.compile(r"\s*```\s*$", re.MULTILINE)
_TRAILING_COMMA_RE = re.compile(r",(\s*[}\]])")


def _extract_balanced_json(text: str) -> Optional[str]:
    """找到第一个配平的 {...} 块，正确处理字符串 / 转义。"""
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]
    return None


def _repair_truncated_json(text: str) -> Optional[str]:
    """尽力修复一个在流中途被截断的 JSON 对象。

    遍历文本，跟踪字符串 / 数组 / 对象的深度，丢弃最后一个完整值之后的所有内容，
    并补上正确数量的闭合括号。返回一个候选 JSON 字符串，若连一个起始的 ``{``
    都没有则返回 None。
    """
    start = text.find("{")
    if start < 0:
        return None
    text = text[start:]

    in_str = False
    escape = False
    stack: list[str] = []   # 元素为 "{" 或 "["
    # 跟踪*当前*深度下最后一个完全结束的值的索引，
    # 以便我们能砍掉任何尾部未完成的键 / 值。
    last_safe = 0

    i = 0
    while i < len(text):
        ch = text[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
                # 在值中途关闭一个字符串：不一定是安全的截断点。
            i += 1
            continue

        if ch == '"':
            in_str = True
        elif ch == "{":
            stack.append("{")
        elif ch == "[":
            stack.append("[")
        elif ch in "}]":
            if stack:
                stack.pop()
                last_safe = i + 1
        elif ch == ",":
            last_safe = i + 1
        i += 1

    if not stack and last_safe == len(text):
        return text  # 已经配平 —— 不过调用方此前已失败过一次

    # 截到最后一个安全边界，再闭合任何未关闭的结构。
    body = text[:last_safe].rstrip().rstrip(",")
    # 针对保留下来的 body 重新扫描栈（若我们在某个未关闭的结构内部截断，
    # 结果可能不同）。
    depth_obj = 0
    depth_arr = 0
    in_str = False
    escape = False
    for ch in body:
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth_obj += 1
        elif ch == "}":
            depth_obj -= 1
        elif ch == "[":
            depth_arr += 1
        elif ch == "]":
            depth_arr -= 1

    if in_str:
        body += '"'
    body += "]" * max(depth_arr, 0)
    body += "}" * max(depth_obj, 0)
    return body


def _escape_unescaped_controls_in_strings(text: str) -> str:
    """转义出现在 JSON 字符串*内部*的字面换行 / 制表 / 回车字符。

    LLM 经常产出多行的 markdown 值，例如::

        "body_md": "| a | b |
                    | - | - |
                    | 1 | 2 |"

    这是非法的 JSON。本函数遍历文本，跟踪"是否处于字符串内部"的状态，
    并把原始的 \\n / \\r / \\t 替换为其 JSON 转义序列。字符串之外的字符
    （包括字段间的空白）保持不变。
    """
    out: list[str] = []
    in_str = False
    escape = False
    for ch in text:
        if in_str:
            if escape:
                out.append(ch)
                escape = False
                continue
            if ch == "\\":
                out.append(ch)
                escape = True
                continue
            if ch == '"':
                out.append(ch)
                in_str = False
                continue
            if ch == "\n":
                out.append("\\n")
                continue
            if ch == "\r":
                out.append("\\r")
                continue
            if ch == "\t":
                out.append("\\t")
                continue
            out.append(ch)
        else:
            if ch == '"':
                in_str = True
            out.append(ch)
    return "".join(out)


def _parse_json_safely(text: str) -> Optional[Dict[str, Any]]:
    """解析 JSON，容忍代码块围栏、文字包裹、尾随逗号和截断。"""
    if not text:
        return None

    # 1) 原样尝试。
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2) 剥除文本中任意位置的 ```json 围栏。
    stripped = _FENCE_RE.sub("", text)
    stripped = _TRAILING_FENCE_RE.sub("", stripped).strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    # 3) 提取第一个配平的 {...} 块。
    block = _extract_balanced_json(stripped)
    if block:
        try:
            return json.loads(block)
        except json.JSONDecodeError:
            cleaned = _TRAILING_COMMA_RE.sub(r"\1", block)
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError:
                pass

    # 4) 转义字符串值内部的字面换行 / 制表符 —— 当 markdown 表格出现在
    #    JSON 字符串字段中时，这是常见的 LLM 失败。
    escaped = _escape_unescaped_controls_in_strings(stripped)
    if escaped != stripped:
        try:
            return json.loads(escaped)
        except json.JSONDecodeError:
            block2 = _extract_balanced_json(escaped)
            if block2:
                try:
                    return json.loads(block2)
                except json.JSONDecodeError:
                    cleaned2 = _TRAILING_COMMA_RE.sub(r"\1", block2)
                    try:
                        return json.loads(cleaned2)
                    except json.JSONDecodeError:
                        pass

    # 5) 最后手段：通过闭合未关闭的结构来修复流中途的截断。
    repaired = _repair_truncated_json(escaped if escaped != stripped else stripped)
    if repaired:
        repaired = _TRAILING_COMMA_RE.sub(r"\1", repaired)
        try:
            return json.loads(repaired)
        except json.JSONDecodeError as exc:
            # 暂存这次修复尝试，使错误消息能指向它。
            _LAST_REPAIR_ATTEMPT["text"] = repaired
            _LAST_REPAIR_ATTEMPT["error"] = str(exc)
            return None
    return None


_LAST_REPAIR_ATTEMPT: Dict[str, str] = {}


def _dump_failed_response(role: str, intent: str, content: str) -> str:
    """把原始的模型响应（以及修复尝试）写入 data/debug/。"""
    settings = get_settings()
    debug_dir = Path(settings.data_dir) / "debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    ts = int(time.time() * 1000)
    base = f"{ts}_{role}_{intent.replace('.', '_')}"
    path = debug_dir / f"{base}.txt"
    try:
        path.write_text(content or "", encoding="utf-8")
    except Exception:
        return "<write-failed>"

    # 如有，也一并转储修复尝试及其错误。
    if _LAST_REPAIR_ATTEMPT.get("text"):
        repair_path = debug_dir / f"{base}.repaired.json"
        try:
            repair_path.write_text(
                _LAST_REPAIR_ATTEMPT["text"] + "\n\n--- json error ---\n" +
                _LAST_REPAIR_ATTEMPT.get("error", ""),
                encoding="utf-8",
            )
        except Exception:
            pass
        _LAST_REPAIR_ATTEMPT.clear()
    return str(path)
