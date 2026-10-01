import {
  ReactFlow,
  Background,
  Controls,
  MarkerType,
  Position,
  BaseEdge,
  type EdgeProps,
  type Node,
  type Edge,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import type { AuditEvent } from "../types";
const positions: Record<string, { x: number; y: number }> = {
  Orchestrator: { x: 0, y: 225 },
  "Requirement Agent": { x: 360, y: 0 },
  "Evidence Agent": { x: 360, y: 75 },
  "Conflict Agent": { x: 360, y: 150 },
  "Repair Planner": { x: 360, y: 225 },
  "Action Agent": { x: 360, y: 300 },
  VERIFY: { x: 360, y: 375 },
  WAIT: { x: 360, y: 450 },
  MANUAL: { x: 360, y: 525 },
};
function DispatchEdge({
  sourceX,
  sourceY,
  targetX,
  targetY,
  markerEnd,
  style,
  label,
}: EdgeProps) {
  const railX = sourceX + 85;
  // A shared dispatch rail lies between the columns; no path traverses another node.
  const path = `M ${sourceX} ${sourceY} H ${railX} V ${targetY} H ${targetX}`;
  return (
    <>
      <BaseEdge path={path} markerEnd={markerEnd} style={style} />
      <text
        x={(railX + targetX) / 2}
        y={targetY - 8}
        textAnchor="middle"
        style={{ fontSize: 10, fill: "#64748b" }}
      >
        {String(label ?? "")}
      </text>
    </>
  );
}
const edgeTypes = { dispatch: DispatchEdge };
export function AgentGraph({
  events,
  caseState,
  running,
}: {
  events: AuditEvent[];
  caseState: string;
  running: boolean;
}) {
  const routed = events.filter((e) => e.kind === "routing" && e.data.target);
  const last = routed.at(-1)?.data.target;
  const failed = new Set(
    Object.keys(positions).filter(
      (id) =>
        events
          .filter(
            (e) =>
              e.agent === id &&
              ["agent_failed", "agent_completed"].includes(e.kind),
          )
          .at(-1)?.kind === "agent_failed",
    ),
  );
  const completed = new Set(
    events.filter((e) => e.kind === "agent_completed").map((e) => e.agent),
  );
  const observed = new Set(routed.map((e) => e.data.target));
  const nodes: Node[] = Object.entries(positions).map(([id, position]) => ({
    id,
    position,
    data: {
      label:
        (id === "VERIFY"
          ? "Verification"
          : id === "WAIT"
            ? "Waiting for input"
            : id === "MANUAL"
              ? "Manual review"
              : id) +
        " · " +
        (id === "Orchestrator"
          ? running
            ? "Running"
            : "Idle"
          : id === "VERIFY" && caseState === "READY"
            ? "Passed"
            : last === id && running
              ? "Running"
              : last === id && failed.has(id)
                ? "Failed"
                : id === "WAIT" && caseState === "WAITING"
                  ? "Waiting"
                  : id === "MANUAL" && caseState === "BLOCKED"
                    ? "Needs review"
                    : completed.has(id)
                      ? "Completed"
                      : observed.has(id)
                        ? "Recorded"
                        : "Not called"),
    },
    style: {
      background:
        last === id && failed.has(id)
          ? "#fceeea"
          : last === id && running
            ? "#e0f2fe"
            : completed.has(id)
              ? "#ecfdf5"
              : "#fff",
      border: `1px solid ${last === id && running ? "#0284c7" : "#cbd5e1"}`,
      color: "#193342",
      width: 185,
      borderRadius: 9,
      fontSize: 12,
      padding: 14,
    },
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
  }));
  const edges: Edge[] = [...observed]
    .filter((x): x is string => !!x && x in positions)
    .flatMap((id) => [
      {
        id: "to-" + id,
        source: "Orchestrator",
        target: id,
        label:
          String(routed.filter((e) => e.data.target === id).length) +
          " dispatch(es)",
        type: "dispatch",
        markerEnd: { type: MarkerType.ArrowClosed },
        style: { stroke: "#64748b" },
        labelStyle: { fontSize: 10 },
        animated: false,
      },
    ]);
  return (
    <div className="graph" aria-label="Observed agent routing graph">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        edgeTypes={edgeTypes}
        fitView
        nodesDraggable={false}
        nodesConnectable={false}
        minZoom={0.3}
        maxZoom={1.3}
        proOptions={{ hideAttribution: false }}
      >
        <Background gap={22} color="#e2e8f0" />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}
