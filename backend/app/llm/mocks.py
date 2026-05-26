"""Mock LLM outputs used when no Ark API key is configured.

Keyed by ``intent`` so each agent receives a shape compatible with its
expected schema. The mock data is deliberately plausible (not just lorem
ipsum) so the demo UI looks real.

The user's product name and market are extracted from the user prompt so
the mock output personalizes a little — enough to feel real on a demo.
"""
from __future__ import annotations

import re
from typing import Any, Callable, Dict


_REGISTRY: Dict[str, Callable[..., Dict[str, Any]]] = {}


def register(intent: str) -> Callable[[Callable[..., Dict[str, Any]]], Callable[..., Dict[str, Any]]]:
    def _wrap(fn: Callable[..., Dict[str, Any]]) -> Callable[..., Dict[str, Any]]:
        _REGISTRY[intent] = fn
        return fn
    return _wrap


def respond(intent: str, *, system: str, user: str) -> Dict[str, Any]:
    fn = _REGISTRY.get(intent)
    if fn is None:
        return {"_mock": True, "_intent": intent, "note": "no mock registered"}
    return fn(system=system, user=user)


def _detect_market(text: str) -> str:
    if re.search(r"market\s*[:=]?\s*us", text, re.IGNORECASE) or "en-US" in text:
        return "us"
    return "cn"


def _detect_product(text: str) -> str:
    m = re.search(r"product\s*[:=]\s*([^\n]+)", text, re.IGNORECASE)
    if m:
        return m.group(1).strip().strip(",.;:\"'")
    return "ProductX"


# ---------------------------------------------------------------------------
# Collector
# ---------------------------------------------------------------------------
@register("collector.identify_competitors")
def _identify(system: str, user: str) -> Dict[str, Any]:
    market = _detect_market(user)
    if market == "us":
        comps = [
            {"name": "Notion", "homepage": "https://www.notion.so", "rationale": "Direct workspace competitor"},
            {"name": "Coda", "homepage": "https://coda.io", "rationale": "Doc+DB hybrid alternative"},
            {"name": "ClickUp", "homepage": "https://clickup.com", "rationale": "All-in-one productivity"},
        ]
    else:
        comps = [
            {"name": "飞书", "homepage": "https://www.feishu.cn", "rationale": "字节系一体化协作"},
            {"name": "钉钉", "homepage": "https://www.dingtalk.com", "rationale": "阿里系企业协作头部"},
            {"name": "语雀", "homepage": "https://www.yuque.com", "rationale": "蚂蚁集团知识库"},
        ]
    return {"competitors": comps}


@register("collector.gather_competitor")
def _gather(system: str, user: str) -> Dict[str, Any]:
    market = _detect_market(user)
    m = re.search(r"competitor\s*[:=]\s*([^\n]+)", user, re.IGNORECASE)
    name = m.group(1).strip().strip(",.;:\"'") if m else "Notion"

    if market == "us":
        return {
            "name": name,
            "homepage": "https://example.com",
            "short_description": f"{name} is an integrated workspace combining docs, databases, and tasks.",
            "market_position": "Mid-market and SMB knowledge work, expanding into enterprise.",
            "function_tree": {
                "root_name": "Capabilities",
                "nodes": [
                    {"name": "Docs", "description": "Block-based documents",
                     "category": "core", "maturity": "ga", "sources": [
                         {"kind": "web", "title": f"{name} docs page",
                          "url": "https://example.com/docs",
                          "snippet": f"{name} offers block-based docs.", "confidence": 0.9}],
                     "children": [
                         {"name": "Real-time collaboration", "maturity": "ga", "sources": [
                             {"kind": "web", "title": "Collab page", "url": "https://example.com/collab",
                              "snippet": "Real-time multiplayer editing.", "confidence": 0.85}]},
                         {"name": "Templates", "maturity": "ga", "sources": [
                             {"kind": "web", "title": "Templates", "url": "https://example.com/templates",
                              "snippet": "5000+ community templates.", "confidence": 0.8}]},
                     ]},
                    {"name": "Databases", "description": "Structured data tables",
                     "maturity": "ga", "sources": [
                         {"kind": "web", "title": "Databases", "url": "https://example.com/db",
                          "snippet": "Tables with custom properties.", "confidence": 0.9}]},
                    {"name": "AI", "description": "LLM-powered writing and Q&A",
                     "maturity": "ga", "sources": [
                         {"kind": "web", "title": "AI page", "url": "https://example.com/ai",
                          "snippet": "Built-in AI for summarization and writing.", "confidence": 0.85}]},
                ],
            },
            "pricing": {
                "summary": "Freemium with three paid tiers; seat-based.",
                "has_free_tier": True,
                "has_enterprise": True,
                "tiers": [
                    {"name": "Free", "monthly_price": 0, "currency": "USD",
                     "included_features": ["Unlimited blocks for individuals"],
                     "sources": [{"kind": "web", "title": "Pricing", "url": "https://example.com/pricing",
                                  "snippet": "Free for personal use.", "confidence": 0.9}]},
                    {"name": "Plus", "monthly_price": 10, "annual_price": 96, "currency": "USD",
                     "included_features": ["Unlimited blocks for teams", "30-day page history"],
                     "sources": [{"kind": "web", "title": "Pricing", "url": "https://example.com/pricing",
                                  "snippet": "$10/seat/mo.", "confidence": 0.9}]},
                    {"name": "Business", "monthly_price": 18, "annual_price": 180, "currency": "USD",
                     "included_features": ["SSO/SAML", "Private teamspaces"],
                     "sources": [{"kind": "web", "title": "Pricing", "url": "https://example.com/pricing",
                                  "snippet": "$18/seat/mo.", "confidence": 0.9}]},
                    {"name": "Enterprise", "currency": "USD",
                     "included_features": ["Audit log", "SCIM", "Customer success"],
                     "sources": [{"kind": "web", "title": "Enterprise",
                                  "url": "https://example.com/enterprise",
                                  "snippet": "Custom pricing.", "confidence": 0.85}]},
                ],
            },
            "user_profile": {
                "primary_segment": "Knowledge workers in tech & startups",
                "segments": [
                    {"name": "Startups & SMB", "company_size": "smb",
                     "industries": ["Software", "Design", "Media"],
                     "geographies": ["North America", "Europe"],
                     "use_cases": ["Wiki", "Project tracking", "Notes"],
                     "pain_points": ["Pricing per seat scales painfully"],
                     "representative_quotes": [
                         {"value": "We replaced Confluence and Asana with it.",
                          "sources": [{"kind": "interview", "title": "Synthetic interview #1",
                                       "snippet": "Replaced two tools.", "confidence": 0.6}]}],
                     "sources": [{"kind": "web", "title": "Case studies",
                                  "url": "https://example.com/customers",
                                  "snippet": "Used by startups.", "confidence": 0.8}]},
                    {"name": "Enterprise", "company_size": "enterprise",
                     "industries": ["Finance", "Healthcare"],
                     "geographies": ["North America"],
                     "use_cases": ["Internal wiki"],
                     "pain_points": ["Limited admin controls vs Confluence"],
                     "sources": [{"kind": "web", "title": "Enterprise case studies",
                                  "url": "https://example.com/enterprise/customers",
                                  "snippet": "Enterprise customers.", "confidence": 0.75}]},
                ],
                "estimated_user_base": "30M+ users (vendor-reported)",
                "nps_or_rating": "4.7/5 (G2)",
                "sources": [{"kind": "web", "title": "G2 reviews",
                             "url": "https://g2.com/products/example",
                             "snippet": "4.7 / 5 stars.", "confidence": 0.85}],
            },
            "sources": [
                {"kind": "web", "title": "Official homepage", "url": "https://example.com",
                 "snippet": "Product landing page.", "confidence": 0.95},
                {"kind": "web", "title": "Pricing", "url": "https://example.com/pricing",
                 "snippet": "Pricing.", "confidence": 0.9},
                {"kind": "web", "title": "G2 reviews",
                 "url": "https://g2.com/products/example",
                 "snippet": "4.7 / 5 stars.", "confidence": 0.85},
            ],
        }

    # ---- CN ----
    return {
        "name": name,
        "homepage": "https://example.cn",
        "short_description": f"{name} 是一款覆盖文档、表格、IM、视频会议的一体化协作平台。",
        "market_position": "中国大陆 SMB 与中大型企业市场,头部协作工具之一。",
        "function_tree": {
            "root_name": "能力",
            "nodes": [
                {"name": "文档", "description": "在线文档与知识库",
                 "category": "core", "maturity": "ga",
                 "sources": [{"kind": "web", "title": "官网文档介绍",
                              "url": "https://example.cn/docs",
                              "snippet": "提供在线文档与多人协作。", "confidence": 0.9}],
                 "children": [
                     {"name": "多人实时协作", "maturity": "ga", "sources": [
                         {"kind": "web", "title": "协作页", "url": "https://example.cn/collab",
                          "snippet": "实时多人编辑。", "confidence": 0.85}]},
                     {"name": "模板市场", "maturity": "ga", "sources": [
                         {"kind": "web", "title": "模板", "url": "https://example.cn/templates",
                          "snippet": "数百个企业模板。", "confidence": 0.8}]},
                 ]},
                {"name": "IM", "description": "企业级即时通讯",
                 "maturity": "ga", "sources": [{"kind": "web", "title": "IM 介绍",
                                                "url": "https://example.cn/im",
                                                "snippet": "群聊、文件、机器人。", "confidence": 0.9}]},
                {"name": "视频会议", "maturity": "ga",
                 "sources": [{"kind": "web", "title": "会议",
                              "url": "https://example.cn/meeting",
                              "snippet": "高清视频会议。", "confidence": 0.85}]},
                {"name": "AI 助手", "description": "大模型驱动的智能助手",
                 "maturity": "ga", "sources": [
                     {"kind": "web", "title": "AI", "url": "https://example.cn/ai",
                      "snippet": "支持摘要、问答、写作。", "confidence": 0.8}]},
            ],
        },
        "pricing": {
            "summary": "提供免费版,按用户数订阅;企业版商务洽谈。",
            "has_free_tier": True,
            "has_enterprise": True,
            "tiers": [
                {"name": "免费版", "monthly_price": 0, "currency": "CNY",
                 "included_features": ["基础协作", "50 人以内"],
                 "sources": [{"kind": "web", "title": "价格", "url": "https://example.cn/pricing",
                              "snippet": "免费版。", "confidence": 0.9}]},
                {"name": "标准版", "monthly_price": 50, "annual_price": 480, "currency": "CNY",
                 "included_features": ["无人数上限", "高级权限"],
                 "sources": [{"kind": "web", "title": "价格", "url": "https://example.cn/pricing",
                              "snippet": "50 元/人/月。", "confidence": 0.85}]},
                {"name": "旗舰版", "monthly_price": 120, "currency": "CNY",
                 "included_features": ["SSO", "审计日志"],
                 "sources": [{"kind": "web", "title": "价格", "url": "https://example.cn/pricing",
                              "snippet": "120 元/人/月。", "confidence": 0.8}]},
                {"name": "企业版", "currency": "CNY",
                 "included_features": ["私有化", "专属客户成功"],
                 "sources": [{"kind": "web", "title": "企业版",
                              "url": "https://example.cn/enterprise",
                              "snippet": "商务洽谈。", "confidence": 0.8}]},
            ],
        },
        "user_profile": {
            "primary_segment": "中大型企业的知识工作者",
            "segments": [
                {"name": "互联网与科技公司", "company_size": "mid_market",
                 "industries": ["互联网", "金融科技"], "geographies": ["中国大陆"],
                 "use_cases": ["知识库", "项目管理", "OKR"],
                 "pain_points": ["与既有 OA/HR 系统集成成本高"],
                 "representative_quotes": [
                     {"value": "我们用它替代了 Confluence 和钉钉文档。",
                      "sources": [{"kind": "interview", "title": "模拟用户访谈 #1",
                                   "snippet": "替代两套工具。", "confidence": 0.6}]}],
                 "sources": [{"kind": "web", "title": "客户案例",
                              "url": "https://example.cn/customers",
                              "snippet": "互联网客户众多。", "confidence": 0.8}]},
                {"name": "教育与政企", "company_size": "enterprise",
                 "industries": ["教育", "政府"], "geographies": ["中国大陆"],
                 "use_cases": ["公文流转", "通知发布"],
                 "pain_points": ["合规审计要求高"],
                 "sources": [{"kind": "web", "title": "政企案例",
                              "url": "https://example.cn/gov",
                              "snippet": "政企客户案例。", "confidence": 0.75}]},
            ],
            "estimated_user_base": "千万级用户(厂商披露)",
            "nps_or_rating": "应用市场 4.6 / 5",
            "sources": [{"kind": "web", "title": "应用市场",
                         "url": "https://example.cn/reviews",
                         "snippet": "4.6 / 5 评分。", "confidence": 0.8}],
        },
        "sources": [
            {"kind": "web", "title": "官网首页", "url": "https://example.cn",
             "snippet": "产品落地页。", "confidence": 0.95},
            {"kind": "web", "title": "价格页", "url": "https://example.cn/pricing",
             "snippet": "价格说明。", "confidence": 0.9},
            {"kind": "web", "title": "用户评价", "url": "https://example.cn/reviews",
             "snippet": "4.6 / 5 评分。", "confidence": 0.8},
        ],
    }


@register("collector.rework")
def _gather_rework(system: str, user: str) -> Dict[str, Any]:
    """A second-pass collector mock — returns a richer payload with more sources,
    so the QC feedback loop visibly improves the output."""
    base = _gather(system=system, user=user)
    extra_src = {"kind": "web", "title": "Additional press coverage",
                 "url": "https://example.com/news",
                 "snippet": "Additional coverage gathered during rework.",
                 "confidence": 0.8}
    base.setdefault("sources", []).append(extra_src)
    # Boost source count on pricing tiers
    for tier in base.get("pricing", {}).get("tiers", []):
        tier.setdefault("sources", []).append(extra_src)
    return base


# ---------------------------------------------------------------------------
# Analyst
# ---------------------------------------------------------------------------
@register("analyst.swot")
def _swot(system: str, user: str) -> Dict[str, Any]:
    market = _detect_market(user)
    if market == "us":
        return {
            "strengths": [
                {"value": "Strong brand and large community",
                 "sources": [{"kind": "web", "title": "G2 reviews",
                              "url": "https://g2.com/products/example",
                              "snippet": "4.7 / 5.", "confidence": 0.85}]},
                {"value": "Block-based editor is best-in-class",
                 "sources": [{"kind": "web", "title": "Editor review",
                              "url": "https://example.com/blog",
                              "snippet": "Reviewers praise the editor.",
                              "confidence": 0.75}]},
            ],
            "weaknesses": [
                {"value": "Per-seat pricing scales poorly for large teams",
                 "sources": [{"kind": "web", "title": "Pricing",
                              "url": "https://example.com/pricing",
                              "snippet": "Seat-based pricing.", "confidence": 0.85}]},
            ],
            "opportunities": [
                {"value": "Vertical templates (legal, healthcare) underserved",
                 "sources": [{"kind": "llm_prior", "title": "Analyst inference",
                              "snippet": "No vertical SKU.", "confidence": 0.55}]},
            ],
            "threats": [
                {"value": "AI-native competitors compressing margins",
                 "sources": [{"kind": "web", "title": "Industry coverage",
                              "url": "https://example.com/news",
                              "snippet": "AI-native entrants.", "confidence": 0.7}]},
            ],
        }
    return {
        "strengths": [
            {"value": "本土化体验与生态打通完善",
             "sources": [{"kind": "web", "title": "应用市场",
                          "url": "https://example.cn/reviews",
                          "snippet": "本土集成丰富。", "confidence": 0.85}]},
            {"value": "IM + 文档 + 视频会议一体化",
             "sources": [{"kind": "web", "title": "产品介绍",
                          "url": "https://example.cn",
                          "snippet": "一体化协作。", "confidence": 0.8}]},
        ],
        "weaknesses": [
            {"value": "海外市场存在感弱",
             "sources": [{"kind": "llm_prior", "title": "分析师推断",
                          "snippet": "海外覆盖少。", "confidence": 0.6}]},
        ],
        "opportunities": [
            {"value": "AI 原生工作流仍有差异化空间",
             "sources": [{"kind": "web", "title": "AI 介绍",
                          "url": "https://example.cn/ai",
                          "snippet": "AI 功能尚可深化。", "confidence": 0.7}]},
        ],
        "threats": [
            {"value": "同类厂商加速跟进 AI 能力",
             "sources": [{"kind": "web", "title": "行业报道",
                          "url": "https://example.cn/news",
                          "snippet": "行业 AI 化加速。", "confidence": 0.7}]},
        ],
    }


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------
@register("writer.report")
def _report(system: str, user: str) -> Dict[str, Any]:
    market = _detect_market(user)
    product = _detect_product(user)
    if market == "us":
        return {
            "title": f"Competitive Landscape: {product} (US Market)",
            "executive_summary_md": (
                f"This report benchmarks **{product}** against three direct competitors in the "
                "US knowledge-work market. Across function tree, pricing, and user profile axes, "
                "the leading vendors converge on block-based docs + structured data + AI; the "
                "remaining differentiation lies in pricing flexibility and enterprise admin depth."
            ),
            "sections": [
                {"heading": "Market overview",
                 "body_md": "The US knowledge-work tooling market is mature and AI-native entrants are "
                             "compressing per-seat economics. [^src_market1]",
                 "sources": []},
                {"heading": "Function comparison",
                 "body_md": "All three competitors cover Docs + Databases + AI at GA. Differences "
                             "appear in templating ecosystems and enterprise admin features.",
                 "sources": []},
                {"heading": "Pricing comparison",
                 "body_md": "Pricing converges on $10–$18 per seat / month with custom enterprise "
                             "tiers above. Free tiers exist for all three.",
                 "sources": []},
                {"heading": "User-profile comparison",
                 "body_md": "Primary segments lean SMB / mid-market for tech; enterprise penetration "
                             "is partial.",
                 "sources": []},
                {"heading": "Recommendations",
                 "body_md": "1. Differentiate via vertical templates.  \n"
                             "2. Lead with AI-native workflows, not bolt-ons.  \n"
                             "3. Offer flat-rate enterprise pricing to break the per-seat ceiling.",
                 "sources": []},
            ],
        }
    return {
        "title": f"竞品分析报告:{product}(中国市场)",
        "executive_summary_md": (
            f"本报告针对 **{product}** 在中国市场的三家主要竞品,从功能树、定价模型、用户画像三个"
            "维度进行对比分析。整体来看,头部竞品在 IM、文档、视频会议一体化方面已高度收敛,"
            "差异化主要来自 AI 能力深度与垂直行业模板。"
        ),
        "sections": [
            {"heading": "市场概览",
             "body_md": "中国协作工具市场进入存量竞争阶段,AI 原生能力成为新的竞争焦点。[^src_m1]",
             "sources": []},
            {"heading": "功能对比",
             "body_md": "三家竞品在 IM + 文档 + 视频会议 + AI 四大基础能力上已覆盖完整,差异体现在"
                         "模板生态与企业管控深度上。",
             "sources": []},
            {"heading": "定价对比",
             "body_md": "标准版价格在 50–120 元 / 人 / 月之间,均提供企业版商务洽谈。",
             "sources": []},
            {"heading": "用户画像对比",
             "body_md": "互联网、科技与教育政企是主要客群,中大型企业渗透率持续提升。",
             "sources": []},
            {"heading": "建议",
             "body_md": "1. 深化垂直行业模板(法律、医疗等)。  \n"
                         "2. 以 AI 原生工作流为差异化卖点。  \n"
                         "3. 针对大客户提供更灵活的非按席位计价。",
             "sources": []},
        ],
    }


# ---------------------------------------------------------------------------
# QC
# ---------------------------------------------------------------------------
@register("qc.review")
def _qc(system: str, user: str) -> Dict[str, Any]:
    """First QC pass — usually returns one MAJOR finding to demonstrate the loop.

    The orchestrator inspects the ``iteration`` counter (passed via prompt) and
    asks ``qc.review_final`` once rework is done.
    """
    # If the prompt indicates this is the rework iteration, approve.
    lower_user = user.lower()
    if "iteration: 1" in lower_user or "iteration: 2" in lower_user:
        return {
            "iteration": 1,
            "decision": "approve",
            "summary": "Rework addressed the missing pricing sources. Approving.",
            "findings": [],
        }
    return {
        "iteration": 0,
        "decision": "rework",
        "summary": "Pricing tiers lack sufficient distinct sources; please re-collect.",
        "findings": [
            {
                "target_agent": "collector",
                "target_path": "competitors[*].pricing.tiers[*].sources",
                "severity": "major",
                "issue": "Some pricing tiers cite only one source — below the credibility threshold.",
                "suggested_fix": "Add at least one additional independent source per pricing tier.",
            }
        ],
    }
