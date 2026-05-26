"""Base class for agents.

Wraps the LLM client with: tracing, JSON parsing + repair, and a
``language`` parameter resolved from the active market profile.
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
        """Call the LLM, record a trace event, return parsed JSON."""
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
    """Find the first balanced {...} block, respecting strings/escapes."""
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
    """Best-effort repair of a JSON object that was cut off mid-stream.

    Walks the text, tracks string / array / object depth, drops anything after
    the last completed value, and appends the right number of closing brackets.
    Returns a candidate JSON string, or None if there isn't even a starting
    ``{`` to work with.
    """
    start = text.find("{")
    if start < 0:
        return None
    text = text[start:]

    in_str = False
    escape = False
    stack: list[str] = []   # entries are "{" or "["
    # Track the index of the last fully-finished value at the *current* depth
    # so we can chop off any half-finished trailing key/value.
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
                # Closing a string mid-value: not necessarily a safe cut point.
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
        return text  # already balanced — caller already failed once though

    # Cut to the last safe boundary, then close any open structures.
    body = text[:last_safe].rstrip().rstrip(",")
    # Re-scan stack against the kept body (it could differ if we cut inside an
    # open structure).
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


def _parse_json_safely(text: str) -> Optional[Dict[str, Any]]:
    """Parse JSON, tolerating fences, prose wrappers, trailing commas, and truncation."""
    if not text:
        return None

    # 1) Try as-is.
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2) Strip ```json fences anywhere in the text.
    stripped = _FENCE_RE.sub("", text)
    stripped = _TRAILING_FENCE_RE.sub("", stripped).strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    # 3) Extract the first balanced {...} block.
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

    # 4) Last resort: repair a mid-stream truncation by closing open structures.
    repaired = _repair_truncated_json(stripped)
    if repaired:
        repaired = _TRAILING_COMMA_RE.sub(r"\1", repaired)
        try:
            return json.loads(repaired)
        except json.JSONDecodeError as exc:
            # Stash the repair attempt so the error message can point at it.
            _LAST_REPAIR_ATTEMPT["text"] = repaired
            _LAST_REPAIR_ATTEMPT["error"] = str(exc)
            return None
    return None


_LAST_REPAIR_ATTEMPT: Dict[str, str] = {}


def _dump_failed_response(role: str, intent: str, content: str) -> str:
    """Write the raw model response (plus repair attempt) to data/debug/."""
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

    # Also dump the repair attempt + its error, if any.
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
