import { useEffect, useMemo, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  DagDef,
  KnowledgeDiff,
  getDag,
  getKnowledgeDiff,
  getReport,
  getTrace,
  patchReport,
  TraceEvent,
} from "../api/client";
import SourceBadge from "../components/SourceBadge";
import AgentFlow, { NodeStatus } from "../components/AgentFlow";
import ComparisonView from "../components/ComparisonView";
import { Locale, makeT } from "../i18n";

// Threaded through the tabs so any field can save a human edit (PATCH) and
// refresh the report in place.
interface Editor {
  reportId: string;
  onSaved: (report: any) => void;
}

export default function Report() {
  const { reportId } = useParams<{ reportId: string }>();
  const [params] = useSearchParams();
  const runId = params.get("run");

  const [report, setReport] = useState<any>(null);
  const [events, setEvents] = useState<TraceEvent[]>([]);
  const [dag, setDag] = useState<DagDef | null>(null);
  const [tab, setTab] = useState<
    "report" | "comparison" | "competitors" | "evolution" | "trace" | "sources"
  >("report");

  const editor: Editor = useMemo(
    () => ({ reportId: reportId || "", onSaved: (r: any) => setReport(r) }),
    [reportId],
  );

  useEffect(() => {
    if (reportId) getReport(reportId).then(setReport).catch(() => {});
  }, [reportId]);

  useEffect(() => {
    getDag().then(setDag).catch(() => {});
  }, []);

  // The trace tab reuses the live Agent-flow layout; in a finished report every
  // stage is, by definition, complete — so light them all up as "done".
  const allDoneStatus = useMemo<Record<string, NodeStatus>>(() => {
    const s: Record<string, NodeStatus> = {};
    for (const n of dag?.nodes || []) s[n.id] = "done";
    return s;
  }, [dag]);

  useEffect(() => {
    // Prefer the live ?run= param; fall back to the run_id persisted on the
    // report so the trace is available even when opened from history.
    const rid = runId || report?.run_id;
    if (rid) getTrace(rid).then(setEvents).catch(() => {});
  }, [runId, report?.run_id]);

  const locale: Locale = useMemo(() => (report?.locale as Locale) || "en-US", [report]);
  const t = useMemo(() => makeT(locale), [locale]);

  // Build a source-id -> source lookup used by every component that renders
  // [^src_xxx] footnote markers inline.
  const sourceMap = useMemo(() => {
    const map: Record<string, any> = {};
    for (const s of report?.all_sources || []) map[s.id] = s;
    for (const c of report?.competitors || []) {
      for (const s of c.sources || []) map[s.id] = s;
    }
    if (report?.target_product) {
      for (const s of report.target_product.sources || []) map[s.id] = s;
    }
    return map;
  }, [report]);

  if (!report) {
    return <div className="max-w-5xl mx-auto p-6 text-slate-500">{t("common.loading")}</div>;
  }

  return (
    <div className="max-w-6xl mx-auto p-6 space-y-4" id="report-root">
      <div className="bg-white border rounded-xl p-5 print:border-0 print:p-0">
        <div className="flex items-baseline gap-3 mb-1">
          <h1 className="text-2xl font-semibold">{report.title}</h1>
          <span className="text-xs px-2 py-0.5 bg-slate-100 rounded">
            {report.market.toUpperCase()}
          </span>
          <span className="text-xs text-slate-500">{report.locale}</span>
          <div className="ml-auto flex items-center gap-2 print:hidden">
            <button
              onClick={() => window.open(`/api/reports/${report.id}/html`, "_blank", "noopener,noreferrer")}
              className="text-xs px-3 py-1.5 rounded border border-brand-600 text-brand-700 hover:bg-brand-50"
              title={t("report.preview_html_title") || "Open the standalone HTML report in a new tab"}
            >
              🔍 {t("report.preview_html") || "Preview HTML"}
            </button>
            <a
              href={`/api/reports/${report.id}/html?download=1`}
              className="text-xs px-3 py-1.5 rounded border border-emerald-600 text-emerald-700 hover:bg-emerald-50"
              title={t("report.download_html_title") || "Download a single-file HTML report"}
            >
              ⬇ {t("report.download_html") || "Download HTML"}
            </a>
            <button
              onClick={() => window.print()}
              className="text-xs px-3 py-1.5 rounded border border-slate-300 text-slate-700 hover:bg-slate-50"
            >
              🖨 {t("report.download_pdf")}
            </button>
          </div>
        </div>
        <p className="text-sm text-slate-500 mb-3">
          {t("form.product.label")}: <b>{report.product}</b> ·{" "}
          {new Date(report.generated_at).toLocaleString()}
        </p>

        <MetricsBar t={t} metrics={report.metrics} />
      </div>

      <div className="bg-white border rounded-xl print:border-0">
        <div className="border-b flex gap-1 px-3 print:hidden">
          {(
            [
              ["report", t("report.title")],
              ["comparison", t("report.comparison")],
              ["competitors", t("report.competitors")],
              ["evolution", t("report.evolution")],
              ["trace", t("trace.title")],
              ["sources", t("report.sources")],
            ] as const
          ).map(([k, label]) => (
            <button
              key={k}
              onClick={() => setTab(k)}
              className={
                "px-3 py-2 text-sm border-b-2 -mb-px " +
                (tab === k
                  ? "border-brand-600 text-brand-700"
                  : "border-transparent text-slate-500")
              }
            >
              {label}
            </button>
          ))}
        </div>

        <div className="p-5 print:p-0">
          {/* On screen: only the active tab. When printing: render everything stacked. */}
          <div className={tab === "report" ? "" : "hidden print:block"}>
            <ReportBody t={t} report={report} sourceMap={sourceMap} editor={editor} />
          </div>
          <div className={tab === "comparison" ? "" : "hidden print:block"}>
            <ComparisonView t={t} comparison={report.comparison} />
          </div>
          <div className={tab === "competitors" ? "" : "hidden print:block"}>
            <CompetitorsTab t={t} report={report} editor={editor} />
          </div>
          <div className={tab === "evolution" ? "" : "hidden print:block"}>
            <EvolutionTab t={t} report={report} />
          </div>
          <div className={tab === "trace" ? "" : "hidden"}>
            <p className="text-xs text-slate-400 mb-4">{t("flow.click_hint")}</p>
            {dag ? (
              <AgentFlow
                dag={dag}
                locale={locale}
                nodeStatus={allDoneStatus}
                activeNodeId={null}
                events={events}
                t={t}
              />
            ) : (
              <div className="text-sm text-slate-400">{t("common.loading")}</div>
            )}
          </div>
          <div className={tab === "sources" ? "" : "hidden print:block"}>
            <SourcesTab t={t} report={report} />
          </div>
        </div>
      </div>
    </div>
  );
}

function MetricsBar({ t, metrics }: { t: (k: string) => string; metrics: any }) {
  if (!metrics) return null;
  const pct = (x: number) => `${(x * 100).toFixed(0)}%`;
  const cells: Array<[string, any, string?]> = [
    [t("metrics.elapsed"), `${metrics.elapsed_seconds.toFixed(1)} s`],
    [t("metrics.tokens"), metrics.total_tokens],
    [t("metrics.llm_calls"), metrics.total_llm_calls],
    [t("metrics.completeness"), pct(metrics.schema_completeness)],
    [t("metrics.avg_sources"), metrics.avg_sources_per_competitor],
    [t("metrics.confidence"), pct(metrics.avg_confidence ?? 0)],
    [t("metrics.conflicts"), metrics.conflict_count ?? 0,
      (metrics.conflict_count ?? 0) > 0 ? "text-amber-700" : ""],
    [t("metrics.iterations"), metrics.qc_iterations],
    [t("metrics.rework"), metrics.rework_count],
    [t("metrics.manual_correction"), pct(metrics.manual_correction_rate ?? 0),
      (metrics.manual_correction_rate ?? 0) > 0 ? "text-sky-700" : ""],
  ];
  return (
    <div className="grid grid-cols-2 sm:grid-cols-5 lg:grid-cols-10 gap-2">
      {cells.map(([k, v, cls]) => (
        <div key={k} className="border rounded px-3 py-2">
          <div className="text-[10px] uppercase tracking-wide text-slate-500">{k}</div>
          <div className={"text-sm font-semibold " + (cls || "")}>{v}</div>
        </div>
      ))}
    </div>
  );
}

/**
 * Inline-editable text — the human-in-the-loop primitive. Renders the value
 * with a small "✎" affordance; editing opens a textarea and Save PATCHes the
 * report at ``path`` (e.g. "competitors[0].market_position"), recording a
 * correction and updating the manual-correction-rate metric.
 */
function EditableText({
  value,
  path,
  editor,
  t,
  multiline = false,
  className = "",
  placeholder = "—",
  buttonOnly = false,
  idleLabel = "",
}: {
  value: string;
  path: string;
  editor?: Editor;
  t: (k: string) => string;
  multiline?: boolean;
  className?: string;
  placeholder?: string;
  buttonOnly?: boolean;
  idleLabel?: string;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value ?? "");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  if (!editor?.reportId) {
    return buttonOnly ? null : <span className={className}>{value || placeholder}</span>;
  }

  async function save() {
    setSaving(true);
    setErr(null);
    try {
      const res = await patchReport(editor!.reportId, [{ target_path: path, value: draft }]);
      editor!.onSaved(res.report);
      setEditing(false);
    } catch (e: any) {
      setErr(String(e?.message || e));
    } finally {
      setSaving(false);
    }
  }

  if (!editing) {
    if (buttonOnly) {
      return (
        <button
          type="button"
          onClick={() => {
            setDraft(value ?? "");
            setEditing(true);
          }}
          title={t("edit.edit")}
          className="print:hidden text-[11px] px-1.5 py-0.5 rounded border border-slate-200 text-slate-500 hover:text-brand-600 hover:border-brand-300 transition"
        >
          ✎ {idleLabel || t("edit.edit")}
        </button>
      );
    }
    return (
      <span className={"group/edit inline-flex items-start gap-1 " + className}>
        <span>{value || placeholder}</span>
        <button
          type="button"
          onClick={() => {
            setDraft(value ?? "");
            setEditing(true);
          }}
          title={t("edit.edit")}
          className="opacity-0 group-hover/edit:opacity-100 print:hidden text-[11px] text-slate-400 hover:text-brand-600 transition"
        >
          ✎
        </button>
      </span>
    );
  }

  return (
    <span className="block print:hidden">
      {multiline ? (
        <textarea
          autoFocus
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          rows={4}
          className="w-full border rounded p-2 text-sm"
        />
      ) : (
        <input
          autoFocus
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          className="w-full border rounded px-2 py-1 text-sm"
        />
      )}
      <span className="flex items-center gap-2 mt-1">
        <button
          type="button"
          disabled={saving}
          onClick={save}
          className="text-xs px-2 py-1 rounded bg-brand-600 text-white hover:bg-brand-700 disabled:opacity-60"
        >
          {saving ? t("edit.saving") : t("edit.save")}
        </button>
        <button
          type="button"
          disabled={saving}
          onClick={() => setEditing(false)}
          className="text-xs px-2 py-1 rounded border border-slate-200 text-slate-600 hover:bg-slate-50"
        >
          {t("common.cancel")}
        </button>
        {err && <span className="text-xs text-rose-600">{err}</span>}
      </span>
    </span>
  );
}

function ConflictBadges({ t, conflicts }: { t: (k: string) => string; conflicts: any[] }) {
  if (!conflicts?.length) return null;
  return (
    <div className="mt-2 space-y-1">
      {conflicts.map((cf, i) => (
        <div
          key={i}
          className="text-[11px] px-2 py-1 rounded bg-amber-50 border border-amber-200 text-amber-800"
          title={cf.detail}
        >
          ⚠ {t("conflict.label")}: <span className="font-mono">{cf.field}</span>
          {cf.values?.length > 0 && <span> — {cf.values.join(" ≠ ")}</span>}
        </div>
      ))}
    </div>
  );
}

function EvolutionTab({ t, report }: { t: (k: string) => string; report: any }) {
  const [diffs, setDiffs] = useState<Record<string, KnowledgeDiff | null>>({});
  const [loading, setLoading] = useState(true);

  const names: string[] = useMemo(() => {
    const out: string[] = [];
    if (report?.target_product?.name) out.push(report.target_product.name);
    for (const c of report?.competitors || []) if (c.name) out.push(c.name);
    return out;
  }, [report]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all(names.map((n) => getKnowledgeDiff(report.market, n).then((d) => [n, d] as const)))
      .then((pairs) => {
        if (cancelled) return;
        const map: Record<string, KnowledgeDiff | null> = {};
        for (const [n, d] of pairs) map[n] = d;
        setDiffs(map);
      })
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [names, report.market]);

  if (loading) return <div className="text-sm text-slate-400">{t("common.loading")}</div>;

  return (
    <div className="space-y-4">
      <p className="text-xs text-slate-500">{t("evolution.help")}</p>
      {names.map((n) => {
        const d = diffs[n];
        const first = !d || d.summary === "first_snapshot";
        return (
          <div key={n} className="border rounded-lg p-4">
            <div className="flex items-center gap-2 mb-2">
              <h3 className="font-semibold">{n}</h3>
              <span className="text-xs text-slate-400">
                {first ? t("evolution.first") : d!.summary}
              </span>
            </div>
            {!first && d!.changes.length > 0 && (
              <ul className="text-sm space-y-1">
                {d!.changes.map((c, i) => (
                  <li key={i} className="flex items-baseline gap-2">
                    <span
                      className={
                        "text-[10px] px-1.5 py-0.5 rounded uppercase " +
                        (c.change === "added"
                          ? "bg-emerald-100 text-emerald-700"
                          : c.change === "removed"
                          ? "bg-rose-100 text-rose-700"
                          : "bg-sky-100 text-sky-700")
                      }
                    >
                      {t(`evolution.${c.change}`)}
                    </span>
                    <span className="font-mono text-xs text-slate-500">{c.path}</span>
                    {c.change === "changed" && (
                      <span className="text-xs text-slate-600">
                        {c.before} → <b>{c.after}</b>
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
        );
      })}
    </div>
  );
}

function ReportBody({
  t,
  report,
  sourceMap,
  editor,
}: {
  t: (k: string) => string;
  report: any;
  sourceMap: Record<string, any>;
  editor?: Editor;
}) {
  return (
    <div className="markdown-body">
      <div className="flex items-center gap-2">
        <h2 className="!mb-0">{t("report.executive")}</h2>
        <span className="not-prose">
          <EditableText
            value={report.executive_summary_md || ""}
            path="executive_summary_md"
            editor={editor}
            t={t}
            multiline
            buttonOnly
            idleLabel={t("edit.edit")}
          />
        </span>
      </div>
      <CitedMarkdown text={report.executive_summary_md || ""} sourceMap={sourceMap} />
      {(report.sections || []).map((s: any, i: number) => (
        <section key={i}>
          <h2>{s.heading}</h2>
          <CitedMarkdown text={s.body_md || ""} sourceMap={sourceMap} />
          {s.sources?.length > 0 && <SourceBadge t={t} sources={s.sources} />}
        </section>
      ))}
    </div>
  );
}

/**
 * Renders markdown that contains [^src_xxx] footnote markers. Each marker is
 * rewritten as a markdown link `[short](#source-src_xxx)` which is then
 * rendered as a clickable superscript that scrolls to the Sources tab entry
 * (or opens the source URL in a new tab when one is available).
 */
function CitedMarkdown({
  text,
  sourceMap,
}: {
  text: string;
  sourceMap: Record<string, any>;
}) {
  const transformed = useMemo(() => {
    if (!text) return "";
    // remark-gfm parses [^xxx] as footnote references and would render them
    // as garbled definitions. Rewrite them to plain markdown links pointing
    // to anchors we control in the Sources tab.
    return text.replace(/\[\^(src_[A-Za-z0-9_]+)\]/g, (_m, id) => {
      // Escape inner brackets so the outer link-text grammar parses cleanly.
      return ` [\\[${shortId(id)}\\]](#source-${id})`;
    });
  }, [text]);

  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        a: (props: any) => {
          const href: string = props.href || "";
          const m = href.match(/^#source-(src_[A-Za-z0-9_]+)$/);
          if (!m) {
            return (
              <a
                {...props}
                target={href.startsWith("http") ? "_blank" : undefined}
                rel="noreferrer"
              />
            );
          }
          const id = m[1];
          const s = sourceMap[id];
          const label = s?.title || id;
          const onClick = (e: React.MouseEvent) => {
            e.preventDefault();
            if (s?.url) {
              window.open(s.url, "_blank", "noopener,noreferrer");
              return;
            }
            const el = document.getElementById(`source-${id}`);
            if (el) {
              el.scrollIntoView({ behavior: "smooth", block: "center" });
              el.classList.add("ring-2", "ring-amber-400");
              setTimeout(() => el.classList.remove("ring-2", "ring-amber-400"), 1600);
            }
          };
          return (
            <sup className="cite-ref">
              <a
                href={s?.url || `#source-${id}`}
                onClick={onClick}
                title={label + (s?.snippet ? `\n\n${s.snippet}` : "")}
                className="text-brand-700 hover:underline"
              >
                [{shortId(id)}]
              </a>
            </sup>
          );
        },
      }}
    >
      {transformed}
    </ReactMarkdown>
  );
}

function shortId(id: string): string {
  // src_abc123def -> abc1
  const tail = id.replace(/^src_/, "");
  return tail.slice(0, 4) || id;
}

function CompetitorsTab({
  t,
  report,
  editor,
}: {
  t: (k: string) => string;
  report: any;
  editor?: Editor;
}) {
  const items: Array<{ data: any; isSelf: boolean; path: string }> = [];
  if (report.target_product) {
    items.push({ data: report.target_product, isSelf: true, path: "target_product" });
  }
  (report.competitors || []).forEach((c: any, i: number) =>
    items.push({ data: c, isSelf: false, path: `competitors[${i}]` }),
  );
  return (
    <div className="space-y-6">
      {items.map(({ data: c, isSelf, path }) => (
        <div
          key={(isSelf ? "self:" : "") + c.name}
          className={
            "border rounded-lg p-4 space-y-3 " +
            (isSelf ? "bg-amber-50/60 ring-1 ring-amber-200 border-amber-200" : "")
          }
        >
          <div className="flex items-baseline gap-3">
            <h3 className="text-lg font-semibold">{c.name}</h3>
            {isSelf && (
              <span className="text-[10px] px-2 py-0.5 rounded-full bg-amber-100 text-amber-800 border border-amber-200">
                ★ {t("comparison.self")}
              </span>
            )}
            {c.homepage && (
              <a
                href={c.homepage}
                target="_blank"
                rel="noreferrer"
                className="text-xs text-brand-600"
              >
                {c.homepage}
              </a>
            )}
          </div>
          <p className="text-sm text-slate-600">
            <EditableText
              value={c.short_description}
              path={`${path}.short_description`}
              editor={editor}
              t={t}
              multiline
            />
          </p>
          <p className="text-xs text-slate-500">
            <b>{t("form.market.label")}:</b>{" "}
            <EditableText
              value={c.market_position || ""}
              path={`${path}.market_position`}
              editor={editor}
              t={t}
            />
          </p>
          <ConflictBadges t={t} conflicts={c.conflicts || []} />

          <div className="grid md:grid-cols-3 gap-4 pt-2">
            <Card title="Function tree">
              <ul className="text-sm list-disc list-inside">
                {(c.function_tree?.nodes || []).map((n: any) => (
                  <li key={n.name}>
                    <span className="font-medium">{n.name}</span>
                    {n.maturity && (
                      <span className="text-[10px] ml-1 text-slate-400">({n.maturity})</span>
                    )}
                    {n.children?.length > 0 && (
                      <ul className="ml-4 list-[circle] list-inside text-slate-600">
                        {n.children.map((cc: any) => (
                          <li key={cc.name}>{cc.name}</li>
                        ))}
                      </ul>
                    )}
                  </li>
                ))}
              </ul>
            </Card>
            <Card title="Pricing">
              <div className="text-sm text-slate-600 mb-2">{c.pricing?.summary}</div>
              <ul className="space-y-1">
                {(c.pricing?.tiers || []).map((p: any) => (
                  <li key={p.name} className="text-sm flex items-baseline justify-between">
                    <span>
                      <b>{p.name}</b>
                      {typeof p.monthly_price === "number" && (
                        <span className="text-slate-500 text-xs ml-2">
                          {p.monthly_price} {p.currency}/mo
                        </span>
                      )}
                    </span>
                    <SourceBadge t={t} sources={p.sources || []} compact />
                  </li>
                ))}
              </ul>
            </Card>
            <Card title="User profile">
              <div className="text-sm text-slate-600 mb-2">{c.user_profile?.primary_segment}</div>
              <ul className="text-sm list-disc list-inside space-y-0.5">
                {(c.user_profile?.segments || []).map((s: any) => (
                  <li key={s.name}>
                    {s.name}{" "}
                    <span className="text-xs text-slate-400">({s.company_size})</span>
                  </li>
                ))}
              </ul>
              {c.user_profile?.nps_or_rating && (
                <div className="text-xs text-slate-500 mt-2">⭐ {c.user_profile.nps_or_rating}</div>
              )}
            </Card>
          </div>

          {c.swot && (
            <div className="grid md:grid-cols-4 gap-3 pt-2">
              <SwotBox label="S" items={c.swot.strengths} color="emerald" t={t} />
              <SwotBox label="W" items={c.swot.weaknesses} color="rose" t={t} />
              <SwotBox label="O" items={c.swot.opportunities} color="sky" t={t} />
              <SwotBox label="T" items={c.swot.threats} color="amber" t={t} />
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="border rounded p-3">
      <div className="text-xs uppercase tracking-wide text-slate-500 mb-2">{title}</div>
      {children}
    </div>
  );
}

function SwotBox({
  label,
  items,
  color,
  t,
}: {
  label: string;
  items: any[];
  color: string;
  t: (k: string) => string;
}) {
  const bg: Record<string, string> = {
    emerald: "bg-emerald-50 border-emerald-200",
    rose: "bg-rose-50 border-rose-200",
    sky: "bg-sky-50 border-sky-200",
    amber: "bg-amber-50 border-amber-200",
  };
  return (
    <div className={"border rounded p-3 " + bg[color]}>
      <div className="text-xs font-semibold uppercase mb-1">{label}</div>
      <ul className="text-sm space-y-1">
        {(items || []).map((it, i) => (
          <li key={i}>
            <div>{it.value}</div>
            <SourceBadge t={t} sources={it.sources || []} compact />
          </li>
        ))}
      </ul>
    </div>
  );
}

function SourcesTab({ t, report }: { t: (k: string) => string; report: any }) {
  const sources = report.all_sources || [];
  return (
    <div className="space-y-2 text-sm">
      {sources.length > 0 && (
        <div className="text-xs text-slate-500 mb-2 italic">{t("source.confidence.help")}</div>
      )}
      {sources.length === 0 && <div className="text-slate-400">—</div>}
      {sources.map((s: any) => (
        <div
          id={`source-${s.id}`}
          key={s.id}
          className="border rounded px-3 py-2 flex items-baseline gap-3 transition"
        >
          <span className="text-[10px] font-mono text-slate-400 w-16 shrink-0">
            [{shortId(s.id)}]
          </span>
          <span className="text-xs text-slate-500 w-20 shrink-0">[{s.kind}]</span>
          <div className="flex-1 min-w-0">
            {s.url ? (
              <a
                href={s.url}
                target="_blank"
                rel="noreferrer"
                className="text-brand-700 hover:underline break-all"
              >
                {s.title || s.url}
              </a>
            ) : (
              <span>{s.title || "—"}</span>
            )}
            {s.snippet && <div className="text-xs text-slate-500 mt-0.5">{s.snippet}</div>}
          </div>
          {typeof s.confidence === "number" && (
            <span
              className="text-xs text-slate-500 shrink-0"
              title={t("source.confidence.help")}
            >
              {t("source.confidence")}: {(s.confidence * 100).toFixed(0)}%
            </span>
          )}
        </div>
      ))}
    </div>
  );
}
