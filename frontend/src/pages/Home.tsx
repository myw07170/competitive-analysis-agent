import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  DagDef,
  MarketInfo,
  TraceEvent,
  getDag,
  getMarkets,
  resumeRun,
  startAnalysis,
  streamRun,
} from "../api/client";
import AnalysisForm from "../components/AnalysisForm";
import AgentFlow, {
  NodeProgress,
  NodeStatus,
  NODE_ORDER,
  intentToNode,
} from "../components/AgentFlow";
import { Locale, makeT, marketToLocale } from "../i18n";

type Phase = "idle" | "running" | "done" | "error";

interface ProgressLine {
  ts: number;
  node: string;
  text: string;
  tone: "info" | "warn" | "ok";
}

interface HomeProps {
  // 由 App 持有，使顶栏语言能随之变化；由设置页驱动它。
  market: string;
  setMarket: (code: string) => void;
}

export default function Home({ market, setMarket }: HomeProps) {
  const [markets, setMarkets] = useState<MarketInfo[]>([]);
  const [dag, setDag] = useState<DagDef | null>(null);
  const [phase, setPhase] = useState<Phase>("idle");
  const [events, setEvents] = useState<TraceEvent[]>([]);
  const [activeNodeId, setActiveNodeId] = useState<string | null>(null);
  const [nodeStatus, setNodeStatus] = useState<Record<string, NodeStatus>>({});
  const [nodeProgress, setNodeProgress] = useState<Record<string, NodeProgress>>({});
  const [progressLog, setProgressLog] = useState<ProgressLine[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [plannedCompetitors, setPlannedCompetitors] = useState<number>(0);
  const [submittedProduct, setSubmittedProduct] = useState<string>("");
  const [runId, setRunId] = useState<string | null>(null);
  const [resuming, setResuming] = useState(false);
  // 当前周期中到达的最远流水线阶段 —— 在已越过 collect 之后再到来一个
  // collect 事件，标志着一次 QC 返工循环。
  const frontierRef = useRef(0);
  const navigate = useNavigate();

  useEffect(() => {
    getMarkets().then(setMarkets).catch(() => {});
    getDag().then(setDag).catch(() => {});
  }, []);

  const locale: Locale = marketToLocale(market);
  const t = useMemo(() => makeT(locale), [locale]);
  const started = phase !== "idle";
  const marketInfo = markets.find((m) => m.code === market);

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
    frontierRef.current = 0;
    setSubmittedProduct(product);
    setPlannedCompetitors(extra.length || 0);
    pushLog({
      node: "identify",
      tone: "info",
      text: t("progress.starting", { product }),
    });

    const start = await startAnalysis({ product, market, extra_competitors: extra });
    setRunId(start.run_id);
    attachStream(start.run_id, extra);
  }

  // 从最近的检查点恢复一次被中断的运行。
  async function onResume() {
    if (!runId) return;
    setResuming(true);
    setError(null);
    setPhase("running");
    try {
      const r = await resumeRun(runId);
      pushLog({ node: "qc", tone: "info", text: t("resume.resuming") });
      attachStream(r.run_id, []);
    } catch (e) {
      setPhase("error");
      setError(String(e));
    } finally {
      setResuming(false);
    }
  }

  function attachStream(streamRunId: string, extra: string[]) {
    streamRun(streamRunId, {
      onTrace: (ev) => {
        setEvents((prev) => [...prev, ev]);
        const n = intentToNode(ev.intent);
        if (!n) return;
        const idx = NODE_ORDER.indexOf(n);

        // QC 返工循环：在已越过 collect 之后再来一个新的 collect 事件，
        // 意味着 QC 已路由回退。重置每个下游阶段 —— 状态与进度 —— 使新一轮
        // 能干净地重新点亮它们（这正是清除陈旧的 "write"/"qc" 进度条的方式）。
        // 没有单独的 "rework" 状态；轮次徽标传达了这个循环。
        if (n === "collect" && frontierRef.current > NODE_ORDER.indexOf("collect")) {
          frontierRef.current = NODE_ORDER.indexOf("collect");
          setNodeStatus((s) => ({
            ...s,
            analyze: "idle",
            write: "idle",
            qc: "idle",
            done: "idle",
          }));
          setNodeProgress((p) => {
            const next = { ...p };
            delete next.collect;
            delete next.analyze;
            delete next.write;
            delete next.qc;
            return next;
          });
          pushLog({ node: "qc", tone: "warn", text: t("progress.qc.rework") });
        }
        frontierRef.current = Math.max(frontierRef.current, idx);

        // 根据追踪的 intent / 决策跟踪每个节点的子进度。
        setNodeProgress((p) => updateProgress(p, ev));
        pushLog({
          node: n,
          tone: ev.status === "error" ? "warn" : "info",
          text: humaniseEvent(ev, t),
        });

        setActiveNodeId(n);
        setNodeStatus((s) => {
          const next: Record<string, NodeStatus> = { ...s };
          // 当前节点保持 "running" 直到一个更后阶段的事件到来。这使一个
          // 多竞品的 collect/analyze 阶段持续处于进行中，直到所有竞品都被处理完
          //（下一阶段的第一个事件即意味着上一阶段已完成）。
          next[n] = "running";
          for (let i = 0; i < idx; i++) next[NODE_ORDER[i]] = "done";
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
            /* 忽略 */
          }
        }
      },
      onDone: (info) => {
        setPhase(info.error ? "error" : "done");
        setActiveNodeId(info.error ? null : "done");
        setNodeStatus((s) => {
          const next: Record<string, NodeStatus> = { ...s };
          if (!info.error) {
            // 最终过渡：此刻每个阶段都已完成。
            for (const id of NODE_ORDER) next[id] = "done";
          }
          return next;
        });
        if (info.error) {
          setError(info.error);
          pushLog({ node: "done", tone: "warn", text: t("progress.error", { msg: info.error }) });
        } else {
          pushLog({ node: "done", tone: "ok", text: t("progress.done") });
        }
        if (info.report_id) navigate(`/report/${info.report_id}?run=${streamRunId}`);
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

  // ── 设置界面 ─────────────────────────────────────────────────────────
  // 一个独立、居中的页面（无侧栏）。在用户启动一次运行之前它是唯一显示的内容
  // —— 流程 / 决策追踪视图在此之前隐藏。
  if (!started) {
    return (
      <div className="max-w-[var(--page-max-width)] mx-auto px-6">
        <div className="max-w-xl mx-auto py-12 sm:py-16">
          <div className="text-center mb-8">
            <h1 className="text-3xl font-semibold">{t("app.title")}</h1>
            <p className="text-slate-500 mt-2">{t("app.subtitle")}</p>
          </div>
          <div className="bg-white border rounded-2xl p-6 sm:p-8 shadow-sm">
            <AnalysisForm
              t={t}
              markets={markets}
              market={market}
              onMarketChange={setMarket}
              onStart={onStart}
              running={false}
            />
          </div>
        </div>
      </div>
    );
  }

  // ── 运行界面 ───────────────────────────────────────────────────────────
  // 一次运行启动后显示：智能体流程 + 决策追踪与实时进度。
  return (
    <div className="max-w-[var(--page-max-width)] mx-auto px-6 py-6 space-y-4">
      <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
        <h1 className="text-2xl font-semibold">{submittedProduct}</h1>
        {marketInfo && (
          <span className="inline-flex items-center gap-1.5 text-sm px-2.5 py-0.5 rounded-full bg-slate-100 text-slate-700">
            <span>{marketInfo.flag}</span>
            {marketInfo.display_name}
          </span>
        )}
      </div>

      {error && (
        <div className="bg-rose-50 border border-rose-200 text-rose-800 rounded-xl p-4 text-sm flex items-start gap-3">
          <span className="flex-1">{t("common.error")}: {error}</span>
          {runId && (
            <button
              type="button"
              disabled={resuming}
              onClick={onResume}
              className="shrink-0 text-xs px-3 py-1.5 rounded border border-rose-300 text-rose-700 hover:bg-rose-100 disabled:opacity-60"
            >
              {resuming ? t("resume.resuming") : `↻ ${t("resume.label")}`}
            </button>
          )}
        </div>
      )}

      <div className="bg-white border rounded-xl p-5">
        <div className="flex items-center justify-between mb-1">
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
        <p className="text-xs text-slate-400 mb-4">{t("flow.click_hint")}</p>

        {dag ? (
          <AgentFlow
            dag={dag}
            locale={locale}
            nodeStatus={nodeStatus}
            activeNodeId={activeNodeId}
            nodeProgress={nodeProgress}
            events={events}
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
    </div>
  );
}

function Legend({ t }: { t: (k: string) => string }) {
  return (
    <div className="flex flex-wrap gap-4 text-xs text-slate-500 mt-4 pt-3 border-t">
      <span className="flex items-center gap-1.5">
        <span className="w-3 h-3 rounded-full border-2 border-slate-300 bg-white inline-block" />
        {t("dag.legend.idle")}
      </span>
      <span className="flex items-center gap-1.5">
        <span className="w-3 h-3 rounded-full border-2 border-amber-500 bg-amber-400 inline-block animate-pulse" />
        {t("dag.legend.running")}
      </span>
      <span className="flex items-center gap-1.5">
        <span className="w-3 h-3 rounded-full border-2 border-emerald-500 bg-emerald-500 inline-block" />
        {t("dag.legend.done")}
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
