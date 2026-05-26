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

interface Props {
  dag: DagDef;
  locale: Locale;
  nodeStatus: Record<string, "idle" | "running" | "done" | "rework">;
  activeNodeId: string | null;
}

const X_POS: Record<string, number> = {
  identify: 0,
  collect: 200,
  analyze: 400,
  write: 600,
  qc: 800,
  done: 1000,
};

export default function DAGFlow({ dag, locale, nodeStatus, activeNodeId }: Props) {
  const useZh = locale.startsWith("zh");

  const nodes: Node[] = useMemo(
    () =>
      dag.nodes.map((n) => {
        const status = nodeStatus[n.id] || "idle";
        const isActive = n.id === activeNodeId;
        return {
          id: n.id,
          position: { x: X_POS[n.id] ?? 0, y: n.id === "qc" ? 0 : (n.id === "done" ? 0 : 0) },
          data: {
            label: (
              <div className={clsx("dag-node", status, isActive && "ring-2 ring-brand-400")}>
                <div className="font-medium">{useZh ? n.label_zh : n.label_en}</div>
                <div className="text-[10px] text-slate-500 mt-0.5">[{n.agent}]</div>
              </div>
            ),
          },
          type: "default",
          sourcePosition: Position.Right,
          targetPosition: Position.Left,
          style: { background: "transparent", border: "none", padding: 0, width: 160 },
        };
      }),
    [dag, nodeStatus, activeNodeId, useZh]
  );

  const edges: Edge[] = useMemo(
    () =>
      dag.edges.map((e, i) => ({
        id: `e_${i}`,
        source: e.src,
        target: e.dst,
        label: e.condition || undefined,
        labelBgPadding: [4, 2],
        labelStyle: e.condition === "rework"
          ? { fill: "#9f1239", fontSize: 11 }
          : { fill: "#475569", fontSize: 11 },
        style: e.condition === "rework"
          ? { stroke: "#fb7185", strokeDasharray: "4 2" }
          : { stroke: "#94a3b8" },
        markerEnd: { type: MarkerType.ArrowClosed },
        animated: e.dst === activeNodeId,
      })),
    [dag, activeNodeId]
  );

  return (
    <div style={{ height: 220 }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        fitView
        proOptions={{ hideAttribution: true }}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
      >
        <Background gap={20} size={1} />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}
