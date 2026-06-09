import { Fragment, useEffect, useMemo, useState } from "react";
import clsx from "clsx";
import type { DagDef, DagNode, TraceEvent } from "../api/client";
import type { Locale } from "../i18n";

// ---------------------------------------------------------------------------
// 共享的节点词汇（也被 Home 导入）。
// ---------------------------------------------------------------------------
export type NodeStatus = "idle" | "running" | "done";

export interface NodeProgress {
  current: number;
  total: number;
  label?: string;
}

export const NODE_ORDER = ["identify", "collect", "analyze", "write", "qc", "done"];

/** 把一个追踪 intent 映射到产生它的 DAG 节点。 */
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
// 布局旋钮 —— 两列可独立调节。
//
//   FLOWCHART_WIDTH  左侧"协作流程图"列的宽度。
//   TRACE_WIDTH      展开某步骤后右侧"决策追踪"列的宽度。请使用 CSS 长度
//                    （px / rem）而非分数，使展开 / 收起的过渡动画平滑。
//   COLUMN_GAP       展开时流程列与追踪列之间的水平间距
//                    （"稍微大一点" → 调大这个值）。
const FLOWCHART_WIDTH = "240px";
const TRACE_WIDTH = "600px";
const COLUMN_GAP = "3rem";
// ═══════════════════════════════════════════════════════════════════════════


/**
 * 把每个事件归入一个"轮次"。第 0 轮是首遍；每一次 QC 审查（它先于一次可能的
 * 返工循环）都会把其后所有内容的轮次加一。这让追踪面板能直观地按
 * "首次 / 第N次返工"分组，并且纯粹从事件流推导得出（无需脆弱的决策解析）。
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
 * 智能体协作流程图（左）搭配一个决策追踪面板（右）。空闲时流程图居中；
 * 选中某个步骤会让追踪面板从右侧滑入，流程图向左漂移以腾出空间。
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
  // 当前展开了决策追踪的步骤。可同时展开多个 —— 每个步骤独立切换。
  const [openIds, setOpenIds] = useState<Set<string>>(() => new Set());
  // 滞后于 openIds，使列收起时面板内容仍保持挂载（平滑关闭）。
  // 在一次过渡期间保留最后一个非空集合。
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

  // 丢弃任何失去其事件的已展开步骤（例如新一次运行重置了它们时）。
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

  // 立即采用展开集合；完全收起时，在卸载已渲染面板前保留它们一次过渡。
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

      {/* 每个步骤一行网格：左单元 = 流程步骤 + 连接线，右单元 = 该步骤的决策追踪。
          因为两个单元共享一行，它们的顶部对齐。`items-stretch` 让每个单元填满行高，于是：
          • 比步骤更高的追踪会拉伸该行 → 连接线变长，下一步骤随之下移以保持对齐
            （需求 1，"靠下"情形）；
          • 比步骤更靠上的追踪会被其上方步骤的空右单元向下推（需求 1，"靠上"情形）。
          列宽 / 间距是上面那些可调旋钮。 */}
      <div
        className="grid items-stretch"
        style={{
          justifyContent: "center",
          columnGap: open ? COLUMN_GAP : "0px",
          rowGap: "0.5rem",
          gridTemplateColumns: open
            ? `${FLOWCHART_WIDTH} ${TRACE_WIDTH}`
            : `${FLOWCHART_WIDTH} 0px`,
          transition:
            "grid-template-columns 500ms ease-out, column-gap 500ms ease-out",
        }}
      >
        {dag.nodes.map((n, i) => {
          const isLast = i === dag.nodes.length - 1;
          const showPanel = renderIds.includes(n.id);
          return (
            <Fragment key={n.id}>
              {/* 流程步骤 + 可伸长的连接线。 */}
              <div className="flex flex-col min-w-0">
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
                {!isLast && (
                  <Arrow done={(nodeStatus[n.id] || "idle") === "done"} />
                )}
              </div>

              {/* 该步骤的决策追踪。步骤未展开时为空（无高度）；列收起时被裁剪。
                  内层固定宽度使面板在滑动过程中不会重排。 */}
              <div className="overflow-hidden min-w-0">
                {showPanel && (
                  <div style={{ width: TRACE_WIDTH }}>
                    <TracePanel
                      node={n}
                      useZh={useZh}
                      events={eventsByNode[n.id] || []}
                      roundOf={roundOf}
                      totalRounds={totalRounds}
                      onClose={() => toggle(n.id)}
                      t={t}
                    />
                  </div>
                )}
              </div>
            </Fragment>
          );
        })}
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

// 两个步骤之间的连接线。`flex-1` 让它吸收当右侧追踪面板比步骤更高时该行
// 增加的额外高度 —— 线干被拉伸，箭头始终钉在下一步骤正上方。
function Arrow({ done }: { done: boolean }) {
  const color = done ? "text-emerald-400" : "text-slate-300";
  const stem = done ? "bg-emerald-400" : "bg-slate-300";
  return (
    <div
      className="flex-1 flex flex-col items-center py-1 min-h-[20px]"
      aria-hidden
    >
      <span
        className={clsx("flex-1 w-0.5 rounded", stem)}
        style={{ minHeight: 10 }}
      />
      <svg width="14" height="8" viewBox="0 0 14 8" className={clsx("-mt-px", color)}>
        <path
          d="M2 1 L7 7 L12 1"
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
