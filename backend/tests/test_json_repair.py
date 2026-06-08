"""JSON-repair pipeline tests — the hallucination-resilience layer.

The collector/analyst/writer frequently return *almost* JSON; ``_parse_json_safely``
recovers fenced, prose-wrapped, trailing-comma, control-char, and truncated
outputs. These cases mirror real failures captured in ``data/debug/``.
"""
from __future__ import annotations

from app.agents.base import _parse_json_safely


def test_plain_object():
    assert _parse_json_safely('{"a": 1, "b": "x"}') == {"a": 1, "b": "x"}


def test_code_fence_stripped():
    assert _parse_json_safely('```json\n{"a": 1}\n```')["a"] == 1


def test_prose_wrapped_object():
    assert _parse_json_safely('Sure, here you go: {"a": 1} — done.')["a"] == 1


def test_trailing_comma_repaired():
    assert _parse_json_safely('{"a": 1, "b": 2,}')["b"] == 2


def test_raw_newline_in_string_escaped():
    # A markdown table dropped raw into a JSON string value (very common).
    r = _parse_json_safely('{"body_md": "| a | b |\n| - | - |\n| 1 | 2 |"}')
    assert r is not None and "| a | b |" in r["body_md"]


def test_truncated_object_recovered():
    # Mid-stream truncation: unbalanced braces/brackets are closed.
    r = _parse_json_safely('{"name": "X", "tiers": [{"t": 1}, {"t": 2')
    assert r is not None and r["name"] == "X"


def test_pure_garbage_returns_none():
    assert _parse_json_safely("this is not json at all") is None
    assert _parse_json_safely("") is None
