import { useMemo } from "react";
import ReactFlow, {
  Background,
  Controls,
  Edge,
  MarkerType,
  Node,
  Position,
} from "reactflow";
import clsx from "clsx";
import type { DagDef } from "../api/client";
import type { Locale } from "../i18n";

export interface NodeProgress {
  current: number;
  total: number;
  label?: string;
}

interface Props {
  dag: DagDef;
  locale: Locale;
  nodeStatus: Record<string, "idle" | "running" | "done" | "rework">;
  activeNodeId: string | null;
  nodeProgress?: Record<string, NodeProgress>;
  t?: (k: string, vars?: Record<string, string | number>) => string;
}

// Generously spaced layout — wider gaps + a slight vertical offset for the
// QC/done branch make the flow read like a real DAG, not a flat chain.
const POS: Record<string, { x: number; y: number }> = {
  identify: { x: 0, y: 60 },
  collect: { x: 220, y: 60 },
  analyze: { x: 440, y: 60 },
  write: { x: 660, y: 60 },
  qc: { x: 880, y: 60 },
  done: { x: 1100, y: 60 },
};

const NODE_WIDTH = 190;

export default function DAGFlow({
  dag,
  locale,
  nodeStatus,
  activeNodeId,
  nodeProgress,
  t,
}: Props) {
  const useZh = locale.startsWith("zh");

  const nodes: Node[] = useMemo(
    () =>
      dag.nodes.map((n) => {
        const status = nodeStatus[n.id] || "idle";
        const isActive = n.id === activeNodeId;
        const progress = nodeProgress?.[n.id];
        return {
          id: n.id,
          position: POS[n.id] ?? { x: 0, y: 0 },
          data: {
            label: (
              <div
                className={clsx(
                  "dag-node",
                  status,
                  isActive && status === "running" && "dag-node-pulse",
                  isActive && "ring-2 ring-brand-400",
                )}
              >
                <div className="font-medium text-[13px] leading-snug">
                  {useZh ? n.label_zh : n.label_en}
                </div>
                <div className="text-[10px] text-slate-500 mt-0.5 uppercase tracking-wide">
                  [{n.agent}]
                </div>
                {status === "running" && (
                  <div className="text-[10px] text-amber-700 mt-1 flex items-center gap-1">
                    <span className="inline-block w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse" />
                    {t ? t("dag.legend.running") : "running"}
                  </div>
                )}
                {progress && progress.total > 0 && (
                  <div className="mt-1.5">
                    <div className="text-[10px] text-slate-600 flex justify-between">
                      <span>{statusVerb(status, t)}</span>
                      <span className="tabular-nums">
                        {progress.current}/{progress.total}
                      </span>
                    </div>
                    <div className="h-1 bg-slate-200 rounded overflow-hidden mt-0.5">
                      <div
                        className={clsx(
                          "h-1 transition-all",
                          status === "rework"
                            ? "bg-rose-500"
                            : status === "done"
                            ? "bg-emerald-500"
                            : "bg-amber-500",
                        )}
                        style={{
                          width: `${Math.min(
                            100,
                            (progress.current / Math.max(1, progress.total)) * 100,
                          )}%`,
                        }}
                      />
                    </div>
                    {progress.label && (
                      <div className="text-[9px] text-slate-400 mt-1 truncate" title={progress.label}>
                        {progress.label}
                      </div>
                    )}
                  </div>
                )}
              </div>
            ),
          },
          type: "default",
          sourcePosition: Position.Right,
          targetPosition: Position.Left,
          style: { background: "transparent", border: "none", padding: 0, width: NODE_WIDTH },
        };
      }),
    [dag, nodeStatus, activeNodeId, useZh, nodeProgress, t],
  );

  const edges: Edge[] = useMemo(
    () =>
      dag.edges.map((e, i) => {
        const isRework = e.condition === "rework";
        const targetActive = e.dst === activeNodeId && nodeStatus[e.dst] === "running";
        const traversed =
          nodeStatus[e.src] === "done" &&
          (nodeStatus[e.dst] === "done" || nodeStatus[e.dst] === "running");
        return {
          id: `e_${i}`,
          source: e.src,
          target: e.dst,
          label: e.condition || undefined,
          labelBgPadding: [6, 3],
          labelBgBorderRadius: 4,
          labelStyle: isRework
            ? { fill: "#9f1239", fontSize: 11, fontWeight: 600 }
            : { fill: "#475569", fontSize: 11, fontWeight: 500 },
          labelBgStyle: isRework
            ? { fill: "#ffe4e6" }
            : { fill: "#f1f5f9" },
          style: isRework
            ? { stroke: "#fb7185", strokeWidth: 3, strokeDasharray: "8 4" }
            : { stroke: traversed ? "#10b981" : "#94a3b8", strokeWidth: 3 },
          markerEnd: {
            type: MarkerType.ArrowClosed,
            width: 22,
            height: 22,
            color: isRework ? "#fb7185" : traversed ? "#10b981" : "#94a3b8",
          },
          animated: targetActive,
        };
      }),
    [dag, activeNodeId, nodeStatus],
  );

  return (
    <div style={{ height: 260 }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        fitView
        fitViewOptions={{ padding: 0.15 }}
        proOptions={{ hideAttribution: true }}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        minZoom={0.4}
        maxZoom={1.6}
      >
        <Background gap={24} size={1} color="#e2e8f0" />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}

function statusVerb(
  status: string,
  t?: (k: string, vars?: Record<string, string | number>) => string,
): string {
  if (!t) return status;
  if (status === "running") return t("dag.progress.running");
  if (status === "done") return t("dag.progress.done");
  if (status === "rework") return t("dag.progress.rework");
  return t("dag.legend.idle");
}
