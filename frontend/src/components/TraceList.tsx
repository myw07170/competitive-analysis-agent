import { useState } from "react";
import type { TraceEvent } from "../api/client";

interface Props {
  t: (k: string) => string;
  events: TraceEvent[];
}

const AGENT_COLOR: Record<string, string> = {
  collector: "bg-sky-100 text-sky-800",
  analyst: "bg-violet-100 text-violet-800",
  writer: "bg-emerald-100 text-emerald-800",
  qc: "bg-rose-100 text-rose-800",
  orchestrator: "bg-slate-100 text-slate-700",
};

export default function TraceList({ t, events }: Props) {
  const [openId, setOpenId] = useState<string | null>(null);

  if (events.length === 0) {
    return <div className="text-sm text-slate-400">{t("trace.empty")}</div>;
  }

  return (
    <div className="space-y-2">
      {events.map((ev) => {
        const open = openId === ev.id;
        return (
          <div key={ev.id} className="border rounded-lg">
            <button
              onClick={() => setOpenId(open ? null : ev.id)}
              className="w-full px-3 py-2 flex items-center gap-3 text-sm hover:bg-slate-50"
            >
              <span className={"px-2 py-0.5 rounded text-xs " + (AGENT_COLOR[ev.agent] || "bg-slate-100 text-slate-700")}>
                {ev.agent}
              </span>
              <span className="font-medium">{ev.decision || ev.intent}</span>
              <span className="text-slate-400 text-xs ml-auto">
                {ev.duration_ms.toFixed(0)} ms · {ev.total_tokens} tok
                {ev.extras?.mocked ? " · mock" : ""}
              </span>
              <span className={"text-xs " + (ev.status === "ok" ? "text-emerald-600" : "text-rose-600")}>
                {ev.status}
              </span>
            </button>
            {open && (
              <div className="px-3 pb-3 space-y-2 text-xs">
                <Detail label={t("trace.detail.system")} text={ev.prompt_system} />
                <Detail label={t("trace.detail.user")} text={ev.prompt_user} />
                <Detail label={t("trace.detail.response")} text={ev.response} mono />
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function Detail({ label, text, mono = false }: { label: string; text?: string; mono?: boolean }) {
  if (!text) return null;
  return (
    <details className="border rounded">
      <summary className="px-2 py-1 cursor-pointer text-slate-600">{label}</summary>
      <pre className={"px-2 py-1 max-h-64 overflow-auto whitespace-pre-wrap " + (mono ? "font-mono" : "")}>
        {text}
      </pre>
    </details>
  );
}
