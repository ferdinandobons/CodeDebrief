import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  layoutFlowDetail,
  type FlowDetailLayout,
  type FlowDetailNodePosition,
} from "./flow-detail-layout";
import {
  type ExpandedFlowMeasure,
  type ProgressiveFlowNode,
  type ScopeLayoutPosition,
  type ScopeNodePosition,
} from "./flowchart-layout";
import {
  flowLabel,
  flowPath,
  type LogicChartFlow,
  type LogicChartPayload,
} from "./logicchart-model";
import { createViewerLayout, isLogicChartFlow } from "./viewer-layout";
import { useViewerStore } from "./viewer-store";
import type { SelectedConnection } from "./viewer-store";

type ActiveConnection = Exclude<SelectedConnection, null>;

export interface ViewerAppProps {
  scope: string;
  scopeNode?: ScopeNodePosition;
  payload?: LogicChartPayload;
  layers?: ProgressiveFlowNode[][];
  routeFlowIds?: string[];
  selectedConnection?: SelectedConnection;
  onConnectionSelect?: (connection: ActiveConnection) => void;
  onFlowSelect?: (flowId: string) => void;
  onSelectionClear?: () => void;
  onScopeSelect?: (scope: string) => void;
  syncHash?: boolean;
  expandedMeasures?: ReadonlyMap<string, ExpandedFlowMeasure>;
}

export function ViewerApp({
  scope,
  scopeNode,
  payload,
  layers,
  routeFlowIds = [],
  selectedConnection: selectedConnectionProp,
  onConnectionSelect,
  onFlowSelect,
  onSelectionClear,
  onScopeSelect,
  syncHash = false,
  expandedMeasures: expandedMeasuresProp,
}: ViewerAppProps) {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const selectedConnection = useViewerStore(state => state.selectedConnection);
  const setSelectedConnection = useViewerStore(state => state.setSelectedConnection);
  const clearSelection = useViewerStore(state => state.clearSelection);
  const [localSelection, setLocalSelection] = useState<SelectedConnection | undefined>(undefined);
  const selectedConnectionPropKey = selectionKey(selectedConnectionProp);
  useEffect(() => {
    setLocalSelection(undefined);
  }, [selectedConnectionPropKey]);
  // React's server renderer observes Zustand's initial server snapshot. Reading the
  // current store state here keeps static-render tests and future SSR exports honest
  // while preserving the live client subscription above.
  const currentSelection: SelectedConnection =
    localSelection !== undefined
      ? localSelection
      : selectedConnectionProp ??
        selectedConnection ??
        useViewerStore.getState().selectedConnection;
  const detailLayouts = useMemo(
    () => flowDetailLayouts(payload, routeFlowIds),
    [payload, routeFlowIds],
  );
  const effectiveExpandedMeasures = useMemo(() => {
    if (!detailLayouts.size) return expandedMeasuresProp;
    const measures = new Map(expandedMeasuresProp ? [...expandedMeasuresProp] : []);
    detailLayouts.forEach((detail, flowId) => {
      measures.set(flowId, detail.measure);
    });
    return measures;
  }, [detailLayouts, expandedMeasuresProp]);
  const layout = useMemo(
    () =>
      createViewerLayout({
        expandedMeasures: effectiveExpandedMeasures,
        layers,
        payload,
        routeFlowIds,
        scope,
        scopeNode,
      }),
    [effectiveExpandedMeasures, layers, payload, routeFlowIds, scope, scopeNode],
  );
  const { entryEdges, flowById, flowPositions, inlineAnchors, scopeNodes, viewBox } = layout;
  const viewMinX = viewBox.minX;
  const viewMinY = viewBox.minY;
  const viewMaxX = viewBox.maxX;
  const viewMaxY = viewBox.maxY;
  const width = Math.max(900, viewMaxX - viewMinX);
  const height = Math.max(640, viewMaxY - viewMinY);
  const hasConnectionSelection = currentSelection !== null;
  const clearCurrentSelection = useCallback(() => {
    clearSelection();
    setLocalSelection(null);
    onSelectionClear?.();
    if (syncHash) setLocationHash(hashForScope(scope));
  }, [clearSelection, onSelectionClear, scope, syncHash]);
  const selectFlow = useCallback(
    (flowId: string) => {
      clearSelection();
      setLocalSelection(null);
      onFlowSelect?.(flowId);
      if (syncHash) setLocationHash(hashForFlow(flowId));
    },
    [clearSelection, onFlowSelect, syncHash],
  );
  const selectScope = useCallback(
    (nextScope: string) => {
      clearSelection();
      setLocalSelection(null);
      onScopeSelect?.(nextScope);
      if (syncHash) setLocationHash(hashForScope(nextScope));
    },
    [clearSelection, onScopeSelect, syncHash],
  );

  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return undefined;
    svg.dataset.interactive = "true";

    const handleEdgePress = (event: Event) => {
      const target = event.target;
      if (!(target instanceof Element)) return;
      const edge = target.closest<SVGElement>(".edge-hit-path, .scope-entry-link");
      if (edge && svg.contains(edge)) {
        const sourceScope = edge.getAttribute("data-source-scope");
        const targetFlowId = edge.getAttribute("data-target-flow-id");
        if (sourceScope && targetFlowId) {
          event.stopPropagation();
          setSelectedConnection({
            kind: "scope-entry",
            scope: sourceScope,
            target: targetFlowId,
          });
          const connection: ActiveConnection = {
            kind: "scope-entry",
            scope: sourceScope,
            target: targetFlowId,
          };
          setLocalSelection(connection);
          onConnectionSelect?.(connection);
          if (syncHash) {
            setLocationHash(edge.getAttribute("data-edge-href") || hashForConnection(connection));
          }
        }
        return;
      }
      if (target === svg) clearCurrentSelection();
    };

    svg.addEventListener("pointerdown", handleEdgePress);
    svg.addEventListener("mousedown", handleEdgePress);
    return () => {
      delete svg.dataset.interactive;
      svg.removeEventListener("pointerdown", handleEdgePress);
      svg.removeEventListener("mousedown", handleEdgePress);
    };
  }, [clearCurrentSelection, onConnectionSelect, setSelectedConnection, syncHash]);

  return (
    <svg
      aria-label="LogicChart progressive flowchart"
      className="logicchart-viewer"
      data-selected-kind={currentSelection?.kind ?? "none"}
      ref={svgRef}
      role="img"
      viewBox={`${viewMinX} ${viewMinY} ${width} ${height}`}
      onPointerDown={event => {
        if (event.target === event.currentTarget) clearCurrentSelection();
      }}
    >
      <defs>
        <filter id="typedNodeShadow" x="-18%" y="-28%" width="136%" height="156%">
          <feDropShadow dx="0" dy="8" stdDeviation="10" floodOpacity=".18" />
        </filter>
        <filter id="typedNodeLift" x="-20%" y="-30%" width="140%" height="160%">
          <feDropShadow dx="0" dy="12" stdDeviation="14" floodOpacity=".24" />
        </filter>
        <marker
          id="typedArrow"
          markerHeight="8"
          markerWidth="8"
          orient="auto"
          refX="7"
          refY="4"
          viewBox="0 0 8 8"
        >
          <path className="typed-arrow" d="M 0 0 L 8 4 L 0 8 z" />
        </marker>
        <marker
          id="typedArrowFocus"
          markerHeight="8"
          markerWidth="8"
          orient="auto"
          refX="7"
          refY="4"
          viewBox="0 0 8 8"
        >
          <path className="typed-arrow-focus" d="M 0 0 L 8 4 L 0 8 z" />
        </marker>
      </defs>
      <rect
        aria-hidden="true"
        className="canvas-hit-zone"
        height={height}
        width={width}
        x={viewMinX}
        y={viewMinY}
        onMouseDown={clearCurrentSelection}
        onPointerDown={clearCurrentSelection}
      />
      <g className="scope-nodes">
        {scopeNodes.map(item => (
          <ScopeNode
            currentSelection={currentSelection}
            hasConnectionSelection={hasConnectionSelection}
            item={item}
            key={item.scope}
            onSelect={selectScope}
          />
        ))}
      </g>
      <g className="scope-entry-edges">
        {entryEdges.map(edge => {
          const selected =
            currentSelection?.kind === "scope-entry" &&
            currentSelection.scope === edge.scope &&
            currentSelection.target === edge.target;
          const dimmed = hasConnectionSelection && !selected;
          const connection: ActiveConnection = {
            kind: "scope-entry",
            scope: edge.scope,
            target: edge.target,
          };
          const edgeHref = hashForConnection(connection);
          const selectEdge = () => {
            setSelectedConnection(connection);
            setLocalSelection(connection);
            onConnectionSelect?.(connection);
            if (syncHash) setLocationHash(edgeHref);
          };
          return (
            <a
              aria-label={`entry link from ${edge.scope} to ${edge.target}`}
              className="edge-link-group"
              data-source-scope={edge.scope}
              data-target-flow-id={edge.target}
              data-edge-href={edgeHref}
              href={edgeHref}
              key={`${edge.scope}:${edge.target}`}
              tabIndex={0}
              onClick={selectEdge}
              onKeyDown={event => {
                if (event.key === " ") {
                  event.preventDefault();
                  selectEdge();
                }
              }}
            >
              <path
                aria-hidden="true"
                className="edge-hit-path"
                d={edge.d}
                data-source-scope={edge.scope}
                data-target-flow-id={edge.target}
                data-edge-href={edgeHref}
                vectorEffect="non-scaling-stroke"
                onClick={event => {
                  event.stopPropagation();
                  selectEdge();
                }}
                onPointerDown={event => {
                  event.stopPropagation();
                  selectEdge();
                }}
                onMouseDown={event => {
                  event.stopPropagation();
                  selectEdge();
                }}
              />
              <path
                className={[
                  "edge",
                  "scope-entry-link",
                  selected ? "selected-link" : "",
                  dimmed ? "dimmed" : "",
                ]
                  .filter(Boolean)
                  .join(" ")}
                d={edge.d}
                data-source-scope={edge.scope}
                data-target-flow-id={edge.target}
                data-edge-href={edgeHref}
                vectorEffect="non-scaling-stroke"
                onClick={event => {
                  event.stopPropagation();
                  selectEdge();
                }}
                onPointerDown={event => {
                  event.stopPropagation();
                  selectEdge();
                }}
                onMouseDown={event => {
                  event.stopPropagation();
                  selectEdge();
                }}
              />
            </a>
          );
        })}
      </g>
      <g className="flow-nodes">
        {[...flowPositions.values()].map(position => {
          const flow = flowById.get(position.id);
          const flowOpen = routeFlowIds.includes(position.id);
          const targetSelected =
            currentSelection?.kind === "scope-entry" &&
            currentSelection.target === position.id;
          const flowClassName = [
            "node",
            "flow-node",
            flowOpen ? "flow-open" : "",
            targetSelected ? "edge-target" : "",
            hasConnectionSelection && !targetSelected ? "dimmed" : "",
          ]
            .filter(Boolean)
            .join(" ");
          return (
            <g
              className={flowClassName}
              data-flow-id={position.id}
              key={position.id}
              role="button"
              tabIndex={0}
              transform={`translate(${position.x} ${position.y})`}
              onClick={event => {
                event.stopPropagation();
                selectFlow(position.id);
              }}
              onKeyDown={event => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  selectFlow(position.id);
                }
              }}
            >
              <rect
                className="shape"
                height={position.height}
                rx="32"
                vectorEffect="non-scaling-stroke"
                width={position.width}
                x={-position.width / 2}
                y={-position.height / 2}
              />
              <text textAnchor="middle">{flow ? flowLabel(flow) : position.id}</text>
              {flow ? (
                <text className="meta" textAnchor="middle" y="22">
                  {flowMeta(flow).join(" · ")}
                </text>
              ) : null}
              {flow && flowPath(flow) ? (
                <title>{flowPath(flow)}</title>
              ) : null}
            </g>
          );
        })}
      </g>
      <g className="flow-details">
        {inlineAnchors.map(anchor => {
          const detail = detailLayouts.get(anchor.flowId);
          if (!detail) return null;
          return (
            <FlowDetail
              detail={detail}
              key={anchor.flowId}
              transform={`translate(${anchor.x} ${anchor.y})`}
            />
          );
        })}
      </g>
    </svg>
  );
}

function ScopeNode({
  currentSelection,
  hasConnectionSelection,
  item,
  onSelect,
}: {
  currentSelection: SelectedConnection;
  hasConnectionSelection: boolean;
  item: ScopeLayoutPosition;
  onSelect: (scope: string) => void;
}) {
  const isEdgeSource =
    currentSelection?.kind === "scope-entry" && currentSelection.scope === item.scope;
  const dimmed = hasConnectionSelection && !isEdgeSource;
  const className = [
    "node",
    "entry",
    "scope-node",
    item.expanded ? "expanded" : "",
    isEdgeSource ? "edge-source" : "",
    dimmed ? "dimmed" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <g
      className={className}
      data-scope={item.scope}
      role="button"
      tabIndex={0}
      transform={`translate(${item.x} ${item.y})`}
      onClick={event => {
        event.stopPropagation();
        onSelect(item.scope);
      }}
      onKeyDown={event => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onSelect(item.scope);
        }
      }}
    >
      <rect
        className="shape"
        height={item.height}
        rx="32"
        vectorEffect="non-scaling-stroke"
        width={item.width}
        x={-item.width / 2}
        y={-item.height / 2}
      />
      <text textAnchor="middle">{item.scope}</text>
      <text className="meta" textAnchor="middle" y="24">
        {item.flowCount} flow{item.flowCount === 1 ? "" : "s"}
      </text>
    </g>
  );
}

function FlowDetail({
  detail,
  transform,
}: {
  detail: FlowDetailLayout;
  transform: string;
}) {
  return (
    <g className="flow-detail" transform={transform}>
      <g className="flow-detail-edges">
        {detail.edgeRoutes.map(route => (
          <g className="flow-detail-edge-group" key={route.id}>
            <path
              className="flow-detail-edge"
              d={route.d}
              vectorEffect="non-scaling-stroke"
            />
            {route.edge.label ? (
              <g className="flow-detail-label" transform={`translate(${route.labelX} ${route.labelY})`}>
                <rect height="20" rx="10" width={Math.max(44, route.edge.label.length * 7 + 18)} x={-Math.max(44, route.edge.label.length * 7 + 18) / 2} y="-10" />
                <text textAnchor="middle" y="4">{route.edge.label}</text>
              </g>
            ) : null}
          </g>
        ))}
      </g>
      <g className="flow-detail-nodes">
        {[...detail.nodePositions.values()].map(position => (
          <FlowDetailNode key={position.id} position={position} />
        ))}
      </g>
    </g>
  );
}

function FlowDetailNode({ position }: { position: FlowDetailNodePosition }) {
  const kind = position.node.kind || "action";
  const className = ["detail-node", kind].filter(Boolean).join(" ");
  const label = position.node.label || position.id;
  return (
    <g className={className} transform={`translate(${position.x} ${position.y})`}>
      {kind === "decision" ? (
        <polygon
          className="detail-shape"
          points={`0 ${-position.height / 2} ${position.width / 2} 0 0 ${position.height / 2} ${-position.width / 2} 0`}
          vectorEffect="non-scaling-stroke"
        />
      ) : (
        <rect
          className="detail-shape"
          height={position.height}
          rx={kind === "entry" || kind === "terminal" ? 32 : 10}
          vectorEffect="non-scaling-stroke"
          width={position.width}
          x={-position.width / 2}
          y={-position.height / 2}
        />
      )}
      <text className="detail-kind" textAnchor="middle" y={-position.height / 2 + 21}>
        {kind}
      </text>
      {wrapLabel(label, kind === "decision" ? 25 : 31).map((line, index, lines) => (
        <text
          className="detail-label"
          key={`${position.id}:${index}`}
          textAnchor="middle"
          y={(index - (lines.length - 1) / 2) * 15 + 8}
        >
          {line}
        </text>
      ))}
      {position.node.location?.start_line ? (
        <text className="detail-meta" textAnchor="middle" y={position.height / 2 + 18}>
          {position.node.location.path}:{position.node.location.start_line}
        </text>
      ) : null}
    </g>
  );
}

function asLogicChartFlow(flow: ProgressiveFlowNode): LogicChartFlow {
  return flow as LogicChartFlow;
}

function flowMeta(flow: ProgressiveFlowNode): string[] {
  if (!isLogicChartFlow(flow)) return [];
  const item = asLogicChartFlow(flow);
  return [item.entry_kind, item.language].filter((value): value is string => Boolean(value));
}

function flowDetailLayouts(
  payload: LogicChartPayload | undefined,
  routeFlowIds: readonly string[],
): Map<string, FlowDetailLayout> {
  const details = new Map<string, FlowDetailLayout>();
  if (!payload) return details;
  const byId = new Map(payload.flows.map(flow => [flow.id, flow]));
  routeFlowIds.forEach(flowId => {
    const flow = byId.get(flowId);
    if (!flow) return;
    const detail = layoutFlowDetail(flow);
    if (detail) details.set(flowId, detail);
  });
  return details;
}

function wrapLabel(value: string, width: number): string[] {
  const words = value.split(/\s+/);
  const lines: string[] = [];
  let current = "";
  words.forEach(word => {
    if (!current || `${current} ${word}`.length <= width) {
      current = current ? `${current} ${word}` : word;
    } else {
      lines.push(current);
      current = word;
    }
  });
  if (current) lines.push(current);
  return lines.slice(0, 3);
}

function hashForConnection(connection: Extract<ActiveConnection, { kind: "scope-entry" }>): string {
  return `#edge=${encodeHashValue(
    JSON.stringify({ scope: connection.scope, target: connection.target }),
  )}`;
}

function hashForScope(scope: string): string {
  return `#scope=${encodeHashValue(scope)}`;
}

function hashForFlow(flowId: string): string {
  return `#flow=${encodeHashValue(flowId)}`;
}

function setLocationHash(hash: string) {
  if (typeof window === "undefined") return;
  if (window.location.hash === hash) return;
  window.location.hash = hash;
}

function selectionKey(selection: SelectedConnection | undefined): string {
  if (!selection) return "none";
  if (selection.kind === "scope-entry") {
    return `scope-entry:${selection.scope}:${selection.target}`;
  }
  return `flow-call:${selection.source}:${selection.target}`;
}

function encodeHashValue(value: string): string {
  if (typeof encodeURIComponent === "function") return encodeURIComponent(value);
  return value.replace(/[^A-Za-z0-9_.~-]/g, char =>
    `%${char.charCodeAt(0).toString(16).padStart(2, "0").toUpperCase()}`,
  );
}
