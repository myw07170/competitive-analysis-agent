import { useEffect, useMemo, useState } from "react";
import clsx from "clsx";
import type { DagDef, DagNode, TraceEvent } from "../api/client";
import type { Locale } from "../i18n";

// ---------------------------------------------------------------------------
// Shared node vocabulary (also imported by Home).
// ---------------------------------------------------------------------------
export type NodeStatus = "idle" | "running" | "done";

export interface NodeProgress {
  current: number;
  total: number;
  label?: string;
}

export const NODE_ORDER = ["identify", "collect", "analyze", "write", "qc", "done"];

/** Map a trace intent to the DAG node that produced it. */
export function intentToNode(intent: string): string | null {
  if (intent.startsWith("collector.identify")) return "identify";
  if (intent.startsWith("collector.")) return "collect";
  if (intent.startsWith("analyst.")) return "analyze";
  if (intent.startsWith("writer.")) return "write";
  if (intent.startsWith("qc.")) return "qc";
  return null;
}

type T = (k: string, vars?: Record<string, string | number>) => string;

interface Props {
  dag: DagDef;
  locale: Locale;
  nodeStatus: Record<string, NodeStatus>;
  activeNodeId: string | null;
  nodeProgress?: Record<string, NodeProgress>;
  events: TraceEvent[];
  t: T;
}

const AGENT_COLOR: Record<string, string> = {
  collector: "bg-sky-100 text-sky-700",
  analyst: "bg-violet-100 text-violet-700",
  writer: "bg-emerald-100 text-emerald-700",
  qc: "bg-rose-100 text-rose-700",
  orchestrator: "bg-slate-100 text-slate-600",
};

// ═══════════════════════════════════════════════════════════════════════════
// LAYOUT KNOB — total width of the flow + decision-trace block once a step is
// expanded. The block is centered in the card; lower this to make the expanded
// trace area narrower. Tune this single value (e.g. "70%" – "80%").
const FLOW_BLOCK_MAX_WIDTH = "78%";
// ═══════════════════════════════════════════════════════════════════════════


/**
 * Assign each event to a "round". Round 0 is the first pass; each QC review
 * (which precedes a possible rework loop) bumps the round for everything that
 * follows. This lets the trace panel group "首次 / 第N次返工" intuitively, and
 * is derived purely from the event stream (no fragile decision parsing).
 */
function computeRounds(events: TraceEvent[]): {
  roundOf: Map<string, number>;
  totalRounds: number;
} {
  const roundOf = new Map<string, number>();
  let qcSeen = 0;
  let maxRound = 0;
  for (const ev of events) {
    roundOf.set(ev.id, qcSeen);
    if (qcSeen > maxRound) maxRound = qcSeen;
    if (ev.intent === "qc.review") qcSeen += 1;
  }
  return { roundOf, totalRounds: maxRound + 1 };
}

/**
 * Agent-collaboration flowchart (left) paired with a decision-trace panel
 * (right). The flow sits centered while idle; selecting a step slides the trace
 * panel in on the right and the flowchart drifts left to make room.
 */
export default function AgentFlow({
  dag,
  locale,
  nodeStatus,
  activeNodeId,
  nodeProgress,
  events,
  t,
}: Props) {
  const useZh = locale.startsWith("zh");
  // Steps whose decision trace is currently expanded. Multiple may be open at
  // once — each step toggles independently.
  const [openIds, setOpenIds] = useState<Set<string>>(() => new Set());
  // Lags behind openIds so panel content stays mounted while the column
  // collapses (smooth close). Holds the last non-empty set for one transition.
  const [renderIds, setRenderIds] = useState<string[]>([]);

  const eventsByNode = useMemo(() => {
    const map: Record<string, TraceEvent[]> = {};
    for (const ev of events) {
      const node = intentToNode(ev.intent);
      if (!node) continue;
      (map[node] ||= []).push(ev);
    }
    return map;
  }, [events]);

  const { roundOf, totalRounds } = useMemo(() => computeRounds(events), [events]);
  const reworkRound = totalRounds - 1;

  const toggle = (id: string) =>
    setOpenIds((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });

  // Drop any open step that loses its events (e.g. when a new run resets them).
  useEffect(() => {
    setOpenIds((prev) => {
      let changed = false;
      const next = new Set(prev);
      for (const id of prev) {
        if (!(eventsByNode[id]?.length)) {
          next.delete(id);
          changed = true;
        }
      }
      return changed ? next : prev;
    });
  }, [eventsByNode]);

  // Adopt the open set immediately; on full collapse, hold the rendered panels
  // for one transition before unmounting them.
  useEffect(() => {
    if (openIds.size > 0) {
      setRenderIds(NODE_ORDER.filter((id) => openIds.has(id)));
      return;
    }
    const tid = setTimeout(() => setRenderIds([]), 500);
    return () => clearTimeout(tid);
  }, [openIds]);

  const open = openIds.size > 0;

  return (
    <div>
      {reworkRound > 0 && (
        <div className="mb-3 inline-flex items-center gap-2 text-xs px-2.5 py-1 rounded-full bg-rose-50 text-rose-700 border border-rose-200">
          <span className="w-1.5 h-1.5 rounded-full bg-rose-500" />
          {t("dag.rework.badge", { n: reworkRound })}
        </div>
      )}

      <div className="mx-auto" style={{ maxWidth: open ? FLOW_BLOCK_MAX_WIDTH : undefined }}>
        <div
          className="grid items-start transition-[grid-template-columns] duration-500 ease-out"
          style={{
            justifyContent: "center",
            gridTemplateColumns: open
              ? "300px minmax(0, 1fr)"
              : "300px minmax(0, 0fr)",
          }}
        >
          {/* Flowchart column */}
          <div className="min-w-0">
            {dag.nodes.map((n, i) => (
              <div key={n.id}>
                <NodeBlock
                  n={n}
                  useZh={useZh}
                  status={nodeStatus[n.id] || "idle"}
                  isActive={n.id === activeNodeId}
                  progress={nodeProgress?.[n.id]}
                  count={(eventsByNode[n.id] || []).length}
                  selected={openIds.has(n.id)}
                  onClick={() => toggle(n.id)}
                  t={t}
                />
                {i < dag.nodes.length - 1 && (
                  <Arrow done={(nodeStatus[n.id] || "idle") === "done"} />
                )}
              </div>
            ))}
          </div>

          {/* Decision-trace panels — clipped while collapsed, slide in when open.
              One panel per expanded step, stacked in pipeline order. */}
          <div className="overflow-hidden min-w-0">
            <div className="min-w-[340px] pl-4 space-y-3">
              {renderIds.map((id) => {
                const node = dag.nodes.find((n) => n.id === id);
                if (!node) return null;
                return (
                  <TracePanel
                    key={id}
                    node={node}
                    useZh={useZh}
                    events={eventsByNode[id] || []}
                    roundOf={roundOf}
                    totalRounds={totalRounds}
                    onClose={() => toggle(id)}
                    t={t}
                  />
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function NodeBlock({
  n,
  useZh,
  status,
  isActive,
  progress,
  count,
  selected,
  onClick,
  t,
}: {
  n: DagNode;
  useZh: boolean;
  status: NodeStatus;
  isActive: boolean;
  progress?: NodeProgress;
  count: number;
  selected: boolean;
  onClick: () => void;
  t: T;
}) {
  const clickable = count > 0;
  return (
    <button
      type="button"
      disabled={!clickable}
      onClick={onClick}
      className={clsx(
        "w-full text-left rounded-lg border px-3 py-2.5 transition-all",
        status === "running" && "border-amber-300 bg-amber-50/60",
        status === "done" && "border-emerald-200 bg-emerald-50/40",
        status === "idle" && "border-slate-200 bg-white",
        selected && "ring-2 ring-brand-500 border-brand-500",
        clickable ? "cursor-pointer hover:shadow-sm" : "cursor-default",
      )}
    >
      <div className="flex items-center gap-2">
        <StatusDot status={status} isActive={isActive} />
        <span className="font-medium text-sm">
          {useZh ? n.label_zh : n.label_en}
        </span>
        <span className="ml-auto flex items-center gap-1.5">
          {count > 0 && (
            <span className="text-[11px] text-slate-400 tabular-nums">×{count}</span>
          )}
          {clickable && (
            <span
              className={clsx(
                "text-xs transition-transform duration-200",
                selected ? "text-brand-600 rotate-90" : "text-slate-300",
              )}
            >
              ›
            </span>
          )}
        </span>
      </div>

      <div className="flex items-center gap-2 mt-1">
        <span
          className={clsx(
            "text-[10px] px-1.5 py-0.5 rounded uppercase tracking-wide",
            AGENT_COLOR[n.agent] || "bg-slate-100 text-slate-600",
          )}
        >
          {n.agent}
        </span>
        <StatusBadge status={status} t={t} />
      </div>

      {progress && progress.total > 0 && status !== "idle" && (
        <div className="mt-2">
          <div className="flex justify-between text-[10px] text-slate-500">
            <span className="truncate pr-2" title={progress.label}>
              {progress.label || ""}
            </span>
            <span className="tabular-nums shrink-0">
              {progress.current}/{progress.total}
            </span>
          </div>
          <div className="h-1 bg-slate-200 rounded overflow-hidden mt-1">
            <div
              className={clsx(
                "h-1 transition-all",
                status === "done" ? "bg-emerald-500" : "bg-amber-500",
              )}
              style={{
                width: `${Math.min(
                  100,
                  (progress.current / Math.max(1, progress.total)) * 100,
                )}%`,
              }}
            />
          </div>
        </div>
      )}
    </button>
  );
}

function StatusDot({ status, isActive }: { status: NodeStatus; isActive: boolean }) {
  return (
    <span
      className={clsx(
        "w-3 h-3 rounded-full border-2 shrink-0",
        status === "done" && "border-emerald-500 bg-emerald-500",
        status === "running" && "border-amber-500 bg-amber-400",
        status === "idle" && "border-slate-300 bg-white",
        status === "running" && isActive && "animate-pulse",
      )}
    />
  );
}

function Arrow({ done }: { done: boolean }) {
  return (
    <div className="flex justify-center py-1" aria-hidden>
      <svg
        width="14"
        height="20"
        viewBox="0 0 14 20"
        className={done ? "text-emerald-400" : "text-slate-300"}
      >
        <line x1="7" y1="0" x2="7" y2="14" stroke="currentColor" strokeWidth="2" />
        <path
          d="M2 12 L7 19 L12 12"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </div>
  );
}

function StatusBadge({ status, t }: { status: NodeStatus; t: T }) {
  const map: Record<NodeStatus, { key: string; cls: string }> = {
    idle: { key: "dag.legend.idle", cls: "bg-slate-100 text-slate-500" },
    running: { key: "dag.legend.running", cls: "bg-amber-100 text-amber-700" },
    done: { key: "dag.legend.done", cls: "bg-emerald-100 text-emerald-700" },
  };
  const m = map[status];
  return (
    <span className={clsx("text-[10px] px-1.5 py-0.5 rounded-full", m.cls)}>
      {status === "running" && (
        <span className="inline-block w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse mr-1 align-middle" />
      )}
      {t(m.key)}
    </span>
  );
}

function TracePanel({
  node,
  useZh,
  events,
  roundOf,
  totalRounds,
  onClose,
  t,
}: {
  node: DagNode;
  useZh: boolean;
  events: TraceEvent[];
  roundOf: Map<string, number>;
  totalRounds: number;
  onClose: () => void;
  t: T;
}) {
  const groups = useMemo(() => {
    const m = new Map<number, TraceEvent[]>();
    for (const ev of events) {
      const r = roundOf.get(ev.id) ?? 0;
      if (!m.has(r)) m.set(r, []);
      m.get(r)!.push(ev);
    }
    return [...m.entries()].sort((a, b) => a[0] - b[0]);
  }, [events, roundOf]);

  const grouped = totalRounds > 1;

  return (
    <div className="rounded-lg border bg-slate-50/40 flex flex-col max-h-[560px]">
      <div className="flex items-center gap-2 px-3 py-2 border-b bg-white rounded-t-lg">
        <span className="font-semibold text-sm">
          {useZh ? node.label_zh : node.label_en}
        </span>
        <span className="text-[11px] text-slate-400">· {t("trace.title")}</span>
        <span className="text-[11px] text-slate-400 tabular-nums">×{events.length}</span>
        <button
          type="button"
          onClick={onClose}
          aria-label={t("common.close")}
          className="ml-auto w-6 h-6 flex items-center justify-center rounded text-slate-400 hover:bg-slate-100 hover:text-slate-600"
        >
          ✕
        </button>
      </div>

      <div className="p-3 space-y-3 overflow-y-auto">
        {events.length === 0 && (
          <div className="text-xs text-slate-400">{t("trace.empty")}</div>
        )}
        {grouped
          ? groups.map(([round, evs]) => (
              <div key={round} className="space-y-1.5">
                <RoundHeader round={round} t={t} />
                {evs.map((ev) => (
                  <EventRow key={ev.id} ev={ev} t={t} />
                ))}
              </div>
            ))
          : events.map((ev) => <EventRow key={ev.id} ev={ev} t={t} />)}
      </div>
    </div>
  );
}

function RoundHeader({ round, t }: { round: number; t: T }) {
  const label =
    round === 0 ? t("trace.round.first") : t("trace.round.rework", { n: round });
  return (
    <div className="flex items-center gap-2">
      <span
        className={clsx(
          "text-[11px] font-medium px-2 py-0.5 rounded-full",
          round === 0 ? "bg-slate-200 text-slate-600" : "bg-rose-100 text-rose-700",
        )}
      >
        {label}
      </span>
      <span className="flex-1 h-px bg-slate-200" />
    </div>
  );
}

function EventRow({ ev, t }: { ev: TraceEvent; t: T }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border rounded-md bg-white">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full px-2.5 py-1.5 flex items-center gap-2 text-xs hover:bg-slate-50"
      >
        <span className="font-medium text-slate-700 truncate">
          {ev.decision || ev.intent}
        </span>
        <span className="ml-auto text-slate-400 tabular-nums shrink-0">
          {ev.duration_ms.toFixed(0)} ms · {ev.total_tokens} tok
          {ev.extras?.mocked ? " · mock" : ""}
        </span>
        <span
          className={clsx(
            "shrink-0",
            ev.status === "ok" ? "text-emerald-600" : "text-rose-600",
          )}
        >
          {ev.status}
        </span>
        <span className={clsx("text-slate-400 transition-transform", open && "rotate-90")}>
          ▸
        </span>
      </button>
      {open && (
        <div className="px-2.5 pb-2 space-y-1.5 text-[11px]">
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
      <pre
        className={clsx(
          "px-2 py-1 max-h-64 overflow-auto whitespace-pre-wrap",
          mono && "font-mono",
        )}
      >
        {text}
      </pre>
    </details>
  );
}
