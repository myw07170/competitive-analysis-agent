"""Standalone HTML rendering of a FinalReport.

Produces a single self-contained HTML document with inline CSS / JS so the
user can preview the analysis report in their browser or download it as a
single ``.html`` file without any external dependencies. Includes a small
amount of vanilla JS for tab switching, citation anchors, and section
collapsing — these are progressive enhancements; the document remains fully
readable with JavaScript disabled.

This module is deliberately self-contained: it depends only on the
``FinalReport`` schema and the standard library.
"""
from __future__ import annotations

import html
import json
import re
from typing import Iterable, List, Optional

from .i18n import get_locale
from .schema import (
    CompetitorKnowledge,
    ComparisonMatrix,
    FinalReport,
    SourceRef,
)


_CITE_RE = re.compile(r"\[\^(src_[A-Za-z0-9_]+)\]")


def _short_id(sid: str) -> str:
    tail = sid[4:] if sid.startswith("src_") else sid
    return tail[:4] or sid


def _esc(value: object) -> str:
    if value is None:
        return ""
    return html.escape(str(value), quote=True)


def _md_to_html(md: str, source_map: dict) -> str:
    """A very small Markdown → HTML transformer, scoped to what the report
    writer actually produces: headers, lists, bold, italic, tables, and the
    custom [^src_xxx] citation markers. Anything fancier is rendered as a
    preformatted block so we never accidentally drop data."""
    if not md:
        return ""

    # Convert citation markers first so the inline rules below don't eat them.
    def _cite_sub(match: re.Match[str]) -> str:
        sid = match.group(1)
        src = source_map.get(sid)
        label = _esc(src.title if src else sid)
        href = _esc((src.url if src and src.url else f"#source-{sid}"))
        return (
            f'<sup class="cite"><a href="{href}" '
            f'data-source-id="{_esc(sid)}" title="{label}">'
            f'[{_esc(_short_id(sid))}]</a></sup>'
        )

    md = _CITE_RE.sub(_cite_sub, md)

    lines = md.split("\n")
    out: List[str] = []
    in_table = False
    table_buf: List[str] = []
    in_list = False
    in_ol = False

    def _flush_list() -> None:
        nonlocal in_list, in_ol
        if in_list:
            out.append("</ul>")
            in_list = False
        if in_ol:
            out.append("</ol>")
            in_ol = False

    def _flush_table() -> None:
        nonlocal in_table, table_buf
        if not in_table:
            return
        rows = [r for r in table_buf if r.strip()]
        if len(rows) >= 2 and re.match(r"^\|[\s\-:|]+\|$", rows[1].strip()):
            header = [c.strip() for c in rows[0].strip().strip("|").split("|")]
            body = rows[2:]
            out.append('<table class="rh-table">')
            out.append("<thead><tr>" + "".join(
                f"<th>{_inline(h)}</th>" for h in header
            ) + "</tr></thead>")
            out.append("<tbody>")
            for r in body:
                cells = [c.strip() for c in r.strip().strip("|").split("|")]
                out.append("<tr>" + "".join(
                    f"<td>{_inline(c)}</td>" for c in cells
                ) + "</tr>")
            out.append("</tbody></table>")
        else:
            out.append("<pre>" + _esc("\n".join(rows)) + "</pre>")
        in_table = False
        table_buf = []

    for raw in lines:
        line = raw.rstrip()
        # Table accumulation
        if line.lstrip().startswith("|") and line.rstrip().endswith("|"):
            _flush_list()
            in_table = True
            table_buf.append(line)
            continue
        elif in_table:
            _flush_table()

        # Headings
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            _flush_list()
            level = len(m.group(1))
            out.append(f"<h{level}>{_inline(m.group(2))}</h{level}>")
            continue

        # Lists
        if re.match(r"^\s*[-*]\s+", line):
            if not in_list:
                _flush_list()
                out.append("<ul>")
                in_list = True
            content = re.sub(r"^\s*[-*]\s+", "", line)
            out.append(f"<li>{_inline(content)}</li>")
            continue
        if re.match(r"^\s*\d+\.\s+", line):
            if not in_ol:
                _flush_list()
                out.append("<ol>")
                in_ol = True
            content = re.sub(r"^\s*\d+\.\s+", "", line)
            out.append(f"<li>{_inline(content)}</li>")
            continue

        _flush_list()

        if not line.strip():
            out.append("")
            continue

        out.append(f"<p>{_inline(line)}</p>")

    _flush_list()
    _flush_table()
    return "\n".join(out)


def _inline(text: str) -> str:
    """Inline Markdown: **bold**, *italic*, `code`, [text](href). Citations
    were already converted to <sup> tags above, so we pass them through."""
    # Protect existing HTML tags we already emitted (sup citations).
    placeholders: dict = {}

    def _stash(match: re.Match[str]) -> str:
        key = f"__P{len(placeholders)}__"
        placeholders[key] = match.group(0)
        return key

    text = re.sub(r"<sup class=\"cite\">.*?</sup>", _stash, text)

    text = _esc(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*([^*]+?)\*(?!\*)", r"<em>\1</em>", text)
    text = re.sub(r"`([^`]+?)`", r"<code>\1</code>", text)
    text = re.sub(
        r"\[([^\]]+?)\]\(([^)]+?)\)",
        lambda m: f'<a href="{_esc(m.group(2))}" target="_blank" rel="noreferrer">{_esc(m.group(1))}</a>',
        text,
    )

    for key, value in placeholders.items():
        text = text.replace(key, value)
    return text


def _collect_source_map(report: FinalReport) -> dict:
    smap: dict = {}
    for s in report.all_sources:
        smap[s.id] = s
    for c in report.competitors:
        for s in c.sources:
            smap[s.id] = s
    if report.target_product is not None:
        for s in report.target_product.sources:
            smap[s.id] = s
    return smap


def _render_metrics(report: FinalReport, loc: dict) -> str:
    m = report.metrics
    cells = [
        (loc.get("metrics.elapsed", "Elapsed"), f"{m.elapsed_seconds:.1f} s"),
        (loc.get("metrics.tokens", "Total tokens"), f"{m.total_tokens}"),
        (loc.get("metrics.llm_calls", "LLM calls"), f"{m.total_llm_calls}"),
        (loc.get("metrics.completeness", "Schema completeness"), f"{m.schema_completeness * 100:.0f}%"),
        (loc.get("metrics.avg_sources", "Avg sources / competitor"), f"{m.avg_sources_per_competitor}"),
        (loc.get("metrics.confidence", "Avg confidence"), f"{m.avg_confidence * 100:.0f}%"),
        (loc.get("metrics.conflicts", "Source conflicts"), f"{m.conflict_count}"),
        (loc.get("metrics.iterations", "QC iterations"), f"{m.qc_iterations}"),
        (loc.get("metrics.rework", "Rework count"), f"{m.rework_count}"),
        (loc.get("metrics.manual_correction", "Manual-correction rate"),
         f"{m.manual_correction_rate * 100:.0f}%"),
    ]
    parts = [
        f'<div class="metric"><div class="metric-label">{_esc(k)}</div>'
        f'<div class="metric-value">{_esc(v)}</div></div>'
        for k, v in cells
    ]
    return f'<div class="metrics-grid">{"".join(parts)}</div>'


def _render_executive(report: FinalReport, source_map: dict, loc: dict) -> str:
    body = _md_to_html(report.executive_summary_md or "", source_map)
    return f"<section><h2>{_esc(loc.get('report.executive', 'Executive Summary'))}</h2>{body}</section>"


def _render_sections(report: FinalReport, source_map: dict) -> str:
    out: List[str] = []
    for s in report.sections:
        body = _md_to_html(s.body_md or "", source_map)
        src_chips = _render_source_chips(s.sources)
        out.append(
            f'<section><h2>{_esc(s.heading)}</h2>{body}{src_chips}</section>'
        )
    return "\n".join(out)


def _render_source_chips(sources: List[SourceRef]) -> str:
    if not sources:
        return ""
    chips = []
    for s in sources:
        label = _esc(s.title or s.url or s.id)
        href = _esc(s.url or f"#source-{s.id}")
        chips.append(
            f'<a class="src-chip" href="{href}" data-source-id="{_esc(s.id)}" '
            f'target="_blank" rel="noreferrer" title="{label}">[{_esc(_short_id(s.id))}]</a>'
        )
    return f'<div class="src-chips">{"".join(chips)}</div>'


def _render_competitor_card(c: CompetitorKnowledge, *, is_self: bool, self_label: str) -> str:
    badges = []
    if is_self:
        badges.append(f'<span class="badge badge-self">★ {_esc(self_label)}</span>')
    if c.homepage:
        badges.append(
            f'<a class="hp" href="{_esc(c.homepage)}" target="_blank" rel="noreferrer">{_esc(c.homepage)}</a>'
        )

    fn_html = _render_function_tree(c)
    pricing_html = _render_pricing(c)
    user_html = _render_user(c)
    swot_html = _render_swot(c)
    conflicts_html = _render_conflicts(c)

    classes = "card competitor-card" + (" card-self" if is_self else "")
    return f"""
    <div class="{classes}">
      <div class="card-head">
        <h3>{_esc(c.name)}</h3>
        {"".join(badges)}
      </div>
      <p class="muted">{_esc(c.short_description or "")}</p>
      {f'<p class="muted small"><strong>Market position:</strong> {_esc(c.market_position)}</p>' if c.market_position else ''}
      {conflicts_html}
      <div class="grid-3">
        {fn_html}
        {pricing_html}
        {user_html}
      </div>
      {swot_html}
    </div>
    """


def _render_conflicts(c: CompetitorKnowledge) -> str:
    if not c.conflicts:
        return ""
    rows = []
    for cf in c.conflicts:
        vals = f" — {_esc(' ≠ '.join(cf.values))}" if cf.values else ""
        rows.append(
            f'<div class="conflict">⚠ <span class="mono">{_esc(cf.field)}</span> '
            f'<span class="muted small">{_esc(cf.detail)}{vals}</span></div>'
        )
    return f'<div class="conflicts">{"".join(rows)}</div>'


def _render_function_tree(c: CompetitorKnowledge) -> str:
    items = []
    for n in c.function_tree.nodes:
        children = "".join(f"<li>{_esc(ch.name)}</li>" for ch in n.children)
        maturity = (
            f' <span class="maturity">({_esc(n.maturity)})</span>' if n.maturity else ""
        )
        items.append(
            f"<li><strong>{_esc(n.name)}</strong>{maturity}"
            + (f"<ul>{children}</ul>" if children else "")
            + "</li>"
        )
    body = f"<ul>{''.join(items)}</ul>" if items else '<div class="muted">—</div>'
    return f'<div class="subcard"><div class="subcard-title">Function tree</div>{body}</div>'


def _render_pricing(c: CompetitorKnowledge) -> str:
    summary = f'<div class="muted small">{_esc(c.pricing.summary)}</div>' if c.pricing.summary else ""
    tiers = []
    for p in c.pricing.tiers:
        price = ""
        if isinstance(p.monthly_price, (int, float)):
            price = f' <span class="muted small">· {p.monthly_price:g} {_esc(p.currency)}/mo</span>'
        tiers.append(f"<li><strong>{_esc(p.name)}</strong>{price}</li>")
    body = f"<ul>{''.join(tiers)}</ul>" if tiers else '<div class="muted">—</div>'
    return f'<div class="subcard"><div class="subcard-title">Pricing</div>{summary}{body}</div>'


def _render_user(c: CompetitorKnowledge) -> str:
    primary = (
        f'<div class="muted small">{_esc(c.user_profile.primary_segment)}</div>'
        if c.user_profile.primary_segment else ""
    )
    segs = []
    for s in c.user_profile.segments:
        size = f' <span class="muted small">({_esc(s.company_size)})</span>' if s.company_size else ""
        segs.append(f"<li>{_esc(s.name)}{size}</li>")
    body = f"<ul>{''.join(segs)}</ul>" if segs else '<div class="muted">—</div>'
    rating = (
        f'<div class="muted small">★ {_esc(c.user_profile.nps_or_rating)}</div>'
        if c.user_profile.nps_or_rating else ""
    )
    return f'<div class="subcard"><div class="subcard-title">User profile</div>{primary}{body}{rating}</div>'


def _render_swot(c: CompetitorKnowledge) -> str:
    if not c.swot:
        return ""

    def _bucket(label: str, color: str, items: Iterable) -> str:
        rows = []
        for it in items:
            rows.append(f"<li>{_esc(it.value)}</li>")
        body = f"<ul>{''.join(rows)}</ul>" if rows else '<div class="muted">—</div>'
        return f'<div class="swot-box swot-{color}"><div class="swot-label">{label}</div>{body}</div>'

    return f"""
    <div class="swot-grid">
      {_bucket("S", "s", c.swot.strengths)}
      {_bucket("W", "w", c.swot.weaknesses)}
      {_bucket("O", "o", c.swot.opportunities)}
      {_bucket("T", "t", c.swot.threats)}
    </div>
    """


def _render_comparison(comp: ComparisonMatrix, loc: dict) -> str:
    if not comp.competitors:
        return f'<div class="muted">{_esc(loc.get("comparison.empty", "No comparable data"))}</div>'

    self_name = comp.self_name or ""
    self_label = loc.get("comparison.self", "Your product")

    # Bar charts (function coverage / source count / pricing floor)
    bars_html = _render_bar_charts(comp, loc)

    # Keyword cards
    kw_html = _render_keyword_cards(comp, self_label)

    # Three tables
    feat = _render_comparison_table(loc.get("comparison.feature", "Feature / Capability"), comp.feature_rows, comp.competitors, self_name, self_label)
    pri = _render_comparison_table(loc.get("comparison.pricing", "Pricing tiers"), comp.pricing_rows, comp.competitors, self_name, self_label)
    usr = _render_comparison_table(loc.get("comparison.user", "User profile"), comp.user_rows, comp.competitors, self_name, self_label)

    return f"""
    <section>
      <h2>{_esc(loc.get("report.comparison", "Comparison"))}</h2>
      {bars_html}
      {kw_html}
      {feat}
      {pri}
      {usr}
    </section>
    """


def _render_bar_charts(comp: ComparisonMatrix, loc: dict) -> str:
    def _chart(title: str, source: dict, missing_value: Optional[float] = None) -> str:
        if not comp.competitors:
            return ""
        values = []
        for n in comp.competitors:
            v = source.get(n)
            if isinstance(v, (int, float)):
                values.append(float(v))
        max_val = max(values) if values else 1.0
        max_val = max_val or 1.0
        rows = []
        for n in comp.competitors:
            v = source.get(n)
            missing = v is None
            display = "—" if missing else f"{v}"
            width = 4 if missing else max(2.0, (float(v) / max_val) * 100.0)
            is_self_row = n == comp.self_name
            color = "#f59e0b" if is_self_row else "#2563eb"
            rows.append(
                f'<div class="bar-row"><span class="bar-name">{_esc(n)}'
                + (f' <span class="badge mini">★</span>' if is_self_row else '')
                + f'</span>'
                f'<div class="bar-track"><div class="bar-fill" '
                f'style="width:{width}%; background:{"#cbd5e1" if missing else color}"></div></div>'
                f'<span class="bar-value">{_esc(display)}</span></div>'
            )
        return (
            f'<div class="bar-chart"><div class="bar-title">{_esc(title)}</div>'
            f'{"".join(rows)}</div>'
        )

    chart1 = _chart(loc.get("comparison.coverage", "Function coverage"), comp.function_coverage)
    chart2 = _chart(loc.get("comparison.sources", "Source count"), comp.source_counts)
    chart3 = _chart(loc.get("comparison.entry_price", "Entry monthly price"), comp.pricing_floor)
    return (
        f'<div class="charts-row"><h3 class="sub-h">'
        f'{_esc(loc.get("comparison.charts", "Visualisations"))}</h3>'
        f'<div class="charts-grid">{chart1}{chart2}{chart3}</div></div>'
    )


def _render_keyword_cards(comp: ComparisonMatrix, self_label: str) -> str:
    if not comp.keywords:
        return ""
    cards = []
    palette = ["#2563eb", "#db2777", "#059669", "#0891b2", "#7c3aed", "#0ea5e9"]
    p_idx = 0
    for n in comp.competitors:
        is_self = n == comp.self_name
        color = "#f59e0b" if is_self else palette[p_idx % len(palette)]
        if not is_self:
            p_idx += 1
        chips = "".join(
            f'<span class="kw-chip" style="background:{color}1a; color:{color}">{_esc(k)}</span>'
            for k in (comp.keywords.get(n) or [])
        ) or '<span class="muted">—</span>'
        badge = (
            f'<span class="badge badge-self mini">★ {_esc(self_label)}</span>'
            if is_self else ""
        )
        cards.append(
            f'<div class="kw-card" style="border-left:4px solid {color}">'
            f'<div class="kw-head"><strong>{_esc(n)}</strong>{badge}</div>'
            f'<div class="kw-chips">{chips}</div></div>'
        )
    return f'<div class="kw-grid">{"".join(cards)}</div>'


def _render_comparison_table(title: str, rows, competitors, self_name: str, self_label: str) -> str:
    if not rows:
        return ""
    headers = []
    for n in competitors:
        is_self = n == self_name
        cls = "th-self" if is_self else ""
        badge = (
            f'<span class="badge badge-self mini">★ {_esc(self_label)}</span>'
            if is_self else ""
        )
        headers.append(f'<th class="{cls}">{_esc(n)} {badge}</th>')

    body_rows = []
    for r in rows:
        cells = ['<td class="row-label">' + _esc(r.label) + "</td>"]
        for n in competitors:
            cell = next((c for c in r.cells if c.competitor == n), None)
            value = cell.value if cell and cell.value else "—"
            detail = (
                f'<div class="muted small">{_esc(cell.detail)}</div>'
                if cell and cell.detail else ""
            )
            cls = "td-self" if n == self_name else ""
            cells.append(f'<td class="{cls}">{_esc(value)}{detail}</td>')
        body_rows.append("<tr>" + "".join(cells) + "</tr>")

    return f"""
    <h3 class="sub-h">{_esc(title)}</h3>
    <div class="table-wrap">
      <table class="rh-table">
        <thead><tr><th class="row-label">—</th>{"".join(headers)}</tr></thead>
        <tbody>{"".join(body_rows)}</tbody>
      </table>
    </div>
    """


def _render_sources(report: FinalReport, loc: dict) -> str:
    if not report.all_sources:
        return ""
    rows = []
    for s in report.all_sources:
        link = (
            f'<a href="{_esc(s.url)}" target="_blank" rel="noreferrer">{_esc(s.title or s.url)}</a>'
            if s.url else _esc(s.title or "—")
        )
        snippet = f'<div class="muted small">{_esc(s.snippet)}</div>' if s.snippet else ""
        conf = (
            f'<span class="muted small">{_esc(loc.get("source.confidence", "Confidence"))}: '
            f'{int(s.confidence * 100)}%</span>'
            if isinstance(s.confidence, (int, float)) else ""
        )
        rows.append(
            f'<div class="src-row" id="source-{_esc(s.id)}">'
            f'<span class="src-id">[{_esc(_short_id(s.id))}]</span>'
            f'<span class="src-kind">[{_esc(s.kind)}]</span>'
            f'<div class="src-body">{link}{snippet}</div>'
            f'{conf}'
            f'</div>'
        )
    return f"""
    <section id="tab-sources">
      <h2>{_esc(loc.get("report.sources", "Sources"))}</h2>
      <div class="src-list">{"".join(rows)}</div>
    </section>
    """


def render_report_html(report: FinalReport) -> str:
    """Build a single self-contained HTML document for the given report."""
    loc = get_locale(report.locale)
    source_map = _collect_source_map(report)
    self_label = loc.get("comparison.self", "Your product")

    metrics_html = _render_metrics(report, loc)
    executive_html = _render_executive(report, source_map, loc)
    sections_html = _render_sections(report, source_map)

    competitor_cards = []
    if report.target_product is not None:
        competitor_cards.append(
            _render_competitor_card(report.target_product, is_self=True, self_label=self_label)
        )
    for c in report.competitors:
        competitor_cards.append(
            _render_competitor_card(c, is_self=False, self_label=self_label)
        )
    competitors_html = "\n".join(competitor_cards) or '<div class="muted">—</div>'

    comparison_html = _render_comparison(report.comparison, loc)
    sources_html = _render_sources(report, loc)

    title = report.title or loc.get("report.title", "Competitive Analysis Report")
    product = report.product
    generated = report.generated_at.strftime("%Y-%m-%d %H:%M")
    market = report.market.upper()

    css = _STYLES
    js = _SCRIPT

    nav_items = [
        ("tab-report", loc.get("report.title", "Report")),
        ("tab-comparison", loc.get("report.comparison", "Comparison")),
        ("tab-competitors", loc.get("report.competitors", "Competitors")),
        ("tab-sources", loc.get("report.sources", "Sources")),
    ]
    nav_html = "".join(
        f'<button class="tab-btn" data-target="{tid}">{_esc(label)}</button>'
        for tid, label in nav_items
    )

    return f"""<!doctype html>
<html lang="{_esc(report.locale)}">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{_esc(title)} — {_esc(product)}</title>
  <style>{css}</style>
</head>
<body>
  <header class="report-header">
    <div class="hdr-left">
      <h1>{_esc(title)}</h1>
      <p class="muted">
        <strong>{_esc(loc.get("form.product.label", "Target product"))}:</strong> {_esc(product)}
        · <span class="pill">{_esc(market)}</span>
        · {_esc(generated)}
      </p>
    </div>
    <div class="hdr-actions">
      <button id="btn-print" class="btn">🖨 {_esc(loc.get("report.download_pdf", "Print / Save PDF"))}</button>
      <button id="btn-toggle-all" class="btn ghost">▾ Expand / Collapse all</button>
    </div>
  </header>

  <nav class="tab-bar">
    {nav_html}
  </nav>

  {metrics_html}

  <main>
    <article id="tab-report" class="tab active">
      {executive_html}
      {sections_html}
    </article>

    <article id="tab-comparison" class="tab">
      {comparison_html}
    </article>

    <article id="tab-competitors" class="tab">
      <h2>{_esc(loc.get("report.competitors", "Competitors at a glance"))}</h2>
      {competitors_html}
    </article>

    <article id="tab-sources" class="tab">
      {sources_html}
    </article>
  </main>

  <footer class="report-footer">
    <span class="muted small">Generated by Competitive Analysis Agent System · schema {_esc(report.schema_version)}</span>
  </footer>

  <script>{js}</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Inline CSS / JS
# ---------------------------------------------------------------------------
_STYLES = """
:root {
  --fg: #0f172a;
  --muted: #64748b;
  --border: #e2e8f0;
  --bg: #f8fafc;
  --card: #ffffff;
  --brand: #2563eb;
  --self: #f59e0b;
  --self-bg: #fef3c7;
  --self-bg-soft: #fff7ed;
}
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Noto Sans", "PingFang SC", "Microsoft YaHei", sans-serif; color: var(--fg); background: var(--bg); }
body { line-height: 1.55; }
h1 { font-size: 26px; margin: 0 0 6px; }
h2 { font-size: 19px; margin: 26px 0 10px; border-bottom: 1px solid var(--border); padding-bottom: 6px; }
h3 { font-size: 16px; margin: 18px 0 8px; }
p { margin: 8px 0; }
.muted { color: var(--muted); }
.small { font-size: 12px; }
.pill { display: inline-block; padding: 1px 8px; background: #e2e8f0; border-radius: 999px; font-size: 11px; }
a { color: var(--brand); text-decoration: none; }
a:hover { text-decoration: underline; }
.report-header { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 22px 32px; background: var(--card); border-bottom: 1px solid var(--border); }
.hdr-actions { display: flex; gap: 8px; }
.btn { padding: 8px 14px; border-radius: 8px; border: 1px solid var(--brand); background: var(--brand); color: white; font-size: 13px; cursor: pointer; }
.btn.ghost { background: white; color: var(--brand); }
.btn:hover { opacity: 0.92; }
.tab-bar { display: flex; gap: 4px; padding: 0 32px; background: var(--card); border-bottom: 1px solid var(--border); position: sticky; top: 0; z-index: 10; }
.tab-btn { padding: 12px 16px; border: none; background: transparent; color: var(--muted); font-size: 14px; cursor: pointer; border-bottom: 2px solid transparent; }
.tab-btn.active { color: var(--brand); border-bottom-color: var(--brand); font-weight: 600; }
.metrics-grid { display: grid; grid-template-columns: repeat(10, 1fr); gap: 8px; padding: 12px 32px; background: var(--card); border-bottom: 1px solid var(--border); }
@media (max-width: 1280px) { .metrics-grid { grid-template-columns: repeat(5, 1fr); } }
@media (max-width: 900px) { .metrics-grid { grid-template-columns: repeat(2, 1fr); } }
.metric { border: 1px solid var(--border); border-radius: 6px; padding: 8px 10px; background: white; }
.metric-label { font-size: 10px; text-transform: uppercase; letter-spacing: 0.04em; color: var(--muted); }
.metric-value { font-size: 14px; font-weight: 600; }
main { padding: 0 32px 60px; max-width: 1280px; margin: 0 auto; }
.tab { display: none; }
.tab.active { display: block; }
section { background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 18px 22px; margin: 16px 0; }
.card { background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 16px 18px; margin: 14px 0; }
.card-head { display: flex; align-items: center; gap: 10px; }
.card-head h3 { margin: 0; }
.hp { font-size: 12px; color: var(--brand); margin-left: auto; }
.card-self { background: var(--self-bg-soft); border-color: #fcd34d; box-shadow: inset 4px 0 0 var(--self); }
.badge { display: inline-block; padding: 2px 8px; font-size: 11px; border-radius: 999px; background: #f1f5f9; color: #334155; border: 1px solid #e2e8f0; }
.badge.mini { padding: 1px 6px; font-size: 10px; }
.badge-self { background: #fde68a; color: #92400e; border-color: #fcd34d; font-weight: 600; }
.grid-3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-top: 10px; }
@media (max-width: 900px) { .grid-3 { grid-template-columns: 1fr; } }
.subcard { border: 1px solid var(--border); border-radius: 8px; padding: 10px 12px; background: #fbfdff; }
.subcard-title { font-size: 10px; text-transform: uppercase; letter-spacing: 0.04em; color: var(--muted); margin-bottom: 6px; }
ul, ol { padding-left: 18px; margin: 6px 0; }
li { margin: 2px 0; font-size: 13px; }
.maturity { font-size: 10px; color: var(--muted); }
.swot-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin-top: 12px; }
@media (max-width: 900px) { .swot-grid { grid-template-columns: repeat(2, 1fr); } }
.swot-box { padding: 10px 12px; border-radius: 6px; border: 1px solid; font-size: 13px; }
.swot-label { font-size: 11px; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; margin-bottom: 4px; }
.swot-s { background: #ecfdf5; border-color: #a7f3d0; color: #065f46; }
.swot-w { background: #fff1f2; border-color: #fecdd3; color: #9f1239; }
.swot-o { background: #f0f9ff; border-color: #bae6fd; color: #075985; }
.swot-t { background: #fffbeb; border-color: #fde68a; color: #92400e; }
.bar-chart { border: 1px solid var(--border); border-radius: 8px; padding: 12px; background: var(--card); }
.charts-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
@media (max-width: 900px) { .charts-grid { grid-template-columns: 1fr; } }
.bar-title { font-size: 12px; font-weight: 600; color: var(--muted); margin-bottom: 8px; }
.bar-row { display: grid; grid-template-columns: 110px 1fr 50px; gap: 8px; align-items: center; margin: 4px 0; font-size: 12px; }
.bar-name { color: #334155; }
.bar-track { background: #eef2f7; height: 10px; border-radius: 3px; overflow: hidden; }
.bar-fill { height: 10px; border-radius: 3px; transition: width 0.3s ease; }
.bar-value { text-align: right; color: #475569; font-variant-numeric: tabular-nums; }
.kw-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 10px; margin: 14px 0; }
.kw-card { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 10px 12px; }
.kw-head { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.kw-chip { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 11px; margin: 2px; }
.kw-chips { display: flex; flex-wrap: wrap; gap: 2px; }
.table-wrap { overflow-x: auto; border: 1px solid var(--border); border-radius: 8px; margin: 8px 0 16px; }
.rh-table { width: 100%; border-collapse: collapse; font-size: 13px; background: var(--card); }
.rh-table th, .rh-table td { padding: 8px 10px; text-align: left; border-bottom: 1px solid var(--border); vertical-align: top; }
.rh-table thead th { background: #f1f5f9; font-weight: 600; color: #334155; }
.rh-table tr:nth-child(even) td { background: #fafbfc; }
.row-label { color: #1e293b; font-weight: 600; }
.th-self, .td-self { background: var(--self-bg) !important; }
.cite a { color: var(--brand); font-size: 0.7em; vertical-align: super; text-decoration: none; }
.cite a:hover { text-decoration: underline; }
.src-chips { margin-top: 6px; display: flex; flex-wrap: wrap; gap: 4px; }
.src-chip { display: inline-block; padding: 1px 6px; background: #f1f5f9; color: #334155; border-radius: 4px; font-size: 10px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; border: 1px solid var(--border); }
.src-list { margin-top: 8px; }
.src-row { display: grid; grid-template-columns: 60px 80px 1fr auto; gap: 8px; align-items: start; padding: 8px 10px; border-bottom: 1px solid var(--border); }
.src-row:last-child { border-bottom: none; }
.src-row.highlight { background: #fef9c3; transition: background 1.5s ease; }
.src-id { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 11px; color: var(--muted); }
.src-kind { font-size: 11px; color: var(--muted); }
.report-footer { text-align: center; padding: 20px; color: var(--muted); font-size: 12px; }
.sub-h { font-size: 14px; color: #334155; margin: 14px 0 6px; }
.conflicts { margin: 8px 0; display: flex; flex-direction: column; gap: 4px; }
.conflict { font-size: 12px; padding: 4px 8px; border-radius: 6px; background: #fffbeb; border: 1px solid #fde68a; color: #92400e; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }

@media print {
  body { background: white; }
  .tab-bar, .hdr-actions { display: none; }
  .tab { display: block !important; page-break-after: always; }
  section, .card { box-shadow: none; }
}
"""

_SCRIPT = """
(function () {
  // Tabs
  var buttons = document.querySelectorAll('.tab-btn');
  var tabs = document.querySelectorAll('.tab');
  function activate(targetId) {
    buttons.forEach(function (b) {
      b.classList.toggle('active', b.dataset.target === targetId);
    });
    tabs.forEach(function (t) {
      t.classList.toggle('active', t.id === targetId);
    });
  }
  buttons.forEach(function (b) {
    b.addEventListener('click', function () { activate(b.dataset.target); });
  });
  if (buttons.length > 0) activate(buttons[0].dataset.target);

  // Citation anchors — when href is an internal #source-xxx, switch to the
  // Sources tab and scroll/flash the target row.
  document.querySelectorAll('a[data-source-id]').forEach(function (a) {
    a.addEventListener('click', function (e) {
      var href = a.getAttribute('href') || '';
      if (href.charAt(0) === '#') {
        e.preventDefault();
        activate('tab-sources');
        var el = document.getElementById('source-' + a.dataset.sourceId);
        if (el) {
          el.scrollIntoView({ behavior: 'smooth', block: 'center' });
          el.classList.add('highlight');
          setTimeout(function () { el.classList.remove('highlight'); }, 1600);
        }
      }
      // Real URLs open in a new tab via target="_blank" already.
    });
  });

  // Print button
  var btn = document.getElementById('btn-print');
  if (btn) btn.addEventListener('click', function () { window.print(); });

  // Expand / collapse all sections (open every tab simultaneously)
  var expanded = false;
  var allBtn = document.getElementById('btn-toggle-all');
  if (allBtn) {
    allBtn.addEventListener('click', function () {
      expanded = !expanded;
      tabs.forEach(function (t) { t.classList.toggle('active', expanded || t.id === 'tab-report'); });
      allBtn.textContent = expanded ? '▴ Collapse all' : '▾ Expand all';
    });
  }
})();
"""


def render_report_html_bytes(report: FinalReport) -> bytes:
    return render_report_html(report).encode("utf-8")


__all__ = ["render_report_html", "render_report_html_bytes"]
