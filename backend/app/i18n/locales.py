"""Server-side locale strings.

The frontend has its own i18n bundle; this one is used by the agents for any
text they emit into the report (section labels, default headings, etc.).
"""
from __future__ import annotations

from typing import Dict


LOCALES: Dict[str, Dict[str, str]] = {
    "zh-CN": {
        "report.title": "竞品分析报告",
        "section.executive_summary": "执行摘要",
        "section.market_overview": "市场概览",
        "section.function_comparison": "功能对比",
        "section.pricing_comparison": "定价对比",
        "section.user_comparison": "用户画像对比",
        "section.swot": "SWOT 分析",
        "section.recommendations": "战略建议",
        "label.source": "来源",
        "label.mock_mode": "演示模式(未配置真实模型)",
        "label.market": "目标市场",
        "label.product": "目标产品",
        "agent.collector": "信息收集 Agent",
        "agent.analyst": "分析 Agent",
        "agent.writer": "报告撰写 Agent",
        "agent.qc": "质控 Agent",
    },
    "en-US": {
        "report.title": "Competitive Analysis Report",
        "section.executive_summary": "Executive Summary",
        "section.market_overview": "Market Overview",
        "section.function_comparison": "Function Comparison",
        "section.pricing_comparison": "Pricing Comparison",
        "section.user_comparison": "User-Profile Comparison",
        "section.swot": "SWOT Analysis",
        "section.recommendations": "Recommendations",
        "label.source": "Source",
        "label.mock_mode": "Mock mode (no live model configured)",
        "label.market": "Target market",
        "label.product": "Target product",
        "agent.collector": "Collector Agent",
        "agent.analyst": "Analyst Agent",
        "agent.writer": "Writer Agent",
        "agent.qc": "QC Agent",
    },
}


def get_locale(locale: str) -> Dict[str, str]:
    return LOCALES.get(locale, LOCALES["en-US"])
