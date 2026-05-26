import { useMemo, useState } from "react";
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

// Intents that should be merged together when they appear contiguously for
// the same agent — e.g. swot(douyin), swot(weixin), swot(xhs) all roll into
// one "SWOT analysis" group.
const GROUPABLE_INTENTS: Record<string, string> = {
  "analyst.swot": "trace.group.swot",
  "collector.gather_competitor": "trace.group.gather",
  "collector.rework": "trace.group.rework",
};

interface TraceGroup {
  key: string;
  agent: string;
  intentKey: string; // groupable intent or full intent
  label: string;
  events: TraceEvent[];
}

export default function TraceList({ t, events }: Props) {
  const [openId, setOpenId] = useState<string | null>(null);
  const [openGroupId, setOpenGroupId] = useState<string | null>(null);

  const groups = useMemo(() => buildGroups(events, t), [events, t]);

  if (events.length === 0) {
    return <div className="text-sm text-slate-400">{t("trace.empty")}</div>;
  }

  return (
    <div className="space-y-2">
      {groups.map((g) => {
        if (g.events.length === 1) {
          return (
            <SingleEvent
              key={g.key}
              ev={g.events[0]}
              open={openId === g.events[0].id}
              onToggle={() => setOpenId(openId === g.events[0].id ? null : g.events[0].id)}
              t={t}
            />
          );
        }
        const groupOpen = openGroupId === g.key;
        const total = g.events.reduce((s, e) => s + e.total_tokens, 0);
        const dur = g.events.reduce((s, e) => s + e.duration_ms, 0);
        const errored = g.events.some((e) => e.status !== "ok");
        return (
          <div key={g.key} className="border rounded-lg bg-slate-50/60">
            <button
              onClick={() => setOpenGroupId(groupOpen ? null : g.key)}
              className="w-full px-3 py-2 flex items-center gap-3 text-sm hover:bg-slate-100/60"
            >
              <span
                className={
                  "px-2 py-0.5 rounded text-xs " +
                  (AGENT_COLOR[g.agent] || "bg-slate-100 text-slate-700")
                }
              >
                {g.agent}
              </span>
              <span className="font-medium">{g.label}</span>
              <span className="text-xs px-1.5 py-0.5 bg-white border rounded text-slate-500">
                ×{g.events.length}
              </span>
              <span className="text-slate-400 text-xs ml-auto">
                {dur.toFixed(0)} ms · {total} tok
              </span>
              <span className={"text-xs " + (errored ? "text-rose-600" : "text-emerald-600")}>
                {errored ? "partial" : "ok"}
              </span>
              <span className="text-slate-400 text-xs">{groupOpen ? "▾" : "▸"}</span>
            </button>
            {groupOpen && (
              <div className="px-3 pb-2 space-y-1.5 border-t bg-white">
                {g.events.map((ev) => (
                  <div key={ev.id} className="pt-2">
                    <SingleEvent
                      ev={ev}
                      open={openId === ev.id}
                      onToggle={() => setOpenId(openId === ev.id ? null : ev.id)}
                      t={t}
                      nested
                    />
                  </div>
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function buildGroups(events: TraceEvent[], t: (k: string) => string): TraceGroup[] {
  const groups: TraceGroup[] = [];
  for (const ev of events) {
    const groupable = GROUPABLE_INTENTS[ev.intent];
    const last = groups[groups.length - 1];
    if (groupable && last && last.intentKey === ev.intent && last.agent === ev.agent) {
      last.events.push(ev);
      continue;
    }
    groups.push({
      key: `g_${groups.length}_${ev.id}`,
      agent: ev.agent,
      intentKey: groupable ? ev.intent : ev.id,
      label: groupable ? t(groupable) : ev.decision || ev.intent,
      events: [ev],
    });
  }
  return groups;
}

function SingleEvent({
  ev,
  open,
  onToggle,
  t,
  nested = false,
}: {
  ev: TraceEvent;
  open: boolean;
  onToggle: () => void;
  t: (k: string) => string;
  nested?: boolean;
}) {
  return (
    <div className={"border rounded-lg " + (nested ? "border-slate-200" : "")}>
      <button
        onClick={onToggle}
        className="w-full px-3 py-2 flex items-center gap-3 text-sm hover:bg-slate-50"
      >
        {!nested && (
          <span
            className={
              "px-2 py-0.5 rounded text-xs " +
              (AGENT_COLOR[ev.agent] || "bg-slate-100 text-slate-700")
            }
          >
            {ev.agent}
          </span>
        )}
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
