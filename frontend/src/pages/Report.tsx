import { useEffect, useMemo, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { getReport, getTrace, TraceEvent } from "../api/client";
import SourceBadge from "../components/SourceBadge";
import TraceList from "../components/TraceList";
import { Locale, makeT, marketToLocale } from "../i18n";

export default function Report() {
  const { reportId } = useParams<{ reportId: string }>();
  const [params] = useSearchParams();
  const runId = params.get("run");

  const [report, setReport] = useState<any>(null);
  const [events, setEvents] = useState<TraceEvent[]>([]);
  const [tab, setTab] = useState<"report" | "competitors" | "trace" | "sources">("report");

  useEffect(() => {
    if (reportId) getReport(reportId).then(setReport).catch(() => {});
  }, [reportId]);

  useEffect(() => {
    if (runId) getTrace(runId).then(setEvents).catch(() => {});
  }, [runId]);

  const locale: Locale = useMemo(() => (report?.locale as Locale) || "en-US", [report]);
  const t = useMemo(() => makeT(locale), [locale]);

  if (!report) {
    return <div className="max-w-5xl mx-auto p-6 text-slate-500">{t("common.loading")}</div>;
  }

  return (
    <div className="max-w-6xl mx-auto p-6 space-y-4">
      <div className="bg-white border rounded-xl p-5">
        <div className="flex items-baseline gap-3 mb-1">
          <h1 className="text-2xl font-semibold">{report.title}</h1>
          <span className="text-xs px-2 py-0.5 bg-slate-100 rounded">{report.market.toUpperCase()}</span>
          <span className="text-xs text-slate-500">{report.locale}</span>
        </div>
        <p className="text-sm text-slate-500 mb-3">
          {t("form.product.label")}: <b>{report.product}</b> · {new Date(report.generated_at).toLocaleString()}
        </p>

        <MetricsBar t={t} metrics={report.metrics} />
      </div>

      <div className="bg-white border rounded-xl">
        <div className="border-b flex gap-1 px-3">
          {([
            ["report", t("report.title")],
            ["competitors", t("report.competitors")],
            ["trace", t("trace.title")],
            ["sources", t("report.sources")],
          ] as const).map(([k, label]) => (
            <button
              key={k}
              onClick={() => setTab(k)}
              className={
                "px-3 py-2 text-sm border-b-2 -mb-px " +
                (tab === k ? "border-brand-600 text-brand-700" : "border-transparent text-slate-500")
              }
            >
              {label}
            </button>
          ))}
        </div>

        <div className="p-5">
          {tab === "report" && <ReportBody t={t} report={report} />}
          {tab === "competitors" && <CompetitorsTab t={t} report={report} />}
          {tab === "trace" && <TraceList t={t} events={events} />}
          {tab === "sources" && <SourcesTab t={t} report={report} />}
        </div>
      </div>
    </div>
  );
}

function MetricsBar({ t, metrics }: { t: (k: string) => string; metrics: any }) {
  if (!metrics) return null;
  const cells = [
    [t("metrics.elapsed"), `${metrics.elapsed_seconds.toFixed(1)} s`],
    [t("metrics.tokens"), metrics.total_tokens],
    [t("metrics.llm_calls"), metrics.total_llm_calls],
    [t("metrics.completeness"), `${(metrics.schema_completeness * 100).toFixed(0)}%`],
    [t("metrics.avg_sources"), metrics.avg_sources_per_competitor],
    [t("metrics.iterations"), metrics.qc_iterations],
    [t("metrics.rework"), metrics.rework_count],
  ];
  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-2">
      {cells.map(([k, v]) => (
        <div key={k} className="border rounded px-3 py-2">
          <div className="text-[10px] uppercase tracking-wide text-slate-500">{k}</div>
          <div className="text-sm font-semibold">{v}</div>
        </div>
      ))}
    </div>
  );
}

function ReportBody({ t, report }: { t: (k: string) => string; report: any }) {
  return (
    <div className="markdown-body">
      <h2>{t("report.executive")}</h2>
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{report.executive_summary_md || ""}</ReactMarkdown>
      {(report.sections || []).map((s: any, i: number) => (
        <section key={i}>
          <h2>{s.heading}</h2>
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{s.body_md || ""}</ReactMarkdown>
          {s.sources?.length > 0 && <SourceBadge t={t} sources={s.sources} />}
        </section>
      ))}
    </div>
  );
}

function CompetitorsTab({ t, report }: { t: (k: string) => string; report: any }) {
  return (
    <div className="space-y-6">
      {(report.competitors || []).map((c: any) => (
        <div key={c.name} className="border rounded-lg p-4 space-y-3">
          <div className="flex items-baseline gap-3">
            <h3 className="text-lg font-semibold">{c.name}</h3>
            {c.homepage && (
              <a href={c.homepage} target="_blank" rel="noreferrer" className="text-xs text-brand-600">
                {c.homepage}
              </a>
            )}
          </div>
          <p className="text-sm text-slate-600">{c.short_description}</p>
          {c.market_position && (
            <p className="text-xs text-slate-500"><b>{t("form.market.label")}:</b> {c.market_position}</p>
          )}

          <div className="grid md:grid-cols-3 gap-4 pt-2">
            <Card title="Function tree">
              <ul className="text-sm list-disc list-inside">
                {(c.function_tree?.nodes || []).map((n: any) => (
                  <li key={n.name}>
                    <span className="font-medium">{n.name}</span>
                    {n.maturity && <span className="text-[10px] ml-1 text-slate-400">({n.maturity})</span>}
                    {n.children?.length > 0 && (
                      <ul className="ml-4 list-[circle] list-inside text-slate-600">
                        {n.children.map((cc: any) => <li key={cc.name}>{cc.name}</li>)}
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
              <div className="text-sm text-slate-600 mb-2">
                {c.user_profile?.primary_segment}
              </div>
              <ul className="text-sm list-disc list-inside space-y-0.5">
                {(c.user_profile?.segments || []).map((s: any) => (
                  <li key={s.name}>{s.name} <span className="text-xs text-slate-400">({s.company_size})</span></li>
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

function SwotBox({ label, items, color, t }: { label: string; items: any[]; color: string; t: (k: string) => string }) {
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
      {sources.length === 0 && <div className="text-slate-400">—</div>}
      {sources.map((s: any) => (
        <div key={s.id} className="border rounded px-3 py-2 flex items-baseline gap-3">
          <span className="text-xs text-slate-500 w-20">[{s.kind}]</span>
          <div className="flex-1">
            {s.url ? (
              <a href={s.url} target="_blank" rel="noreferrer" className="text-brand-700 hover:underline">
                {s.title || s.url}
              </a>
            ) : (
              <span>{s.title}</span>
            )}
            {s.snippet && <div className="text-xs text-slate-500 mt-0.5">{s.snippet}</div>}
          </div>
          {typeof s.confidence === "number" && (
            <span className="text-xs text-slate-400">{(s.confidence * 100).toFixed(0)}%</span>
          )}
        </div>
      ))}
    </div>
  );
}
