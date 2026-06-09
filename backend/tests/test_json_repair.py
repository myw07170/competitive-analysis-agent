"""JSON 修复流水线测试 —— 抗幻觉韧性层。

采集器 / 分析师 / 撰写器经常返回*几乎*是 JSON 的内容；``_parse_json_safely``
能恢复被代码块围栏、文字包裹、尾随逗号、控制字符和截断的输出。
这些用例对应 ``data/debug/`` 中捕获的真实失败。
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
    # 一张 markdown 表格被原样塞进 JSON 字符串值（非常常见）。
    r = _parse_json_safely('{"body_md": "| a | b |\n| - | - |\n| 1 | 2 |"}')
    assert r is not None and "| a | b |" in r["body_md"]


def test_truncated_object_recovered():
    # 流中途截断：未配平的花括号 / 方括号会被闭合。
    r = _parse_json_safely('{"name": "X", "tiers": [{"t": 1}, {"t": 2')
    assert r is not None and r["name"] == "X"


def test_pure_garbage_returns_none():
    assert _parse_json_safely("this is not json at all") is None
    assert _parse_json_safely("") is None
