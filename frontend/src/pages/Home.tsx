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
import DAGFlow from "../components/DAGFlow";
import TraceList from "../components/TraceList";
import { Locale, makeT, marketToLocale } from "../i18n";

type Phase = "idle" | "running" | "done" | "error";

export default function Home() {
  const [markets, setMarkets] = useState<MarketInfo[]>([]);
  const [dag, setDag] = useState<DagDef | null>(null);
  const [market, setMarket] = useState<string>("cn");
  const [phase, setPhase] = useState<Phase>("idle");
  const [events, setEvents] = useState<TraceEvent[]>([]);
  const [activeNodeId, setActiveNodeId] = useState<string | null>(null);
  const [nodeStatus, setNodeStatus] = useState<Record<string, "idle" | "running" | "done" | "rework">>({});
  const [error, setError] = useState<string | null>(null);
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

  async function onStart(product: string, extra: string[]) {
    setPhase("running");
    setEvents([]);
    setNodeStatus({});
    setError(null);

    const start = await startAnalysis({ product, market, extra_competitors: extra });
    streamRun(start.run_id, {
      onTrace: (ev) => {
        setEvents((prev) => [...prev, ev]);
        const n = intentToNode(ev.intent);
        if (n) {
          setActiveNodeId(n);
          setNodeStatus((s) => ({ ...s, [n]: "done" }));
          // QC rework: mark collect node as needing rework
          if (n === "qc") {
            try {
              const parsed = ev.response ? JSON.parse(ev.response) : null;
              if (parsed?.decision === "rework") {
                setNodeStatus((s) => ({ ...s, collect: "rework" }));
              }
            } catch { /* mock data may not be JSON */ }
          }
        }
      },
      onDone: (info) => {
        setPhase(info.error ? "error" : "done");
        if (info.error) setError(info.error);
        if (info.report_id) navigate(`/report/${info.report_id}?run=${start.run_id}`);
      },
      onError: (err) => {
        setPhase("error");
        setError(String(err));
      },
    });
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
          <h2 className="font-semibold mb-3">{t("dag.title")}</h2>
          {dag ? (
            <DAGFlow
              dag={dag}
              locale={locale}
              nodeStatus={nodeStatus}
              activeNodeId={activeNodeId}
            />
          ) : (
            <div className="text-sm text-slate-400">{t("common.loading")}</div>
          )}
          <Legend t={t} />
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
    <div className="flex gap-4 text-xs text-slate-500 mt-3">
      <span className="flex items-center gap-1"><span className="w-3 h-3 rounded border bg-white inline-block" />{t("dag.legend.idle")}</span>
      <span className="flex items-center gap-1"><span className="w-3 h-3 rounded bg-amber-200 inline-block" />{t("dag.legend.running")}</span>
      <span className="flex items-center gap-1"><span className="w-3 h-3 rounded bg-emerald-200 inline-block" />{t("dag.legend.done")}</span>
      <span className="flex items-center gap-1"><span className="w-3 h-3 rounded bg-rose-200 inline-block" />{t("dag.legend.rework")}</span>
    </div>
  );
}
