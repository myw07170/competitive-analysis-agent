"""Robots.txt 合规辅助函数（合规维度）。"""
from __future__ import annotations

import urllib.robotparser

from app.agents.qc import _looks_placeholder


def test_placeholder_hosts_flagged():
    assert _looks_placeholder("https://example.com/pricing")
    assert _looks_placeholder("http://sub.example.org/x")
    assert _looks_placeholder("https://localhost:8000")
    assert _looks_placeholder("http://127.0.0.1/admin")


def test_real_hosts_not_flagged():
    assert not _looks_placeholder("https://g2.com/products/notion")
    assert not _looks_placeholder("https://www.notion.so/pricing")
    assert not _looks_placeholder("https://feishu.cn")


def test_robotparser_disallow_is_respected():
    # 对采集器所依赖的标准库解析器做基本校验。
    rp = urllib.robotparser.RobotFileParser()
    rp.parse([
        "User-agent: *",
        "Disallow: /private",
    ])
    assert rp.can_fetch("CompetitiveAnalysisAgent/1.0", "https://x.com/public")
    assert not rp.can_fetch("CompetitiveAnalysisAgent/1.0", "https://x.com/private/x")
