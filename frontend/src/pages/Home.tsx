import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  DagDef,
  MarketInfo,
  TraceEvent,
  getDag,
  getMarkets,
  startAnalysis,
  streamRun,
} from "../api/client";
import AnalysisForm from "../components/AnalysisForm";
import DAGFlow, { NodeProgress } from "../components/DAGFlow";
import TraceList from "../components/TraceList";
import { Locale, makeT, marketToLocale } from "../i18n";

type Phase = "idle" | "running" | "done" | "error";
type NodeStatus = "idle" | "running" | "done" | "rework";

interface ProgressLine {
  ts: number;
  node: string;
  text: string;
  tone: "info" | "warn" | "ok";
}

const NODE_ORDER = ["identify", "collect", "analyze", "write", "qc", "done"];

export default function Home() {
  const [markets, setMarkets] = useState<MarketInfo[]>([]);
  const [dag, setDag] = useState<DagDef | null>(null);
  const [market, setMarket] = useState<string>("cn");
  const [phase, setPhase] = useState<Phase>("idle");
  const [events, setEvents] = useState<TraceEvent[]>([]);
  const [activeNodeId, setActiveNodeId] = useState<string | null>(null);
  const [nodeStatus, setNodeStatus] = useState<Record<string, NodeStatus>>({});
  const [nodeProgress, setNodeProgress] = useState<Record<string, NodeProgress>>({});
  const [progressLog, setProgressLog] = useState<ProgressLine[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [plannedCompetitors, setPlannedCompetitors] = useState<number>(0);
  const navigate = useNavigate();

  useEffect(() => {
    getMarkets().then(setMarkets).catch(() => {});
    getDag().then(setDag).catch(() => {});
  }, []);

  const locale: Locale = marketToLocale(market);
  const t = useMemo(() => makeT(locale), [locale]);

  function intentToNode(intent: string): string | null {
    if (intent.startsWith("collector.identify")) return "identify";
    if (intent.startsWith("collector.")) return "collect";
    if (intent.startsWith("analyst.")) return "analyze";
    if (intent.startsWith("writer.")) return "write";
    if (intent.startsWith("qc.")) return "qc";
    return null;
  }

  function pushLog(line: Omit<ProgressLine, "ts">) {
    setProgressLog((l) => [...l, { ...line, ts: Date.now() }].slice(-50));
  }

  async function onStart(product: string, extra: string[]) {
    setPhase("running");
    setEvents([]);
    setError(null);
    setActiveNodeId("identify");
    setNodeStatus({ identify: "running" });
    setNodeProgress({});
    setProgressLog([]);
    setPlannedCompetitors(extra.length || 0);
    pushLog({
      node: "identify",
      tone: "info",
      text: t("progress.starting", { product }),
    });

    const start = await startAnalysis({ product, market, extra_competitors: extra });
    streamRun(start.run_id, {
      onTrace: (ev) => {
        setEvents((prev) => [...prev, ev]);
        const n = intentToNode(ev.intent);
        if (!n) return;

        // Track sub-progress per node from the trace intents / decisions.
        setNodeProgress((p) => updateProgress(p, ev));
        pushLog({
          node: n,
          tone: ev.status === "error" ? "warn" : "info",
          text: humaniseEvent(ev, t),
        });

        setActiveNodeId(n);
        setNodeStatus((s) => {
          const next: Record<string, NodeStatus> = { ...s };
          // Current node is still "running" — it only transitions to "done"
          // when a later-stage event arrives. This keeps a multi-competitor
          // collect/analyze stage marked as in-progress until ALL competitors
          // have been processed (the next stage's first event implies the
          // previous stage is complete).
          next[n] = next[n] === "rework" ? "rework" : "running";
          const idx = NODE_ORDER.indexOf(n);
          for (let i = 0; i < idx; i++) {
            const prev = NODE_ORDER[i];
            if (next[prev] !== "rework") next[prev] = "done";
          }
          // QC rework: mark collect node as needing rework so the next round
          // of collect events relight it as running.
          if (n === "qc") {
            try {
              const parsed = ev.response ? JSON.parse(ev.response) : null;
              if (parsed?.decision === "rework") {
                next["collect"] = "rework";
                next["analyze"] = "rework";
                pushLog({ node: "qc", tone: "warn", text: t("progress.qc.rework") });
              }
            } catch {
              /* mock data may not be JSON */
            }
          }
          return next;
        });

        if (n === "identify") {
          try {
            const parsed = ev.response ? JSON.parse(ev.response) : null;
            const names: string[] = parsed?.competitors?.map((c: any) => c.name).filter(Boolean) || [];
            if (names.length) {
              const total = names.length + extra.length;
              setPlannedCompetitors(total);
              pushLog({
                node: "identify",
                tone: "ok",
                text: t("progress.identify.found", { names: names.join(" · "), total: String(total) }),
              });
            }
          } catch {
            /* ignore */
          }
        }
      },
      onDone: (info) => {
        setPhase(info.error ? "error" : "done");
        setActiveNodeId(info.error ? null : "done");
        setNodeStatus((s) => {
          const next: Record<string, NodeStatus> = { ...s };
          if (!info.error) {
            // Final transition: every prior stage must be done now.
            for (const id of NODE_ORDER) {
              if (next[id] !== "rework") next[id] = "done";
            }
            next["done"] = "done";
          } else {
            next["done"] = "rework";
          }
          return next;
        });
        if (info.error) {
          setError(info.error);
          pushLog({ node: "done", tone: "warn", text: t("progress.error", { msg: info.error }) });
        } else {
          pushLog({ node: "done", tone: "ok", text: t("progress.done") });
        }
        if (info.report_id) navigate(`/report/${info.report_id}?run=${start.run_id}`);
      },
      onError: (err) => {
        setPhase("error");
        setError(String(err));
        pushLog({ node: "done", tone: "warn", text: t("progress.error", { msg: String(err) }) });
      },
    });
  }

  function updateProgress(
    prev: Record<string, NodeProgress>,
    ev: TraceEvent,
  ): Record<string, NodeProgress> {
    const node = intentToNode(ev.intent);
    if (!node) return prev;
    const cur = prev[node] || { current: 0, total: 0, label: "" };

    if (node === "collect" && ev.intent === "collector.gather_competitor") {
      return {
        ...prev,
        [node]: {
          current: cur.current + 1,
          total: Math.max(cur.total, plannedCompetitors, cur.current + 1),
          label: ev.decision || ev.intent,
        },
      };
    }
    if (node === "analyze" && ev.intent === "analyst.swot") {
      return {
        ...prev,
        [node]: {
          current: cur.current + 1,
          total: Math.max(cur.total, plannedCompetitors, cur.current + 1),
          label: ev.decision || ev.intent,
        },
      };
    }
    if (node === "qc") {
      return {
        ...prev,
        [node]: { current: cur.current + 1, total: cur.current + 1, label: ev.decision || "review" },
      };
    }
    return {
      ...prev,
      [node]: { current: 1, total: 1, label: ev.decision || ev.intent },
    };
  }

  return (
    <div className="max-w-7xl mx-auto px-6 py-6 grid grid-cols-1 lg:grid-cols-3 gap-6">
      <section className="lg:col-span-1 space-y-4">
        <div className="bg-white border rounded-xl p-5">
          <h1 className="text-xl font-semibold mb-1">{t("app.title")}</h1>
          <p className="text-sm text-slate-500 mb-4">{t("app.subtitle")}</p>
          <AnalysisForm
            t={t}
            markets={markets}
            market={market}
            onMarketChange={setMarket}
            onStart={onStart}
            running={phase === "running"}
          />
        </div>

        {error && (
          <div className="bg-rose-50 border border-rose-200 text-rose-800 rounded-xl p-4 text-sm">
            {t("common.error")}: {error}
          </div>
        )}
      </section>

      <section className="lg:col-span-2 space-y-4">
        <div className="bg-white border rounded-xl p-5">
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-semibold">{t("dag.title")}</h2>
            {phase === "running" && (
              <span className="inline-flex items-center gap-2 text-xs px-2 py-0.5 rounded-full bg-amber-100 text-amber-800">
                <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse" />
                {t("dag.legend.running")}
              </span>
            )}
            {phase === "done" && (
              <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800">
                {t("dag.legend.done")}
              </span>
            )}
          </div>
          {dag ? (
            <DAGFlow
              dag={dag}
              locale={locale}
              nodeStatus={nodeStatus}
              activeNodeId={activeNodeId}
              nodeProgress={nodeProgress}
              t={t}
            />
          ) : (
            <div className="text-sm text-slate-400">{t("common.loading")}</div>
          )}
          <Legend t={t} />
          {(phase === "running" || progressLog.length > 0) && (
            <ProgressFeed t={t} lines={progressLog} />
          )}
        </div>

        <div className="bg-white border rounded-xl p-5">
          <h2 className="font-semibold mb-3">{t("trace.title")}</h2>
          <TraceList t={t} events={events} />
        </div>
      </section>
    </div>
  );
}

function Legend({ t }: { t: (k: string) => string }) {
  return (
    <div className="flex flex-wrap gap-4 text-xs text-slate-500 mt-3">
      <span className="flex items-center gap-1.5">
        <span className="w-3 h-3 rounded border bg-white inline-block" />
        {t("dag.legend.idle")}
      </span>
      <span className="flex items-center gap-1.5">
        <span className="w-3 h-3 rounded bg-amber-200 border border-amber-400 inline-block animate-pulse" />
        {t("dag.legend.running")}
      </span>
      <span className="flex items-center gap-1.5">
        <span className="w-3 h-3 rounded bg-emerald-200 border border-emerald-400 inline-block" />
        {t("dag.legend.done")}
      </span>
      <span className="flex items-center gap-1.5">
        <span className="w-3 h-3 rounded bg-rose-200 border border-rose-400 inline-block" />
        {t("dag.legend.rework")}
      </span>
    </div>
  );
}

function humaniseEvent(ev: TraceEvent, t: (k: string, v?: Record<string, string>) => string): string {
  const intent = ev.intent;
  if (intent === "collector.identify_competitors") return t("progress.identify.start");
  if (intent === "collector.gather_competitor") return t("progress.collect.one", { name: extractName(ev.decision) });
  if (intent === "collector.rework") return t("progress.collect.rework", { name: extractName(ev.decision) });
  if (intent === "analyst.swot") return t("progress.analyze.one", { name: extractName(ev.decision) });
  if (intent === "writer.report") return t("progress.writer");
  if (intent === "qc.review") return t("progress.qc");
  return ev.decision || ev.intent;
}

function extractName(decision: string | undefined): string {
  if (!decision) return "—";
  const m = decision.match(/\(([^,)]+)/);
  return m ? m[1].trim() : decision;
}

function ProgressFeed({
  t,
  lines,
}: {
  t: (k: string) => string;
  lines: ProgressLine[];
}) {
  const [expanded, setExpanded] = useState(false);
  const latest = lines.length > 0 ? lines[lines.length - 1] : null;
  const history = lines.slice(0, -1).slice().reverse();

  const toneClass = (tone: ProgressLine["tone"]) =>
    tone === "warn"
      ? "bg-rose-100 text-rose-800"
      : tone === "ok"
      ? "bg-emerald-100 text-emerald-800"
      : "bg-slate-100 text-slate-700";

  return (
    <div className="mt-4 border-t pt-3">
      <div className="flex items-center justify-between mb-2">
        <div className="text-xs font-medium text-slate-600">{t("progress.feed")}</div>
        {lines.length > 1 && (
          <button
            onClick={() => setExpanded((v) => !v)}
            className="text-[11px] px-2 py-0.5 rounded border border-slate-200 hover:bg-slate-50 text-slate-600"
            aria-expanded={expanded}
          >
            {expanded
              ? `${t("progress.collapse") || "Collapse"} ▴`
              : `${t("progress.expand") || "Expand"} (${lines.length}) ▾`}
          </button>
        )}
      </div>

      {!latest && <div className="text-xs text-slate-400">—</div>}

      {latest && (
        <div className="flex items-start gap-2 text-xs">
          <span className="text-slate-400 w-14 shrink-0 tabular-nums">
            {new Date(latest.ts).toLocaleTimeString().slice(0, 8)}
          </span>
          <span className={"px-1.5 rounded shrink-0 " + toneClass(latest.tone)}>
            {latest.node}
          </span>
          <span className="text-slate-700 flex-1">{latest.text}</span>
        </div>
      )}

      {expanded && history.length > 0 && (
        <ul className="space-y-1 max-h-56 overflow-y-auto pr-2 mt-2 pt-2 border-t border-dashed border-slate-200">
          {history.map((l, i) => (
            <li key={i} className="flex items-start gap-2 text-xs opacity-80">
              <span className="text-slate-400 w-14 shrink-0 tabular-nums">
                {new Date(l.ts).toLocaleTimeString().slice(0, 8)}
              </span>
              <span className={"px-1.5 rounded shrink-0 " + toneClass(l.tone)}>{l.node}</span>
              <span className="text-slate-700 flex-1">{l.text}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
