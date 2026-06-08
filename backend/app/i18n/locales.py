"""服务端 locale 字符串。

前端有自己的 i18n 语言包；这一份由智能体用于它们写入报告的任何文本
（章节标签、默认标题等）。
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
        # ---- HTML / 报告渲染器相关键 ----
        "form.product.label": "目标产品",
        "report.executive": "执行摘要",
        "report.competitors": "竞品概览",
        "report.sources": "数据来源",
        "report.comparison": "横向对比",
        "report.download_pdf": "打印 / 保存为 PDF",
        "comparison.feature": "功能 / 能力",
        "comparison.pricing": "定价分层",
        "comparison.user": "用户画像",
        "comparison.coverage": "功能覆盖数",
        "comparison.sources": "数据来源数",
        "comparison.entry_price": "入门月费",
        "comparison.keywords": "关键词卡片",
        "comparison.empty": "暂无可对比数据",
        "comparison.charts": "可视化图表",
        "comparison.self": "本品",
        "metrics.elapsed": "总耗时",
        "metrics.tokens": "总 Token",
        "metrics.llm_calls": "LLM 调用",
        "metrics.completeness": "Schema 完整度",
        "metrics.avg_sources": "平均来源数 / 竞品",
        "metrics.iterations": "QC 迭代",
        "metrics.rework": "重做次数",
        "source.confidence": "置信度",
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
        # ---- HTML / 报告渲染器相关键 ----
        "form.product.label": "Target product",
        "report.executive": "Executive Summary",
        "report.competitors": "Competitors at a glance",
        "report.sources": "Sources",
        "report.comparison": "Comparison",
        "report.download_pdf": "Print / Save as PDF",
        "comparison.feature": "Feature / Capability",
        "comparison.pricing": "Pricing tiers",
        "comparison.user": "User profile",
        "comparison.coverage": "Function coverage",
        "comparison.sources": "Source count",
        "comparison.entry_price": "Entry monthly price",
        "comparison.keywords": "Keyword cards",
        "comparison.empty": "No comparable data",
        "comparison.charts": "Visualisations",
        "comparison.self": "Your product",
        "metrics.elapsed": "Elapsed",
        "metrics.tokens": "Total tokens",
        "metrics.llm_calls": "LLM calls",
        "metrics.completeness": "Schema completeness",
        "metrics.avg_sources": "Avg sources / competitor",
        "metrics.iterations": "QC iterations",
        "metrics.rework": "Rework count",
        "source.confidence": "Confidence",
    },
}


def get_locale(locale: str) -> Dict[str, str]:
    return LOCALES.get(locale, LOCALES["en-US"])
